#!/usr/bin/env python3
"""Custom-dates deal search: request parsing, validation and the result file checks.

Used in two places:
  * .github/workflows/custom-search.yml - validates the JSON in a "Deal search:" issue
    body before the Routine is fired:
        BODY="$ISSUE_BODY" python3 scripts/custom_request.py request
    prints the normalised request JSON (exit 0) or one error line (exit 1).
  * the Routine, before pushing a result file:
        python3 scripts/custom_request.py result custom/<key>.json
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

DESTINATIONS = ["Budapest", "Prague", "Vienna", "Tenerife", "Dubai", "Phuket", "Bangkok", "Maldives"]
PAX_COUNT = {"couple": 2, "family": 6}
MAX_STAY_DAYS = 30
MAX_DAYS_AHEAD = 365
TOTAL_TOLERANCE_USD = 1


class RequestError(ValueError):
    """The request is malformed; the message is shown to the user."""


def extract_json(body: str) -> dict:
    """Take the first {...} object from the issue body (fenced or bare)."""
    match = re.search(r"\{.*?\}", body or "", re.S)
    if not match:
        raise RequestError("no JSON request found in the issue body")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise RequestError(f"request is not valid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise RequestError("request must be a JSON object")
    return data


def normalise_request(raw: dict, today: date | None) -> dict:
    """Validate every field and return only the known ones, in canonical form.

    today=None skips the past/too-far-ahead checks (used when re-checking a stored result).
    """
    dest = str(raw.get("dest", "")).strip()
    if dest.lower() == "all":
        dest = "all"
    elif dest not in DESTINATIONS:
        raise RequestError(f"dest must be 'all' or one of {', '.join(DESTINATIONS)}")
    try:
        start = date.fromisoformat(str(raw.get("from")))
        end = date.fromisoformat(str(raw.get("to")))
    except ValueError as exc:
        raise RequestError("from/to must be dates in YYYY-MM-DD format") from exc
    if today is not None and start < today:
        raise RequestError(f"from {start} is in the past")
    if end <= start:
        raise RequestError("to must be after from")
    if (end - start).days > MAX_STAY_DAYS:
        raise RequestError(f"stay is longer than {MAX_STAY_DAYS} days")
    if today is not None and (start - today).days > MAX_DAYS_AHEAD:
        raise RequestError(f"from is more than {MAX_DAYS_AHEAD} days ahead")
    pax = str(raw.get("pax", "")).lower()
    if pax not in PAX_COUNT:
        raise RequestError("pax must be 'couple' or 'family'")
    return {"dest": dest, "from": start.isoformat(), "to": end.isoformat(), "pax": pax}


def result_key(request: dict) -> str:
    """File name (without .json) shared by the page, the Action and the Routine."""
    return f"{request['from']}_{request['to']}_{request['dest'].lower()}_{request['pax']}"


def validate_result(data: dict, path: Path) -> list[str]:
    """Checks for custom/<key>.json written by the Routine."""
    errors: list[str] = []
    request = data.get("request") or {}
    try:
        normalised = normalise_request(request, None)
    except RequestError as exc:
        return [f"request: {exc}"]
    if path.stem != result_key(normalised):
        errors.append(f"file name {path.stem} does not match request key {result_key(normalised)}")
    try:
        datetime.fromisoformat(str(data.get("updatedAt", "")).replace("Z", "+00:00"))
    except ValueError:
        errors.append("updatedAt missing or not ISO-8601")
    pax_count = PAX_COUNT[normalised["pax"]]
    wanted = DESTINATIONS if normalised["dest"] == "all" else [normalised["dest"]]
    destinations = data.get("destinations")
    if not isinstance(destinations, list):
        return errors + ["destinations must be a list"]
    for item in destinations:
        where = item.get("dest", "?")
        if where not in wanted:
            errors.append(f"{where}: not part of the request")
        flight, hotel = item.get("flight"), item.get("hotel")
        if not flight and not hotel:
            errors.append(f"{where}: needs a flight or a hotel")
        for part in (flight, hotel):
            if part and not str(part.get("link", "")).startswith("https://"):
                errors.append(f"{where}: link missing or not https")
        if flight and hotel:
            expected = flight.get("price", 0) + hotel.get("priceUSD", 0)
            if abs(item.get("totalUSD", -1) - expected) > TOTAL_TOLERANCE_USD:
                errors.append(f"{where}: totalUSD {item.get('totalUSD')} != flight + hotel {expected}")
            if abs(item.get("perPersonUSD", -1) - expected / pax_count) > TOTAL_TOLERANCE_USD:
                errors.append(f"{where}: perPersonUSD != totalUSD/{pax_count}")
        if hotel and normalised["pax"] == "family" and (hotel.get("rooms") or 0) < 2:
            errors.append(f"{where}: family hotel needs rooms >= 2")
    return errors


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else ""
    if mode == "request":
        try:
            request = normalise_request(extract_json(os.environ.get("BODY", "")), datetime.now(timezone.utc).date())
        except RequestError as exc:
            print(exc)
            return 1
        print(json.dumps({**request, "key": result_key(request)}))
        return 0
    if mode == "result" and len(argv) == 3:
        path = Path(argv[2])
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR: cannot read {path}: {exc}")
            return 1
        errors = validate_result(data, path)
        for error in errors:
            print(f"ERROR: {error}")
        if not errors:
            print(f"OK: {len(data['destinations'])} destinations for {path.stem}")
        return 1 if errors else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
