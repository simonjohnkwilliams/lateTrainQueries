# Late Train Query Engine — As-Built Documentation

> **Status:** This describes *exactly what the code does today* (2026-07), quirks
> and all. It is the baseline we lock behaviour against before changing anything.
> It is deliberately descriptive, not aspirational — bugs are documented as
> bugs, not silently corrected.

---

## 1. What it is for

A personal Python tool that asks the National Rail **HSP (Historic Service
Performance) API** how late Simon's commute trains ran, so late-running days can
be identified (and, ultimately, claimed back via Delay Repay).

- **Outbound:** Godalming (`GOD`) → London Waterloo (`WAT`), morning.
- **Inbound:** Waterloo (`WAT`) → Godalming (`GOD`), evening.

For each weekday in a lookback window it finds the **worst-delayed** train of the
day and writes a CSV row: `date, departure time, delay in minutes`.

---

## 2. How to run it (as it stands)

```bash
cd TrainLine
python TestFileGenerator.py
```

- **Must** be run from inside `TrainLine/` — paths are built from `os.getcwd()`.
- No CLI arguments → uses the hardcoded default config (see §4).
- Credentials come from an INI file pointed to by `HSP_CREDENTIALS_FILE`
  (falls back to a hardcoded macOS path `/Users/simonwilliams/Documents/...`).

Output: `TrainLine/Results/outboundLateTrains.csv` and `inboundLateTrains.csv`.
Raw API responses are cached under `TrainLine/downloaded/{outbound,inbound}/{sao,saopid}/`.

---

## 3. The end-to-end pipeline

Entry point is `newMain(serviceDetailsMap)` in `TestFileGenerator.py`. It loops
over each journey (outbound, then inbound) and for each one runs 6 steps:

```
1. clearOldData()              → wipe the downloaded/ cache dirs (all four)
2. writeServiceMetricsTestData → POST /serviceMetrics, one call per day, cache JSON
3. generatePidList             → read cached metrics, pull the first RID per service
4. writeAttributeMessageTestData → POST /serviceDetails per RID, cache JSON
5. generateAttrbuteDictionary  → load all cached details JSON into a list
6. trimToRouteOnlyDictionary   → keep only days where BOTH legs are >1 min late
   getLatestTrainObject        → per day, pick the worst-delayed train
   writeLateTrainsToFile        → write the CSV
```

### The two HSP API calls

| Call | Endpoint | Purpose | Payload |
|------|----------|---------|---------|
| Metrics | `POST /api/v1/serviceMetrics` | Which services ran? | `from_loc, to_loc, from_time, to_time, from_date, to_date, days=WEEKDAY` |
| Details | `POST /api/v1/serviceDetails` | Actual vs scheduled times | `rid` |

Both are HTTP Basic Auth using the HSP credentials. Metrics is called **once per
day** in the window (there appears to be a per-response size limit, hence the
day-by-day loop). Details is called **once per RID**.

### Delay calculation (`LateObject.calculate_delay`)

```
delay = actual_arrival_HHMM − scheduled_arrival_HHMM   (in minutes)
if delay < 0: delay = 0    # early trains clamp to zero
```

- Parses `HHMM` strings as hours/minutes only. **No date component** → any train
  crossing midnight computes a nonsense/negative delay (clamped to 0).
- A train is "late" only if `delay_time > 1` (strictly greater than 1 minute; a
  1-minute-late train is **not** counted).

### The "both legs must be late" rule

`trimToRouteOnlyDictionary` keeps a day only if `generateLateTrainObject` returned
**exactly 2** LateObjects (the departure leg and the arrival leg), and each of
those only exists if that leg was `> 1` minute late. So:

> **A day is silently dropped unless BOTH the origin and destination legs were
> more than 1 minute late.** If the origin departed on time but the train arrived
> 30 minutes late, that day produces no CSV row.

This is a real behavioural constraint (recorded in project memory), not obviously
intended, and it is the single biggest reason real late days go unreported.

### Picking the worst train (`getLatestTrainObject`)

Intended: per day, keep the train with the largest arrival delay. **Actual
behaviour has a bug** — the inner comparison loop iterates over *every day's*
stored entry (`for trainArray in returnTrainObjectList.values()`) rather than
just the current day, and overwrites the current day's slot based on that
cross-day comparison. It produces roughly-right answers on typical data but the
logic is not what the name implies.

---

## 4. Default configuration (`JsonArgs.getJson`)

With no CLI args, two journeys are returned:

