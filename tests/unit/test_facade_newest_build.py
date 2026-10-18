"""B177 (DEC-29): the HTTP facade follows the newest published build while it
runs, keeps one build per request, and says in /api/health what it serves.

Every builds directory here is made in a temporary folder from mock data the
test writes (tests/unit/published_builds.py); no test reads the developer's
.env (the autouse fixture in conftest.py) or any sibling repository."""

from __future__ import annotations

import json
import re
import threading
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from tests.unit.published_builds import publish_build

import tere4ai.http_facade.app as facade
import tere4ai.http_facade.served_state as served_state
from tere4ai.http_facade.served_state import RECHECK_ENV, ServedState, build_recheck_seconds

FIRST = "2026-10-17-model-high"
SECOND = "2026-10-18-model-high"
FIRST_AT = "2026-10-17T12:00:00+00:00"
SECOND_AT = "2026-10-18T12:00:00+00:00"


@pytest.fixture()
def request_log(monkeypatch, tmp_path) -> Path:
    path = tmp_path / "facade_requests.jsonl"
    monkeypatch.setenv(facade.REQUEST_LOG_ENV, str(path))
    return path


def _builds(tmp_path, monkeypatch, recheck: str | None = "0") -> Path:
    builds = tmp_path / "builds"
    builds.mkdir()
    monkeypatch.setenv("TERE4AI_BUILDS_DIR", str(builds))
    if recheck is not None:
        monkeypatch.setenv(RECHECK_ENV, recheck)
    return builds


def _build_id(folder: str, chain_id: str) -> str:
    return f"build-{folder}+chain-{chain_id}"


def _described(folder: str, chain_id: str, published_at: str) -> dict:
    return {"folder": folder, "chain_id": chain_id, "build_id": _build_id(folder, chain_id),
            "published_at": published_at}


def _switch_lines(log: Path) -> list[dict]:
    if not log.is_file():
        return []
    return [line for line in map(json.loads, log.read_text(encoding="utf-8").splitlines())
            if line.get("event") == "served_build_switch"]


def test_the_recheck_setting_defaults_to_thirty_seconds_and_refuses_a_bad_value(monkeypatch):
    assert build_recheck_seconds() == 30
    monkeypatch.setenv(RECHECK_ENV, "0")
    assert build_recheck_seconds() == 0
    monkeypatch.setenv(RECHECK_ENV, "2.5")
    assert build_recheck_seconds() == 2.5
    for bad in ("-1", "soon", "nan", "inf"):
        monkeypatch.setenv(RECHECK_ENV, bad)
        with pytest.raises(ValueError, match=RECHECK_ENV):
            build_recheck_seconds()


def test_a_bad_recheck_value_stops_the_facade_at_start_up(tmp_path, monkeypatch):
    builds = _builds(tmp_path, monkeypatch, recheck="soon")
    publish_build(builds / FIRST, FIRST_AT)
    with pytest.raises(ValueError, match=RECHECK_ENV), TestClient(facade.create_app()):
        pass


def test_a_facade_on_a_builds_directory_serves_the_newest(tmp_path, monkeypatch, request_log):
    builds = _builds(tmp_path, monkeypatch)
    publish_build(builds / FIRST, FIRST_AT)
    second = publish_build(builds / SECOND, SECOND_AT)
    with TestClient(facade.create_app()) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        body = health.json()
        assert body["ok"] is True and body["graph_version"] == _build_id(SECOND, second)
        assert body["served"] == {"source": "newest", **_described(SECOND, second, SECOND_AT)}
        assert body["newest_published"] == _described(SECOND, second, SECOND_AT)
        assert body["served_is_newest"] is True
        assert client.post("/api/classify", json={"features": {}}).status_code == 200
        # audit W4: the build folder by its name only, never a directory path
        assert str(tmp_path) not in health.text
    assert _switch_lines(request_log) == []


def test_a_build_published_while_the_facade_runs_is_served_by_the_next_request(tmp_path, monkeypatch, request_log):
    builds = _builds(tmp_path, monkeypatch)
    first = publish_build(builds / FIRST, FIRST_AT)
    with TestClient(facade.create_app()) as client:
        assert client.get("/api/health").json()["graph_version"] == _build_id(FIRST, first)
        second = publish_build(builds / SECOND, SECOND_AT)
        body = client.get("/api/health").json()
        assert body["graph_version"] == _build_id(SECOND, second)
        assert body["served"]["folder"] == SECOND and body["served_is_newest"] is True
        # the switch is made once: a later request finds nothing newer
        assert client.get("/api/health").json()["graph_version"] == _build_id(SECOND, second)
    switches = _switch_lines(request_log)
    assert len(switches) == 1
    assert {k: v for k, v in switches[0].items() if k != "ts"} == {
        "event": "served_build_switch", "old_chain_id": first, "old_published_at": FIRST_AT,
        "new_chain_id": second, "new_published_at": SECOND_AT}
    assert str(tmp_path) not in request_log.read_text(encoding="utf-8")


