#!/usr/bin/env python3
"""momondo price check: build the search plan from deals.json and validate momondo.json.

  python3 scripts/momondo_quotes.py plan [--dest Budapest|all] [--week 1|all] [--pax couple|family]
      prints one JSON line per search: {dest, pax, depart, return, kiwi_price, url}
      (dates = the Kiwi flight's local departure / return day, so the prices are like-for-like)
  python3 scripts/momondo_quotes.py plan --dest Dubai --from 2027-02-21 --to 2027-02-24 --pax couple
      custom dates (no Kiwi price to compare)
  python3 scripts/momondo_quotes.py validate [momondo.json]

momondo.json = {"checkedAt": ISO-Z, "quotes": [{dest, pax, depart, return, price, airline, stops,
departsLocal, link}]}; price = TOTAL USD for all passengers. Written only by the momondo-deals skill.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

AIRPORTS = {"Budapest": "BUD", "Prague": "PRG", "Vienna": "VIE", "Tenerife": "TFS", "Dubai": "DXB",
            "Phuket": "HKT", "Bangkok": "BKK", "Maldives": "MLE"}
PAX_PATH = {"couple": "2adults", "family": "4adults/children-8-12"}
QUOTE_KEYS = ("dest", "pax", "depart", "return", "price", "link")


def search_url(dest: str, depart: str, ret: str, pax: str) -> str:
    return (f"https://www.momondo.com/flight-search/TLV-{AIRPORTS[dest]}/{depart}/{ret}/"
            f"{PAX_PATH[pax]}?sort=price_a")


def arg(argv: list[str], name: str, default: str) -> str:
    return argv[argv.index(name) + 1] if name in argv else default


def plan(argv: list[str]) -> list[dict]:
    dest, pax = arg(argv, "--dest", "all"), arg(argv, "--pax", "couple")
    if pax not in PAX_PATH:
        raise SystemExit(f"--pax must be one of {sorted(PAX_PATH)}")
    if dest != "all" and dest not in AIRPORTS:
        raise SystemExit(f"--dest must be 'all' or one of {sorted(AIRPORTS)}")
    if "--from" in argv:                                   # custom dates
        frm, to = arg(argv, "--from", ""), arg(argv, "--to", "")
        date.fromisoformat(frm), date.fromisoformat(to)
        dests = list(AIRPORTS) if dest == "all" else [dest]
        return [{"dest": d, "pax": pax, "depart": frm, "return": to, "kiwi_price": None,
                 "url": search_url(d, frm, to, pax)} for d in dests]
    data = json.loads(Path("deals.json").read_text(encoding="utf-8"))
    today = date.today().isoformat()
    weeks = [w for w in data["weeks"] if w["departure"] > today]   # same rule as the app (Saturday-1 kept)
    week = arg(argv, "--week", "1")
    if week != "all":
        weeks = weeks[int(week) - 1:int(week)]
    out = []
    for w in weeks:
        for d in w["destinations"]:
            if dest != "all" and d["dest"] != dest:
                continue
            offer = d if pax == "couple" else d.get("family")
            if not offer or not offer.get("flight"):
                continue
            fl = offer["flight"]
            dep, ret = fl["departsLocal"][:10], (fl.get("returnDeparts") or w["return"])[:10]
            out.append({"dest": d["dest"], "pax": pax, "depart": dep, "return": ret,
                        "kiwi_price": fl["price"], "url": search_url(d["dest"], dep, ret, pax)})
    return out


def validate(path: Path) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read {path}: {exc}"]
    errors = []
    try:
        datetime.fromisoformat(data["checkedAt"].replace("Z", "+00:00"))
    except (KeyError, AttributeError, ValueError):
        errors.append("checkedAt missing or not ISO-8601")
    for i, q in enumerate(data.get("quotes") or []):
        where = f"quote {i} ({q.get('dest', '?')})"
        missing = [k for k in QUOTE_KEYS if q.get(k) in (None, "")]
        if missing:
            errors.append(f"{where}: missing {missing}")
            continue
        if q["dest"] not in AIRPORTS:
            errors.append(f"{where}: unknown dest")
        if q["pax"] not in PAX_PATH:
            errors.append(f"{where}: pax must be couple|family")
        if not isinstance(q["price"], (int, float)) or q["price"] <= 0:
            errors.append(f"{where}: price must be a positive total in USD")
        if not str(q["link"]).startswith("https://www.momondo.com/"):
            errors.append(f"{where}: link must be an https momondo URL")
        try:
            if date.fromisoformat(q["return"]) <= date.fromisoformat(q["depart"]):
                errors.append(f"{where}: return must be after depart")
        except ValueError:
            errors.append(f"{where}: depart/return not YYYY-MM-DD")
    return errors


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else ""
    if mode == "plan":
        for item in plan(argv):
            print(json.dumps(item))
        return 0
    if mode == "validate":
        path = Path(argv[2] if len(argv) > 2 else "momondo.json")
        if not path.exists():
            print(f"OK: {path} not present")
            return 0
        errors = validate(path)
        for error in errors:
            print(f"ERROR: {error}")
        if not errors:
            print(f"OK: {len(json.loads(path.read_text(encoding='utf-8')).get('quotes') or [])} momondo quotes")
        return 1 if errors else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
