import re
from typing import Dict, List, Optional

from bs4 import BeautifulSoup, Tag

from app.config.settings import BASE_URL


def _extract_image_url(card: Tag) -> Optional[str]:
    img = card.select_one("img[src*='list.am'], img[data-original*='list.am']")
    if img is None:
        return None
    src = img.get("data-original") or img.get("src")
    if src and src.startswith("//"):
        src = "https:" + src
    return src


def _parse_details(details_text: str) -> dict:
    """Parse the details line: 'Kentron, 2 rm., 43 sq.m., 8/10 floor'"""
    result = {}
    if not details_text:
        return result

    parts = [p.strip() for p in details_text.split(",")]
    if parts:
        result["district"] = parts[0]

    rooms = re.search(r"(\d+)\s*rm\.", details_text)
    if rooms:
        result["rooms"] = int(rooms.group(1))

    sqm = re.search(r"([\d.]+)\s*sq\.m\.", details_text)
    if sqm:
        result["floor_area"] = float(sqm.group(1))

    floor = re.search(r"(\d+)/(\d+)\s*floor", details_text)
    if floor:
        result["floor"] = int(floor.group(1))
        result["total_floors"] = int(floor.group(2))

    return result


def _parse_price(price_text: str) -> dict:
    """Parse price text like '20,000 ֏ daily' or '$53 daily'"""
    result = {}
    if not price_text:
        return result

    # Detect period
    for period in ("daily", "monthly", "weekly"):
        if period in price_text.lower():
            result["price_period"] = period
            break

    # Detect currency and amount
    if "$" in price_text:
        result["currency"] = "USD"
    elif "֏" in price_text:
        result["currency"] = "AMD"
    elif "€" in price_text:
        result["currency"] = "EUR"

    amount = re.search(r"[\d,]+", price_text)
    if amount:
        result["price"] = int(amount.group().replace(",", ""))

    return result


def parse_listings(html: str) -> List[Dict]:
    """Parse listing cards from a category page."""
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select("a[href*='/item/']")
    listings = []

    for card in cards:
        href = card.get("href", "")
        listing_id = href.split("/item/")[-1].split("?")[0] if "/item/" in href else None

        title_div = card.select_one("div.l")
        price_div = card.select_one("div.p")
        details_div = card.select_one("div.at")
        dealer_tag = card.select_one("span.ge5")

        title = title_div.get_text(strip=True) if title_div else None
        price_text = price_div.get_text(strip=True) if price_div else None
        details_text = details_div.get_text(strip=True) if details_div else None

        entry = {
            "id": listing_id,
            "url": BASE_URL + href.split("?")[0] if href else None,
            "title": title,
            "image_url": _extract_image_url(card),
            "is_dealer": dealer_tag is not None,
        }

        entry.update(_parse_price(price_text))
        entry.update(_parse_details(details_text))

        listings.append(entry)

    return listings
