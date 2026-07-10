"""Facade hardening tests (#51): rate limiting and body-free request log.

Section 8 (rate limiting, request logging, secret redaction). The log must
never contain request bodies, because evidence text is sensitive project
data (Section 13 redaction rule).
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import tere4ai.http_facade.app as facade


@pytest.fixture()
def client_with_log(monkeypatch, tmp_path):
    log_path = tmp_path / "facade_requests.jsonl"
    monkeypatch.setenv(facade.REQUEST_LOG_ENV, str(log_path))
    with TestClient(facade.create_app()) as test_client:
        yield test_client, log_path


@pytest.fixture()
def client_rate_limited(monkeypatch, tmp_path):
    monkeypatch.setenv(facade.REQUEST_LOG_ENV, str(tmp_path / "log.jsonl"))
    monkeypatch.setenv(facade.RATE_LIMIT_ENV, "3")
    with TestClient(facade.create_app()) as test_client:
        yield test_client


def test_requests_are_logged_without_bodies(client_with_log):
    client, log_path = client_with_log
    secret_body = {"features": {"description": "SECRET-EVIDENCE-TEXT"}}
    response = client.post("/api/classify", json=secret_body)
    assert response.status_code == 200

    lines = [json.loads(x) for x in log_path.read_text().splitlines()]
    entry = next(e for e in lines if e["path"] == "/api/classify")
    assert entry["method"] == "POST"
    assert entry["status"] == 200
    assert entry["latency_ms"] >= 0
    assert entry["paid"] is False
    # Redaction rule: the body never reaches the log.
    assert "SECRET-EVIDENCE-TEXT" not in log_path.read_text()


def test_rate_limit_returns_429_with_retry_after(client_rate_limited):
    client = client_rate_limited
    codes = [client.get("/api/health").status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200]
    assert 429 in codes[3:]
    over = client.get("/api/health")
    assert over.status_code == 429
    assert "Retry-After" in over.headers
    assert over.json()["limit_per_minute"] == 3


def test_rate_limit_zero_disables(monkeypatch, tmp_path):
    monkeypatch.setenv(facade.REQUEST_LOG_ENV, str(tmp_path / "log.jsonl"))
    monkeypatch.setenv(facade.RATE_LIMIT_ENV, "0")
    with TestClient(facade.create_app()) as client:
        codes = [client.get("/api/health").status_code for _ in range(10)]
    assert codes == [200] * 10


def test_unwritable_log_never_breaks_the_request(monkeypatch, tmp_path):
    # Point the log at a path whose parent is a FILE, so mkdir/open fails.
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv(facade.REQUEST_LOG_ENV, str(blocker / "log.jsonl"))
    with TestClient(facade.create_app()) as client:
        assert client.get("/api/health").status_code == 200
