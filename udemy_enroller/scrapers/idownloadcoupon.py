"""IDownloadCoupon scraper."""
import asyncio
import re
import urllib.parse
from typing import List

from bs4 import BeautifulSoup

from udemy_enroller.http_utils import http_get, http_get_final_url
from udemy_enroller.logger import get_logger
from udemy_enroller.scrapers.base_scraper import BaseScraper

logger = get_logger()

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/149.0.0.0 Safari/537.36"
    )
}


class IDownloadCouponScraper(BaseScraper):
    """Contains any logic related to scraping of site data."""

    DOMAIN = "https://www.idownloadcoupon.com"

    def __init__(self, enabled, max_pages=None):
        """Initialize."""
        super().__init__()
        self.scraper_name = "idownloadcoupon"
        if not enabled:
            self.set_state_disabled()
        self.last_page = None
        self.max_pages = max_pages

    @BaseScraper.time_run
    async def run(self) -> List:
        """
        Run the steps to scrape links.

        :return: list of udemy coupon links
        """
        links = await self.get_links()
        self.max_pages_reached()
        return links

    async def get_links(self):
        """
        Scrape udemy links.

        :return: List of udemy course urls
        """
        self.current_page += 1
        course_links = await self.get_course_links(
            f"{self.DOMAIN}/page/{self.current_page}/"
        )

        logger.info(
            f"Page: {self.current_page} of {self.last_page} scraped from {self.scraper_name}"
        )
        udemy_links = await self.gather_udemy_course_links(course_links)

        for counter, course in enumerate(udemy_links):
            logger.debug(f"Received Link {counter + 1} : {course}")

        return udemy_links

    async def get_course_links(self, url: str) -> List:
        """
        Get the url of pages which contain the udemy link we want to get.

        :param str url: The url to scrape data from
        :return: list of pages that contain Udemy coupons
        """
        text = await http_get(url)
        if text is not None:
            soup = BeautifulSoup(text.decode("utf-8"), "html.parser")

            links = soup.find_all("li", class_="product")
            course_links = [link.find_all("a")[1].get("href") for link in links]

            self.last_page = int(
                soup.find("ul", class_="page-numbers")
                .find_all("a", class_="page-numbers")[-2]
                .text.replace(",", "")
            )

            return course_links

    @classmethod
    async def get_udemy_course_link(cls, url: str) -> str:
        """
        Get the udemy course link.

        idownloadcoupon links now point to an internal redirect
        (e.g. https://idownloadcoupon.com/udemy/13933/) that bounces through
        affiliate trackers before landing on the real Udemy coupon url. We
        follow the redirect and strip the tracking params down to the
        course path + couponCode.

        :param str url: The url to scrape data from
        :return: Coupon link of the udemy course
        """
        final_url = await http_get_final_url(url, headers=BROWSER_HEADERS)
        if not final_url:
            return None
        clean_url = cls._clean_udemy_url(final_url)
        if clean_url is None:
            return None
        return cls.validate_coupon_url(clean_url)

    @staticmethod
    def _clean_udemy_url(url: str) -> str:
        """
        Reduce a Udemy url with tracking params to just the course + couponCode.

        The url may be a tracker (e.g. trk.udemy.com/...?u=<encoded udemy url>)
        that embeds the real Udemy link in a query param, so we decode and pull
        the course path and coupon code out of the full string.

        :param str url: A url that contains a udemy.com course + couponCode
        :return: A clean https://www.udemy.com/course/<slug>/?couponCode=<code> url or None
        """
        decoded = urllib.parse.unquote(url)
        path_match = re.search(r"https://www\.udemy\.com(/course/[^/?\s]+)", decoded)
        code_match = re.search(r"couponCode=([A-Za-z0-9]+)", decoded)
        if path_match and code_match:
            return (
                f"https://www.udemy.com{path_match.group(1)}/"
                f"?couponCode={code_match.group(1)}"
            )
        return None

    async def gather_udemy_course_links(self, courses: List[str]):
        """
        Async fetching of the udemy course links.

        :param list courses: A list of course links we want to fetch the udemy links for
        :return: list of udemy links
        """
        return [
            link
            for link in await asyncio.gather(*map(self.get_udemy_course_link, courses))
            if link is not None
        ]
