"""Webdriver manager."""
import json
import os
import platform
import shutil
import socket
import subprocess
import tempfile
import time
from urllib.request import urlopen

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.ie.service import Service as IEService
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType
from webdriver_manager.firefox import GeckoDriverManager
from webdriver_manager.microsoft import EdgeChromiumDriverManager, IEDriverManager
from webdriver_manager.opera import OperaDriverManager

from udemy_enroller.logger import get_logger

logger = get_logger()

VALID_FIREFOX_STRINGS = {"ff", "firefox"}
VALID_CHROME_STRINGS = {"chrome", "google-chrome"}
VALID_CHROMIUM_STRINGS = {"chromium"}
VALID_BRAVE_STRINGS = {"brave"}
VALID_INTERNET_EXPLORER_STRINGS = {"internet_explorer", "ie"}
VALID_OPERA_STRINGS = {"opera"}
VALID_EDGE_STRINGS = {"edge"}

# Default macOS install location for the Brave binary
BRAVE_BINARY_LOCATION = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"

# Default install locations per OS for the supported Chromium browsers. Absolute
# paths are checked with os.path.isfile first; bare names fall back to
# shutil.which (handy for PATH installs, mainly on Linux).
BROWSER_BINARIES = {
    "chrome": {
        "Darwin": ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"],
        "Windows": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ],
        "Linux": ["google-chrome", "google-chrome-stable", "chrome"],
    },
    "chromium": {
        "Darwin": ["/Applications/Chromium.app/Contents/MacOS/Chromium"],
        "Windows": [r"C:\Program Files\Chromium\Application\chrome.exe"],
        "Linux": ["chromium", "chromium-browser"],
    },
    "brave": {
        "Darwin": [BRAVE_BINARY_LOCATION],
        "Windows": [
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
        ],
        "Linux": ["brave-browser", "brave"],
    },
    "edge": {
        "Darwin": ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"],
        "Windows": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ],
        "Linux": ["microsoft-edge", "microsoft-edge-stable"],
    },
}

# Distinct debug ports per browser so switching browsers between runs doesn't
# accidentally attach to a leftover instance of a different browser.
BROWSER_DEBUG_PORTS = {
    "brave": 9222,
    "chrome": 9223,
    "edge": 9224,
    "chromium": 9225,
}

ALL_VALID_BROWSER_STRINGS = (
    VALID_CHROME_STRINGS.union(VALID_CHROMIUM_STRINGS)
    .union(VALID_BRAVE_STRINGS)
    .union(VALID_EDGE_STRINGS)
)


