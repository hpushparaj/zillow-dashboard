"""
Fetch current Zillow valuations for every ZPID in properties.txt
and append a row per property to data/snapshots.csv.

Run locally:   RAPIDAPI_KEY=xxx python fetch_data.py
Run in CI:     secrets.RAPIDAPI_KEY is set by the GitHub Action.
"""

from __future__ import annotations

import csv
import datetime as dt
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).parent
PROPERTIES_FILE = ROOT / "properties.txt"
SNAPSHOTS_FILE = ROOT / "data" / "snapshots.csv"

RAPIDAPI_HOST = "real-estate-zillow-com.p.rapidapi.com"
RAPIDAPI_URL = f"https://{RAPIDAPI_HOST}/v1/property"

FIELDS = [
    "fetched_at",
    "zpid",
    "label",
    "address",
    "zestimate",
    "rent_zestimate",
    "price",
    "bedrooms",
    "bathrooms",
    "living_area",
    "year_built",
    "home_type",
    "last_sold_price",
    "last_sold_date",
    "latitude",
    "longitude",
]


def read_properties(path: Path) -> list[tuple[str, str]]:
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(",", 1)]
        zpid = parts[0]
        label = parts[1] if len(parts) > 1 else zpid
        out.append((zpid, label))
    return out


def fetch_property(zpid: str, api_key: str) -> dict:
    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
    }
    resp = requests.get(
        RAPIDAPI_URL, headers=headers, params={"zpid_or_url": zpid}, timeout=30
    )
    resp.raise_for_status()
    payload = resp.json()
    # API wraps the property under "data"
    return payload.get("data", payload)


def first(data: dict, *keys, default=None):
    """Return the first non-None value among the given keys."""
    for k in keys:
        v = data.get(k)
        if v is not None:
            return v
    return default


def format_address(data: dict) -> str | None:
    # Prefer top-level fields; fall back to nested "address" dict.
    src = data
    if not src.get("streetAddress"):
        nested = data.get("address")
        if isinstance(nested, dict):
            src = nested
        elif isinstance(nested, str):
            return nested
    parts = [
        src.get("streetAddress"),
        src.get("city"),
        f"{src.get('state', '')} {src.get('zipcode', '')}".strip(),
    ]
    joined = ", ".join(p for p in parts if p)
    return joined or None


def extract_row(zpid: str, label: str, data: dict) -> dict:
    return {
        "fetched_at": dt.datetime.utcnow().isoformat(timespec="seconds"),
        "zpid": zpid,
        "label": label,
        "address": format_address(data),
        "zestimate": first(data, "zestimate", "zEstimate"),
        "rent_zestimate": first(data, "rentZestimate", "rent_zestimate"),
        "price": first(data, "price"),
        "bedrooms": first(data, "bedrooms"),
        "bathrooms": first(data, "bathrooms"),
        "living_area": first(data, "livingArea", "livingAreaValue", "living_area"),
        "year_built": first(data, "yearBuilt", "year_built"),
        "home_type": first(data, "homeType", "home_type", "propertyType"),
        "last_sold_price": first(data, "lastSoldPrice", "last_sold_price"),
        "last_sold_date": first(data, "dateSold", "dateSoldString", "last_sold_date"),
        "latitude": first(data, "latitude"),
        "longitude": first(data, "longitude"),
    }


def append_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    api_key = os.environ.get("RAPIDAPI_KEY")
    if not api_key:
        print("RAPIDAPI_KEY env var is not set", file=sys.stderr)
        return 1

    properties = read_properties(PROPERTIES_FILE)
    if not properties:
        print("No properties to fetch", file=sys.stderr)
        return 0

    rows = []
    for zpid, label in properties:
        try:
            data = fetch_property(zpid, api_key)
            row = extract_row(zpid, label, data)
            rows.append(row)
            print(f"OK   {label} (zpid={zpid})  zestimate={row['zestimate']}")
        except Exception as exc:
            print(f"FAIL {label} (zpid={zpid}): {exc}", file=sys.stderr)
        time.sleep(1)  # polite spacing for free-tier rate limits

    if rows:
        append_rows(SNAPSHOTS_FILE, rows)
        print(f"Appended {len(rows)} rows to {SNAPSHOTS_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