| Field | Outbound | Inbound |
|-------|----------|---------|
| Departure | `GOD` | `WAT` |
| Arrival | `WAT` | `GOD` |
| Time window | `0400`–`1300` | `1200`–`2359` |
| Start date | today − 2 days | today − 2 days |
| Days back | 9 | 9 |
| Clear cache first | `True` | `True` |

`writeServiceMetricsTestData` walks **backwards** `days` days from the start date,
so the effective window is `(today−2) … (today−11)`.

The non-default branch (`len(argsJson) > 1`) expects a pre-built dict and only
fills in start-date/days defaults — there is **no actual command-line argument
parsing** despite the README's `GOD WAT 0600 1200 ...` example.

---

## 5. Known quirks / latent bugs (documented, not fixed)

1. **Inbound reuses the outbound service directory.** `newMain` hardcodes
   `OUTBOUND_SERVICE_MESSAGE` / `OUTBOUND_SERVICE_MESSAGE_DIR` in steps 4–5 for
   *both* journeys. It happens to work because the cache is cleared each
   iteration, but the `inbound/saopid` dir is never used.
2. **CSV header always says "Outbound".** `writeLateTrainsToFile` hardcodes
   `'Outbound Train To ' + arrival`, so the inbound CSV is mislabelled.
3. **`getLatestTrainObject` cross-day comparison bug** (see §3).
4. **`LateObject.__init_`** has a typo (single trailing underscore) — the
   constructor is dead code; every field relies on class-level defaults and is
   set attribute-by-attribute by the pipeline.
5. **Substring location matching.** `departureLocation in item[LOCATION]` is a
   substring test, not equality, so a station code that is a substring of
   another could match unexpectedly.
6. **Hardcoded macOS credentials fallback path.**
7. **No midnight handling** in delay maths (see §3).
8. **`messageCreator.py` is dead/legacy code** — points at a `../test/files`
   tree that no longer exists.
9. **Only the first RID per service is used** (`rList[0]` in `generatePidList`).

---

## 6. Test suite (the safety net)

Run with `python -m pytest` (offline + recorded; `live` is excluded by default).

- **Unit / behaviour-regression** (`tests/test_*.py`): cover `calculate_delay`,
  `generateLateTrainObject` (threshold, filtering, direction), `trimToRoute…`
  (both-legs rule), `getLatestTrainObject` (worst-per-day), `generatePidList`,
  the two HTTP writers (mocked `requests.post`), and `JsonArgs.getJson`.
- **BDD** (`tests/features/`, pytest-bdd):
  - `late_trains.feature` — `@offline` scenarios (23-min late reported, on-time
    ignored, 1-min below threshold, worst-of-day picked) + one `@recorded`
    scenario replaying real 2026-05-28 HSP JSON.
  - `live_hsp_api.feature` — one `@live` scenario hitting the real API, gated by
    `HSP_CREDENTIALS_FILE`, skipped by default.
- **Fixtures** (`tests/fixtures/`): synthetic `service_details_*.json` /
  `service_metrics_god_wat.json`, plus real captured `recorded_*` responses.
- `scripts/verify_last_week.py` — one-off script that fetches last Mon–Fri live,
  parses the raw truth independently, runs the pipeline over the same data, and
  reports discrepancies (this is how the "both legs late" drop was diagnosed).

### Environment note
AVG (or corporate) TLS interception on this machine breaks live HTTPS from
Python; the README documents building a project-local CA bundle
(`creds/ca-bundle.pem`) and setting `REQUESTS_CA_BUNDLE` to work around it.

---

## 7. File map

| Path | Role |
|------|------|
| `TrainLine/TestFileGenerator.py` | Everything: API calls, caching, pipeline, CSV write, `main` |
| `TrainLine/LateObject.py` | Value object + `calculate_delay` |
| `TrainLine/JsonArgs.py` | Default/route configuration |
| `TrainLine/messageCreator.py` | Dead legacy code |
| `TrainLine/Results/*.csv` | Output |
| `TrainLine/downloaded/**` | Raw API response cache |
| `tests/**` | pytest + pytest-bdd suite and fixtures |
| `scripts/verify_last_week.py` | Live cross-check tool |
| `creds/**` | Credentials + CA-bundle workaround (gitignored) |

---

## 8. The README's own road map (author's stated intent)

1. Clean up the code
2. Break down the classes
3. Parallelise the file writes
4. Add an option to run directly from messages without writing to disk
5. Split into Lambda functions
6. Build Terraform for the above
