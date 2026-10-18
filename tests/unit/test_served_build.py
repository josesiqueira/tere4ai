"""B177 (DEC-29): which build tere4ai2 serves, and the MCP server following it.

Every builds directory here is made in a temporary folder from mock data the
test writes; no test reads the developer's .env or any sibling repository."""

from __future__ import annotations

import json
import os
from pathlib import Path

import dotenv
import pytest
from tests.unit.published_builds import publish_build as _publish

import tere4ai.judge.config as config_module
import tere4ai.mcp_server.server as server
from tere4ai.graph_store.publication import ACTIVE_POINTER
from tere4ai.graph_store.served_build import (
    DEFAULT_DUMP_DIR,
    PublishedBuild,
    Resolution,
    newest_published,
    resolve_served,
)


def test_no_variable_serves_the_default_directory():
    resolution = resolve_served()
    assert resolution == Resolution(dump_dir=DEFAULT_DUMP_DIR, source="default", newest=None, error=None)
    assert DEFAULT_DUMP_DIR == Path(server.DUMP_PATH).parent


def test_the_explicit_argument_beats_both_variables(tmp_path, monkeypatch):
    builds = tmp_path / "builds"
    _publish(builds / "2026-10-18-model-high", "2026-10-18T10:00:00+00:00")
    monkeypatch.setenv("TERE4AI_DUMP_DIR", str(tmp_path / "pinned"))
    monkeypatch.setenv("TERE4AI_BUILDS_DIR", str(builds))
    resolution = resolve_served(tmp_path / "explicit")
    assert resolution.dump_dir == tmp_path / "explicit" and resolution.source == "explicit"
    assert resolution.newest is not None and resolution.newest.folder == "2026-10-18-model-high"
    assert resolve_served(str(tmp_path / "explicit")).dump_dir == tmp_path / "explicit"


def test_a_pinned_directory_beats_the_builds_directory_and_newest_is_still_reported(tmp_path, monkeypatch):
    builds = tmp_path / "builds"
    chain_id = _publish(builds / "2026-10-18-model-high", "2026-10-18T10:00:00+00:00")
    monkeypatch.setenv("TERE4AI_DUMP_DIR", str(tmp_path / "pinned"))
    monkeypatch.setenv("TERE4AI_BUILDS_DIR", str(builds))
    resolution = resolve_served()
    assert resolution.dump_dir == tmp_path / "pinned" and resolution.source == "pinned"
    assert resolution.error is None
    assert resolution.newest == PublishedBuild(
        folder="2026-10-18-model-high", dump_dir=builds / "2026-10-18-model-high", chain_id=chain_id,
        build_id=f"build-2026-10-18-model-high+chain-{chain_id}", published_at="2026-10-18T10:00:00+00:00")


def test_an_empty_variable_counts_as_unset(monkeypatch):
    monkeypatch.setenv("TERE4AI_DUMP_DIR", "")
    monkeypatch.setenv("TERE4AI_BUILDS_DIR", "")
    assert resolve_served() == Resolution(dump_dir=DEFAULT_DUMP_DIR, source="default", newest=None, error=None)


def test_the_builds_directory_serves_the_newest_by_published_at_not_by_name_or_mtime(tmp_path, monkeypatch):
    builds = tmp_path / "builds"
    # The name order (z after a) and the write order (z written last) both
    # disagree with the time order: a was published later.
    later = _publish(builds / "a-build", "2026-10-18T09:00:00+02:00")
    _publish(builds / "z-build", "2026-10-18T06:30:00+00:00")
    monkeypatch.setenv("TERE4AI_BUILDS_DIR", str(builds))
    resolution = resolve_served()
    assert resolution.source == "newest" and resolution.error is None
    assert resolution.dump_dir == builds / "a-build"
    assert resolution.newest.folder == "a-build" and resolution.newest.chain_id == later
    assert newest_published(builds) == resolution.newest


def test_a_tie_on_published_at_goes_to_the_greater_folder_name(tmp_path):
    builds = tmp_path / "builds"
    _publish(builds / "2026-10-18-model-high-2", "2026-10-18T10:00:00Z")
    _publish(builds / "2026-10-18-model-high", "2026-10-18T10:00:00+00:00")
    assert newest_published(builds).folder == "2026-10-18-model-high-2"


