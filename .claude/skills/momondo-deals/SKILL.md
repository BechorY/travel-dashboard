---
name: momondo-deals
description: Check momondo flight prices for the TLV Travel Deals app's searches in the user's own Chrome and publish them to momondo.json, so the app shows a momondo price (and "cheaper on momondo") next to each Kiwi deal. Use when the user asks to check momondo, compare prices with momondo, or update deals from momondo. Runs on the user's PC with Claude in Chrome; never in a cloud session.
argument-hint: "[dest|all] [week N|all] [couple|family]  or  custom <dest|all> <YYYY-MM-DD> <YYYY-MM-DD> <couple|family>"
---

# momondo price check for TLV Travel Deals

Reads momondo results for the same trips the app shows (or a custom date range) in the user's
signed-in Chrome, and writes `momondo.json`. It never edits `deals.json` (owned by the Routine).

## Hard rules
- **Never type, paste, guess or store any email, password, 2FA code or payment detail.**
- **Login / sign-in / captcha / "verify you are human" / cookie wall that blocks results** → stop
  immediately and alert the user with a pop-up: call `AskUserQuestion` with the question
  "momondo is asking for <Google sign-in | a captcha | …> in the Chrome tab '<tab title>'. Please
  complete it yourself in Chrome, then choose Continue." and options **Continue** / **Skip this
  search** / **Stop**. If a `PushNotification` tool is available, also send the same text so the
  phone gets it. Resume only after the user answers. Do not click "Sign in with Google".
- Never invent prices or links. If a price can't be read, leave that search out and say why.
- Low volume, like a person browsing: one tab, searches one after another, no more than 16 per run.
- Run only where Claude in Chrome is available (desktop app / Claude Code on the PC). In a cloud
  session (no Chrome, momondo blocked by the network) stop and tell the user.

## Steps
1. Load the `anthropic-skills:chrome-browser` skill and follow it (open a **new tab**, don't touch
   the user's other tabs).
2. In the repo: `git pull origin main`. Build the plan:
   - default / `[dest] [week] [pax]`:
     `python3 scripts/momondo_quotes.py plan --dest <dest|all> --week <N|all> --pax <couple|family>`
     (defaults: all destinations, week 1, couple → 8 searches)
   - `custom <dest|all> <from> <to> <pax>`:
     `python3 scripts/momondo_quotes.py plan --dest <dest> --from <from> --to <to> --pax <pax>`
   Each line has `dest, pax, depart, return, kiwi_price, url`.
3. For each line: open `url`, wait until results finish loading (the progress bar stops), then check:
   - route TLV → destination, dates and passengers match the line (2 adults; or 4 adults + 2
     children aged 8 and 12). If momondo changed passengers, fix them in the page, never guess.
   - currency is **USD**. If not, switch it in momondo's settings; if you can't, skip and report.
   - For weekly trips (kiwi_price set) keep only flights departing **Saturday ≥ 19:00 or Sunday
     04:00–08:00** (local); for custom dates take any time.
   Read the **cheapest qualifying** result: total price for all passengers (if momondo shows a
   per-person price, multiply by the passenger count and say so), airline, stops, outbound local
   departure time, and the result's booking/details link (or the search URL if there is none).
4. Write `momondo.json` (UTF-8, `ensure_ascii=False`, indent 1). Keep quotes from earlier runs for
   other trips; replace a quote with the same `dest + pax + depart + return`:
   ```json
   {"checkedAt": "<now UTC ISO Z>",
    "quotes": [{"dest": "Budapest", "pax": "couple", "depart": "2026-11-14", "return": "2026-11-22",
                "price": 455, "airline": "Wizz Air", "stops": 0,
                "departsLocal": "2026-11-14T19:30:00", "link": "https://www.momondo.com/…"}]}
   ```
5. `python3 scripts/momondo_quotes.py validate` must print OK; fix and re-run otherwise.
6. `git add momondo.json && git commit -m "momondo check <date> – N quotes (<k> cheaper than Kiwi)"`
   then `git pull --rebase origin main && git push origin HEAD:main`.
7. Report a table: destination, dates, Kiwi price, momondo price, difference, and any skipped
   searches with the reason. The app shows the momondo price on matching cards within ~1 minute.
