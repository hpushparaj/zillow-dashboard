"""One-time backfill of historical Zestimates from Zillow.com's monthly history.

Idempotent: skips months already present for a given ZPID. Re-runnable any time.
"""

import csv
from pathlib import Path

ROOT = Path(__file__).parent
SNAPSHOTS_FILE = ROOT / "data" / "snapshots.csv"

LABELS = {
    "54770934": "558 Marble Arch",
    "97999338": "4465 Ambassador Way",
    "58606207": "1554 Hayden Mill",
    "14827461": "3290 Northcliff",
}

# Zillow's "Zestimate history" table, one row per month.
# Marble Arch is rounded to nearest $0.1M (Zillow's display rounding for >$1M);
# others are at $0.1K precision.
HISTORY = {
    "97999338": {  # 4465 Ambassador Way
        "2026-05": 413900, "2026-03": 413200, "2026-02": 417300,
        "2026-01": 412300, "2025-12": 418500, "2025-11": 410700,
        "2025-10": 420600, "2025-09": 415000, "2025-08": 419100,
        "2025-07": 420000, "2025-06": 424600, "2025-05": 425300,
        "2025-04": 427300, "2025-03": 427100, "2025-02": 428000,
        "2025-01": 426400,
    },
    "58606207": {  # 1554 Hayden Mill
        "2026-05": 398300, "2026-04": 397500, "2026-03": 395900,
        "2026-02": 392400, "2026-01": 381200, "2025-12": 386900,
        "2025-11": 388000, "2025-10": 392500, "2025-09": 394200,
        "2025-08": 397600, "2025-07": 401200, "2025-06": 401900,
        "2025-05": 403500, "2025-04": 405000, "2025-03": 400300,
        "2025-02": 400700,
    },
    "14827461": {  # 3290 Northcliff
        "2026-05": 463100, "2026-04": 460800, "2026-03": 459900,
        "2026-02": 456900, "2026-01": 454000, "2025-12": 448800,
        "2025-11": 448500, "2025-10": 450000, "2025-09": 444800,
        "2025-08": 441100, "2025-07": 444300, "2025-06": 450800,
        "2025-05": 450000, "2025-04": 450800, "2025-03": 447200,
        "2025-02": 449400,
    },
    "54770934": {  # 558 Marble Arch (rounded to $0.1M by Zillow)
        "2026-05": 1000000, "2026-04": 1000000, "2026-03": 1000000,
        "2026-02": 1100000, "2026-01": 1000000, "2025-12": 1100000,
        "2025-11": 1000000, "2025-10": 1100000, "2025-09": 1100000,
        "2025-08": 1100000, "2025-07": 1100000, "2025-06": 1100000,
        "2025-05": 1100000, "2025-04": 1100000, "2025-03": 1200000,
        "2025-02": 1200000,
    },
}


def main() -> None:
    fieldnames = [
        "fetched_at", "zpid", "label", "address",
        "zestimate", "rent_zestimate", "price",
        "bedrooms", "bathrooms", "living_area",
        "year_built", "home_type", "last_sold_price",
        "last_sold_date", "latitude", "longitude",
    ]
    existing = []
    if SNAPSHOTS_FILE.exists():
        with SNAPSHOTS_FILE.open() as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or fieldnames
            existing = list(reader)

    have = {(r["fetched_at"][:7], r["zpid"]) for r in existing}

    new_rows = []
    for zpid, months in HISTORY.items():
        for ym, value in months.items():
            if (ym, zpid) in have:
                continue
            new_rows.append({
                "fetched_at": f"{ym}-01T00:00:00",
                "zpid": zpid,
                "label": LABELS.get(zpid, zpid),
                "zestimate": value,
            })

    if not new_rows:
        print("Nothing to add — all months already present.")
        return

    all_rows = existing + new_rows
    all_rows.sort(key=lambda r: (r["fetched_at"], str(r.get("zpid"))))

    SNAPSHOTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with SNAPSHOTS_FILE.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"Appended {len(new_rows)} historical rows. Total now: {len(all_rows)}.")


if __name__ == "__main__":
    main()