def test_the_recheck_waits_its_interval_and_the_health_answer_says_a_newer_build_exists(tmp_path, monkeypatch,
                                                                                         request_log):
    builds = _builds(tmp_path, monkeypatch, recheck="3600")
    first = publish_build(builds / FIRST, FIRST_AT)
    with TestClient(facade.create_app()) as client:
        second = publish_build(builds / SECOND, SECOND_AT)
        body = client.get("/api/health").json()
        assert body["graph_version"] == _build_id(FIRST, first)
        assert body["served"]["folder"] == FIRST
        assert body["newest_published"] == _described(SECOND, second, SECOND_AT)
        assert body["served_is_newest"] is False
    assert _switch_lines(request_log) == []


def test_a_request_in_flight_when_the_switch_happens_answers_from_its_own_build(tmp_path, monkeypatch,
                                                                                 request_log):
    builds = _builds(tmp_path, monkeypatch)
    first = publish_build(builds / FIRST, FIRST_AT)
    app = facade.create_app()
    entered, release = threading.Event(), threading.Event()

    @app.get("/test/held")
    def held(request: Request) -> dict:
        # A handler like every other: it reads the build through the
        # request's snapshot, here only after the switch has happened.
        entered.set()
        assert release.wait(10)
        return {"graph_version": facade._served(request).dump["build"]["build_id"]}

    answers: dict[str, dict] = {}
    with TestClient(app) as client:
        worker = threading.Thread(target=lambda: answers.setdefault("held", client.get("/test/held").json()))
        worker.start()
        assert entered.wait(10)
        second = publish_build(builds / SECOND, SECOND_AT)
        assert client.get("/api/health").json()["graph_version"] == _build_id(SECOND, second)
        release.set()
        worker.join(10)
        assert not worker.is_alive()
        assert answers["held"] == {"graph_version": _build_id(FIRST, first)}
        assert client.get("/test/held").json() == {"graph_version": _build_id(SECOND, second)}


def test_a_second_request_during_a_load_is_served_by_the_old_build_and_starts_no_second_load(tmp_path, monkeypatch,
                                                                                              request_log):
    builds = _builds(tmp_path, monkeypatch)
    first = publish_build(builds / FIRST, FIRST_AT)
    real_load = served_state.load_served_state
    loads: list[str] = []
    loading, finish = threading.Event(), threading.Event()

    def slow_load(resolution):
        # the switch's load (the start-up load is the facade's own call)
        loads.append(resolution.dump_dir.name)
        loading.set()
        assert finish.wait(10)
        return real_load(resolution)

    monkeypatch.setattr(served_state, "load_served_state", slow_load)
    answers: dict[str, str] = {}
    with TestClient(facade.create_app()) as client:
        second = publish_build(builds / SECOND, SECOND_AT)
        worker = threading.Thread(
            target=lambda: answers.setdefault("switching", client.get("/api/health").json()["graph_version"]))
        worker.start()
        assert loading.wait(10)
        # the newer build is loading: this request is not held, and is served
        # by the build that is ready
        assert client.get("/api/health").json()["graph_version"] == _build_id(FIRST, first)
        finish.set()
        worker.join(10)
        assert not worker.is_alive()
        assert answers["switching"] == _build_id(SECOND, second)
        assert client.get("/api/health").json()["graph_version"] == _build_id(SECOND, second)
    assert loads == [SECOND]
    assert len(_switch_lines(request_log)) == 1


def test_a_newer_build_that_fails_verification_is_served_as_its_error_never_the_older_one(tmp_path, monkeypatch,
                                                                                          request_log):
    builds = _builds(tmp_path, monkeypatch)
    publish_build(builds / FIRST, FIRST_AT)
    with TestClient(facade.create_app()) as client:
        assert client.get("/api/health").status_code == 200
        second = publish_build(builds / SECOND, SECOND_AT)
        (builds / SECOND / "norms_core.json").write_text(json.dumps({"norms": [1]}), encoding="utf-8")
        health = client.get("/api/health")
        assert health.status_code == 503
        body = health.json()
        assert body["ok"] is False and "differs" in body["error"] and "norms_core.json" in body["error"]
        assert body["served"] == {"source": "newest", **_described(SECOND, second, SECOND_AT)}
        assert body["newest_published"] == _described(SECOND, second, SECOND_AT)
        # it is the newest; it is broken
        assert body["served_is_newest"] is True
        classify = client.post("/api/classify", json={"features": {}})
        assert classify.status_code == 503 and classify.json() == {"error": body["error"]}
        assert str(tmp_path) not in health.text


