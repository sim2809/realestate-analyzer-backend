import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "listings.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            id TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            title TEXT NOT NULL,
            price INTEGER,
            currency TEXT,
            price_period TEXT,
            image_url TEXT,
            is_dealer INTEGER NOT NULL DEFAULT 0,

            -- Location
            district TEXT,
            city TEXT,
            address TEXT,

            -- Property
            rooms INTEGER,
            bathrooms INTEGER,
            floor_area REAL,
            floor INTEGER,
            total_floors INTEGER,
            ceiling_height REAL,
            construction_type TEXT,
            new_construction INTEGER,
            balcony TEXT,
            renovation TEXT,

            -- Building
            elevator INTEGER,
            intercom INTEGER,
            concierge INTEGER,
            playground INTEGER,
            parking_outdoor INTEGER,
            parking_covered INTEGER,
            parking_garage INTEGER,

            -- Amenities & Appliances
            has_tv INTEGER,
            has_ac INTEGER,
            has_internet INTEGER,
            has_fridge INTEGER,
            has_stove INTEGER,
            has_microwave INTEGER,
            has_coffee_maker INTEGER,
            has_dishwasher INTEGER,
            has_washer INTEGER,
            has_dryer INTEGER,
            has_water_heater INTEGER,
            has_iron INTEGER,
            has_hair_dryer INTEGER,

            -- Views
            view_yard INTEGER,
            view_street INTEGER,
            view_city INTEGER,
            view_park INTEGER,
            view_ararat INTEGER,

            -- Rental extras
            has_towels INTEGER,
            has_bed_sheets INTEGER,
            has_hygiene_products INTEGER,
            max_guests INTEGER,
            children_welcome TEXT,
            pets_allowed TEXT,

            -- Metadata
            description TEXT,
            photos TEXT,
            price_history TEXT,
            posted_date TEXT,
            renewed_date TEXT,
            seller_name TEXT,
            seller_rating REAL,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
