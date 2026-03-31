import json
import re
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate

from app.db.connection import DB_PATH

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# LangChain setup
llm = ChatOllama(model="llama3", temperature=0)

# Stage 1: Extract search filters from question
EXTRACT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You extract search filters from a user question about short-term rental apartments in Armenia.
Return a JSON object with any of these optional fields:
  district   - area/district (e.g. "Kentron", "Arabkir", "Davtashen")
  min_rooms  - minimum number of rooms (integer)
  max_rooms  - maximum number of rooms (integer)
  min_price  - minimum daily price (integer, in AMD dram)
  max_price  - maximum daily price (integer, in AMD dram)
  min_area   - minimum floor area in sq.m. (integer)
  max_area   - maximum floor area in sq.m. (integer)
  keywords   - array of other search terms (e.g. ["balcony", "elevator", "designer"])

Note: typical daily prices in AMD are 8,000-50,000. If the user says dollars, convert roughly (1 USD ~ 380 AMD).
Only include fields you can confidently extract. Return ONLY valid JSON, nothing else."""),
    ("human", "{question}"),
])

# Stage 2: Reason over all the listing data
REASON_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an expert rental market analyst for list.am, the Armenian real estate marketplace.
Today's date is {today}.

You receive a user's question and a set of short-term (daily) rental apartment listings. Each listing
is a combined text block with ALL available data: title, price (AMD dram, daily), district, rooms,
floor area, floor, amenities (TV, AC, internet, washer, etc.), appliances, views, building info
(elevator, construction type, renovation), house rules (max guests, pets, children), description,
photos count, seller info, posted/renewed dates, and price history (drops/increases in dram).

Your job is to reason deeply over this data. You can:
- Analyze price trends using price_history (e.g. "+3,000 ֏ ▲" means price went up by 3000 dram)
- Compare price per sq.m. across districts
- Evaluate amenity levels (fully equipped vs basic)
- Use posted_date and renewed_date to gauge market activity
- Spot patterns (e.g. "Kentron is pricier", "new construction costs more")
- Calculate averages, ranges, counts from the data
- Reference specific listings by title and price when recommending
- Consider renovation type, views, and building features in value assessment

Be data-driven. Use concrete numbers. Format clearly with bullet points or sections.
If you don't have enough data to fully answer, say so."""),
    ("human", """Question: {question}

I found {count} matching listings. Here is the full data for each:

{listings_text}

Analyze and answer the question:"""),
])


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _parse_row(row) -> dict:
    d = dict(row)
    for field in ("photos", "price_history"):
        if field in d and isinstance(d[field], str):
            try:
                d[field] = json.loads(d[field])
            except (json.JSONDecodeError, TypeError):
                d[field] = []
        elif field in d and d[field] is None:
            d[field] = []
    return d


