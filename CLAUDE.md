# TLV Travel Deals — project memory

Mobile-first static dashboard of flight + hotel package deals from Tel Aviv, served by
GitHub Pages from `main` and used mainly as an iPhone home-screen web app.

## Files
| Path | Role |
|---|---|
| `index.html` | The whole app (HTML/CSS/JS, no build step). Fetches `deals.json` at runtime. |
| `deals.json` | Deal data. Written only by the refresh Routine — never hand-edit prices. |
| `scripts/validate_deals.py` | Stdlib validator: schema, totals, https links, future dates, season window, sort order, optional `--max-age-hours`. |
| `scripts/custom_request.py` | Custom-search request validation (`request`, reads `$BODY`) and result checks (`result <file>`). Key = `from_to_dest_pax`. |
| `custom/<key>.json` | Custom-dates search results, written only by the Routine (JOB B). |
| `.github/workflows/custom-search.yml` | On issue opened by the owner with title `Deal search:` → validate → fire Routine API. Secrets `ROUTINE_FIRE_URL`, `ROUTINE_TOKEN`. |
| `.github/workflows/deals-freshness.yml` | Daily 09:00 UTC + on push: runs the validator with `--max-age-hours 384`; failure emails the owner. |

## Data flow
1. Claude cloud Routine **"TLV travel deals daily refresh"** (`trig_01FuRq1BepWztcwVU8shsAJv`).
   Its prompt has JOB A (scheduled refresh, below) and JOB B (custom search, see Rules).
   Schedule:
   cron `CRON_TZ=Asia/Jerusalem 47 9 1,15 * *` (1st and 15th, ≈ every 2 weeks).
   - Needs, in the Routine config: connectors **Kiwi.com** + **Booking.com**, and repository
     **BechorY/travel-dashboard** (without the repo, `git push` gets 403).
   - Searches 8 destinations (Budapest, Prague, Vienna, Tenerife, Dubai, Phuket, Bangkok,
     Maldives) × first **4** Sundays inside the target season × 2 passenger groups, USD:
     Couple = 2 adults, 1 room; Family = 4 adults + 2 children (ages 8, 12), 2 rooms.
   - Flight window: Saturday ≥ 19:00 or Sunday 04:00–08:00. Hotel: score ≥ 8.0, ≥ 50 reviews.
   - Runs the validator, commits only `deals.json`, pushes to `main`.
     Cost: ≈ $3–4 per run at 3 weeks couple-only; ≈ $10–15 estimated at 4 weeks + family.
2. GitHub Pages redeploys `main` (~1 min).
3. The page fetches `deals.json?t=…` with `cache:'no-store'` on load, on every **Search** press,
   and when the iOS app returns to the foreground after 30 min.

## Rules
- **Seasons:** winter = 1 Nov – 31 Jan, summer = 1 Jun – 31 Aug. January belongs to the winter
  that began the previous November. Outside both, target the season that starts next.
  Must stay identical in `seasonWindow()` (index.html) and `season_window()` (validator).
- **Search Deals** (public page) reloads `deals.json`, then applies the chosen filters to the
  loaded deals. Controls take effect only when Search is pressed (`S.applied`). No live API on
  GitHub Pages (`window.cowork` exists only inside the Claude desktop artifact); Search never
  triggers a Routine run — owner's choice. The live path (`hasLiveBridge()`) is unchanged.
- **Filters:** Season (Summer / Winter / Custom), Destination
  (`#destSel`: All + the 8 destinations), Search for (Package = total, Flights = `flight.price`,
  Hotels = `hotel.priceUSD`; cards sorted by that price), Passengers (Couple = own fields,
  Family = `family` block; "/person" divides by 2 or 6).
- **Layout:** weeks 1–3 = "Best Deals" tabs (`BEST_WEEKS`), weeks 4+ = "More weeks" section.
  Picking the season that isn't loaded shows when it will be loaded (day after the current
  season window ends).
- **Custom Dates** = on-demand search for any Departure/Return (≤ 30 nights), dest (one or all),
  pax. Flow: page checks `custom/<key>.json` (≤ 24 h old → show it) → else a card links to a
  pre-filled GitHub issue ("Deal search: …", body = request JSON) → owner taps Submit →
  `custom-search.yml` (owner-only) validates and POSTs `DEAL_SEARCH_REQUEST {json} ISSUE n` to
  the Routine `/fire` → Routine JOB B searches Kiwi + Booking, writes `custom/<key>.json`,
  commit "… (Closes #n)" → page polls every 30 s for 20 min (pending kept in `localStorage`).
  The file always holds flight + hotel for the requested pax; the page derives Package /
  Flights / Hotels from it. Cost estimate: ≈ $0.5–1 one destination, ≈ $3–5 all (unverified).
  One-time setup: Routine API trigger (URL + token) saved as the two repo secrets.
- **Staleness:** page shows "N days ago"; amber banner after 16 days (`STALE_AFTER_HOURS`).
- Weeks whose Saturday has passed are hidden automatically.
- `deals.json` schema: `updatedAt` (ISO Z), `season`, `nextSunday`, `weeks[] {label, departure,
  return, destinations[] {dest, flag, type, flight{…}, hotel{…}, totalUSD, perPersonUSD,
  family?{flight, hotel{…, rooms≥2}, totalUSD, perPersonUSD=total/6}}}`, up to 8 weeks,
  destinations sorted by couple `totalUSD`, `totalUSD = flight.price + hotel.priceUSD`.
  A missing `family` block shows "Family prices not available for: …".

## Testing
```bash
python3 scripts/validate_deals.py                 # validate deals.json
python3 -m http.server 8765                       # then open http://localhost:8765/
```
Playwright is available (Chromium at `/opt/pw-browsers/chromium`); test at iPhone 13 size and
use `page.clock.install()` to simulate data age and season dates.

## History
- ≤ 9 Sep 2026: refreshed by a Claude desktop scheduled task (only while the PC was on); data
  was embedded in `index.html`. It stopped on 9 Sep.
- 29 Sep 2026: data moved to `deals.json`; fixed invisible mobile "Search & Filters" toggle;
  staleness label/banner; validator + freshness workflow; cloud Routine created and verified
  (first push `f8371ef`); winter/summer windows enforced; schedule changed to every 2 weeks.
- 30 Sep 2026: Search applies Season/Destination/Search for/Passengers filters to the loaded
  deals; 4 weeks (3 Best + More weeks); Family (6) prices via optional `family` block.
  Custom Dates became an on-demand search (GitHub issue → Action → Routine API → custom/).
