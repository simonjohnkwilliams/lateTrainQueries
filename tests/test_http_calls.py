"""Tests for the two HTTP-touching functions using unittest.mock so that no
real network or filesystem credential lookup happens.

writeServiceMetricsTestData → POST /api/v1/serviceMetrics
writeAttributeMessageTestData → POST /api/v1/serviceDetails
"""
import json
import os
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

import TestFileGenerator as tfg


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mock_response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


# ---------------------------------------------------------------------------
# writeServiceMetricsTestData
# ---------------------------------------------------------------------------
class TestWriteServiceMetricsTestData:
    def test_posts_once_per_day_in_window_and_writes_file(self, tmp_path):
        file_prefix = str(tmp_path / "metrics_")
        payload = {"Services": [{"serviceAttributesMetrics": {"rids": ["abc"]}}]}

        with patch.object(tfg, "getCredentials", return_value=["user", "pw"]), \
             patch.object(tfg.requests, "post", return_value=_mock_response(payload)) as mock_post:
            tfg.writeServiceMetricsTestData(
                "GOD", "WAT", "0600", "1200",
                date(2020, 1, 5), 3, file_prefix,
            )

        # 3 days of data → 3 POSTs.
        assert mock_post.call_count == 3
        # Latest day is the to_date itself, then walking backwards.
        called_dates = [c.kwargs["json"]["from_date"] for c in mock_post.call_args_list]
        assert called_dates == ["2020-01-05", "2020-01-04", "2020-01-03"]

        # Payload shape matches what the Darwin HSP API expects.
        first_call = mock_post.call_args_list[0]
        assert first_call.args[0] == "https://hsp-prod.rockshore.net/api/v1/serviceMetrics"
        assert first_call.kwargs["json"] == {
            "from_loc": "GOD",
            "to_loc": "WAT",
            "from_time": "0600",
            "to_time": "1200",
            "from_date": "2020-01-05",
            "to_date": "2020-01-05",
            "days": "WEEKDAY",
        }
        assert first_call.kwargs["auth"] == ("user", "pw")

        # One file per day was written, named with the date suffix.
        written = sorted(os.listdir(tmp_path))
        assert written == [
            "metrics_2020-01-03.json",
            "metrics_2020-01-04.json",
            "metrics_2020-01-05.json",
        ]
        with open(tmp_path / "metrics_2020-01-05.json") as fh:
            assert json.load(fh) == payload

    def test_skips_post_when_file_already_exists(self, tmp_path):
        file_prefix = str(tmp_path / "metrics_")
        existing = tmp_path / "metrics_2020-01-05.json"
        existing.write_text('{"already": "here"}')

        with patch.object(tfg, "getCredentials", return_value=["u", "p"]), \
             patch.object(tfg.requests, "post") as mock_post:
            tfg.writeServiceMetricsTestData(
                "GOD", "WAT", "0600", "1200",
                date(2020, 1, 5), 1, file_prefix,
            )

        mock_post.assert_not_called()
        # Existing file untouched.
        assert existing.read_text() == '{"already": "here"}'

    def test_http_error_is_swallowed_and_loop_continues(self, tmp_path):
        from requests.exceptions import HTTPError

        file_prefix = str(tmp_path / "metrics_")

        ok = _mock_response({"Services": []})
        bad = MagicMock()
        bad.raise_for_status.side_effect = HTTPError("500 Server Error")

        with patch.object(tfg, "getCredentials", return_value=["u", "p"]), \
             patch.object(tfg.requests, "post", side_effect=[bad, ok]):
            tfg.writeServiceMetricsTestData(
                "GOD", "WAT", "0600", "1200",
                date(2020, 1, 5), 2, file_prefix,
            )

        # First day errored, no file. Second day succeeded.
        written = sorted(os.listdir(tmp_path))
        assert written == ["metrics_2020-01-04.json"]


# ---------------------------------------------------------------------------
# writeAttributeMessageTestData
# ---------------------------------------------------------------------------
class TestWriteAttributeMessageTestData:
    def test_posts_one_serviceDetails_request_per_rid(self, tmp_path):
        file_prefix = str(tmp_path / "service_")
        payload = {"serviceAttributesDetails": {"date_of_service": "2020-01-01",
                                                 "locations": []}}

        with patch.object(tfg, "getCredentials", return_value=["u", "p"]), \
             patch.object(tfg.requests, "post", return_value=_mock_response(payload)) as mock_post:
            tfg.writeAttributeMessageTestData(["rid-a", "rid-b"], file_prefix)

        assert mock_post.call_count == 2
        urls = {c.args[0] for c in mock_post.call_args_list}
        assert urls == {"https://hsp-prod.rockshore.net/api/v1/serviceDetails"}
        rids_sent = [c.kwargs["json"]["rid"] for c in mock_post.call_args_list]
        assert rids_sent == ["rid-a", "rid-b"]

        # Two files: one per rid.
        assert sorted(os.listdir(tmp_path)) == ["service_rid-a.json",
                                                "service_rid-b.json"]

    def test_does_not_re_request_existing_rid_file(self, tmp_path):
        file_prefix = str(tmp_path / "service_")
        (tmp_path / "service_rid-a.json").write_text("{}")

        with patch.object(tfg, "getCredentials", return_value=["u", "p"]), \
             patch.object(tfg.requests, "post",
                          return_value=_mock_response({"x": 1})) as mock_post:
            tfg.writeAttributeMessageTestData(["rid-a", "rid-b"], file_prefix)

        assert mock_post.call_count == 1
        assert mock_post.call_args.kwargs["json"]["rid"] == "rid-b"


# ---------------------------------------------------------------------------
# getCredentials — reads username/password from an INI-style config file
# ---------------------------------------------------------------------------
class TestGetCredentials:
    def test_reads_credentials_from_config_file(self, tmp_path):
        cfg = tmp_path / "trainConfig.txt"
        cfg.write_text(
            "[configuration]\n"
            "username=alice\n"
            "password=hunter2\n"
        )
        assert tfg.getCredentials(str(cfg)) == ["alice", "hunter2"]