def _flatten_listing(d: dict) -> str:
    """Combine all columns of a listing into one readable text block."""
    lines = []
    lines.append("--- Listing ID: %s ---" % d.get("id", "?"))
    lines.append("Title: %s" % (d.get("title") or "N/A"))
    lines.append("URL: %s" % (d.get("url") or "N/A"))

    price = d.get("price")
    currency = d.get("currency") or ""
    period = d.get("price_period") or ""
    if price is not None:
        lines.append("Price: %s %s %s" % (currency, price, period))
    else:
        lines.append("Price: not listed")

    for label, key in [
        ("District", "district"), ("City", "city"), ("Address", "address"),
        ("Rooms", "rooms"), ("Bathrooms", "bathrooms"),
        ("Floor Area", "floor_area"), ("Floor", "floor"),
        ("Total Floors", "total_floors"), ("Ceiling Height", "ceiling_height"),
        ("Construction Type", "construction_type"),
        ("Balcony", "balcony"), ("Renovation", "renovation"),
        ("Max Guests", "max_guests"),
        ("Children Welcome", "children_welcome"),
        ("Pets Allowed", "pets_allowed"),
    ]:
        val = d.get(key)
        if val is not None and val != "":
            lines.append("%s: %s" % (label, val))

    bool_labels = [
        ("New Construction", "new_construction"),
        ("Elevator", "elevator"), ("Intercom", "intercom"),
        ("Concierge", "concierge"), ("Playground", "playground"),
        ("Parking Outdoor", "parking_outdoor"),
        ("Parking Covered", "parking_covered"),
        ("Parking Garage", "parking_garage"),
        ("TV", "has_tv"), ("AC", "has_ac"), ("Internet", "has_internet"),
        ("Fridge", "has_fridge"), ("Stove", "has_stove"),
        ("Microwave", "has_microwave"), ("Coffee Maker", "has_coffee_maker"),
        ("Dishwasher", "has_dishwasher"), ("Washer", "has_washer"),
        ("Dryer", "has_dryer"), ("Water Heater", "has_water_heater"),
        ("Iron", "has_iron"), ("Hair Dryer", "has_hair_dryer"),
        ("Yard View", "view_yard"), ("Street View", "view_street"),
        ("City View", "view_city"), ("Park View", "view_park"),
        ("Ararat View", "view_ararat"),
        ("Towels", "has_towels"), ("Bed Sheets", "has_bed_sheets"),
        ("Hygiene Products", "has_hygiene_products"),
    ]
    has_features = [label for label, key in bool_labels if d.get(key)]
    missing_features = [label for label, key in bool_labels if d.get(key) is False]
    if has_features:
        lines.append("Has: %s" % ", ".join(has_features))
    if missing_features:
        lines.append("Missing: %s" % ", ".join(missing_features))

    lines.append("Dealer: %s" % ("Yes" if d.get("is_dealer") else "No"))

    posted = d.get("posted_date")
    renewed = d.get("renewed_date")
    if posted:
        lines.append("Posted: %s" % posted)
    if renewed:
        lines.append("Renewed: %s" % renewed)

    seller = d.get("seller_name")
    rating = d.get("seller_rating")
    if seller:
        s = "Seller: %s" % seller
        if rating:
            s += " (rating: %s/5)" % rating
        lines.append(s)

    ph = d.get("price_history")
    if ph:
        if isinstance(ph, str):
            try:
                ph = json.loads(ph)
            except Exception:
                ph = []
        if ph:
            lines.append("Price History: %s" % " -> ".join(str(p) for p in ph))

    photos = d.get("photos")
    if photos:
        lines.append("Photos: %d images" % len(photos))

    desc = d.get("description")
    if desc:
        lines.append("Description: %s" % desc[:500])

    return "\n".join(lines)


# --- JSON API Endpoints ---


