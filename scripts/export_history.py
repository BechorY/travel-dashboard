#!/usr/bin/env python3
"""Search history: flatten deals.json / custom/<key>.json into history/deals-history.csv.

  python3 scripts/export_history.py append <file> --job refresh|custom   add one run (idempotent)
  python3 scripts/export_history.py backfill                             rebuild from git history
  python3 scripts/export_history.py summary                              write history/deals-summary.csv

history/deals-history.csv = full detail (master, in git). history/deals-summary.csv = compact view for the
Drive sheet: per run x destination x passenger group, the cheapest week.

One row per destination x passenger group (couple/family) x week. The CSV is the master copy;
the Routine also uploads it to the Google Drive folder "Travel deals" (see history/drive.json).
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

HISTORY = Path("history/deals-history.csv")
SUMMARY = Path("history/deals-summary.csv")
SUMMARY_COLUMNS = ["run_at", "job", "season", "dest", "pax", "week_dep", "total", "per_person",
                   "flight_price", "hotel_price", "hotel", "score", "nights"]
COLUMNS = ["run_at", "job", "season", "week_dep", "week_ret", "dest", "pax", "flight_price", "stops",
           "departs", "hotel", "score", "nights", "hotel_price", "total", "per_person",
           "flight_link", "hotel_link"]
KEY = ("run_at", "job", "dest", "pax", "week_dep")


def row(run_at, job, season, dep, ret, dest, pax, block, total, per_person):
    flight, hotel = block.get("flight") or {}, block.get("hotel") or {}
    return {"run_at": run_at, "job": job, "season": season, "week_dep": dep, "week_ret": ret,
            "dest": dest, "pax": pax, "flight_price": flight.get("price", ""),
            "stops": flight.get("stops", ""), "departs": flight.get("departsLocal", ""),
            "hotel": hotel.get("name", ""), "score": hotel.get("score", ""),
            "nights": hotel.get("nights", ""), "hotel_price": hotel.get("priceUSD", ""),
            "total": total if total is not None else "", "per_person": per_person if per_person is not None else "",
            "flight_link": flight.get("link", ""), "hotel_link": hotel.get("link", "")}


def flatten(data: dict, job: str) -> list[dict]:
    run_at = data.get("updatedAt", "")
    rows = []
    if "weeks" in data:                                   # deals.json
        for week in data["weeks"]:
            for d in week.get("destinations", []):
                rows.append(row(run_at, job, data.get("season", ""), week.get("departure", ""),
                                week.get("return", ""), d["dest"], "couple", d, d.get("totalUSD"), d.get("perPersonUSD")))
                fam = d.get("family")
                if fam:
                    rows.append(row(run_at, job, data.get("season", ""), week.get("departure", ""),
                                    week.get("return", ""), d["dest"], "family", fam, fam.get("totalUSD"), fam.get("perPersonUSD")))
    else:                                                 # custom/<key>.json
        req = data.get("request", {})
        for d in data.get("destinations", []):
            rows.append(row(run_at, job, "custom", req.get("from", ""), req.get("to", ""), d["dest"],
                            req.get("pax", ""), d, d.get("totalUSD"), d.get("perPersonUSD")))
    return rows


def read_history() -> list[dict]:
    if not HISTORY.exists():
        return []
    with HISTORY.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def merge(existing: list[dict], new: list[dict]) -> tuple[list[dict], int]:
    seen = {tuple(str(r[k]) for k in KEY) for r in existing}
    added = [r for r in new if tuple(str(r[k]) for k in KEY) not in seen]
    return existing + added, len(added)


def write_history(rows: list[dict]) -> None:
    rows = sorted(rows, key=lambda r: (r["run_at"], r["job"], r["week_dep"], r["dest"], r["pax"]))
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(rows: list[dict]) -> int:
    best: dict[tuple, dict] = {}
    for r in rows:
        if r["total"] == "":
            continue
        key = (r["run_at"], r["job"], r["dest"], r["pax"])
        if key not in best or float(r["total"]) < float(best[key]["total"]):
            best[key] = r
    out = sorted(best.values(), key=lambda r: (r["run_at"], r["job"], r["dest"], r["pax"]))
    with SUMMARY.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=SUMMARY_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(out)
    return len(out)


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def backfill() -> list[dict]:
    rows: list[dict] = []
    for path, job in (("deals.json", "refresh"),):
        for sha in git("log", "--format=%h", "--", path).split():
            try:
                rows += flatten(json.loads(git("show", f"{sha}:{path}")), job)
            except (subprocess.CalledProcessError, json.JSONDecodeError):
                continue
    for path in git("log", "--all", "--name-only", "--format=", "--", "custom/*.json").split():
        for sha in git("log", "--format=%h", "--", path).split():
            try:
                rows += flatten(json.loads(git("show", f"{sha}:{path}")), "custom")
            except (subprocess.CalledProcessError, json.JSONDecodeError):
                continue
    return merge([], rows)[0]


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[1] == "append":
        job = argv[argv.index("--job") + 1] if "--job" in argv else "refresh"
        rows, added = merge(read_history(), flatten(json.loads(Path(argv[2]).read_text(encoding="utf-8")), job))
        write_history(rows)
        write_summary(rows)
        print(f"OK: {added} rows added, {len(rows)} total")
        return 0
    if len(argv) == 2 and argv[1] == "backfill":
        rows = backfill()
        write_history(rows)
        print(f"OK: {len(rows)} rows from git history, {write_summary(rows)} summary rows")
        return 0
    if len(argv) == 2 and argv[1] == "summary":
        print(f"OK: {write_summary(read_history())} summary rows")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
