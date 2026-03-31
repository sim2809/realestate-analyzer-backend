from app.config.settings import Category
from app.services.scraper_service import scrape_category


def main():
    listings = scrape_category(Category.DAILY_RENTALS)
    print("\nScraped %d listings" % len(listings))


if __name__ == "__main__":
    main()