@app.get("/api/search")
def search_listings(
    q: str = Query("", description="Search term"),
    district: Optional[str] = Query(None),
    min_rooms: Optional[int] = Query(None),
    max_rooms: Optional[int] = Query(None),
    min_price: Optional[int] = Query(None),
    max_price: Optional[int] = Query(None),
    dealer_only: bool = Query(False),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    conn = get_db()
    conditions = []
    params = []

    if q:
        conditions.append("(title LIKE ? OR description LIKE ? OR district LIKE ? OR address LIKE ?)")
        params.extend(["%" + q + "%"] * 4)
    if district:
        conditions.append("district LIKE ?")
        params.append("%" + district + "%")
    if min_rooms is not None:
        conditions.append("rooms >= ?")
        params.append(min_rooms)
    if max_rooms is not None:
        conditions.append("rooms <= ?")
        params.append(max_rooms)
    if min_price is not None:
        conditions.append("price >= ?")
        params.append(min_price)
    if max_price is not None:
        conditions.append("price <= ?")
        params.append(max_price)
    if dealer_only:
        conditions.append("is_dealer = 1")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    offset = (page - 1) * limit

    total = conn.execute(
        "SELECT COUNT(*) FROM listings " + where, params
    ).fetchone()[0]

    rows = conn.execute(
        "SELECT * FROM listings " + where + " ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()

    listings = [_parse_row(row) for row in rows]
    conn.close()

    return {
        "listings": listings,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit if limit else 1,
    }


@app.get("/api/listing/{listing_id}")
def get_listing(listing_id: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
    conn.close()
    if row is None:
        return {"error": "Not found"}
    return _parse_row(row)


@app.get("/api/stats")
def get_stats(
    q: str = Query(""),
    district: Optional[str] = Query(None),
    min_rooms: Optional[int] = Query(None),
    max_rooms: Optional[int] = Query(None),
    min_price: Optional[int] = Query(None),
    max_price: Optional[int] = Query(None),
    dealer_only: bool = Query(False),
):
    conn = get_db()
    conditions = []
    params = []

    if q:
        conditions.append("(title LIKE ? OR description LIKE ? OR district LIKE ? OR address LIKE ?)")
        params.extend(["%" + q + "%"] * 4)
    if district:
        conditions.append("district LIKE ?")
        params.append("%" + district + "%")
    if min_rooms is not None:
        conditions.append("rooms >= ?")
        params.append(min_rooms)
    if max_rooms is not None:
        conditions.append("rooms <= ?")
        params.append(max_rooms)
    if min_price is not None:
        conditions.append("price >= ?")
        params.append(min_price)
    if max_price is not None:
        conditions.append("price <= ?")
        params.append(max_price)
    if dealer_only:
        conditions.append("is_dealer = 1")

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    extra_and = "AND" if conditions else "WHERE"

    total = conn.execute("SELECT COUNT(*) FROM listings " + where, params).fetchone()[0]

    price_stats = conn.execute(
        "SELECT COUNT(price) as with_price, AVG(price) as avg_price,"
        " MIN(price) as min_price, MAX(price) as max_price"
        " FROM listings " + where + " " + extra_and + " price IS NOT NULL",
        params,
    ).fetchone()

    district_rows = conn.execute(
        "SELECT district, COUNT(*) as count, AVG(price) as avg_price, AVG(floor_area) as avg_area"
        " FROM listings " + where + " " + extra_and + " district IS NOT NULL"
        " GROUP BY district ORDER BY count DESC",
        params,
    ).fetchall()

    dealer_count = conn.execute(
        "SELECT COUNT(*) FROM listings " + where + " " + extra_and + " is_dealer = 1",
        params,
    ).fetchone()[0]

    room_rows = conn.execute(
        "SELECT rooms, COUNT(*) as count, AVG(price) as avg_price"
        " FROM listings " + where + " " + extra_and + " rooms IS NOT NULL"
        " GROUP BY rooms ORDER BY rooms",
        params,
    ).fetchall()

    conn.close()

    return {
        "total_listings": total,
        "dealer_count": dealer_count,
        "private_count": total - dealer_count,
        "price": {
            "with_price": price_stats["with_price"],
            "avg": round(price_stats["avg_price"]) if price_stats["avg_price"] else None,
            "min": price_stats["min_price"],
            "max": price_stats["max_price"],
        },
        "by_district": [
            {
                "district": r["district"],
                "count": r["count"],
                "avg_price": round(r["avg_price"]) if r["avg_price"] else None,
                "avg_area": round(r["avg_area"], 1) if r["avg_area"] else None,
            }
            for r in district_rows
        ],
        "by_rooms": [
            {
                "rooms": r["rooms"],
                "count": r["count"],
                "avg_price": round(r["avg_price"]) if r["avg_price"] else None,
            }
            for r in room_rows
        ],
    }


@app.get("/api/analytics")
def get_analytics(district: Optional[str] = Query(None)):
    conn = get_db()

    all_districts = conn.execute("""
        SELECT district,
            COUNT(*) as count,
            AVG(price) as avg_price,
            MIN(price) as min_price,
            MAX(price) as max_price,
            AVG(floor_area) as avg_area,
            AVG(rooms) as avg_rooms,
            SUM(CASE WHEN has_ac = 1 THEN 1 ELSE 0 END) as with_ac,
            SUM(CASE WHEN elevator = 1 THEN 1 ELSE 0 END) as with_elevator,
            SUM(CASE WHEN has_internet = 1 THEN 1 ELSE 0 END) as with_internet,
            SUM(CASE WHEN is_dealer = 1 THEN 1 ELSE 0 END) as dealer_count
        FROM listings
        WHERE district IS NOT NULL AND price IS NOT NULL
        GROUP BY district
        ORDER BY count DESC
    """).fetchall()

    districts_summary = []
    for r in all_districts:
        cnt = r["count"]
        districts_summary.append({
            "district": r["district"],
            "count": cnt,
            "avg_price": round(r["avg_price"]) if r["avg_price"] else None,
            "min_price": r["min_price"],
            "max_price": r["max_price"],
            "avg_area": round(r["avg_area"], 1) if r["avg_area"] else None,
            "avg_rooms": round(r["avg_rooms"], 1) if r["avg_rooms"] else None,
            "pct_ac": round(100 * r["with_ac"] / cnt) if cnt else 0,
            "pct_elevator": round(100 * r["with_elevator"] / cnt) if cnt else 0,
            "pct_internet": round(100 * r["with_internet"] / cnt) if cnt else 0,
            "pct_dealer": round(100 * r["dealer_count"] / cnt) if cnt else 0,
        })

    result = {"districts": districts_summary}

    if district:
        base = "WHERE district LIKE ?"
        p = ["%" + district + "%"]

        room_rows = conn.execute(
            "SELECT rooms, COUNT(*) as count, AVG(price) as avg_price"
            " FROM listings " + base + " AND rooms IS NOT NULL"
            " GROUP BY rooms ORDER BY rooms", p
        ).fetchall()

        reno_rows = conn.execute(
            "SELECT renovation, COUNT(*) as count, AVG(price) as avg_price"
            " FROM listings " + base + " AND renovation IS NOT NULL"
            " GROUP BY renovation", p
        ).fetchall()

        const_rows = conn.execute(
            "SELECT construction_type, COUNT(*) as count, AVG(price) as avg_price"
            " FROM listings " + base + " AND construction_type IS NOT NULL"
            " GROUP BY construction_type", p
        ).fetchall()

        ppsqm = conn.execute(
            "SELECT AVG(price * 1.0 / floor_area) as avg_ppsqm,"
            " MIN(price * 1.0 / floor_area) as min_ppsqm,"
            " MAX(price * 1.0 / floor_area) as max_ppsqm"
            " FROM listings " + base + " AND floor_area > 0 AND price IS NOT NULL", p
        ).fetchone()

        amenity_rows = conn.execute(
            "SELECT COUNT(*) as total,"
            " SUM(CASE WHEN has_tv=1 THEN 1 ELSE 0 END) as tv,"
            " SUM(CASE WHEN has_ac=1 THEN 1 ELSE 0 END) as ac,"
            " SUM(CASE WHEN has_internet=1 THEN 1 ELSE 0 END) as internet,"
            " SUM(CASE WHEN has_fridge=1 THEN 1 ELSE 0 END) as fridge,"
            " SUM(CASE WHEN has_washer=1 THEN 1 ELSE 0 END) as washer,"
            " SUM(CASE WHEN has_microwave=1 THEN 1 ELSE 0 END) as microwave,"
            " SUM(CASE WHEN has_dishwasher=1 THEN 1 ELSE 0 END) as dishwasher,"
            " SUM(CASE WHEN has_coffee_maker=1 THEN 1 ELSE 0 END) as coffee_maker,"
            " SUM(CASE WHEN has_iron=1 THEN 1 ELSE 0 END) as iron,"
            " SUM(CASE WHEN has_hair_dryer=1 THEN 1 ELSE 0 END) as hair_dryer"
            " FROM listings " + base, p
        ).fetchone()

        total_d = amenity_rows["total"] or 1
        amenities_pct = {}
        for key in ["tv", "ac", "internet", "fridge", "washer", "microwave",
                     "dishwasher", "coffee_maker", "iron", "hair_dryer"]:
            amenities_pct[key] = round(100 * (amenity_rows[key] or 0) / total_d)

        listings_with_history = conn.execute(
            "SELECT price_history FROM listings " + base +
            " AND price_history IS NOT NULL AND price_history != '[]'", p
        ).fetchall()

        drops = 0
        increases = 0
        for row in listings_with_history:
            try:
                history = json.loads(row["price_history"])
                for h in history:
                    if "\u25bc" in str(h):
                        drops += 1
                    elif "\u25b2" in str(h):
                        increases += 1
            except Exception:
                pass

        result["detail"] = {
            "district": district,
            "by_rooms": [
                {"rooms": r["rooms"], "count": r["count"],
                 "avg_price": round(r["avg_price"]) if r["avg_price"] else None}
                for r in room_rows
            ],
            "by_renovation": [
                {"type": r["renovation"], "count": r["count"],
                 "avg_price": round(r["avg_price"]) if r["avg_price"] else None}
                for r in reno_rows
            ],
            "by_construction": [
                {"type": r["construction_type"], "count": r["count"],
                 "avg_price": round(r["avg_price"]) if r["avg_price"] else None}
                for r in const_rows
            ],
            "price_per_sqm": {
                "avg": round(ppsqm["avg_ppsqm"], 1) if ppsqm["avg_ppsqm"] else None,
                "min": round(ppsqm["min_ppsqm"], 1) if ppsqm["min_ppsqm"] else None,
                "max": round(ppsqm["max_ppsqm"], 1) if ppsqm["max_ppsqm"] else None,
            },
            "amenities_pct": amenities_pct,
            "price_trends": {
                "total_drops": drops,
                "total_increases": increases,
                "listings_with_changes": len(listings_with_history),
            },
        }

    conn.close()
    return result


class AskRequest(BaseModel):
    question: str


@app.post("/api/ask")
def ask_question(req: AskRequest):
    from datetime import date

    extract_response = llm.invoke(
        EXTRACT_PROMPT.format_messages(question=req.question)
    )

    filters = {}
    try:
        raw = extract_response.content.strip()
        if raw.startswith("```"):
            raw = re.sub(r"```(?:json)?\s*", "", raw).rstrip("`").strip()
        filters = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        pass

    conn = get_db()
    conditions = []
    params = []

    if filters.get("district") and isinstance(filters["district"], str):
        conditions.append("district LIKE ?")
        params.append("%" + filters["district"] + "%")
    if filters.get("min_rooms") and isinstance(filters["min_rooms"], (int, float)):
        conditions.append("rooms >= ?")
        params.append(int(filters["min_rooms"]))
    if filters.get("max_rooms") and isinstance(filters["max_rooms"], (int, float)):
        conditions.append("rooms <= ?")
        params.append(int(filters["max_rooms"]))
    if filters.get("min_price") and isinstance(filters["min_price"], (int, float)):
        conditions.append("price >= ?")
        params.append(int(filters["min_price"]))
    if filters.get("max_price") and isinstance(filters["max_price"], (int, float)):
        conditions.append("price <= ?")
        params.append(int(filters["max_price"]))
    if filters.get("min_area") and isinstance(filters["min_area"], (int, float)):
        conditions.append("floor_area >= ?")
        params.append(int(filters["min_area"]))
    if filters.get("max_area") and isinstance(filters["max_area"], (int, float)):
        conditions.append("floor_area <= ?")
        params.append(int(filters["max_area"]))

    keywords = filters.get("keywords", [])
    if isinstance(keywords, list):
        for kw in keywords:
            if isinstance(kw, str):
                conditions.append("(title LIKE ? OR description LIKE ?)")
                params.extend(["%" + kw + "%", "%" + kw + "%"])

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    rows = conn.execute(
        "SELECT * FROM listings " + where + " ORDER BY created_at DESC LIMIT 50",
        params,
    ).fetchall()

    listings = [_parse_row(row) for row in rows]
    conn.close()

    listings_text_parts = [_flatten_listing(l) for l in listings]
    listings_text = "\n\n".join(listings_text_parts) if listings_text_parts else "No matching listings found."

    answer_response = llm.invoke(
        REASON_PROMPT.format_messages(
            question=req.question,
            count=len(listings),
            listings_text=listings_text,
            today=date.today().strftime("%Y-%m-%d"),
        )
    )

    return {
        "filters": filters,
        "answer": answer_response.content,
        "listings": listings[:20],
    }