class DriverManager:
    """Webdriver manager."""

    def __init__(
        self,
        browser: str,
        is_ci_build: bool = False,
        cloudflare_bypass: bool = False,
    ):
        """
        Initialize.

        :param str browser: Name of the browser to create a driver for
        :param bool is_ci_build: Whether this is a headless CI run
        :param bool cloudflare_bypass: When True, launch Chromium browsers
            unflagged and attach over CDP so Cloudflare sees a real browser
            (required for the interactive login/bridge step). Brave always uses
            this mode regardless of the flag.
        """
        self.driver = None
        self.options = None
        self.browser = browser
        self.is_ci_build = is_ci_build
        self.cloudflare_bypass = cloudflare_bypass
        self._init_driver()

    def _init_driver(self):
        """
        Initialize the correct web driver based on the users requested browser.

        :return: None
        """
        browser = self.browser.lower()
        if browser in VALID_BRAVE_STRINGS:
            # Brave only clears Cloudflare through the attach method
            self.driver = self._init_chromium_attached("brave")
        elif browser in VALID_CHROME_STRINGS:
            self.driver = self._init_chrome()
        elif browser in VALID_CHROMIUM_STRINGS:
            self.driver = self._init_chromium()
        elif browser in VALID_EDGE_STRINGS:
            self.driver = self._init_edge()
        elif browser in VALID_FIREFOX_STRINGS:
            self.driver = webdriver.Firefox(
                service=FirefoxService(GeckoDriverManager().install())
            )
        elif browser in VALID_OPERA_STRINGS:
            webdriver_service = ChromeService(OperaDriverManager().install())
            webdriver_service.start()
            options = webdriver.ChromeOptions()
            options.add_experimental_option("w3c", True)
            self.driver = webdriver.Remote(
                webdriver_service.service_url, options=options
            )
        elif browser in VALID_INTERNET_EXPLORER_STRINGS:
            self.driver = webdriver.Ie(service=IEService(IEDriverManager().install()))
        else:
            raise ValueError("No matching browser found")

        # Get around captcha
        self.driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": "const newProto = navigator.__proto__;"
                "delete newProto.webdriver;"
                "navigator.__proto__ = newProto;"
            },
        )
        # Maximize the browser
        self.driver.maximize_window()

    def _init_chrome(self):
        """
        Create a Chrome driver (CI headless, Cloudflare-attach, or standard).

        :return: A Chrome webdriver
        """
        if self.is_ci_build:
            self.options = self._build_ci_options_chrome()
            return webdriver.Chrome(
                service=ChromeService(ChromeDriverManager().install()),
                options=self.options,
            )
        if self.cloudflare_bypass:
            return self._init_chromium_attached("chrome")
        return webdriver.Chrome(
            service=ChromeService(ChromeDriverManager().install()),
            options=self.options,
        )

    def _init_chromium(self):
        """
        Create a Chromium driver (Cloudflare-attach or standard).

        :return: A Chromium webdriver
        """
        if self.cloudflare_bypass:
            return self._init_chromium_attached("chromium")
        return webdriver.Chrome(
            service=ChromeService(
                ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install()
            )
        )

    def _init_edge(self):
        """
        Create an Edge driver (Cloudflare-attach or standard).

        :return: An Edge webdriver
        """
        if self.cloudflare_bypass:
            return self._init_chromium_attached("edge")
        return webdriver.Edge(
            service=EdgeService(EdgeChromiumDriverManager().install())
        )

    @staticmethod
    def _resolve_browser_binary(browser: str) -> str:
        """
        Find the executable for the requested Chromium browser.

        Checks the known install locations for the current OS first, then falls
        back to anything with that name on PATH. Raises a clear error if nothing
        is found.

        :param str browser: One of chrome, chromium, brave, edge
        :return: Path to the browser binary
        """
        candidates = BROWSER_BINARIES.get(browser, {}).get(platform.system(), [])
        for candidate in candidates:
            if os.path.isfile(candidate):
                return candidate
            found = shutil.which(candidate)
            if found:
                return found
        raise RuntimeError(
            f"Could not find the {browser} browser on this system. Install it, "
            f"or edit BROWSER_BINARIES in driver_manager.py to point to its "
            f"location."
        )

    def _init_chromium_attached(self, browser: str):
        """
        Launch a Chromium-based browser as a normal process and attach Selenium.

        Cloudflare's bot protection blocks browsers that chromedriver launches
        directly (they expose automation flags). By starting the browser
        ourselves with only a remote-debugging port and attaching over CDP, the
        browser looks like a regular user session and clears the Cloudflare
        check. Works for Chrome, Chromium, Brave and Edge.

        :param str browser: One of chrome, chromium, brave, edge
        :return: A webdriver attached to the running browser instance
        """
        binary_location = self._resolve_browser_binary(browser)
        # A dedicated port + profile per browser so login cookies persist across
        # runs and switching browsers won't attach to the wrong instance. The
        # profile is separate from the user's normal browser (Chromium locks
        # per profile), so it won't collide with their everyday browsing.
        debug_port = BROWSER_DEBUG_PORTS.get(browser, 9222)
        profile_dir = os.path.join(
            tempfile.gettempdir(), f"udemy_enroller_{browser}_profile"
        )

        # Reuse an already-running enroller instance if one is up
        if self._wait_for_port("127.0.0.1", debug_port, timeout=1):
            logger.info(f"Attaching to already-running {browser} instance")
        else:
            logger.info(f"Launching {browser} (manual login mode to bypass Cloudflare)")
            # Launch directly (not via chromedriver) so no automation flags are set
            subprocess.Popen(
                [
                    binary_location,
                    f"--remote-debugging-port={debug_port}",
                    f"--user-data-dir={profile_dir}",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Wait for the debugging port to become available
            if not self._wait_for_port("127.0.0.1", debug_port, timeout=30):
                raise RuntimeError(
                    f"{browser} did not open a debugging port on {debug_port} "
                    f"in time. Close any {browser} windows started by this tool "
                    "and try again."
                )

        # When attaching, Selenium Manager can't detect the browser version and
        # would grab the latest driver (mismatch). Read the underlying Chromium
        # version from the debug endpoint and pin the matching driver.
        chromium_version = self._get_chromium_version(debug_port)
        debugger_address = f"127.0.0.1:{debug_port}"

        if browser == "edge":
            edge_options = EdgeOptions()
            edge_options.add_experimental_option("debuggerAddress", debugger_address)
            if chromium_version:
                logger.info(f"Edge Chromium version detected: {chromium_version}")
                try:
                    service = EdgeService(
                        EdgeChromiumDriverManager(
                            driver_version=chromium_version
                        ).install()
                    )
                    return webdriver.Edge(service=service, options=edge_options)
                except Exception as e:
                    logger.warning(
                        f"Could not pin Edge driver to {chromium_version}: {e}"
                    )
            # Fallback: let Selenium Manager resolve the driver
            return webdriver.Edge(options=edge_options)

        chrome_options = ChromeOptions()
        chrome_options.add_experimental_option("debuggerAddress", debugger_address)
        if chromium_version:
            logger.info(f"{browser} Chromium version detected: {chromium_version}")
            service = ChromeService(
                ChromeDriverManager(driver_version=chromium_version).install()
            )
            return webdriver.Chrome(service=service, options=chrome_options)

        # Fallback: let Selenium Manager try (may mismatch on very new versions)
        return webdriver.Chrome(options=chrome_options)

    @staticmethod
    def _get_chromium_version(port: int):
        """Read the underlying Chromium version from the debug endpoint."""
        try:
            with urlopen(
                f"http://127.0.0.1:{port}/json/version", timeout=5
            ) as response:
                data = json.loads(response.read().decode())
            browser = data.get("Browser", "")  # e.g. "Chrome/149.0.7827.155"
            if "/" in browser:
                return browser.split("/")[-1]
        except Exception as e:
            logger.warning(f"Could not detect the browser's Chromium version: {e}")
        return None

    @staticmethod
    def _wait_for_port(host: str, port: int, timeout: int = 30) -> bool:
        """Block until a TCP port is accepting connections or timeout elapses."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with socket.create_connection((host, port), timeout=1):
                    return True
            except OSError:
                time.sleep(0.5)
        return False

    @staticmethod
    def _build_ci_options_chrome():
        """
        Build chrome options required to run in CI.

        :return:
        """
        # Having the user-agent with Headless param was always leading to robot check
        user_agent = (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.102 "
            "Safari/537.36"
        )
        options = ChromeOptions()
        # We need to run headless when using github CI
        options.add_argument("--headless")
        options.add_argument("user-agent={0}".format(user_agent))
        options.add_argument("accept-language=en-GB,en-US;q=0.9,en;q=0.8")
        options.add_argument("--window-size=1325x744")
        logger.info("This is a CI run")
        return options
