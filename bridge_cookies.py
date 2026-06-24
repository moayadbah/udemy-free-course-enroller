"""Bridge a logged-in browser session to the REST-based udemy_enroller.

Udemy now enforces Cloudflare + 2FA on login, which blocks the REST login
flow. This helper logs in through a real browser window (manual, bypassing
Cloudflare), then extracts the authentication cookies Udemy needs
(access_token, client_id, csrftoken) and writes them to the .cookie file that
`udemy_enroller` reads. After running this once you can use the fast,
API-based enrollment by running `udemy_enroller` (no --browser flag).

Usage:
    python3 bridge_cookies.py [browser]

where [browser] is one of: brave (default), chrome, edge, chromium.
"""
import json
import os
import sys

from udemy_enroller.driver_manager import DriverManager
from udemy_enroller.logger import get_logger, load_logging_config
from udemy_enroller.settings import Settings
from udemy_enroller.udemy_ui import UdemyActionsUI
from udemy_enroller.utils import get_app_dir

load_logging_config()
logger = get_logger()

REQUIRED_COOKIES = ("access_token", "client_id", "csrftoken")
SUPPORTED_BROWSERS = ("brave", "chrome", "edge", "chromium")


def main() -> int:
    """Log in via a browser and save Udemy auth cookies for REST mode."""
    browser = sys.argv[1].lower() if len(sys.argv) > 1 else "brave"
    if browser not in SUPPORTED_BROWSERS:
        logger.error(
            f"Unsupported browser '{browser}'. "
            f"Choose one of: {', '.join(SUPPORTED_BROWSERS)}."
        )
        return 1

    logger.info(f"Using {browser} for login (Cloudflare-bypass mode)")
    settings = Settings()
    dm = DriverManager(browser=browser, cloudflare_bypass=True)
    try:
        ui = UdemyActionsUI(dm.driver, settings)
        # Ensures we are logged in (prompts for manual login if needed)
        ui.login()

        # Make sure we are on the udemy domain so all auth cookies are present
        dm.driver.get("https://www.udemy.com/")

        browser_cookies = {
            cookie["name"]: cookie["value"] for cookie in dm.driver.get_cookies()
        }

        missing = [name for name in REQUIRED_COOKIES if name not in browser_cookies]
        if missing:
            logger.error(
                f"Could not find these required cookies in the browser session: {missing}. "
                "Make sure you are fully logged in to Udemy before the script extracts cookies."
            )
            return 1

        cookie_file = os.path.join(get_app_dir(), ".cookie")
        with open(cookie_file, "w") as f:
            f.write(json.dumps(browser_cookies))

        logger.info(f"Saved Udemy auth cookies to {cookie_file}")
        logger.info(
            "You can now run `udemy_enroller` (without --browser) to enroll via the "
            "faster REST API."
        )
        return 0
    finally:
        logger.info("Closing browser")
        dm.driver.quit()


if __name__ == "__main__":
    sys.exit(main())