def test_folders_without_a_usable_pointer_or_manifest_are_skipped(tmp_path):
    builds = tmp_path / "builds"
    _publish(builds / "a-good", "2026-10-01T00:00:00+00:00")
    # no pointer at all: a copied folder never activated
    (builds / "b-no-pointer").mkdir()
    (builds / "b-no-pointer" / "layer1.json").write_text("{}")
    # an unreadable pointer
    _publish(builds / "c-unreadable-pointer", "2026-10-18T00:00:00+00:00")
    (builds / "c-unreadable-pointer" / ACTIVE_POINTER).write_text("{not json")
    # a pointer whose publication manifest is missing
    chain_id = _publish(builds / "d-missing-manifest", "2026-10-18T00:00:00+00:00")
    (builds / "d-missing-manifest" / "publications" / f"{chain_id}.json").unlink()
    # a manifest whose published_at is not an ISO 8601 time
    _publish(builds / "e-bad-time", "t")
    # a file, not a folder
    (builds / "f-file.json").write_text("{}")
    assert newest_published(builds).folder == "a-good"


def test_no_candidate_is_an_error_naming_the_builds_folder_only(tmp_path, monkeypatch):
    builds = tmp_path / "my-builds"
    (builds / "copied").mkdir(parents=True)
    monkeypatch.setenv("TERE4AI_BUILDS_DIR", str(builds))
    resolution = resolve_served()
    assert resolution.source == "newest" and resolution.dump_dir == builds and resolution.newest is None
    assert resolution.error == "no published build in the builds directory my-builds"
    assert str(tmp_path) not in resolution.error
    assert resolution.unreadable is False
    assert newest_published(tmp_path / "absent") is None


def test_the_mcp_server_answers_a_resolution_error_as_a_missing_build(tmp_path, monkeypatch):
    builds = tmp_path / "my-builds"
    builds.mkdir()
    monkeypatch.setenv("TERE4AI_BUILDS_DIR", str(builds))
    report = server.coverage_report()
    assert report["graph_version"] == "unavailable"
    assert report["missing_facts"] == ["no published build in the builds directory my-builds"]


def test_an_mcp_tool_call_follows_a_build_published_after_the_first_call(tmp_path, monkeypatch):
    builds = tmp_path / "builds"
    first = _publish(builds / "2026-10-17-model-high", "2026-10-17T12:00:00+00:00")
    monkeypatch.setenv("TERE4AI_BUILDS_DIR", str(builds))
    assert server.coverage_report()["graph_version"] == f"build-2026-10-17-model-high+chain-{first}"
    second = _publish(builds / "2026-10-18-model-high", "2026-10-18T12:00:00+00:00")
    assert second != first
    assert server.coverage_report()["graph_version"] == f"build-2026-10-18-model-high+chain-{second}"


def test_the_mcp_server_refuses_a_drifted_newest_build_and_never_falls_back(tmp_path, monkeypatch):
    builds = tmp_path / "builds"
    _publish(builds / "2026-10-17-model-high", "2026-10-17T12:00:00+00:00")
    _publish(builds / "2026-10-18-model-high", "2026-10-18T12:00:00+00:00")
    (builds / "2026-10-18-model-high" / "norms_core.json").write_text(json.dumps({"norms": [1]}))
    monkeypatch.setenv("TERE4AI_BUILDS_DIR", str(builds))
    refused = server.coverage_report()
    assert refused["graph_version"] == "unavailable"
    assert "differs" in refused["missing_facts"][0] and "norms_core.json" in refused["missing_facts"][0]


def test_the_startup_check_verifies_the_newest_build(tmp_path, monkeypatch):
    builds = tmp_path / "builds"
    _publish(builds / "2026-10-18-model-high", "2026-10-18T12:00:00+00:00")
    monkeypatch.setenv("TERE4AI_BUILDS_DIR", str(builds))
    monkeypatch.setenv("TERE4AI_MCP_REQUIRE_DUMP_INTEGRITY", "1")
    server._check_dump_integrity_at_startup()
    (builds / "2026-10-18-model-high" / "norms_core.json").write_text(json.dumps({"norms": [1]}))
    with pytest.raises(RuntimeError, match="dump integrity check FAILED: norms file norms_core.json differs"):
        server._check_dump_integrity_at_startup()


