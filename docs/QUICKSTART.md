# Quickstart — Late Train Query Engine (MVP)

One command. Last week’s claims. CSV + JSON you can check before filing on SWR.

## Prerequisites (once)

1. Python 3.10+ and dependencies:

```powershell
pip install -r requirements-dev.txt
```

2. HSP credentials in `creds/trainConfig.txt` (never commit this file):

```ini
[configuration]
username=your-open-rail-data-email@example.com
password=your-password
```

3. Optional: keep `creds/ca-bundle.pem` if you use AVG HTTPS scanning.
   The app **auto-detects** it — you do **not** need to set `REQUESTS_CA_BUNDLE`.
   If TLS fails with the bundle, it retries with normal system certificates (and
   the reverse if the bundle is missing and system trust fails).

## The one command

From the project root:

```powershell
python -m trainline
```

That will:

- load credentials from `creds/trainConfig.txt` automatically  
  (or from `HSP_CREDENTIALS_FILE` if you set it)
- analyse the **last 5 weekdays** ending yesterday (last week’s work)
- write:
  - `Results/claims.csv`
  - `Results/claims.json`
- stream progress on stderr (each day, metrics/details, cache hits)
- print a short JSON summary (claims found, any “not analysed” days)


## How long does it take?

- **First cold run** (empty `.hsp-cache/`): often **2-10+ minutes** for 5 full weekdays.
  Default windows are 00:00-23:59 both directions, so each day can trigger many
  `serviceDetails` calls (one per train RID).
- **Re-runs**: much faster (seconds to a couple of minutes) because responses
  are cached under `.hsp-cache/`.
- Progress lines go to **stderr** so you can see request/cache activity while
  waiting; the final summary stays as JSON on stdout.

## Change the date window

### Days back (weekdays ending yesterday)

```powershell
python -m trainline --days-back 3
```

`--lookback-days` is the same thing (alias).

| Flag | Meaning |
| --- | --- |
| *(default)* | last **5** weekdays ending yesterday |
| `--days-back N` | last **N** weekdays ending yesterday |
| `--lookback-days N` | same as `--days-back` |

### Concrete dates (inclusive, weekdays only)

```powershell
python -m trainline --from-date 2026-07-07 --to-date 2026-07-11
```

| Flag | Meaning |
| --- | --- |
| `--from-date YYYY-MM-DD` | first day (inclusive) |
| `--to-date YYYY-MM-DD` | last day (inclusive; default yesterday if omitted with `--from-date`) |

Weekends in the range are skipped (HSP queries are weekday-only).

Do **not** mix `--from-date`/`--to-date` with `--days-back`/`--lookback-days`.

## Useful extras

```powershell
python -m trainline --out-dir Results
python -m trainline --batch-size 3
python -m trainline --credentials-file creds\trainConfig.txt
python -m trainline --help
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `--out-dir` | `Results` | where `claims.csv` / `claims.json` land |
| `--batch-size` | `3` | days fetched per HSP batch |
| `--credentials-file` | `creds/trainConfig.txt` | override credentials path |
| `--origin` / `--destination` | `GOD` / `WAT` | route CRS codes |
| `--no-cancellations` | *(off)* | exclude cancellation-derived claims |

## Cancelled trains

By default, a **cancelled** train that has no actual-late alternative on the same
leg is still claimed: the engine computes the delay to the **next train you could
catch** (next-catchable arrival − the cancelled train's scheduled arrival). Such a
row shows the cancelled train's schedule, the actual arrival of the train you
caught, and its `late_canc_reason` code in the `reason` column.

An **actual late train always takes precedence** over a cancellation-derived claim
for the same direction. Pass `--no-cancellations` to exclude cancellation claims
entirely (actual-late claims only).

## What “not analysed” means

If a day’s HSP fetch failed, the summary lists it under `not_analysed`. That is **not** the same as a clean day with nothing to claim — check those days again before assuming zero payout.

## Manual check (after a run)

1. Open `Results/claims.csv`.
2. For each row, confirm date, origin→destination, times, delay, and band against the SWR Delay Repay form before filing.
