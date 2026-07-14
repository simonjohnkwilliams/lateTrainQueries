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
    assert cfg.enable_cancellation_fallback is False


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
