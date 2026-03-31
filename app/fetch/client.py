from curl_cffi import requests

from app.config.settings import BASE_URL


def fetch_page(url: str) -> str:
    """Fetch a single page and return its HTML content.

    Uses curl_cffi with browser impersonation to bypass TLS fingerprint checks.
    """
    response = requests.get(url, impersonate="chrome", timeout=15)
    response.raise_for_status()
    return response.text
