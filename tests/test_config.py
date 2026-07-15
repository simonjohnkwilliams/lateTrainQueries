"""Story 3.1: config route/window/dates + credential loading (FR16, FR17).

Offline, no network, no real secrets — credential tests use a tmp file, never
the real creds/trainConfig.txt.
"""
import pytest

from trainline.adapters.config import (
    FULL_DAY,
    CredentialsError,
    default_config,
    load_credentials,
    make_config,
)


# --- FR16 defaults + overrides ----------------------------------------------
@pytest.mark.offline
def test_default_config_is_god_wat_full_day():
    cfg = default_config()
    assert cfg.origin == "GOD"
    assert cfg.destination == "WAT"
    assert cfg.outbound_window == FULL_DAY == ("0000", "2359")
    assert cfg.inbound_window == ("0000", "2359")
    assert cfg.lookback_days >= 1
    assert cfg.batch_size >= 1


@pytest.mark.offline
def test_overrides_are_honoured_and_defaults_fall_through():
    cfg = make_config(origin="SUR", outbound_window=("0700", "0930"),
                      lookback_days=3, batch_size=1)
    assert cfg.origin == "SUR"
    assert cfg.destination == "WAT"  # untouched default
    assert cfg.outbound_window == ("0700", "0930")
    assert cfg.lookback_days == 3
    assert cfg.batch_size == 1


@pytest.mark.offline
def test_changing_route_needs_no_code_edit():
    # Everything flows through config — a new route is data, not a code change.
    cfg = make_config(origin="CLJ", destination="VIC")
    assert (cfg.origin, cfg.destination) == ("CLJ", "VIC")


@pytest.mark.offline
def test_unknown_override_raises():
    with pytest.raises(TypeError):
        make_config(from_loc="GOD")  # typo'd field name should not be silently ignored


@pytest.mark.offline
def test_optimiser_flags_present_on_config():
    cfg = default_config()
    assert cfg.per_day_cap is None
    # OQ1 resolved: production config enables the cancellation fallback (AD-6).
    assert cfg.enable_cancellation_fallback is True


# --- FR17 credential loading ------------------------------------------------
def _write_creds(tmp_path, body):
    path = tmp_path / "trainConfig.txt"
    path.write_text(body)
    return str(path)


@pytest.mark.offline
def test_loads_credentials_from_env_path(tmp_path, monkeypatch):
    path = _write_creds(
        tmp_path,
        "[configuration]\nusername=alice\npassword=hunter2\n")
    monkeypatch.setenv("HSP_CREDENTIALS_FILE", path)
    assert load_credentials() == ("alice", "hunter2")


@pytest.mark.offline
def test_loads_credentials_from_explicit_path(tmp_path, monkeypatch):
    monkeypatch.delenv("HSP_CREDENTIALS_FILE", raising=False)
    path = _write_creds(
        tmp_path, "[configuration]\nusername=bob\npassword=s3cret\n")
    assert load_credentials(path) == ("bob", "s3cret")


@pytest.mark.offline
def test_missing_env_var_reports_clearly(monkeypatch):
    monkeypatch.delenv("HSP_CREDENTIALS_FILE", raising=False)
    with pytest.raises(CredentialsError, match="HSP_CREDENTIALS_FILE"):
        load_credentials()


@pytest.mark.offline
def test_missing_file_reports_clearly(tmp_path, monkeypatch):
    monkeypatch.setenv("HSP_CREDENTIALS_FILE", str(tmp_path / "nope.txt"))
    with pytest.raises(CredentialsError, match="not found"):
        load_credentials()


@pytest.mark.offline
def test_malformed_file_missing_section(tmp_path):
    path = _write_creds(tmp_path, "username=alice\npassword=hunter2\n")
    with pytest.raises(CredentialsError, match="configuration"):
        load_credentials(path)


@pytest.mark.offline
def test_malformed_file_missing_keys(tmp_path):
    path = _write_creds(tmp_path, "[configuration]\nusername=alice\n")
    with pytest.raises(CredentialsError):
        load_credentials(path)


@pytest.mark.offline
def test_loads_credentials_ignoring_trailing_non_ini_notes(tmp_path, monkeypatch):
    path = str(tmp_path / "trainConfig.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("[configuration]\nusername=alice\npassword=hunter2\n")
        fh.write("Fares documentation\nhttps://example.invalid/docs\n")
        fh.write("https://example.invalid/other\n")
    monkeypatch.setenv("HSP_CREDENTIALS_FILE", path)
    assert load_credentials() == ("alice", "hunter2")


SAMPLE_MULTI = """[configuration]
username=portal@example.com
password=portal-secret
## Fares, Routeing Guide and Timetable data - API Information ##
Fares=https://opendata.nationalrail.co.uk/api/staticfeeds/2.0/fares
Documentation=https://wiki.openraildata.com/index.php/DTD
## Darwin FTP Information ##
Hostname=darwin-dist.example
Username=ftpuser
Password=ftp-secret
Documentation=https://wiki.openraildata.com/index.php/Darwin:Push_Port
## Historical Service Performance (HSP) - API Information ##
Service Details URL=https://hsp-prod.rockshore.net/api/v1/serviceDetails
Service Metrics URL=https://hsp-prod.rockshore.net/api/v1/serviceMetrics
Documentation=https://wiki.openraildata.com/index.php/HSP
"""


@pytest.mark.offline
def test_hsp_uses_portal_not_darwin_ftp_credentials(tmp_path):
    from trainline.adapters.config import load_hsp_credentials
    path = _write_creds(tmp_path, SAMPLE_MULTI)
    creds = load_hsp_credentials(path)
    assert creds.username == "portal@example.com"
    assert creds.password == "portal-secret"
    assert creds.username != "ftpuser"
    assert creds.service_metrics_url.endswith("/serviceMetrics")
    assert creds.service_details_url.endswith("/serviceDetails")
    assert creds.source == "configuration"


@pytest.mark.offline
def test_hsp_section_username_preferred_when_present(tmp_path):
    from trainline.adapters.config import load_hsp_credentials
    body = """[configuration]
username=portal@example.com
password=portal-secret
## Historical Service Performance (HSP) - API Information ##
Username=hsp-user@example.com
Password=hsp-only-secret
Service Details URL=https://hsp-prod.rockshore.net/api/v1/serviceDetails
Service Metrics URL=https://hsp-prod.rockshore.net/api/v1/serviceMetrics
"""
    path = _write_creds(tmp_path, body)
    creds = load_hsp_credentials(path)
    assert creds.username == "hsp-user@example.com"
    assert creds.password == "hsp-only-secret"
    assert "Historical Service Performance" in creds.source


@pytest.mark.offline
def test_parse_credentials_file_sections(tmp_path):
    from trainline.adapters.config import parse_credentials_file
    path = _write_creds(tmp_path, SAMPLE_MULTI)
    sections = parse_credentials_file(path)
    assert "configuration" in sections
    assert any("Darwin FTP" in k for k in sections)
    assert any("Historical Service Performance" in k for k in sections)
