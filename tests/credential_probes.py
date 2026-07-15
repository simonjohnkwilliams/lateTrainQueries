"""Live probes for multi-product Open Rail Data credentials.

Classifies each ``## … ##`` / ``[configuration]`` section from
``creds/trainConfig.txt`` by its title and keys, then validates the auth model
documented for that product. Secrets are never logged — only pass/fail + status.

Used by ``tests/test_live_credentials_matrix.py`` (``@live``).
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import hmac
import json
import os
import socket
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from email.utils import format_datetime
from ftplib import FTP, error_perm
from typing import Any
from urllib.parse import quote, urlparse

import requests

from trainline.adapters.config import (
    CredentialsError,
    load_hsp_credentials,
    parse_credentials_file,
)

NRDP_AUTH_URL = "https://opendata.nationalrail.co.uk/authenticate"
TIMEOUT = 30


@dataclass
class ProbeResult:
    product: str
    section: str
    ok: bool
    detail: str
    values_for_working_file: dict[str, str] = field(default_factory=dict)


def _verify():
    return os.environ.get("REQUESTS_CA_BUNDLE") or True


def classify_section(name: str, values: dict[str, str]) -> str | None:
    """Map a section title/keys to a probe product id."""
    n = name.casefold()
    if name.casefold() == "configuration":
        return "nrdp_portal"
    if "historical service performance" in n or n.strip() == "hsp":
        return "hsp"
    if "darwin file" in n or (
        "access key" in values and "secret key" in values and "s3 bucket" in values
    ):
        return "darwin_s3"
    if "darwin sftp" in n:
        return "darwin_sftp"
    if "darwin ftp" in n:
        return "darwin_ftp"
    if "darwin topic" in n:
        return "darwin_topic"
    if "real time" in n and "knowledgebase" in n:
        return "kb_realtime"
    if "knowledgebase" in n and "real time" not in n:
        return "kb_api"
    if any(k in n for k in ("fares", "routeing", "timetable", "dtd")):
        return "dtd"
    # Generic NRDP staticfeed URL bag (fares/stations/…)
    url_keys = [k for k, v in values.items() if v.startswith("https://opendata.nationalrail.co.uk/")]
    if url_keys and "username" not in values:
        if "knowledgebase" in n:
            return "kb_api"
        return "dtd"
    return None


def probe_nrdp_portal(section: str, values: dict[str, str]) -> ProbeResult:
    user, password = values.get("username"), values.get("password")
    if not user or not password:
        return ProbeResult("nrdp_portal", section, False, "missing username/password")
    resp = requests.post(
        NRDP_AUTH_URL,
        data={"username": user, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        verify=_verify(),
        timeout=TIMEOUT,
    )
    if resp.status_code == 401:
        return ProbeResult(
            "nrdp_portal", section, False,
            "NRDP rejected username/password (Invalid username/password)",
        )
    if not resp.ok:
        return ProbeResult(
            "nrdp_portal", section, False,
            f"NRDP authenticate HTTP {resp.status_code}",
        )
    body = resp.json()
    token = body.get("token")
    roles = body.get("roles") or []
    if not token:
        return ProbeResult("nrdp_portal", section, False, "response missing token")
    return ProbeResult(
        "nrdp_portal", section, True,
        f"token issued; roles={roles}",
        {"username": user, "password": password, "_token": token, "_roles": json.dumps(roles)},
    )


def probe_staticfeeds(
    product: str, section: str, values: dict[str, str], token: str | None,
) -> ProbeResult:
    urls = {
        k: v for k, v in values.items()
        if k != "documentation" and isinstance(v, str) and v.startswith("http")
    }
    if not urls:
        return ProbeResult(product, section, False, "no feed URLs in section")
    if not token:
        return ProbeResult(
            product, section, False,
            "skipped — need working NRDP portal token (fix [configuration] first)",
        )
    failures = []
    ok_urls = {}
    for key, url in urls.items():
        resp = requests.get(
            url,
            headers={"X-Auth-Token": token, "Accept": "*/*"},
            verify=_verify(),
            timeout=TIMEOUT,
            allow_redirects=True,
        )
        if resp.status_code == 200 and resp.content:
            ok_urls[key] = url
        else:
            failures.append(f"{key}:{resp.status_code}")
    working = {**ok_urls}
    if "documentation" in values:
        working["documentation"] = values["documentation"]
    if ok_urls and not failures:
        return ProbeResult(product, section, True, f"all {len(ok_urls)} feeds OK", working)
    if ok_urls:
        return ProbeResult(
            product, section, True,
            f"{len(ok_urls)} feeds OK; failed: {failures}",
            working,
        )
    return ProbeResult(product, section, False, f"all feeds failed: {failures}")


def probe_hsp(section: str, values: dict[str, str], portal: dict[str, str] | None) -> ProbeResult:
    try:
        creds = load_hsp_credentials()
    except CredentialsError as exc:
        return ProbeResult("hsp", section, False, str(exc))
    day = date.today() - timedelta(days=3)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    payload = {
        "from_loc": "GOD", "to_loc": "WAT",
        "from_time": "0700", "to_time": "0800",
        "from_date": day.isoformat(), "to_date": day.isoformat(),
        "days": "WEEKDAY",
    }
    resp = requests.post(
        creds.service_metrics_url,
        json=payload,
        auth=(creds.username, creds.password),
        headers={"Content-Type": "application/json"},
        verify=_verify(),
        timeout=TIMEOUT,
    )
    working = {
        "service metrics url": creds.service_metrics_url,
        "service details url": creds.service_details_url,
    }
    if "documentation" in values:
        working["documentation"] = values["documentation"]
    # Prefer recording the auth that HSP actually used
    working["username"] = creds.username
    working["password"] = creds.password
    if resp.status_code == 401:
        return ProbeResult(
            "hsp", section, False,
            "HTTP 401 — portal/HSP username+password rejected (or no HSP subscription)",
        )
    if not resp.ok:
        return ProbeResult("hsp", section, False, f"HTTP {resp.status_code}")
    body = resp.json()
    if "Services" not in body:
        return ProbeResult("hsp", section, False, "JSON missing Services key")
    return ProbeResult(
        "hsp", section, True,
        f"serviceMetrics OK ({len(body.get('Services', []))} services) via {creds.source}",
        working,
    )


def _aws_sign_v4(method, url, access_key, secret_key, region, service="s3"):
    """Minimal AWS SigV4 for a GET with empty body (ListObjects)."""
    parsed = urlparse(url)
    host = parsed.netloc
    canonical_uri = parsed.path or "/"
    canonical_querystring = parsed.query
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(b"").hexdigest()
    canonical_headers = f"host:{host}\nx-amz-content-sha256:{payload_hash}\nx-amz-date:{amz_date}\n"
    signed_headers = "host;x-amz-content-sha256;x-amz-date"
    canonical_request = "\n".join([
        method, canonical_uri, canonical_querystring,
        canonical_headers, signed_headers, payload_hash,
    ])
    credential_scope = f"{datestamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join([
        "AWS4-HMAC-SHA256", amz_date, credential_scope,
        hashlib.sha256(canonical_request.encode()).hexdigest(),
    ])

    def _sign(key, msg):
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    k_date = _sign(("AWS4" + secret_key).encode(), datestamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    k_signing = _sign(k_service, "aws4_request")
    signature = hmac.new(k_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()
    authorization = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return {
        "Host": host,
        "x-amz-date": amz_date,
        "x-amz-content-sha256": payload_hash,
        "Authorization": authorization,
    }


def probe_darwin_s3(section: str, values: dict[str, str]) -> ProbeResult:
    access = values.get("access key")
    secret = values.get("secret key")
    bucket = values.get("s3 bucket")
    prefix = values.get("s3 object prefix", "")
    region = values.get("region", "eu-west-1")
    if not all([access, secret, bucket]):
        return ProbeResult("darwin_s3", section, False, "missing Access Key / Secret Key / S3 Bucket")
    # Path-style URL (virtual-host style often fails under MITM/AVG CA bundles).
    query = f"list-type=2&max-keys=1&prefix={quote(prefix, safe='/')}"
    url = f"https://s3.{region}.amazonaws.com/{bucket}?{query}"
    working = {
        "s3 bucket": bucket,
        "s3 object prefix": prefix,
        "access key": access,
        "secret key": secret,
        "region": region,
    }
    if "documentation" in values:
        working["documentation"] = values["documentation"]
    try:
        headers = _aws_sign_v4("GET", url, access, secret, region)
        resp = requests.get(url, headers=headers, timeout=TIMEOUT, verify=_verify())
    except requests.RequestException as exc:
        return ProbeResult(
            "darwin_s3", section, False,
            f"request error: {type(exc).__name__}: {exc}",
            working,
        )
    if resp.status_code == 200 and b"<ListBucketResult" in resp.content:
        return ProbeResult("darwin_s3", section, True, "S3 ListObjectsV2 OK", working)
    snippet = resp.text[:160].replace("\n", " ")
    return ProbeResult(
        "darwin_s3", section, False,
        f"HTTP {resp.status_code}: {snippet}",
        working,
    )


def probe_ftp(section: str, values: dict[str, str], *, sftp: bool = False) -> ProbeResult:
    product = "darwin_sftp" if sftp else "darwin_ftp"
    host = values.get("hostname")
    user = values.get("username")
    password = values.get("password")
    port = int(values.get("port", "22" if sftp else "21"))
    if not all([host, user, password]):
        return ProbeResult(product, section, False, "missing Hostname/Username/Password")
    working = {
        "hostname": host,
        "username": user,
        "password": password,
    }
    if "port" in values:
        working["port"] = values["port"]
    for k in ("pushport messages directory", "snapshot directory", "documentation"):
        if k in values:
            working[k] = values[k]
    if sftp:
        try:
            import paramiko  # type: ignore
        except ImportError:
            # Connectivity smoke without paramiko: TCP connect only + note.
            try:
                with socket.create_connection((host, port), timeout=TIMEOUT):
                    pass
                return ProbeResult(
                    product, section, False,
                    "TCP port open but paramiko not installed — cannot verify login "
                    "(pip install paramiko to deepen this probe)",
                    working,
                )
            except OSError as exc:
                return ProbeResult(product, section, False, f"TCP connect failed: {exc}")
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(host, port=port, username=user, password=password, timeout=TIMEOUT)
            sftp_client = client.open_sftp()
            sftp_client.listdir(".")
            sftp_client.close()
            return ProbeResult(product, section, True, "SFTP login + listdir OK", working)
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(product, section, False, f"SFTP failed: {type(exc).__name__}")
        finally:
            client.close()

    # FTP (stdlib)
    try:
        with FTP() as ftp:
            ftp.connect(host, port if "port" in values else 21, timeout=TIMEOUT)
            ftp.login(user, password)
            ftp.nlst()
        return ProbeResult(product, section, True, "FTP login + nlst OK", working)
    except error_perm as exc:
        return ProbeResult(product, section, False, f"FTP auth/perm error: {exc}")
    except Exception as exc:  # noqa: BLE001
        return ProbeResult(product, section, False, f"FTP failed: {type(exc).__name__}: {exc}")


def probe_messaging(product: str, section: str, values: dict[str, str]) -> ProbeResult:
    """Validate STOMP/OpenWire endpoint shape; TCP-connect to messaging host."""
    host = values.get("messaging host")
    user = values.get("username")
    password = values.get("password")
    stomp_port = int(values.get("stomp port", "7") or 0)
    if not all([host, user, password, stomp_port]):
        return ProbeResult(
            product, section, False,
            "missing Messaging host / Username / Password / STOMP Port",
        )
    working = {k: values[k] for k in values}
    try:
        with socket.create_connection((host, stomp_port), timeout=TIMEOUT):
            pass
    except OSError as exc:
        return ProbeResult(product, section, False, f"STOMP TCP connect failed: {exc}", working)
    # Full STOMP CONNECT needs stomp.py; without it, TCP+field presence is the smoke.
    try:
        import stomp  # type: ignore
    except ImportError:
        return ProbeResult(
            product, section, True,
            "fields present; STOMP TCP open (install stomp.py to verify LOGIN frame)",
            working,
        )
    conn = stomp.Connection([(host, stomp_port)], heartbeats=(0, 0))
    try:
        conn.connect(user, password, wait=True)
        conn.disconnect()
        return ProbeResult(product, section, True, "STOMP CONNECT OK", working)
    except Exception as exc:  # noqa: BLE001
        return ProbeResult(product, section, False, f"STOMP login failed: {type(exc).__name__}", working)


def run_all_probes(path: str | None = None) -> list[ProbeResult]:
    sections = parse_credentials_file(path)
    results: list[ProbeResult] = []
    portal_token: str | None = None
    portal_values: dict[str, str] | None = None

    # Always probe portal first — token unlocks staticfeeds.
    if "configuration" in sections:
        try:
            r = probe_nrdp_portal("configuration", sections["configuration"])
        except Exception as exc:  # noqa: BLE001
            r = ProbeResult(
                "nrdp_portal", "configuration", False,
                f"probe crashed: {type(exc).__name__}: {exc}",
            )
        results.append(r)
        if r.ok:
            portal_token = r.values_for_working_file.get("_token")
            portal_values = {
                "username": r.values_for_working_file["username"],
                "password": r.values_for_working_file["password"],
            }

    for name, values in sections.items():
        if name == "configuration":
            continue
        product = classify_section(name, values)
        if product is None:
            results.append(ProbeResult("unknown", name, False, "unclassified section — skipped"))
            continue
        if product == "nrdp_portal":
            continue
        try:
            if product == "hsp":
                results.append(probe_hsp(name, values, portal_values))
            elif product in ("dtd", "kb_api"):
                results.append(probe_staticfeeds(product, name, values, portal_token))
            elif product == "darwin_s3":
                results.append(probe_darwin_s3(name, values))
            elif product == "darwin_ftp":
                results.append(probe_ftp(name, values, sftp=False))
            elif product == "darwin_sftp":
                results.append(probe_ftp(name, values, sftp=True))
            elif product in ("darwin_topic", "kb_realtime"):
                results.append(probe_messaging(product, name, values))
            else:
                results.append(ProbeResult(product, name, False, "no probe implemented"))
        except Exception as exc:  # noqa: BLE001 — never abort the matrix on one product
            results.append(ProbeResult(
                product, name, False,
                f"probe crashed: {type(exc).__name__}: {exc}",
            ))
    return results


def write_working_credentials(
    results: list[ProbeResult],
    dest: str | os.PathLike,
    original_sections: dict[str, dict[str, str]] | None = None,
) -> Path:
    """Write only successful sections to ``dest`` (never commit this file)."""
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Auto-generated by tests/credential_probes.py — WORKING credentials only.",
        "# Do not commit. Regenerated by: pytest -m live tests/test_live_credentials_matrix.py",
        "",
    ]
    # Portal first
    for r in results:
        if not r.ok:
            continue
        vals = {k: v for k, v in r.values_for_working_file.items() if not k.startswith("_")}
        if not vals:
            continue
        if r.product == "nrdp_portal" or r.section == "configuration":
            lines.append("[configuration]")
        else:
            lines.append(f"## {r.section} ##")
        # Prefer original key casing via original_sections when available
        original = (original_sections or {}).get(r.section, {})
        # emit with Title Case-ish labels matching common file style where possible
        key_aliases = {
            "username": "Username" if r.product != "nrdp_portal" else "username",
            "password": "Password" if r.product != "nrdp_portal" else "password",
            "access key": "Access Key",
            "secret key": "Secret Key",
            "s3 bucket": "S3 Bucket",
            "s3 object prefix": "S3 Object Prefix",
            "region": "Region",
            "hostname": "Hostname",
            "port": "Port",
            "messaging host": "Messaging host",
            "stomp port": "STOMP Port",
            "openwire port": "OpenWire Port",
            "service metrics url": "Service Metrics URL",
            "service details url": "Service Details URL",
            "documentation": "Documentation",
            "pushport messages directory": "Pushport messages directory",
            "snapshot directory": "Snapshot directory",
            "incidents topic": "Incidents Topic",
            "live feed topic": "Live Feed Topic",
            "status messages topic": "Status Messages Topic",
        }
        for key, value in vals.items():
            label = key_aliases.get(key, key)
            # For feed URL keys keep readable names from original if possible
            if key not in key_aliases and original:
                for ok, ov in original.items():
                    if ok == key:
                        # restore a nicer label from first letters
                        label = " ".join(w.capitalize() for w in key.split())
                        break
            lines.append(f"{label}={value}")
        lines.append("")
    dest_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return dest_path


def results_report(results: list[ProbeResult]) -> dict[str, Any]:
    """JSON-serialisable report with no secret values."""
    return {
        "generated": datetime.now(timezone.utc).isoformat(),
        "results": [
            {
                "product": r.product,
                "section": r.section,
                "ok": r.ok,
                "detail": r.detail,
                "keys_recorded": sorted(
                    k for k in r.values_for_working_file if not k.startswith("_")
                ),
            }
            for r in results
        ],
        "working_count": sum(1 for r in results if r.ok),
        "failed_count": sum(1 for r in results if not r.ok),
    }
