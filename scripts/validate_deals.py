#!/usr/bin/env python3
"""Validate deals.json before it is published.

Usage:
    python3 scripts/validate_deals.py [path] [--max-age-hours N]

Exits 0 when the file is valid, 1 with one line per problem otherwise.
--max-age-hours additionally fails when updatedAt is older than N hours
(used by the freshness workflow).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

VALID_SEASONS = {"summer", "winter"}
VALID_TYPES = {"beach", "city", "exotic"}
MAX_WEEKS = 4
TOTAL_TOLERANCE_USD = 1


def parse_iso_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def season_window(season: str, today: date) -> tuple[date, date]:
    """Season as the page defines it: summer 1 Jun-31 Aug, winter 1 Nov-31 Jan.

    Returns this year's window, or next year's once this year's has closed.
    Mirrors seasonWindow() in index.html.
    """
    def window(year: int) -> tuple[date, date]:
        if season == "summer":
            return date(year, 6, 1), date(year, 8, 31)
        return date(year, 11, 1), date(year + 1, 1, 31)

    start, end = window(today.year)
    # Early January still belongs to the winter that began last November.
    if season == "winter" and today <= date(today.year, 1, 31):
        start, end = window(today.year - 1)
    if end < today:
        start, end = window(start.year + 1)
    return start, end


def check_destination(where: str, dest: dict, errors: list[str]) -> None:
    missing = [k for k in ("dest", "flag", "type", "flight", "totalUSD", "perPersonUSD") if k not in dest]
    if missing:
        errors.append(f"{where}: missing {missing}")
        return
    if dest["type"] not in VALID_TYPES:
        errors.append(f"{where}: type '{dest['type']}' not in {sorted(VALID_TYPES)}")

    flight, hotel = dest["flight"], dest.get("hotel")
    for key in ("price", "departsLocal", "durationSec", "stops", "link"):
        if flight.get(key) in (None, ""):
            errors.append(f"{where}: flight missing '{key}'")
    links = [flight.get("link")]
    hotel_price = 0
    if hotel:
        for key in ("name", "score", "priceUSD", "nights", "link"):
            if hotel.get(key) in (None, ""):
                errors.append(f"{where}: hotel missing '{key}'")
        links.append(hotel.get("link"))
        hotel_price = hotel.get("priceUSD") or 0
    for link in links:
        if link and not str(link).startswith("https://"):
            errors.append(f"{where}: link is not https: {link}")

    expected_total = (flight.get("price") or 0) + hotel_price
    if abs(dest["totalUSD"] - expected_total) > TOTAL_TOLERANCE_USD:
        errors.append(f"{where}: totalUSD {dest['totalUSD']} != flight + hotel {expected_total}")


def validate(data: dict, today: date) -> list[str]:
    errors: list[str] = []
    try:
        parse_iso_datetime(data["updatedAt"])
    except (KeyError, TypeError, ValueError):
        errors.append("updatedAt missing or not ISO-8601")
    if data.get("season") not in VALID_SEASONS:
        errors.append(f"season must be one of {sorted(VALID_SEASONS)}")

    weeks = data.get("weeks")
    if not isinstance(weeks, list) or not 1 <= len(weeks) <= MAX_WEEKS:
        errors.append(f"weeks must be a list of 1-{MAX_WEEKS} entries")
        return errors

    window = season_window(data["season"], today) if data.get("season") in VALID_SEASONS else None
    for i, week in enumerate(weeks):
        label = week.get("label", f"week {i}")
        try:
            departure = date.fromisoformat(week["departure"])
            date.fromisoformat(week["return"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"{label}: departure/return missing or not YYYY-MM-DD")
            continue
        # Saturday-night flights leave the day before the week's Sunday.
        if departure - timedelta(days=1) < today:
            errors.append(f"{label}: departure {departure} is in the past")
        if window and not window[0] <= departure <= window[1]:
            errors.append(
                f"{label}: departure {departure} outside {data['season']} window {window[0]}..{window[1]}"
            )
        destinations = week.get("destinations") or []
        if not destinations:
            errors.append(f"{label}: no destinations")
        for dest in destinations:
            check_destination(f"{label}/{dest.get('dest', '?')}", dest, errors)
        totals = [d.get("totalUSD", 0) for d in destinations]
        if totals != sorted(totals):
            errors.append(f"{label}: destinations not sorted by totalUSD")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", nargs="?", default=Path(__file__).resolve().parent.parent / "deals.json")
    parser.add_argument("--max-age-hours", type=float, default=None)
    args = parser.parse_args()

    try:
        data = json.loads(Path(args.path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read {args.path}: {exc}")
        return 1

    errors = validate(data, date.today())
    if args.max_age_hours is not None and "updatedAt" in data:
        try:
            age = datetime.now(timezone.utc) - parse_iso_datetime(data["updatedAt"])
            if age > timedelta(hours=args.max_age_hours):
                errors.append(f"stale: updatedAt {data['updatedAt']} is {age.total_seconds() / 3600:.0f}h old")
        except ValueError:
            pass  # already reported by validate()

    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        return 1
    count = sum(len(w["destinations"]) for w in data["weeks"])
    print(f"OK: {len(data['weeks'])} weeks, {count} deals, updated {data['updatedAt']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
