import json
from typing import List, Optional

from app.db.connection import get_connection
from app.models.listing import Listing


_ALL_COLUMNS = [
    "id", "url", "title", "price", "currency", "price_period",
    "image_url", "is_dealer",
    "district", "city", "address",
    "rooms", "bathrooms", "floor_area", "floor", "total_floors",
    "ceiling_height", "construction_type", "new_construction",
    "balcony", "renovation",
    "elevator", "intercom", "concierge", "playground",
    "parking_outdoor", "parking_covered", "parking_garage",
    "has_tv", "has_ac", "has_internet",
    "has_fridge", "has_stove", "has_microwave", "has_coffee_maker",
    "has_dishwasher", "has_washer", "has_dryer", "has_water_heater",
    "has_iron", "has_hair_dryer",
    "view_yard", "view_street", "view_city", "view_park", "view_ararat",
    "has_towels", "has_bed_sheets", "has_hygiene_products",
    "max_guests", "children_welcome", "pets_allowed",
    "description", "photos", "price_history",
    "posted_date", "renewed_date", "seller_name", "seller_rating",
]

_BOOL_COLUMNS = {
    "is_dealer", "new_construction",
    "elevator", "intercom", "concierge", "playground",
    "parking_outdoor", "parking_covered", "parking_garage",
    "has_tv", "has_ac", "has_internet",
    "has_fridge", "has_stove", "has_microwave", "has_coffee_maker",
    "has_dishwasher", "has_washer", "has_dryer", "has_water_heater",
    "has_iron", "has_hair_dryer",
    "view_yard", "view_street", "view_city", "view_park", "view_ararat",
    "has_towels", "has_bed_sheets", "has_hygiene_products",
}

_JSON_COLUMNS = {"photos", "price_history"}


def _listing_to_row(listing: Listing) -> dict:
    """Flatten a Listing into a DB-ready dict."""
    flat = listing.to_flat_dict()
    row = {}
    for col in _ALL_COLUMNS:
        val = flat.get(col)
        if col in _BOOL_COLUMNS:
            val = (1 if val else 0) if val is not None else None
        elif col in _JSON_COLUMNS:
            val = json.dumps(val) if val else None
        row[col] = val
    return row


def _row_to_listing(row) -> Listing:
    """Reconstruct a Listing from a DB row."""
    keys = row.keys()
    flat = {}
    for col in _ALL_COLUMNS:
        if col not in keys:
            continue
        val = row[col]
        if col in _BOOL_COLUMNS:
            val = bool(val) if val is not None else None
        elif col in _JSON_COLUMNS:
            if isinstance(val, str):
                try:
                    val = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    val = []
            else:
                val = []
        flat[col] = val
    return Listing.from_flat_dict(flat)


def upsert_listings(listings: List[Listing]) -> tuple:
    conn = get_connection()
    inserted = 0
    updated = 0

    for listing in listings:
        row = _listing_to_row(listing)
        existing = conn.execute(
            "SELECT id FROM listings WHERE id = ?", (listing.id,)
        ).fetchone()

        if existing:
            sets = ", ".join("%s = ?" % c for c in _ALL_COLUMNS if c != "id")
            vals = [row[c] for c in _ALL_COLUMNS if c != "id"]
            conn.execute(
                "UPDATE listings SET %s, updated_at = CURRENT_TIMESTAMP WHERE id = ?" % sets,
                vals + [listing.id],
            )
            updated += 1
        else:
            cols = ", ".join(_ALL_COLUMNS)
            placeholders = ", ".join("?" for _ in _ALL_COLUMNS)
            vals = [row[c] for c in _ALL_COLUMNS]
            conn.execute(
                "INSERT INTO listings (%s) VALUES (%s)" % (cols, placeholders),
                vals,
            )
            inserted += 1

    conn.commit()
    conn.close()
    return inserted, updated


def get_all_listings() -> List[Listing]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM listings ORDER BY created_at DESC").fetchall()
    conn.close()
    return [_row_to_listing(row) for row in rows]


def get_listing_by_id(listing_id: str) -> Optional[Listing]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    return _row_to_listing(row)
