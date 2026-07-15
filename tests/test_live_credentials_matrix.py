"""Live credential matrix — validate every ## product section intelligently.

Opt-in:
  $env:HSP_CREDENTIALS_FILE = (Resolve-Path creds\\trainConfig.txt).Path
  if (Test-Path creds\\ca-bundle.pem) { $env:REQUESTS_CA_BUNDLE = (Resolve-Path creds\\ca-bundle.pem).Path }
  python -m pytest -m live tests/test_live_credentials_matrix.py -v -o addopts= -s

Working credentials (sections that passed) → ``creds/workingConfig.txt`` (gitignored).
Secret-free report → ``live-capture/credential_probe_report.json``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.credential_probes import (
    classify_section,
    results_report,
    run_all_probes,
    write_working_credentials,
)
from trainline.adapters.config import CredentialsError, parse_credentials_file

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKING_FILE = PROJECT_ROOT / "creds" / "workingConfig.txt"
REPORT_FILE = PROJECT_ROOT / "live-capture" / "credential_probe_report.json"


@pytest.fixture(scope="module")
def sections():
    try:
        return parse_credentials_file()
    except CredentialsError as exc:
        pytest.skip(str(exc))


@pytest.fixture(scope="module")
def probe_results(sections):
    results = run_all_probes()
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(json.dumps(results_report(results), indent=2), encoding="utf-8")
    write_working_credentials(results, WORKING_FILE, original_sections=sections)
    for r in results:
        mark = "OK " if r.ok else "FAIL"
        print(f"[{mark}] {r.product:14} | {r.section}: {r.detail}")
    print(f"Report:  {REPORT_FILE}")
    print(f"Working: {WORKING_FILE}")
    return results


@pytest.mark.live
def test_credentials_file_has_classifiable_sections(sections):
    classified = {
        name: classify_section(name, values) for name, values in sections.items()
    }
    assert "configuration" in sections
    assert classified["configuration"] == "nrdp_portal"
    assert any(p == "hsp" for p in classified.values()), "expected an HSP ## section"


@pytest.mark.live
def test_matrix_runs_and_writes_working_file(probe_results):
    """Always completes: writes report + working file for every product that passed."""
    assert REPORT_FILE.is_file()
    assert WORKING_FILE.is_file()
    report = json.loads(REPORT_FILE.read_text(encoding="utf-8"))
    assert report["failed_count"] + report["working_count"] == len(probe_results)
    # At least one non-portal product may still work (e.g. Darwin FTP) even if
    # NRDP portal password is wrong — those land in workingConfig.txt.
    if report["working_count"] == 0:
        pytest.fail(
            "No credential sections validated successfully. "
            f"See {REPORT_FILE}"
        )


def _result(probe_results, product: str):
    return next((r for r in probe_results if r.product == product), None)


@pytest.mark.live
def test_nrdp_portal_credentials(probe_results):
    r = _result(probe_results, "nrdp_portal")
    assert r is not None
    if not r.ok:
        pytest.fail(
            "NRDP [configuration] username/password invalid. "
            "Log in at https://opendata.nationalrail.co.uk/ and update the file. "
            f"Detail: {r.detail}"
        )


@pytest.mark.live
def test_hsp_credentials_mvp_required(probe_results):
    r = _result(probe_results, "hsp")
    assert r is not None
    if not r.ok:
        pytest.fail(
            "HSP is required for the MVP CLI. Uses portal username/password "
            "(or Username/Password under the HSP ## section). "
            f"Detail: {r.detail}"
        )


@pytest.mark.live
@pytest.mark.parametrize("product", [
    "dtd", "kb_api", "kb_realtime",
    "darwin_s3", "darwin_ftp", "darwin_sftp", "darwin_topic",
])
def test_optional_product_credentials(probe_results, product):
    r = _result(probe_results, product)
    if r is None:
        pytest.skip(f"no {product} section in credentials file")
    if not r.ok:
        pytest.xfail(f"{product} not working yet: {r.detail}")
    assert r.ok


@pytest.mark.live
def test_working_file_round_trips_loader_when_hsp_ok(probe_results):
    hsp = _result(probe_results, "hsp")
    if hsp is None or not hsp.ok:
        pytest.skip("HSP not working — working file may still hold other products")
    os.environ["HSP_CREDENTIALS_FILE"] = str(WORKING_FILE)
    from trainline.adapters.config import load_hsp_credentials
    creds = load_hsp_credentials()
    assert creds.username and creds.password
    assert "serviceMetrics" in creds.service_metrics_url
