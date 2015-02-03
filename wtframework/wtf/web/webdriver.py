##########################################################################
# This file is part of WTFramework.
#
#    WTFramework is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    WTFramework is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with WTFramework.  If not, see <http://www.gnu.org/licenses/>.
##########################################################################

import os
from threading import current_thread
import time
import urllib2
from selenium import webdriver
from selenium.webdriver.firefox.firefox_binary import FirefoxBinary
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from six import u
from wtframework.wtf import _wtflog
from wtframework.wtf.config import WTF_CONFIG_READER, WTF_TIMEOUT_MANAGER
from selenium.webdriver.chrome.options import Options

class WebDriverFactory(object):

    '''
    This class constructs a Selenium Webdriver using settings in the config file.
    This allows you to substitute different Webdrivers by changing the config settings
    while keeping your tests using the same Webdriver interface.

    Ideally you will not use this directly.  You will normally use the global instance,
    WTF_WEBDRIVER_MANAGER.new_driver(), to create a new instance of Webdriver.  This allows
    the framework to take screenshots during test failures.  When you're done with the
    Webdriver, call WTF_WEBDRIVER_MANAGER.close_driver().

    You can extend this class for the purposes of adding support for Webdrivers that are not
    currently supported.
    '''

    #    Note: please be sure to uncomment the Unit test and run them manually before
    #    pushing any changes.  This is because they are disabled.  The reason is
    #    because the unit tests for this class can use up billable hours on sauce labs
    #    or open annoying browser windows.

    # CONFIG SETTINGS #
    DRIVER_TYPE_CONFIG = "selenium.type"
    REMOTE_URL_CONFIG = "selenium.remote_url"
    BROWSER_TYPE_CONFIG = "selenium.browser"
    DESIRED_CAPABILITIES_CONFIG = "selenium.desired_capabilities"
    CHROME_DRIVER_PATH = "selenium.chromedriver_path"
    PHANTOMEJS_EXEC_PATH = "selenium.phantomjs_path"
    SELENIUM_SERVER_LOCATION = "selenium.selenium_server_path"
    LOG_REMOTEDRIVER_PROPS = "selenium.log_remote_webdriver_props"

    # BROWSER CONSTANTS #
    HTMLUNIT = "HTMLUNIT"
    HTMLUNITWITHJS = "HTMLUNITWITHJS"
    ANDROID = "ANDROID"
    CHROME = "CHROME"
    FIREFOX = "FIREFOX"
    INTERNETEXPLORER = "INTERNETEXPLORER"
    IPAD = "IPAD"
    IPHONE = "IPHONE"
    OPERA = "OPERA"
    PHANTOMJS = "PHANTOMJS"
    SAFARI = "SAFARI"
    OTHER = "OTHER"  # Use a blank desired capabilities as a base for RemoteWebdriver.

    # Driver Type constants
    DRIVER_TYPE_LOCAL   = "LOCAL"
    DRIVER_TYPE_REMOTE  = "REMOTE"

    # ENV vars that are used by selenium.
    __SELENIUM_SERVER_JAR_ENV = "SELENIUM_SERVER_JAR"
    # System ENV prefix for variables in desired capabilities.
    DESIRED_CAPABILITIES_ENV_PREFIX = "WTF_selenium_desired_capabilities_"



    def __init__(self, config_reader=None, env_vars=None, timeout_mgr=None):
        '''
        Initializer.

        Kwargs:
            config_reader (ConfigReader) - Override the default config reader.
            env_vars (Dictionary) - Override the default ENV vars provider.
        '''
        # Block of if/else statements setting dependencies.  If provided,
        # we'll use the provided (unit testing), other wise we'll use the
        # default for normal usage scenarios.
        if config_reader is not None:
            self._config_reader = config_reader
        else:
            self._config_reader = WTF_CONFIG_READER

        if env_vars is not None:
            self._env_vars = env_vars
        else:
            self._env_vars = os.environ

        if timeout_mgr is not None:
            self._timeout_mgr = timeout_mgr
        else:
            self._timeout_mgr = WTF_TIMEOUT_MANAGER


    def create_webdriver(self, testname=None):
        '''
            Creates an instance of Selenium webdriver based on config settings.
            This should only be called by a shutdown hook.  Do not call directly within
            a test.

            Kwargs:
                testname: Optional test name to pass, this gets appended to the test name
                          sent to selenium grid.

            Returns:
                WebDriver - Selenium Webdriver instance.

        '''
        try:
            driver_type = self._config_reader.get(
                self.DRIVER_TYPE_CONFIG)
        except:
            driver_type = self.DRIVER_TYPE_LOCAL
            _wtflog.warn("%s setting is missing from config. Using default setting, %s",
                         self.DRIVER_TYPE_CONFIG, driver_type)

        if driver_type == self.DRIVER_TYPE_REMOTE:
            # Create desired capabilities.
            self.webdriver = self.__create_remote_webdriver_from_config(
                testname=testname)
        else:
            # handle as local webdriver
            self.webdriver = self.__create_driver_from_browser_config()

        try:
            self.webdriver.maximize_window()
        except:
            # wait a short period and try again.
            time.sleep(self._timeout_mgr.BRIEF)
            try:
                self.webdriver.maximize_window()
            except Exception as e:
                if (isinstance(e, WebDriverException) and
                    "implemented" in e.msg.lower()):
                    pass  # Maximizing window not supported by this webdriver.
                else:
                    _wtflog.warn("Unable to maxmize browser window. " +
                                 "It may be possible the browser did not instantiate correctly. % s",
                                 e)

        return self.webdriver

    def __create_driver_from_browser_config(self):
        '''
        Reads the config value for browser type.
        '''
        try:
            browser_type = self._config_reader.get(
                WebDriverFactory.BROWSER_TYPE_CONFIG)
        except KeyError:
            _wtflog("%s missing is missing from config file. Using defaults",
                    WebDriverFactory.BROWSER_TYPE_CONFIG)
            browser_type = WebDriverFactory.FIREFOX
        browser_type_dict = {
            self.CHROME: lambda: self.__get_chrome_webdriver(),
            self.FIREFOX: lambda: self.__get_firefox_webdriver(),
            self.INTERNETEXPLORER: lambda: webdriver.Ie(
                self._config_reader.get('versions.ie_driver', None)),
            self.OPERA: lambda: webdriver.Opera(),
            self.PHANTOMJS: lambda: self.__create_phantom_js_driver(),
            self.SAFARI: lambda: self.__create_safari_driver()
        }

        try:
            return browser_type_dict[browser_type]()
        except KeyError:
            raise TypeError(
                u("Unsupported Browser Type {0}").format(browser_type))
        # End of method.


    def __get_chrome_webdriver(self):
        '''
        Returns chromedriver with given config
        '''
        chrome_driver = self._config_reader.get('versions.chrome_driver', None)

        if chrome_driver:
            chrome_driver_path = chrome_driver
        else:
            chrome_driver_path = self._config_reader.get(WebDriverFactory.CHROME_DRIVER_PATH)
        desired_capabilities = self._generate_desired_capabilities(None)
        return webdriver.Chrome(chrome_driver_path, chrome_options=self.__get_crome_options(), desired_capabilities=desired_capabilities, service_args=["--verbose", "--log-path=/tmp/webdriver_log.log"])


    def __get_crome_options(self):
        '''
        Creates chrome_options with extension to be added
        '''
        chrome_options = Options()
        home_dir = os.getcwd()
        chrome_version = self._config_reader.get('versions.chrome_version', None)
        if chrome_version:
            binary_path = os.path.join(home_dir, chrome_version)
            chrome_options.add_argument("binary=" + binary_path)
        chrome_extension = self._config_reader.get('extensions.chrome_extension', None)
        if chrome_extension:
            chrome_options.add_extension(chrome_extension)
        profile_prefs = self._config_reader.get('profile_prefs.chrome', None)
        for pref in profile_prefs:
            pref_val = profile_prefs[pref]
            if pref_val:
                chrome_options.add_argument(pref + "=" + pref_val)
            else:
                chrome_options.add_argument(pref)
        return chrome_options

    def __get_firefox_webdriver(self):
        '''
        Returns the firefox webdriver and if firefox binary given then creates
        webdriver with specific firefox binary
        '''
        home_dir = os.getcwd()
        firefox_version = self._config_reader.get('versions.firefox_version', None)
        if firefox_version:
            ff_binary_path = os.path.join(home_dir, firefox_version)
            binary = FirefoxBinary(ff_binary_path)
            return webdriver.Firefox(firefox_binary=binary, firefox_profile=self.__get_firefox_profile())

        return webdriver.Firefox(firefox_profile=self.__get_firefox_profile())


    def __get_firefox_profile(self):
        '''
        Creates Firefox profile with extension added to it
        '''
        home_dir = os.getcwd()
        ff_profile = self._config_reader.get('versions.firefox_profile', None)
        firefox_profile_path = None

        fp = webdriver.FirefoxProfile()
        firefox_extension = None
        firefox_extension = self._config_reader.get('extensions.firefox_extension', None)
        if firefox_extension:
            fp.add_extension(firefox_extension)
        profile_prefs = self._config_reader.get('profile_prefs.firefox', None)
        for pref in profile_prefs:
            pref_val = profile_prefs[pref]
            if pref_val:
                fp.set_preference(pref, pref_val)
            else:
                fp.set_preference(pref)
        return fp


    def __create_safari_driver(self):
        '''
        Creates an instance of Safari webdriver.
        '''
        # Check for selenium jar env file needed for safari driver.
        if not os.getenv(self.__SELENIUM_SERVER_JAR_ENV):
            # If not set, check if we have a config setting for it.
            try:
                selenium_server_path = self._config_reader.get(
                    self.SELENIUM_SERVER_LOCATION)
                self._env_vars[
                    self.__SELENIUM_SERVER_JAR_ENV] = selenium_server_path
            except KeyError:
                raise RuntimeError(u("Missing selenium server path config {0}.").format(
                    self.SELENIUM_SERVER_LOCATION))

        return webdriver.Safari()

    def __create_phantom_js_driver(self):
        '''
        Creates an instance of PhantomJS driver.
        '''
        try:
            return webdriver.PhantomJS(executable_path=self._config_reader.get(self.PHANTOMEJS_EXEC_PATH),
                                       service_args=['--ignore-ssl-errors=true'])
        except KeyError:
            return webdriver.PhantomJS(service_args=['--ignore-ssl-errors=true'])

    def __create_remote_webdriver_from_config(self, testname=None):
        '''
        Reads the config value for browser type.
        '''
        desired_capabilities = self._generate_desired_capabilities(testname)
        remote_url = self._config_reader.get(
            WebDriverFactory.REMOTE_URL_CONFIG)

        # Instantiate remote webdriver.
        driver = webdriver.Remote(
            desired_capabilities=desired_capabilities,
            command_executor=remote_url
        )

        # Log IP Address of node if configured, so it can be used to
        # troubleshoot issues if they occur.
        log_driver_props = \
            self._config_reader.get(
                WebDriverFactory.LOG_REMOTEDRIVER_PROPS, default_value=False
            ) in [True, "true", "TRUE", "True"]
        if "wd/hub" in remote_url and log_driver_props:
            try:
                grid_addr = remote_url[:remote_url.index("wd/hub")]
                info_request_response = urllib2.urlopen(
                    grid_addr + "grid/api/testsession?session=" + driver.session_id, "", 5000)
                node_info = info_request_response.read()
                _wtflog.info(
                    u("RemoteWebdriver using node: ") + u(node_info).strip())
            except:
                # Unable to get IP Address of remote webdriver.
                # This happens with many 3rd party grid providers as they don't want you accessing info on nodes on
                # their internal network.
                pass

        return driver
        # End of method.

    def _generate_desired_capabilities(self, testname):
        # Generate desired capabilities object using config settings.
        browser_type = self._config_reader.get(
            WebDriverFactory.BROWSER_TYPE_CONFIG)

        browser_constant_dict = {self.HTMLUNIT: DesiredCapabilities.HTMLUNIT,
                                 self.HTMLUNITWITHJS: DesiredCapabilities.HTMLUNITWITHJS,
                                 self.ANDROID: DesiredCapabilities.ANDROID,
                                 self.CHROME: DesiredCapabilities.CHROME,
                                 self.FIREFOX: DesiredCapabilities.FIREFOX,
                                 self.INTERNETEXPLORER: DesiredCapabilities.INTERNETEXPLORER,
                                 self.IPAD: DesiredCapabilities.IPAD,
                                 self.IPHONE: DesiredCapabilities.IPHONE,
                                 self.OPERA: DesiredCapabilities.OPERA,
                                 self.SAFARI: DesiredCapabilities.SAFARI,
                                 self.PHANTOMJS: DesiredCapabilities.PHANTOMJS,
                                 self.OTHER: {'browserName': ''}  # Blank Desired Capabilities.
                                 }

        try:
            # Get a copy of the desired capabilities object. (to avoid
            # overwriting the global.)
            desired_capabilities = browser_constant_dict[browser_type].copy()
        except KeyError:
            raise TypeError(
                u("Unsupported Browser Type {0}").format(browser_type))

        # Get additional desired properties from config file and add them in.
        other_desired_capabilities = self._config_reader.get(
            WebDriverFactory.DESIRED_CAPABILITIES_CONFIG)

        for prop in other_desired_capabilities:
            value = other_desired_capabilities[prop]

            # if type(other_desired_capabilities[prop]) is dict:
            #    # do some recursive call to flatten this setting.
            #    self.__flatten_capabilities(
            #        desired_capabilities, prop, other_desired_capabilities[prop])
            # else:  # Handle has a single string value.

            # if isinstance(value, basestring):
            #     desired_capabilities[prop] = value

                # Version is specified as a string, but we'll allow user to use
                # an int for convenience.
            if prop == "version":
                desired_capabilities[prop] = str(value)
            else:
                desired_capabilities[prop] = value

        # Set the test name property if specified in the WTF_TESTNAME var.
        try:
            test_name = self._config_reader.get("TESTNAME")
            desired_capabilities['name'] = test_name
        except KeyError:
            pass  # No test name is specified, use the default.

        # If there is desired capabilities properties specified in the OS ENV vars,
        # override the desired capabilities value with those values.
        for key in self._env_vars.keys():
            if key.startswith(self.DESIRED_CAPABILITIES_ENV_PREFIX):
                dc_key = key[len(self.DESIRED_CAPABILITIES_ENV_PREFIX):]
                desired_capabilities[dc_key] = self._env_vars[key]

        # Append optional testname postfix if supplied.
        if testname:
            if desired_capabilities['name']:
                desired_capabilities['name'] += "-" + testname
            else:
                # handle case where name is not specified.
                desired_capabilities['name'] = testname

        return desired_capabilities


    def __flatten_capabilities(self, desired_capabilities, prefix, setting_group):
        for key in setting_group.keys():
            if type(setting_group[key]) is dict:
                # Do recursive call
                self.__flatten_capabilities(
                    desired_capabilities, prefix + "." + key, setting_group[key])
            else:
                value = setting_group[key]
                if isinstance(value, basestring):
                    desired_capabilities[prefix + "." + key] = value
                else:
                    desired_capabilities[prefix + "." + key] = str(value)
        # End of method.


