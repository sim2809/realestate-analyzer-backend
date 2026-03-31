from typing import List, Optional

from pydantic import BaseModel


class Location(BaseModel):
    district: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None


class Property(BaseModel):
    rooms: Optional[int] = None
    bathrooms: Optional[int] = None
    floor_area: Optional[float] = None
    floor: Optional[int] = None
    total_floors: Optional[int] = None
    ceiling_height: Optional[float] = None
    construction_type: Optional[str] = None
    new_construction: Optional[bool] = None
    balcony: Optional[str] = None
    renovation: Optional[str] = None


class Building(BaseModel):
    elevator: Optional[bool] = None
    intercom: Optional[bool] = None
    concierge: Optional[bool] = None
    playground: Optional[bool] = None
    parking_outdoor: Optional[bool] = None
    parking_covered: Optional[bool] = None
    parking_garage: Optional[bool] = None


class Amenities(BaseModel):
    has_tv: Optional[bool] = None
    has_ac: Optional[bool] = None
    has_internet: Optional[bool] = None
    has_fridge: Optional[bool] = None
    has_stove: Optional[bool] = None
    has_microwave: Optional[bool] = None
    has_coffee_maker: Optional[bool] = None
    has_dishwasher: Optional[bool] = None
    has_washer: Optional[bool] = None
    has_dryer: Optional[bool] = None
    has_water_heater: Optional[bool] = None
    has_iron: Optional[bool] = None
    has_hair_dryer: Optional[bool] = None


class Views(BaseModel):
    view_yard: Optional[bool] = None
    view_street: Optional[bool] = None
    view_city: Optional[bool] = None
    view_park: Optional[bool] = None
    view_ararat: Optional[bool] = None


class RentalRules(BaseModel):
    has_towels: Optional[bool] = None
    has_bed_sheets: Optional[bool] = None
    has_hygiene_products: Optional[bool] = None
    max_guests: Optional[int] = None
    children_welcome: Optional[str] = None
    pets_allowed: Optional[str] = None


class ListingMeta(BaseModel):
    description: Optional[str] = None
    photos: List[str] = []
    price_history: List[str] = []
    posted_date: Optional[str] = None
    renewed_date: Optional[str] = None
    seller_name: Optional[str] = None
    seller_rating: Optional[float] = None


class Listing(BaseModel):
    """Normalized real estate rental listing DTO."""
    id: str
    url: str
    title: str

    price: Optional[int] = None
    currency: Optional[str] = None
    price_period: Optional[str] = None
    image_url: Optional[str] = None
    is_dealer: bool = False

    location: Location = Location()
    property: Property = Property()
    building: Building = Building()
    amenities: Amenities = Amenities()
    views: Views = Views()
    rental_rules: RentalRules = RentalRules()
    meta: ListingMeta = ListingMeta()

    def to_flat_dict(self) -> dict:
        """Flatten nested models into a single dict for DB storage."""
        d = {
            "id": self.id, "url": self.url, "title": self.title,
            "price": self.price, "currency": self.currency,
            "price_period": self.price_period, "image_url": self.image_url,
            "is_dealer": self.is_dealer,
        }
        for sub in (self.location, self.property, self.building,
                    self.amenities, self.views, self.rental_rules, self.meta):
            d.update(sub.model_dump())
        return d

    @classmethod
    def from_flat_dict(cls, d: dict) -> "Listing":
        """Reconstruct a Listing from a flat dict (e.g. DB row)."""

        def _pick(model_cls):
            return {k: d[k] for k in model_cls.model_fields if k in d and d[k] is not None}

        return cls(
            id=d["id"], url=d["url"], title=d.get("title", ""),
            price=d.get("price"), currency=d.get("currency"),
            price_period=d.get("price_period"), image_url=d.get("image_url"),
            is_dealer=d.get("is_dealer", False),
            location=Location(**_pick(Location)),
            property=Property(**_pick(Property)),
            building=Building(**_pick(Building)),
            amenities=Amenities(**_pick(Amenities)),
            views=Views(**_pick(Views)),
            rental_rules=RentalRules(**_pick(RentalRules)),
            meta=ListingMeta(**_pick(ListingMeta)),
        )
