import json
import re
from typing import Dict

from bs4 import BeautifulSoup


# Map section headers to parser functions
# at2 items can be:
#   - key-value: "72 sq.m.Floor Area" -> value comes first, label second
#   - boolean flag: "Television" -> present (enabled) or absent (disabled class)
#   - key-value with text: "Construction TypePanels"

# Property specs: value is a number or measurement, label follows
# Order matters: longer/more specific labels first to avoid partial matches
_PROPERTY_SPECS = [
    ("Floors in the Building", "total_floors", "int"),
    ("Floor Area", "floor_area", "float"),
    ("Ceiling Height", "ceiling_height", "float"),
    ("Number of Rooms", "rooms", "int"),
    ("Number of Bathrooms", "bathrooms", "int"),
    ("Floor", "floor", "int"),  # must be last among Floor* entries
]

# Key-value text attributes
_KV_ATTRS = {
    "Construction Type": "construction_type",
    "Balcony": "balcony",
    "Renovation": "renovation",
    "Number of Guests": ("max_guests", "int"),
    "Children Are Welcome": "children_welcome",
    "Pets Allowed": "pets_allowed",
}

# Yes/No attributes
_YESNO_ATTRS = {
    "New Construction": "new_construction",
    "Elevator": "elevator",
}

# Boolean flags (present = True if not disabled)
_BOOL_FLAGS = {
    "Intercom entry": "intercom",
    "Concierge": "concierge",
    "Playground": "playground",
    # Parking
    "Outdoor": "parking_outdoor",
    "Covered": "parking_covered",
    "Garage": "parking_garage",
    # Amenities
    "Television": "has_tv",
    "Air conditioner": "has_ac",
    "Internet": "has_internet",
    # Appliances
    "Fridge": "has_fridge",
    "Stove": "has_stove",
    "Microwave": "has_microwave",
    "Coffee maker": "has_coffee_maker",
    "Dishwasher": "has_dishwasher",
    "Washing machine": "has_washer",
    "Drying machine": "has_dryer",
    "Water Heater": "has_water_heater",
    "Iron": "has_iron",
    "Hair dryer": "has_hair_dryer",
    # Views
    "Yard view": "view_yard",
    "Street view": "view_street",
    "City view": "view_city",
    "Park view": "view_park",
    "View of Ararat": "view_ararat",
    # Rental extras
    "Towels": "has_towels",
    "Bed sheets": "has_bed_sheets",
    "Hygiene products": "has_hygiene_products",
}


def _parse_at2_item(text: str, disabled: bool) -> tuple:
    """Parse a single at2 div. Returns (field_name, value) or None."""

    # Check boolean flags first (exact match)
    if text in _BOOL_FLAGS:
        return _BOOL_FLAGS[text], not disabled

    # Check property specs: value comes first, then label
    for label, field, typ in _PROPERTY_SPECS:
        if label in text:
            val_str = text.replace(label, "").strip()
            val_str = val_str.replace("sq.m.", "").replace("m", "").strip()
            try:
                if typ == "int":
                    return field, int(val_str)
                elif typ == "float":
                    return field, float(val_str)
            except ValueError:
                pass
            return None

    # Check key-value attributes: label comes first, value after
    for label, target in _KV_ATTRS.items():
        if text.startswith(label):
            value = text[len(label):].strip()
            if isinstance(target, tuple):
                field, typ = target
                try:
                    if typ == "int":
                        return field, int(value)
                except ValueError:
                    pass
                return None
            return target, value if value else None

    # Check yes/no attributes
    for label, field in _YESNO_ATTRS.items():
        if text.startswith(label):
            value = text[len(label):].strip().lower()
            if "available" in value or "yes" in value:
                return field, True
            elif "no" in value or not value:
                return field, not disabled
            return field, not disabled

    return None


def parse_detail_page(html: str) -> Dict:
    """Parse a rental listing detail page."""
    soup = BeautifulSoup(html, "lxml")
    result = {}

    # Parse all at2 items across all .attr sections
    for at2 in soup.select(".attr div.at2"):
        text = at2.get_text(strip=True)
        disabled = "disabled" in (at2.get("class") or [])
        parsed = _parse_at2_item(text, disabled)
        if parsed:
            field, value = parsed
            result[field] = value

    # Address
    loc = soup.select_one(".loc")
    if loc:
        result["address"] = loc.get_text(strip=True)

    # Description
    body = soup.find("div", class_="body")
    if body:
        result["description"] = body.get_text(strip=True)

    # Dates
    date_matches = re.findall(r"(Posted|Renewed)\s+(\d{2}\.\d{2}\.\d{4})", html)
    for label, date_str in date_matches:
        if label == "Posted":
            result["posted_date"] = date_str
        elif label == "Renewed":
            result["renewed_date"] = date_str

    # Seller info from JSON-LD
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            if data.get("@type") == "AggregateRating":
                reviewed = data.get("itemReviewed", {})
                name = reviewed.get("name")
                if name:
                    result["seller_name"] = name
                rating = data.get("ratingValue")
                if rating is not None:
                    result["seller_rating"] = float(rating)
        except (json.JSONDecodeError, TypeError):
            pass

    # Photos
    photo_urls = re.findall(r"//s\.list\.am/f/\d+/\d+\.(?:jpg|webp)", html)
    seen_ids = set()
    photos = []
    for url in photo_urls:
        pid = re.search(r"/(\d+)\.\w+$", url)
        if pid and pid.group(1) not in seen_ids:
            seen_ids.add(pid.group(1))
            photos.append("https:" + url)
    result["photos"] = photos

    # Price history
    price_changes = []
    for el in soup.select(".down, .up"):
        text = el.get_text(strip=True)
        if text:
            price_changes.append(text)
    result["price_history"] = price_changes

    return result
