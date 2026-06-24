"""Freebiesglobal Scraper."""
import asyncio
from typing import List

from bs4 import BeautifulSoup

from udemy_enroller.http_utils import http_get
from udemy_enroller.logger import get_logger
from udemy_enroller.scrapers.base_scraper import BaseScraper

logger = get_logger()

# freebiesglobal blocks requests that don't look like a real browser
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/149.0.0.0 Safari/537.36"
    )
}


class FreebiesglobalScraper(BaseScraper):
    """Contains any logic related to scraping of data from Freebiesglobal.com."""

    DOMAIN = "https://freebiesglobal.com"

    def __init__(self, enabled, max_pages=None):
        """Initialize."""
        super().__init__()
        self.scraper_name = "freebiesglobal"
        if not enabled:
            self.set_state_disabled()
        self.max_pages = max_pages

    @BaseScraper.time_run
    async def run(self) -> List:
        """
        Gathers the udemy links.

        :return: List of udemy course links
        """
        links = await self.get_links()
        logger.info(
            f"Page: {self.current_page} of {self.last_page} scraped from freebiesglobal.com"
        )
        self.max_pages_reached()
        return links

    async def get_links(self) -> List:
        """
        Scrape udemy links from freebiesglobal.com.

        :return: List of udemy course urls
        """
        freebiesglobal_links = []
        self.current_page += 1
        coupons_data = await http_get(
            f"{self.DOMAIN}/tag/udemy/page/{self.current_page}/",
            headers=BROWSER_HEADERS,
        )
        soup = BeautifulSoup(coupons_data.decode("utf-8"), "html.parser")

        # Each deal is a post linked from an <h2> heading. Non-deal links that
        # sneak in are harmless: their post pages won't contain a coupon button
        # and get filtered out in gather_udemy_course_links.
        for heading in soup.find_all("h2"):
            anchor = heading.find("a", href=True)
            if anchor is not None and "/tag/" not in anchor["href"]:
                freebiesglobal_links.append(anchor["href"])

        links = await self.gather_udemy_course_links(freebiesglobal_links)

        for counter, course in enumerate(links):
            logger.debug(f"Received Link {counter + 1} : {course}")

        self.last_page = self._get_last_page(soup)

        return links

    @classmethod
    async def get_udemy_course_link(cls, url: str) -> str:
        """
        Get the udemy course link.

        :param str url: The url to scrape data from
        :return: Coupon link of the udemy course
        """
        data = await http_get(url, headers=BROWSER_HEADERS)
        if data is None:
            return None
        soup = BeautifulSoup(data.decode("utf-8"), "html.parser")
        for link in soup.find_all("a", class_="re_track_btn"):
            udemy_link = cls.validate_coupon_url(link["href"])

            if udemy_link is not None:
                return udemy_link

    async def gather_udemy_course_links(self, courses: List[str]):
        """
        Async fetching of the udemy course links from freebiesglobal.com.

        :param list courses: A list of freebiesglobal.com course links we want to fetch the udemy links for
        :return: list of udemy links
        """
        return [
            link
            for link in await asyncio.gather(*map(self.get_udemy_course_link, courses))
            if link is not None
        ]

    def _get_last_page(self, soup: BeautifulSoup) -> int:
        """
        Extract the last page number to scrape.

        :param soup:
        :return: The last page number to scrape
        """
        page_numbers = soup.find("ul", class_="page-numbers")
        if page_numbers is None:
            # No pagination markup found; stop after the current page
            return self.current_page
        page_values = [
            int(i.text) for i in page_numbers.find_all("li") if i.text.isdigit()
        ]
        return max(page_values) if page_values else self.current_page