def test_a_dotenv_in_the_repository_root_is_not_seen_by_a_test_that_does_not_set_the_variable(tmp_path, monkeypatch):
    # Teardown restores both variables to unset even if a regression let the
    # loader write them, so no later test inherits them.
    for name in ("TERE4AI_BUILDS_DIR", "TERE4AI_DUMP_DIR"):
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)
    builds = tmp_path / "builds"
    _publish(builds / "2026-10-18-model-high", "2026-10-18T12:00:00+00:00")
    root = tmp_path / "repo"
    (root / "src" / "tere4ai" / "judge").mkdir(parents=True)
    dotenv_file = root / ".env"
    dotenv_file.write_text(f"TERE4AI_BUILDS_DIR={builds}\nTERE4AI_DUMP_DIR={builds}\n", encoding="utf-8")
    # The file is a valid .env naming both variables ...
    assert dotenv.dotenv_values(dotenv_file)["TERE4AI_BUILDS_DIR"] == str(builds)
    # ... and load_dotenv_once is pointed at this temporary repository root,
    # as it points at the developer's tere4ai2 root outside a test.
    monkeypatch.setattr(config_module, "__file__", str(root / "src" / "tere4ai" / "judge" / "config.py"))
    config_module.load_dotenv_once()
    assert "TERE4AI_BUILDS_DIR" not in os.environ
    assert "TERE4AI_DUMP_DIR" not in os.environ
    assert resolve_served() == Resolution(dump_dir=DEFAULT_DUMP_DIR, source="default", newest=None, error=None)


def _raising_for(monkeypatch, method: str, folder: Path) -> None:
    """Path.<method> raises PermissionError for folder, as a folder whose
    permissions were removed does (a chmod would not stop a root user)."""
    real = getattr(Path, method)

    def raising(self, *args, **kwargs):
        if self == folder:
            raise PermissionError(13, "Permission denied", str(folder))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, method, raising)


@pytest.mark.parametrize("method", ["iterdir", "is_dir"])
def test_an_unreadable_builds_directory_is_an_error_naming_its_folder_only(tmp_path, monkeypatch, method):
    builds = tmp_path / "my-builds"
    _publish(builds / "2026-10-18-model-high", "2026-10-18T12:00:00+00:00")
    monkeypatch.setenv("TERE4AI_BUILDS_DIR", str(builds))
    _raising_for(monkeypatch, method, builds)
    resolution = resolve_served()
    assert resolution.source == "newest" and resolution.dump_dir == builds and resolution.newest is None
    assert resolution.error.startswith("the builds directory my-builds cannot be read: PermissionError")
    assert resolution.unreadable is True
    assert str(tmp_path) not in resolution.error
    assert newest_published(builds) is None
    # the MCP server answers it as a missing build
    assert server.coverage_report()["missing_facts"] == [resolution.error]


def test_an_unreadable_builds_directory_still_honours_an_explicit_or_pinned_directory(tmp_path, monkeypatch):
    builds = tmp_path / "builds"
    _publish(builds / "2026-10-18-model-high", "2026-10-18T12:00:00+00:00")
    monkeypatch.setenv("TERE4AI_BUILDS_DIR", str(builds))
    _raising_for(monkeypatch, "iterdir", builds)
    assert resolve_served(tmp_path / "explicit") == Resolution(tmp_path / "explicit", "explicit", None, None)
    monkeypatch.setenv("TERE4AI_DUMP_DIR", str(tmp_path / "pinned"))
    assert resolve_served() == Resolution(tmp_path / "pinned", "pinned", None, None)


def test_an_unreadable_subfolder_is_not_a_candidate(tmp_path, monkeypatch):
    builds = tmp_path / "builds"
    _publish(builds / "a-good", "2026-10-01T00:00:00+00:00")
    _publish(builds / "b-unreadable", "2026-10-18T00:00:00+00:00")
    _raising_for(monkeypatch, "is_dir", builds / "b-unreadable")
    assert newest_published(builds).folder == "a-good"


@pytest.mark.parametrize("key", ["chain_id", "build_id"])
@pytest.mark.parametrize("value", [None, 7])
def test_a_manifest_whose_chain_or_build_id_is_no_string_is_not_a_candidate(tmp_path, key, value):
    builds = tmp_path / "builds"
    _publish(builds / "a-good", "2026-10-01T00:00:00+00:00")
    chain_id = _publish(builds / "b-no-id", "2026-10-18T00:00:00+00:00")
    manifest_file = builds / "b-no-id" / "publications" / f"{chain_id}.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if value is None:
        del manifest[key]
    else:
        manifest[key] = value
    manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
    newest = newest_published(builds)
    assert newest.folder == "a-good"
    assert "None" not in (newest.chain_id, newest.build_id)


