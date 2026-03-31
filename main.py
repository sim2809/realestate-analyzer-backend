import sys
import time

from app.config.settings import Category
from app.services.scraper_service import scrape_category


def scrape():
    listings = scrape_category(Category.DAILY_RENTALS)
    print("\nScraped %d listings" % len(listings))


def enrich():
    """Fetch detail pages for all listings that haven't been enriched yet."""
    from app.db.connection import init_db, get_connection
    from app.db.repository import get_listing_by_id, upsert_listings
    from app.fetch.client import fetch_page
    from app.parse.detail_parser import parse_detail_page
    from app.models.listing import Listing

    init_db()
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, url FROM listings WHERE rooms IS NULL ORDER BY created_at DESC"
    ).fetchall()
    conn.close()

    total = len(rows)
    print("[enrich] %d listings need detail data" % total)

    batch = []
    for i, row in enumerate(rows):
        print("[enrich] %d/%d fetching %s" % (i + 1, total, row["url"]))
        try:
            html = fetch_page(row["url"])
            details = parse_detail_page(html)
            listing = get_listing_by_id(row["id"])
            if listing:
                merged = listing.to_flat_dict()
                merged.update(details)
                updated = Listing.from_flat_dict(merged)
                batch.append(updated)
        except Exception as e:
            print("[enrich] failed for %s: %s" % (row["id"], e))

        if len(batch) >= 10:
            upsert_listings(batch)
            print("[enrich] saved batch of %d" % len(batch))
            batch = []

        if i < total - 1:
            time.sleep(0.5)

    if batch:
        upsert_listings(batch)
        print("[enrich] saved final batch of %d" % len(batch))

    print("[enrich] done")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "scrape":
        scrape()
    elif len(sys.argv) > 1 and sys.argv[1] == "enrich":
        enrich()
    else:
        print("Usage: python main.py [scrape|enrich]")


if __name__ == "__main__":
    main()
