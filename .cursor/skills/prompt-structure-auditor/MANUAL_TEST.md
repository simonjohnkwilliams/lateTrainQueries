# Manual test plan — Releases 1–6

**Built through: R1 Audit → R2 Prioritise → R3 Preview → R4 Validate → R5 Apply → R6 Continuous (baseline/diff/CI).**

Automated: `cd scripts; $env:PYTHONPATH=(Get-Location).Path; python -m pytest`

**Release automation (R1–R6, fixtures + live IdeaProjects):**

```powershell
python -m pytest tests/acceptance/test_releases_r1_r6.py -v -s
```

Runs fixtures always; live VR1/VR2/VR3 when those paths exist. Every release stage asserts the frozen audit format stays identical across repos.

User guide: [QUICKSTART.md](QUICKSTART.md)

## What was performed (engineering)

| Item | Done |
|------|------|
| R1 Discovery, model, rules, inventory, human+JSON audit, determinism | Yes |
| Phase 1 acceptance suite (A–I) | Yes |
| ORDER001 false-positive fix (On Hold / Debugging) | Yes |
| R2 Roadmap + “Fix these first” + dependency hints | Yes |
| R3 `psa patch preview` (ORDER001; finding id or rule id) | Yes |
| R4 `psa patch validate` (scratch re-audit; invariant) | Yes |
| R5 `psa patch apply` (git branch + commit + `--yes` + rollback text) | Yes |
| R6 `baseline save` / `diff` / `--fail-on-introduced` + GitHub Actions | Yes |

## Setup

```powershell
cd c:\Users\simon\cursor\SJW_skills\prompt-structure-auditor\scripts
$env:PYTHONPATH = (Get-Location).Path
```

---

### 1) R1 — Audit + Doctor (frozen UX)

```powershell
python -m psa audit .\tests\fixtures\vr3_demo
python -m psa audit .\tests\fixtures\empty_repo
python -m psa doctor .\tests\fixtures\vr3_demo
python -m psa audit .\tests\fixtures\vr3_demo --format json
```

**Pass if:** every `audit` starts with **Prompt Structure Auditor**, then **Summary**, then **Findings** only — **no Recommended Plan**; empty repos show Findings placeholder and `Healthy`; issue repos show `Needs Attention`; ASCII output. Then `psa plan` shows Recommended Plan separately. `doctor` still lists ignores and Guidance Surface paths.

**Contract tests:** `python -m pytest tests/acceptance/test_audit_contract_r1.py`

**Regression (install-in-repo):** no findings from `.cursor/skills/**/scripts/tests/fixtures/**`.

**Optional live repos (in complete suite when present):** VR1 `ai-context-benchmark` (healthy empty); VR2 `lateTrainQueries` (ACT+DUP); VR3 `financeTracker_SW` (healthy CLAUDE.md). Covered by `test_releases_r1_r6.py` + `test_live_validation_repos.py`.

---

### 2) R2 — Plan (separate from audit)

```powershell
python -m psa plan .\tests\fixtures\vr3_demo
python -m psa plan .\tests\fixtures\empty_repo
python -m psa audit .\tests\fixtures\vr3_demo   # must NOT contain Recommended Plan
```

**Pass if:** `plan` has Summary + Recommended Plan table (with Why now) + compact Details + Expected end state; no Unblocks duplication; healthy repos show empty-state; structure identical across repos; `audit` remains factual only; plan never mentions preview/apply.

---

### 3) R3 — Preview (no writes)

```powershell
git status --porcelain   # optional baseline
python -m psa patch preview ORDER001 .\tests\fixtures\vr3_demo
git status --porcelain   # unchanged
```

**Pass if:** unified diff only; working tree unchanged; `STYLE001` preview errors clearly if tried.

---

### 4) R4 — Validate

```powershell
python -m psa patch validate ORDER001 .\tests\fixtures\vr3_demo
python -m psa patch validate ORDER001 .\tests\fixtures\vr3_demo --format json
```

**Pass if:** `Result: PASS`, Introduced 0, exit code 0; fixture files unchanged.

---

### 5) R5 — Apply (throwaway git repo)

```powershell
$demo = Join-Path $env:TEMP "psa-apply-demo"
Remove-Item -Recurse -Force $demo -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $demo | Out-Null
Copy-Item .\tests\fixtures\vr3_demo\* $demo -Recurse
Set-Location $demo
git init
git add -A
git -c user.email=t@t -c user.name=t commit -m init
$env:PYTHONPATH = "c:\Users\simon\cursor\SJW_skills\prompt-structure-auditor\scripts"
python -m psa patch apply ORDER001 . --yes
git log -1 --oneline
git branch --show-current
# Rollback when done:
# git checkout main   # or master
# git branch -D <psa/fix-…>
```

**Pass if:** refuses without `--yes` (exit 2); with `--yes` creates `psa/fix-…` branch, one commit, prints rollback text; `## CSV Format` appears before `## Current Focus` in `AGENTS.md`.

**Skip / note:** apply on OneDrive-synced trees may be unreliable — use a local temp path.

---

### 6) R6 — Continuous

```powershell
cd c:\Users\simon\cursor\SJW_skills\prompt-structure-auditor\scripts
$env:PYTHONPATH = (Get-Location).Path
python -m psa baseline save .\tests\fixtures\empty_repo --out empty.json
python -m psa diff .\tests\fixtures\vr3_demo --baseline empty.json
python -m psa diff .\tests\fixtures\vr3_demo --baseline empty.json --fail-on-introduced
echo $LASTEXITCODE   # expect 1
```

**Pass if:** Introduced > 0; `--fail-on-introduced` exits 1; no quality score in output.

**CI:** after push, `.github/workflows/psa.yml` should run pytest + CLI smoke.

---

## Skill smoke (Cursor)

1. `/prompt-structure-auditor` → `audit` health view; offer `doctor` if discovery is unclear; **does not apply** unless asked.  
2. `/prompt-structure-auditor doctor` → discovery diagnostics.  
3. `/prompt-structure-auditor preview ORDER001` → diff only.  
4. `/prompt-structure-auditor validate ORDER001` → PASS/FAIL summary.  
5. `/prompt-structure-auditor apply ORDER001` → only with explicit user confirm; agent uses `--yes`.  
6. `/prompt-structure-auditor baseline` / `diff` → save + compare.  
