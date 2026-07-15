"""Offline unit tests for section classification + working-file writer."""
from pathlib import Path

import pytest

from tests.credential_probes import (
    ProbeResult,
    classify_section,
    write_working_credentials,
)


@pytest.mark.offline
@pytest.mark.parametrize(
    "name,values,expected",
    [
        ("configuration", {"username": "a", "password": "b"}, "nrdp_portal"),
        (
            "Historical Service Performance (HSP) - API Information",
            {
                "service metrics url": "https://hsp-prod.rockshore.net/api/v1/serviceMetrics",
                "service details url": "https://hsp-prod.rockshore.net/api/v1/serviceDetails",
            },
            "hsp",
        ),
        (
            "Fares, Routeing Guide and Timetable data - API Information",
            {"fares": "https://opendata.nationalrail.co.uk/api/staticfeeds/2.0/fares"},
            "dtd",
        ),
        (
            "Knowledgebase (KB) API - Knowledgebase API Information",
            {"stations": "https://opendata.nationalrail.co.uk/api/staticfeeds/4.0/stations"},
            "kb_api",
        ),
        (
            "Knowledgebase (KB) Real Time Incidents - Knowledgebase Topic Information",
            {"username": "u", "password": "p", "messaging host": "h", "stomp port": "61613"},
            "kb_realtime",
        ),
        (
            "Darwin File Information",
            {"access key": "A", "secret key": "S", "s3 bucket": "b"},
            "darwin_s3",
        ),
        (
            "Darwin FTP Information",
            {"hostname": "h", "username": "u", "password": "p"},
            "darwin_ftp",
        ),
        (
            "Darwin SFTP Information",
            {"hostname": "h", "username": "u", "password": "p", "port": "2222"},
            "darwin_sftp",
        ),
        (
            "Darwin Topic Information",
            {"username": "u", "password": "p", "messaging host": "h", "stomp port": "61613"},
            "darwin_topic",
        ),
    ],
)
def test_classify_section(name, values, expected):
    assert classify_section(name, values) == expected


@pytest.mark.offline
def test_write_working_credentials_omits_failures(tmp_path):
    results = [
        ProbeResult(
            "nrdp_portal", "configuration", True, "ok",
            {"username": "a@example.com", "password": "secret"},
        ),
        ProbeResult("hsp", "Historical Service Performance (HSP) - API Information", True, "ok", {
            "username": "a@example.com",
            "password": "secret",
            "service metrics url": "https://hsp-prod.rockshore.net/api/v1/serviceMetrics",
            "service details url": "https://hsp-prod.rockshore.net/api/v1/serviceDetails",
        }),
        ProbeResult("darwin_ftp", "Darwin FTP Information", False, "nope", {
            "username": "ftpuser", "password": "x",
        }),
    ]
    dest = tmp_path / "workingConfig.txt"
    write_working_credentials(results, dest)
    text = dest.read_text(encoding="utf-8")
    assert "[configuration]" in text
    assert "Historical Service Performance" in text
    assert "Darwin FTP" not in text
    assert "ftpuser" not in text
