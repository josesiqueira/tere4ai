"""The facade image (B70 task 2): what goes into it and how it runs.

DEC-08 (Section 8 hardening: no server banner, the request log path from
TERE4AI_REQUEST_LOG) and DEC-16 (the served build named by the image).
The Dockerfile and .dockerignore are read as text; the build context rules
are checked with a small matcher that follows Docker's .dockerignore rules
(the last matching line wins, "!" re-includes, "**" spans directories, a
pattern that matches a directory excludes everything under it). The
served build id script runs on mock data in a temporary directory.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "Dockerfile"
DOCKERIGNORE = ROOT / ".dockerignore"
SCRIPT = ROOT / "scripts" / "served_build_id.py"


def _pattern_regex(pattern: str) -> re.Pattern[str]:
    out = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out))


def _rules() -> list[tuple[bool, re.Pattern[str]]]:
    rules = []
    for raw in DOCKERIGNORE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negate = line.startswith("!")
        body = line[1:] if negate else line
        rules.append((negate, _pattern_regex(body.strip("/"))))
    return rules


def _ignored(path: str) -> bool:
    parts = path.split("/")
    prefixes = ["/".join(parts[: n + 1]) for n in range(len(parts))]
    ignored = False
    for negate, regex in _rules():
        if any(regex.fullmatch(p) for p in prefixes):
            ignored = not negate
    return ignored


def _core_stage() -> str:
    text = DOCKERFILE.read_text(encoding="utf-8")
    start = text.index(" AS core")
    end = text.index("\nFROM ", start)
    return text[start:end]


@pytest.mark.parametrize("path", [
    ".env",
    ".env.local",
    "web/.env",
    "web/.env.production",
    ".venv/bin/python",
    "web/node_modules/next/package.json",
    "web/.next/BUILD_ID",
    "src/tere4ai/__pycache__/x.cpython-312.pyc",
    ".pytest_cache/v/cache/lastfailed",
    ".ruff_cache/0.1/x",
    ".git/HEAD",
    ".superpowers/sdd/x.md",
    "graphify-out/graph.json",
    "data/review_queue/facade_requests.jsonl",
    "data/graph_dumps/alignments_core.b74.checkpoint.jsonl",
    "data/graph_dumps/norms_core.writing.json",
    "data/graph_dumps/layer1.building.json",
    "data/graph_dumps/layer23.nt",
    "data/graph_dumps/core.dump",
    "data/graph_dumps/evaluation_records/52ba2c33da35.lock",
    "data/graph_dumps/build_records/x.lock",
    "data/snapshots/benchmark/full_payload.json",
])
def test_the_build_context_leaves_out_secrets_local_state_and_work_files(path):
    assert _ignored(path), f"{path} would enter the image's build context"


@pytest.mark.parametrize("path", [
    # the four served files
    "data/graph_dumps/layer1.json",
    "data/graph_dumps/norms_core.json",
    "data/graph_dumps/alignments_core.json",
    "data/graph_dumps/core_nodes.txt",
    # what load_active and the served build id read
    "data/graph_dumps/BUILD_CHAIN_CURRENT.txt",
    "data/graph_dumps/build_chain_ae11ea6292e3.json",
    "data/graph_dumps/ACTIVE_MANIFEST.json",
    "data/graph_dumps/publications/abc.json",
    # what /api/builds and /api/evaluations read (the Build and Research views)
    "data/graph_dumps/NEO4J_TARGET.json",
    "data/graph_dumps/norms_core.b74.json",
    "data/graph_dumps/build_records/0001.json",
    "data/graph_dumps/evaluation_records/52ba2c33da35.json",
    "data/graph_dumps/evaluation_records/52ba2c33da35/artifact.json",
    "data/graph_dumps/LICENSE",
    "data/snapshots/MANIFEST.json",
    "data/amendments/omnibus_exceptions.json",
    "data/amendments/omnibus_markers.json",
    "docs/omnibus_amendments.md",
    "src/tere4ai/http_facade/app.py",
    "schema/json_schemas/system_features.json",
    "web/package.json",
])
def test_the_build_context_keeps_what_the_image_serves(path):
    assert not _ignored(path), f"{path} is left out of the image's build context"


def test_the_core_command_sends_no_server_header():
    cmd = re.search(r"^CMD \[(.*)\]$", _core_stage(), re.MULTILINE)
    assert cmd is not None
    args = json.loads(f"[{cmd.group(1)}]")
    assert args[:2] == ["uvicorn", "tere4ai.http_facade.app:app"]
    assert "--no-server-header" in args


def test_the_core_command_leaves_the_request_log_path_to_the_environment():
    # the facade reads TERE4AI_REQUEST_LOG; the hosted value (/dev/stdout)
    # is set by the deployment, never baked into the image
    assert not re.search(r"^(ENV|ARG)\b[^\n]*TERE4AI_REQUEST_LOG", _core_stage(), re.MULTILINE)


def test_the_core_image_runs_as_a_non_root_user_in_group_0():
    users = re.findall(r"^USER (\S+)$", _core_stage(), re.MULTILINE)
    assert users, "the core stage sets no USER"
    uid, _, gid = users[-1].partition(":")
    assert uid not in ("0", "root") and uid.isdigit()
    assert gid in ("", "0")


def test_the_request_log_directory_is_writable_by_group_0():
    stage = _core_stage()
    assert re.search(r"chgrp -R 0 [^\n]*data/review_queue", stage)
    assert re.search(r"chmod -R g=u [^\n]*data/review_queue", stage)


def test_the_core_image_is_labelled_with_the_served_build_id_checked_against_the_files():
    stage = _core_stage()
    assert re.search(r"^ARG TERE4AI_SERVED_BUILD_ID=", stage, re.MULTILINE)
    assert re.search(r'^LABEL tere4ai\.served_build_id="\$TERE4AI_SERVED_BUILD_ID"$', stage, re.MULTILINE)
    run = re.search(r"^RUN python scripts/served_build_id\.py [^\n]*\$TERE4AI_SERVED_BUILD_ID", stage, re.MULTILINE)
    assert run is not None
    # the check runs after the dumps are copied in
    assert stage.index("COPY data/graph_dumps") < run.start()


def test_the_image_build_never_rewrites_the_served_dumps():
    # parse_legal_structure stamps a new built_at, so a parse into the served
    # directory changes layer1.json and with it the served chain id (and
    # refuses to run once a publication names the file); the build-time
    # parse check writes into a scratch directory
    stage = _core_stage()
    parses = re.findall(r"python -m tere4ai\.parse_legal_structure([^\n&]*)", stage)
    assert parses, "the build-time Layer 1 check is gone"
    for args in parses:
        dump_dir = re.search(r"--dump-dir (\S+)", args)
        assert dump_dir is not None and "graph_dumps" not in dump_dir.group(1)


def _mock_dump(directory: Path) -> Path:
    directory.mkdir()
    (directory / "layer1.json").write_text(json.dumps({"build": {"build_id": "snap1"}, "nodes": []}))
    (directory / "norms_core.json").write_text(json.dumps({"build": {"build_id": "snap1"}, "norms": []}))
    return directory


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=False)


def test_served_build_id_prints_the_id_the_facade_serves(tmp_path):
    from tere4ai.graph_store.publication import load_active

    dump = _mock_dump(tmp_path / "dumps")
    result = _run("--dump-dir", str(dump))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == load_active(dump).build_id
    assert result.stdout.strip().startswith("snap1+chain-")


def test_served_build_id_accepts_the_matching_expected_id(tmp_path):
    dump = _mock_dump(tmp_path / "dumps")
    served = _run("--dump-dir", str(dump)).stdout.strip()
    result = _run("--dump-dir", str(dump), "--expect", served)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == served


def test_served_build_id_refuses_an_expected_id_the_files_do_not_serve(tmp_path):
    dump = _mock_dump(tmp_path / "dumps")
    result = _run("--dump-dir", str(dump), "--expect", "snap1+chain-000000000000")
    assert result.returncode == 1
    assert "snap1+chain-000000000000" in result.stderr
    assert "serve" in result.stderr


def test_served_build_id_with_an_empty_expected_id_only_prints(tmp_path):
    dump = _mock_dump(tmp_path / "dumps")
    result = _run("--dump-dir", str(dump), "--expect", "")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().startswith("snap1+chain-")


def test_served_build_id_refuses_a_directory_that_serves_no_graph(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = _run("--dump-dir", str(empty))
    assert result.returncode == 1
    assert "layer1.json" in result.stderr


def test_the_image_parse_installs_the_hleg_libraries_and_removes_them_in_the_same_step():
    """B143 (R8): the build-time parse runs the HLEG checks, which need pdfplumber and
    pypdf; the served image does not carry them, so they are installed and removed in
    the one RUN step that parses (a removal in a later step would keep them in a layer)."""
    stage = _core_stage()
    run = next(step for step in re.split(r"\nRUN ", stage) if "python -m tere4ai.parse_legal_structure" in step)
    assert 'pip install --no-cache-dir -e ".[hleg]"' in run
    assert re.search(r"pip uninstall -y pdfplumber pdfminer\.six pypdf pypdfium2", run)
    assert run.index('".[hleg]"') < run.index("parse_legal_structure") < run.index("pip uninstall")


def test_the_core_stage_copies_what_its_parse_reads():
    """R25 (review I5): since B132 the parse reads data/amendments and docs/omnibus_amendments.md
    (parse_legal_structure/amendments.py), which the core stage did not copy, so the image's
    build-time parse failed before B143."""
    stage = _core_stage()
    assert re.search(r"^COPY data/amendments \./data/amendments$", stage, re.MULTILINE)
    assert re.search(r"^COPY docs/omnibus_amendments\.md \./docs/omnibus_amendments\.md$", stage, re.MULTILINE)
