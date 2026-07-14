# Late Train Query Engine

This program queires the Darwin API for train times from SWR and returns the data from this. 

By default you pass in a set of arguments which include the 

Departure station
Arrival Station
Start search time
End Search time
Start search data
End Search date. 

In the format - GOD WAT 0600 1200 2019-11-01 2019-11-30

As the API for Darwin is asynchronous there are two seperate calls one to the serviceMetrics endpoint to get all of the id's of the trains running at that time, then secondly to the serviceDetails endpoint to get the specific train times. 

At the moment it's pretty specific and only gives you back the latest trains in a range and outputs them to a local file.

# Quick Start

## What it does

For each weekday in the lookback window it asks the National Rail
[HSP (Historic Service Performance) API](https://wiki.openraildata.com/index.php/HSP)
two questions:

1. `POST /serviceMetrics` — which trains ran between **Godalming (GOD)** and
   **London Waterloo (WAT)** in the time window?
2. `POST /serviceDetails` — for each of those services, what were the actual
   versus scheduled arrival times?

It then computes a delay in minutes per train, keeps only those more than
1 minute late, picks the **worst-delayed** train for each day, and writes a
CSV summary to `TrainLine/Results/`:

```
Outbound Train To WAT
Date, Departure Time, Delay Time
2019-12-13,0727,23
2019-12-12,0727,57
...
```

The same is done in reverse for the inbound WAT → GOD evening journey.

## Prerequisites

- Python 3.8+
- An HSP API account from [Open Rail Data](https://wiki.openraildata.com/index.php/Registration)
- The `requests` library: `pip install -r requirements-dev.txt`

## External configuration: `trainConfig.txt`

The app reads your HSP credentials from a local INI-style file. Set the
`HSP_CREDENTIALS_FILE` environment variable to the absolute path of the file;
if unset the code falls back to the original hardcoded
`/Users/simonwilliams/Documents/trainApp/trainConfig.txt`. Format:

```ini
[configuration]
username=your-hsp-email@example.com
password=your-hsp-password
```

On Windows you'd typically use a path like
`C:\path\to\repo\creds\trainConfig.txt` and add `creds/` to `.gitignore` (this
repo already does).

## Running

From the project root:

```bash
cd TrainLine
python TestFileGenerator.py
```

With no arguments it defaults to:

- Outbound GOD → WAT, 04:00–13:00
- Inbound  WAT → GOD, 12:00–23:59
- Start date = today − 2 days, window = 9 days back
- Clears the `downloaded/` cache directories before each run

Raw API responses are cached under `TrainLine/downloaded/{outbound,inbound}/{sao,saopid}/`
so re-runs don't re-hit the API for the same day/service. The CSV summary lands
in `TrainLine/Results/`.

## Running the tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The default invocation runs only the offline tests — no network and no
credentials needed. There are two layers:

**Unit tests** (under `tests/test_*.py` excluding the BDD files) cover:

- `LateObject.calculate_delay` — the "is it late" arithmetic (on-time, late,
  early-clamped-to-zero, large delays).
- `generateLateTrainObject` — the > 1 minute threshold, location filtering,
  inbound/outbound direction.
- `trimToRouteOnlyDictionary` — keeping only services with both legs of the
  route present.
- `getLatestTrainObject` — picking the worst-delayed train per day.
- `generatePidList` — extracting RIDs from cached `serviceMetrics` responses.
- `writeServiceMetricsTestData` / `writeAttributeMessageTestData` — payload
  shape, auth, file caching, and HTTP-error handling, all with mocked
  `requests.post`.
- `JsonArgs.getJson` — the default config dictionary and the override path.

**Behavioural tests** in `tests/features/*.feature` use [pytest-bdd]
(https://pytest-bdd.readthedocs.io/) and describe the end-to-end commuter
journey in Gherkin. Two feature files:

- `late_trains.feature` — four `@offline` scenarios that drive the full
  pipeline (metrics download → details download → CSV write) with HTTP
  stubbed out: a 23-minute-late train is reported, an on-time train is not,
  a 1-minute-late train is below threshold, and given multiple services per
  day the worst-delayed one is picked.
- `live_hsp_api.feature` — one `@live` scenario that actually hits
  `hsp-prod.rockshore.net`. Skipped by default; see the CI section below.

### Recorded scenarios

`@recorded` scenarios drive the pipeline with JSON captured from the real HSP
API (see `tests/fixtures/recorded_metrics_*.json` and
`tests/fixtures/recorded_details_*.json`). They run offline as part of the
default `python -m pytest` invocation but their assertions are grounded in
real Darwin responses — so an upstream API shape change shows up here first.
To refresh the recordings, run the `@live` scenario and copy the captured
files in `live-capture/` over the `recorded_*.json` fixtures.

### Working around AVG / corporate HTTPS interception

If `python -m pytest -m live` fails with
`SSLError(SSLCertVerificationError(... unable to get local issuer certificate))`,
your machine is doing TLS MITM (e.g. AVG Web Shield, ZScaler, corporate proxy)
and the intercepting CA is in the Windows cert store but not in `certifi`. The
fix is to add that CA root to a project-local CA bundle and point requests at
it:

```powershell
# 1. Export the intercepting CA root from the Windows user cert store.
#    For AVG specifically:
powershell -ExecutionPolicy Bypass -File creds/export-avg-root.ps1
#    Or for any other interceptor, find and export the relevant root from
#    Cert:\CurrentUser\Root / Cert:\LocalMachine\Root manually.

# 2. Combine certifi's bundle with the exported root.
python -c "import certifi, shutil; shutil.copy(certifi.where(), 'creds/ca-bundle.pem')"
type creds\avg-root.pem >> creds\ca-bundle.pem
```

Then set both env vars when running the live scenario:

```bash
HSP_CREDENTIALS_FILE=creds/trainConfig.txt \
REQUESTS_CA_BUNDLE=creds/ca-bundle.pem \
python -m pytest -m live
```

CI runners that don't have a TLS interceptor won't need any of this.

### CI / pipeline invocation

```bash
# Default — offline only (no credentials, no network):
python -m pytest

# Live + offline together (CI runners with HSP creds):
HSP_CREDENTIALS_FILE=/path/to/trainConfig.txt python -m pytest -m "live or not live"

# Live only:
HSP_CREDENTIALS_FILE=/path/to/trainConfig.txt python -m pytest -m live
```

The `@live` scenario is gated by `HSP_CREDENTIALS_FILE` and silently skips
(not fails) if the env var is unset or the file is malformed, so CI jobs
without secrets won't go red.

# Road map

1.) Clean up the code 
2.) Break down the classes
3.) Split the write of to files for data to be parallell. 
4.) Add an option to run it directly from the messgaes without writing to disk. 
5.) Split it out into Lambda functions
6.) Build the terraform for the above. 
