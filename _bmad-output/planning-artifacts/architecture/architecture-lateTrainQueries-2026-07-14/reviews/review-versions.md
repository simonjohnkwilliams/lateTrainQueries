# Stack Version Review — Late Train Query Engine

**Date:** 2026-07-14
**Reviewer:** automated web-verified review
**Target:** `../ARCHITECTURE-SPINE.md` — Stack table
**Method:** live web search against PyPI / project release pages / endoflife.date (not memory)

## Stack as written

| Name | Version (spine) |
| --- | --- |
| Python | 3.8+ (dev on 3.12) |
| requests | >=2.25 |
| pytest | >=7.0 |
| pytest-bdd | >=7.0 |

## Findings

### Python 3.8+ — FLAG (headline issue)

- Python 3.8 reached **end of life on 31 October 2024**; last release was 3.8.20 (4 Oct 2024). No security/bug fixes since. Current stable line is 3.14 (June 2026).
- For a **personal, local-only CLI** the EOL status is low security risk on its own — it hits no untrusted input beyond the National Rail HSP API and runs on the author's machine.
- The real problem is **internal inconsistency**: every dependency the spine pins has, at its *current* version, already dropped Python 3.8:
  - pytest-bdd 8.1.0 (Apr 2026) dropped 3.8; supports 3.9+.
  - pytest 9.x (Nov 2025+) requires **Python >=3.10**.
  - requests 2.34.x (2026) requires **Python >=3.10**.
- So "Python 3.8+" is not truthfully achievable with the going versions of the chosen libraries. To actually run on 3.8 you would have to pin all three deps to old lines — contradicting the `>=` floors.
- Dev is on 3.12, which is fine and current. **Recommendation:** drop the claimed floor from 3.8+ to **3.10+** (or at minimum 3.9). Costs nothing for a solo tool and makes the stack self-consistent with the current deps.

### requests >=2.25 — OK (floor advisory)

- Exists, extremely well maintained: latest **2.34.2** (14 May 2026), ~300M downloads/week, PSF-backed. No credible reason a reviewer would swap it out for a small CLI (httpx is the only alternative and is not "insisted upon").
- `>=2.25` (2020) is not yanked and is a valid lower bound. Caveat: current requests requires Python >=3.10, so the requests floor is only reachable on 3.8 by pinning old requests — another argument for raising the Python floor. Floor itself is sane; leave as-is or bump to `>=2.31` to pick up known CVE fixes for free.

### pytest >=7.0 — OK

- Exists, actively maintained: latest **9.1.1** (19 Jun 2026). `>=7.0` is a sane, non-yanked floor and won't break the choice. Note pytest 9 needs Python >=3.10 — consistent with raising the Python floor. No better alternative for a Python project.

### pytest-bdd >=7.0 — OK (with note)

- Exists, maintained under pytest-dev: latest **8.1.0** (6 Apr 2026). `>=7.0` floor is fine and current 7.x/8.x both work on 3.9+.
- Note 1: pytest-bdd **8.x dropped Python 3.8** — reinforces the Python-floor flag; a `>=7.0` install on a 3.9+ interpreter will pull 8.x by default.
- Note 2 (design, not version): pytest-bdd is a niche choice; a reviewer *might* question BDD overhead for a solo CLI, but it is mandated by FR19–FR21, so it is defensible and in-scope. Not a version risk.

## Verdict summary

| Item | Verdict | Action |
| --- | --- | --- |
| Python 3.8+ | **FLAG** | Raise floor to 3.10+ (or 3.9); 3.8 is EOL and all pinned deps' current versions no longer support it |
| requests >=2.25 | OK | Fine; optionally bump to `>=2.31` for CVE fixes |
| pytest >=7.0 | OK | No change |
| pytest-bdd >=7.0 | OK | No change; be aware 8.x needs Python 3.9+ |

## Sources

- https://endoflife.date/python
- https://www.anaconda.com/blog/python-3-8-reaches-end-of-life
- https://devguide.python.org/versions/
- https://pypi.org/project/requests/
- https://github.com/psf/requests/releases
- https://pypi.org/project/pytest/
- https://github.com/pytest-dev/pytest/releases
- https://pypi.org/project/pytest-bdd/
- https://github.com/pytest-dev/pytest-bdd/releases