def test_a_pointer_or_manifest_that_is_not_utf8_is_unreadable(tmp_path):
    from tere4ai.graph_store.publication import load_active

    builds = tmp_path / "builds"
    _publish(builds / "a-good", "2026-10-01T00:00:00+00:00")
    _publish(builds / "b-bad-pointer", "2026-10-18T00:00:00+00:00")
    (builds / "b-bad-pointer" / ACTIVE_POINTER).write_bytes(b'{"chain_id": "\xff\xfe"}')
    chain_id = _publish(builds / "c-bad-manifest", "2026-10-18T00:00:00+00:00")
    (builds / "c-bad-manifest" / "publications" / f"{chain_id}.json").write_bytes(b"\xff\xfe{}")
    assert newest_published(builds).folder == "a-good"
    assert load_active(builds / "b-bad-pointer").error == "the activation pointer is unreadable"
    assert load_active(builds / "c-bad-manifest").error == f"no readable publication manifest for chain {chain_id}"


def test_the_resolver_loads_the_repository_dotenv_outside_a_test(tmp_path, monkeypatch):
    # The production path: the real dotenv loader (the autouse fixture makes
    # it a no-op) and load_dotenv_once pointed at a temporary repository root
    # whose .env names a builds directory. Removing load_dotenv_once from
    # resolve_served fails this test. Teardown restores both variables to
    # unset, whatever the loader wrote.
    for name in ("TERE4AI_BUILDS_DIR", "TERE4AI_DUMP_DIR"):
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)
    builds = tmp_path / "builds"
    _publish(builds / "2026-10-18-model-high", "2026-10-18T12:00:00+00:00")
    root = tmp_path / "repo"
    (root / "src" / "tere4ai" / "judge").mkdir(parents=True)
    (root / ".env").write_text(f"TERE4AI_BUILDS_DIR={builds}\n", encoding="utf-8")
    monkeypatch.setattr(dotenv, "load_dotenv", dotenv.main.load_dotenv)
    monkeypatch.setattr(config_module, "__file__", str(root / "src" / "tere4ai" / "judge" / "config.py"))
    resolution = resolve_served()
    assert resolution.source == "newest" and resolution.newest.folder == "2026-10-18-model-high"


def test_a_resolution_error_is_answered_without_reading_the_builds_directory(tmp_path, monkeypatch):
    builds = tmp_path / "my-builds"
    builds.mkdir()
    monkeypatch.setenv("TERE4AI_BUILDS_DIR", str(builds))

    def no_load(dump_dir):
        raise AssertionError(f"load_active read {Path(dump_dir).name}")

    monkeypatch.setattr(server, "load_active", no_load)
    loaded = server._active()
    assert loaded.error == "no published build in the builds directory my-builds"
    assert loaded.source == "manifest" and loaded.dump is None


_CHILD_RESOLVES = (
    "import sys; import tere4ai.judge.config as c; c.__file__ = sys.argv[1]; "
    "from tere4ai.graph_store.served_build import resolve_served; print(resolve_served().source)"
)


def test_a_server_child_never_reads_the_build_settings_of_the_developer_dotenv(tmp_path):
    # A child process started with server_env (the MCP server of the
    # protocol, duplicate-key and server-docs tests, and gen_server_docs.py)
    # runs the real dotenv loader. Pointed at a temporary repository root
    # whose .env names a builds directory, it serves
    # the default, because server_env sets both variables empty; without
    # those two entries the same child reads the .env.
    import subprocess
    import sys

    from tere4ai.server_docs.session import ROOT, server_env

    builds = tmp_path / "builds"
    _publish(builds / "2026-10-18-model-high", "2026-10-18T12:00:00+00:00")
    root = tmp_path / "repo"
    (root / "src" / "tere4ai" / "judge").mkdir(parents=True)
    (root / ".env").write_text(f"TERE4AI_BUILDS_DIR={builds}\n", encoding="utf-8")
    config_file = str(root / "src" / "tere4ai" / "judge" / "config.py")

    def child_source(env: dict[str, str]) -> str:
        result = subprocess.run([sys.executable, "-c", _CHILD_RESOLVES, config_file], env=env,
                                capture_output=True, text=True, timeout=120, cwd=str(tmp_path))
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    env = server_env(root=ROOT)
    assert env["TERE4AI_BUILDS_DIR"] == "" and env["TERE4AI_DUMP_DIR"] == ""
    assert child_source(env) == "default"
    unpinned = {k: v for k, v in env.items() if k not in ("TERE4AI_BUILDS_DIR", "TERE4AI_DUMP_DIR")}
    assert child_source(unpinned) == "newest"
    # a caller's extra still sets them
    assert server_env({"TERE4AI_BUILDS_DIR": str(builds)}, root=ROOT)["TERE4AI_BUILDS_DIR"] == str(builds)
