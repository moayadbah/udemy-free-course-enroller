"""HTTP helpers."""
import aiohttp

from udemy_enroller.logger import get_logger

logger = get_logger()


async def http_get(url, headers=None):
    """
    Send REST get request to the url passed in.

    :param url: The Url to get call get request on
    :param headers: The headers to pass with the get request
    :return: data if any exists
    """
    if headers is None:
        headers = {}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                text = await response.read()
                return text
    except Exception as e:
        logger.error(f"Error in get request: {e}")


async def http_get_final_url(url, headers=None):
    """
    Follow redirects for the url and return the final destination url.

    Useful for affiliate/redirect links (e.g. idownloadcoupon) that bounce
    through trackers before landing on the real Udemy coupon url.

    :param url: The url to resolve
    :param headers: The headers to pass with the get request
    :return: The final url after following redirects, or None on error
    """
    if headers is None:
        headers = {}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=headers, allow_redirects=True
            ) as response:
                await response.read()
                return str(response.url)
    except Exception as e:
        logger.error(f"Error resolving redirect for {url}: {e}")