class WebDriverManager(object):

    '''
    Provides Singleton instance of Selenium WebDriver based on
    config settings.

    Reason we don't make this a Utility class that provides a singleton
    of the WebDriver itself is so we can allow that pice to be mocked
    out to assist in unit testing framework classes that may use this.
    '''

    "Config setting to reuse browser instances between WebdriverManager.new_driver() calls."
    REUSE_BROWSER = "selenium.reusebrowser"

    "Config setting to automatically tear down webdriver upon exiting the main script."
    SHUTDOWN_HOOK_CONFIG = "selenium.shutdown_hook"

    "Config setting to use new webdriver instance per thread."
    ENABLE_THREADING_SUPPORT = "selenium.threaded"

    def __init__(self, webdriver_factory=None, config=None):
        '''
        Initializer

        Kwargs:
            webdriver_factory (WebDriverFactory): Override default webdriver factory.
            config (ConfigReader): Override default config reader.

        '''
        self.__webdriver = {}  # Object with channel as a key
        self.__registered_drivers = {}

        # if/else blocks handling dependency injections.
        if config:
            self.__config = config
        else:
            self.__config = WTF_CONFIG_READER

        if(webdriver_factory is not None):
            self._webdriver_factory = webdriver_factory
        else:
            self._webdriver_factory = WebDriverFactory()

        # Set shutdown hook flag.
        self.__use_shutdown_hook = self.__config.get(
            WebDriverManager.SHUTDOWN_HOOK_CONFIG, True)


    def clean_up_webdrivers(self):
        '''
        Clean up webdrivers created during execution.
        '''
        # Quit webdrivers.
        _wtflog.info("WebdriverManager: Cleaning up webdrivers")
        try:
            if self.__use_shutdown_hook:
                for key in self.__registered_drivers.keys():
                    for driver in self.__registered_drivers[key]:
                        try:
                            _wtflog.debug(
                                "Shutdown hook closing Webdriver for thread: %s", key)
                            driver.quit()
                        except:
                            pass
        except:
            pass

    def close_driver(self):
        """
        Close current running instance of Webdriver.

        Usage::

            driver = WTF_WEBDRIVER_MANAGER.new_driver()
            driver.get("http://the-internet.herokuapp.com")
            WTF_WEBDRIVER_MANAGER.close_driver()
        """
        channel = self.__get_channel()
        driver = self.__get_driver_for_channel(channel)
        if self.__config.get(self.REUSE_BROWSER, True):
            # If reuse browser is set, we'll avoid closing it and just clear out the cookies,
            # and reset the location.
            try:
                driver.delete_all_cookies()
                # check to see if webdriver is still responding
                driver.get("about:blank")
            except:
                pass

        if driver is not None:
            try:
                driver.quit()
            except:
                pass

            self.__unregister_driver(channel)
            if driver in self.__registered_drivers[channel]:
                self.__registered_drivers[channel].remove(driver)

            self.webdriver = None

    def get_driver(self):
        '''
        Get an already running instance of Webdriver. If there is none, it will create one.

        Returns:
            Webdriver - Selenium Webdriver instance.

        Usage::

            driver = WTF_WEBDRIVER_MANAGER.new_driver()
            driver.get("http://the-internet.herokuapp.com")
            same_driver = WTF_WEBDRIVER_MANAGER.get_driver()
            print(driver is same_driver) # True
        '''
        driver = self.__get_driver_for_channel(self.__get_channel())
        if driver is None:
            driver = self.new_driver()

        return driver

    def is_driver_available(self):
        '''
        Check if a webdriver instance is created.

        Returns:
            bool - True, webdriver is available; False, webdriver not yet initialized.
        '''
        channel = self.__get_channel()
        try:
            return self.__webdriver[channel] != None
        except:
            return False

    def new_driver(self, testname=None):
        '''
        Used at a start of a test to get a new instance of WebDriver.  If the
        'resuebrowser' setting is true, it will use a recycled WebDriver instance
        with delete_all_cookies() called.

        Kwargs:
            testname (str) - Optional test name to pass to Selenium Grid.  Helpful for
                             labeling tests on 3rd party WebDriver cloud providers.

        Returns:
            Webdriver - Selenium Webdriver instance.

        Usage::

            driver = WTF_WEBDRIVER_MANAGER.new_driver()
            driver.get("http://the-internet.herokuapp.com")
        '''
        channel = self.__get_channel()

        # Get reference for the current driver.
        driver = self.__get_driver_for_channel(channel)

        if self.__config.get(WebDriverManager.REUSE_BROWSER, True):

            if driver is None:
                driver = self._webdriver_factory.create_webdriver(
                    testname=testname)

                # Register webdriver so it can be retrieved by the manager and
                # cleaned up after exit.
                self.__register_driver(channel, driver)
            else:
                try:
                    # Attempt to get the browser to a pristine state as possible when we are
                    # reusing this for another test.
                    driver.delete_all_cookies()
                    # check to see if webdriver is still responding
                    driver.get("about:blank")
                except:
                    # In the case the browser is unhealthy, we should kill it
                    # and serve a new one.
                    try:
                        if driver.is_online():
                            driver.quit()
                    except:
                        pass

                    driver = self._webdriver_factory.create_webdriver(
                        testname=testname)
                    self.__register_driver(channel, driver)

        else:
            # Attempt to tear down any existing webdriver.
            if driver is not None:
                try:
                    driver.quit()
                except:
                    pass
            self.__unregister_driver(channel)
            driver = self._webdriver_factory.create_webdriver(
                testname=testname)
            self.__register_driver(channel, driver)

        return driver
        # End of new_driver method.

    def __register_driver(self, channel, webdriver):
        "Register webdriver to a channel."

        # Add to list of webdrivers to cleanup.
        if not self.__registered_drivers.has_key(channel):
            self.__registered_drivers[channel] = []  # set to new empty array

        self.__registered_drivers[channel].append(webdriver)

        # Set singleton instance for the channel
        self.__webdriver[channel] = webdriver

    def __unregister_driver(self, channel):
        "Unregister webdriver"
        driver = self.__get_driver_for_channel(channel)

        if self.__registered_drivers.has_key(channel) \
                and driver in self.__registered_drivers[channel]:

            self.__registered_drivers[channel].remove(driver)

        self.__webdriver[channel] = None

    def __get_driver_for_channel(self, channel):
        "Get webdriver for channel"
        try:
            return self.__webdriver[channel]
        except:
            return None

    def __get_channel(self):
        "Get the channel to register webdriver to."
        if self.__config.get(WebDriverManager.ENABLE_THREADING_SUPPORT, False):
            channel = current_thread().ident
        else:
            channel = 0

        return channel

    def __del__(self):
        "Deconstructor, call cleanup drivers."
        try:
            self.clean_up_webdrivers()
        except:
            pass


# Global Instance of WebDriver Manager
WTF_WEBDRIVER_MANAGER = WebDriverManager()
"""Global instance of webdriver manager.

Usage::

    driver = WTF_WEBDRIVER_MANAGER.new_driver()
    driver.get('http://www.example.com')

"""
# Adding a shut down hook for cleaning up webdrivers that get
# created by WTF_WEBDRIVER_MANAGER instnace.
try:
    import atexit
    atexit.register(WTF_WEBDRIVER_MANAGER.clean_up_webdrivers)
except:
    pass