def test_a_builds_directory_with_no_published_build_answers_503_naming_its_folder(tmp_path, monkeypatch):
    builds = _builds(tmp_path, monkeypatch)
    with TestClient(facade.create_app()) as client:
        health = client.get("/api/health")
        assert health.status_code == 503
        body = health.json()
        assert body["error"] == "no published build in the builds directory builds"
        assert body["served"] == {"source": "newest", "folder": "builds", "chain_id": None, "build_id": None,
                                  "published_at": None}
        assert body["newest_published"] is None and body["served_is_newest"] is None
        # the first build published is served at the next request
        chain = publish_build(builds / FIRST, FIRST_AT)
        assert client.get("/api/health").json()["graph_version"] == _build_id(FIRST, chain)


def test_the_health_fields_of_an_explicit_published_directory_beside_a_builds_directory(tmp_path, monkeypatch):
    builds = _builds(tmp_path, monkeypatch)
    first = publish_build(builds / FIRST, FIRST_AT)
    second = publish_build(builds / SECOND, SECOND_AT)
    with TestClient(facade.create_app(builds / FIRST)) as client:
        body = client.get("/api/health").json()
    assert body["graph_version"] == _build_id(FIRST, first)
    assert body["served"] == {"source": "explicit", **_described(FIRST, first, FIRST_AT)}
    assert body["newest_published"] == _described(SECOND, second, SECOND_AT)
    assert body["served_is_newest"] is False


def test_a_pinned_directory_is_never_switched_and_says_it_is_not_the_newest(tmp_path, monkeypatch, request_log):
    builds = _builds(tmp_path, monkeypatch)
    first = publish_build(builds / FIRST, FIRST_AT)
    monkeypatch.setenv("TERE4AI_DUMP_DIR", str(builds / FIRST))
    with TestClient(facade.create_app()) as client:
        body = client.get("/api/health").json()
        assert body["served"] == {"source": "pinned", **_described(FIRST, first, FIRST_AT)}
        assert body["served_is_newest"] is True
        second = publish_build(builds / SECOND, SECOND_AT)
        body = client.get("/api/health").json()
        assert body["graph_version"] == _build_id(FIRST, first)
        assert body["newest_published"] == _described(SECOND, second, SECOND_AT)
        assert body["served_is_newest"] is False
    assert _switch_lines(request_log) == []


def test_the_health_fields_of_the_legacy_files_with_no_builds_directory():
    with TestClient(facade.create_app()) as client:
        body = client.get("/api/health").json()
    assert body["served"] == {"source": "default", "folder": facade.DEFAULT_DUMP_DIR.name, "chain_id": None,
                              "build_id": None, "published_at": None}
    assert body["newest_published"] is None and body["served_is_newest"] is None


def test_the_503_answer_of_missing_legacy_files_carries_the_fields(tmp_path):
    with TestClient(facade.create_app(tmp_path / "empty")) as client:
        body = client.get("/api/health").json()
    assert body["ok"] is False and "graph dumps unavailable" in body["error"]
    assert body["served"] == {"source": "explicit", "folder": "empty", "chain_id": None, "build_id": None,
                              "published_at": None}
    assert body["newest_published"] is None and body["served_is_newest"] is None


def test_the_served_state_is_one_frozen_object_per_request(tmp_path, monkeypatch):
    builds = _builds(tmp_path, monkeypatch)
    publish_build(builds / FIRST, FIRST_AT)
    with TestClient(facade.create_app()) as client:
        state = client.app.state.served
        assert isinstance(state, ServedState)
        with pytest.raises(AttributeError):
            state.load_error = "x"  # type: ignore[misc]
        client.app.state.served = replace(state, load_error="graph dumps unavailable: mock")
        assert client.get("/api/health").json()["error"] == "graph dumps unavailable: mock"


def test_no_handler_reads_the_build_through_app_state():
    # One request, one build: a handler reads the build only through the
    # snapshot its request took (_served), never through app.state, where a
    # switch during the request would reach it.
    source = Path(facade.__file__).read_text(encoding="utf-8")
    fields = "dump|norms|alignments|served_source|dump_dir|core_nodes|served_hleg|load_error"
    assert re.findall(rf"app\.state\.(?:{fields})\b", source) == []
