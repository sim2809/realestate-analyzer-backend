from typing import List, Dict

from app.models.listing import Listing


def normalize_listing(raw: Dict) -> Listing:
    """Convert a raw parsed listing dict into a normalized Listing DTO."""
    clean = {k: v for k, v in raw.items() if v is not None}
    return Listing.from_flat_dict(clean)


def normalize_listings(raw_listings: List[Dict]) -> List[Listing]:
    return [normalize_listing(raw) for raw in raw_listings]
