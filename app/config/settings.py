from enum import IntEnum
from typing import Optional

BASE_URL = "https://www.list.am"
CATEGORY_URL = BASE_URL + "/en/category"

# Pagination — set MAX_PAGES = None to scrape all pages
MAX_PAGES = 5


class Category(IntEnum):
    """Top-level listing categories on list.am."""
    DAILY_RENTALS = 166


class District(IntEnum):
    """Yerevan district IDs (n parameter) for rental filters."""
    KENTRON = 1
    ARABKIR = 2
    DAVTASHEN = 3
    AJAPNYAK = 4
    MALATIA_SEBASTIA = 5
    SHENGAVIT = 6
    EREBUNI = 7
    NUBARASHEN = 8
    AVAN = 9
    NOR_NORK = 10
    KANAKER_ZEYTUN = 13
    NORK_MARASH = 11
    QANAQER = 12


def build_category_url(
    category: Category,
    *,
    page: int = 0,
) -> str:
    """Build a list.am category listing URL for real estate rentals."""
    params = "?n=1,2,3,4,5,6,7,8,9,10,13,11,12"
    if page > 0:
        params += "&pn=%d" % page
    return "%s/%d%s" % (CATEGORY_URL, category.value, params)
