"""HTTP helpers."""

import ssl

import aiohttp
import certifi

from udemy_enroller.logger import get_logger

logger = get_logger()

# Verify HTTPS against certifi's CA bundle. aiohttp otherwise relies on the
# system CA store, which is unavailable in frozen/packaged builds and causes
# "certificate verify failed" errors (requests/cloudscraper already use certifi).
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def _build_session() -> aiohttp.ClientSession:
    """
    Create a session that resolves DNS with the OS resolver.

    When aiodns is present, aiohttp uses the c-ares async resolver — and in
    packaged Windows builds c-ares frequently cannot read the system's DNS
    server list, failing every request with "Could not contact DNS servers".
    Forcing ThreadedResolver routes lookups through socket.getaddrinfo, the
    same resolver requests/cloudscraper already use successfully.
    """
    connector = aiohttp.TCPConnector(
        resolver=aiohttp.ThreadedResolver(), ssl=_SSL_CONTEXT
    )
    return aiohttp.ClientSession(connector=connector)


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
        async with _build_session() as session:
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
        async with _build_session() as session:
            async with session.get(
                url, headers=headers, allow_redirects=True
            ) as response:
                await response.read()
                return str(response.url)
    except Exception as e:
        logger.error(f"Error resolving redirect for {url}: {e}")
