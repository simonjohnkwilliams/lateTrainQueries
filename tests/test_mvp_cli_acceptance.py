"""MVP CLI acceptance unit checks (offline) — date flags + defaults."""
from datetime import date

import pytest

from trainline import cli


@pytest.mark.offline
def test_default_lookback_is_five_weekdays():
    """AC: bare command = last week of weekday work ending yesterday."""
    days = cli.resolve_run_dates(today=date(2026, 7, 15))
    assert days == [
        "2026-07-08", "2026-07-09", "2026-07-10", "2026-07-13", "2026-07-14",
    ]


@pytest.mark.offline
def test_days_back_alias():
    days = cli.resolve_run_dates(days_back=3, today=date(2026, 7, 15))
    assert len(days) == 3
    assert days[-1] == "2026-07-14"


@pytest.mark.offline
def test_concrete_from_to_inclusive_weekdays_only():
    days = cli.resolve_run_dates(
        from_date="2026-07-07", to_date="2026-07-12", today=date(2026, 7, 15))
    # 7 Tue .. 12 Sun → weekdays 7,8,9,10 (11 Sat 12 Sun skipped)
    assert days == ["2026-07-07", "2026-07-08", "2026-07-09", "2026-07-10"]


@pytest.mark.offline
def test_from_date_alone_runs_through_yesterday():
    days = cli.resolve_run_dates(from_date="2026-07-13", today=date(2026, 7, 15))
    assert days == ["2026-07-13", "2026-07-14"]


@pytest.mark.offline
def test_invalid_date_range_raises():
    with pytest.raises(ValueError, match="from-date"):
        cli.resolve_run_dates(from_date="2026-07-14", to_date="2026-07-10")


@pytest.mark.offline
def test_default_credentials_path_points_at_creds_trainconfig(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "creds").mkdir()
    (tmp_path / "creds" / "trainConfig.txt").write_text("[configuration]\n")
    path = cli._default_credentials_path()
    assert path.replace("\\", "/").endswith("creds/trainConfig.txt")
