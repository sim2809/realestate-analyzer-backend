import time
from typing import List

from app.config.settings import (
    build_category_url,
    Category,
    MAX_PAGES,
)
from app.fetch.client import fetch_page
from app.parse.listing_parser import parse_listings
from app.parse.detail_parser import parse_detail_page
from app.normalize.listing_normalizer import normalize_listings
from app.db.connection import init_db
from app.db.repository import upsert_listings
from app.models.listing import Listing


def _enrich_with_details(listings: List[Listing], delay: float = 0.5) -> List[Listing]:
    """Fetch each listing's detail page and merge the extra fields."""
    enriched = []
    for i, listing in enumerate(listings):
        print("[detail] %d/%d fetching %s" % (i + 1, len(listings), listing.url))
        try:
            html = fetch_page(listing.url)
            details = parse_detail_page(html)
            # Merge flat detail dict back into the listing
            merged = listing.to_flat_dict()
            merged.update(details)
            updated = Listing.from_flat_dict(merged)
            enriched.append(updated)
        except Exception as e:
            print("[detail] failed for %s: %s" % (listing.id, e))
            enriched.append(listing)
        if delay and i < len(listings) - 1:
            time.sleep(delay)
    return enriched


def scrape_category(
    category: Category = Category.DAILY_RENTALS,
    fetch_details: bool = True,
    detail_delay: float = 0.5,
) -> List[Listing]:
    """Run the full pipeline: Fetch -> Parse -> Normalize -> Detail -> Store."""
    init_db()

    all_listings: List[Listing] = []
    page = 0

    while True:
        if MAX_PAGES is not None and page >= MAX_PAGES:
            break

        url = build_category_url(category, page=page)
        print("[fetch] page %d: %s" % (page + 1, url))

        html = fetch_page(url)
        raw = parse_listings(html)

        if not raw:
            print("[fetch] no listings on page %d, stopping." % (page + 1))
            break

        normalized = normalize_listings(raw)
        all_listings.extend(normalized)
        print("[parse] got %d listings (total: %d)" % (len(normalized), len(all_listings)))

        page += 1

    if fetch_details:
        print("[detail] enriching %d listings..." % len(all_listings))
        all_listings = _enrich_with_details(all_listings, delay=detail_delay)

    inserted, updated = upsert_listings(all_listings)
    print("[store] %d new, %d updated" % (inserted, updated))

    return all_listings
