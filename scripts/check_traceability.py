#!/usr/bin/env python3
"""CI traceability checker for TERE4AI v2.

Implements the convention in docs/architecture.md Section 17: every decision
in Section 16 must be traceable to code via tags in module headers, every
cited REF id must exist in docs/references.md, and docs/traceability.md is
generated from the tags, never hand-written.

Stdlib only. Usage:
    python scripts/check_traceability.py [--root PATH]

Exit codes: 0 on success, 1 on any failure (unknown REF id, unknown DEC id,
expected decision not implemented, a forbidden dash character, or an
absolute home path in tracked sources).

Scans the GIT INDEX, not the filesystem (B55): an untracked local file must
never write rows into docs/traceability.md, because those rows would not
exist on a fresh clone and CI's diff gate would fail. Outside a git checkout
the scan falls back to the filesystem.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# Directories (relative to root) scanned for traceability tags.
TAG_SCAN_DIRS = ("src", "scripts")
# Directories scanned for forbidden dash characters (em dash U+2014,
# en dash U+2013), in .py and .md files.
DASH_SCAN_DIRS = ("src", "scripts", "docs", "tests")
EXCLUDED_DIR_NAMES = {"data", ".venv", "web", ".git", "__pycache__", "node_modules"}

EM_DASH = "\N{EM DASH}"
EN_DASH = "\N{EN DASH}"
FORBIDDEN_DASHES = {EM_DASH: "em dash (U+2014)", EN_DASH: "en dash (U+2013)"}
DASH_RE = re.compile("[" + EN_DASH + EM_DASH + "]")

DEC_ID_RE = re.compile(r"DEC-\d+")
# Reference ids: REF-NN (optionally a letter suffix, e.g. REF-14c), plus the
# SELF-NN (author's own work) and ADD-NN (added literature) namespaces used by
# the authoritative register in references.md.
_REF_ID_ALT = r"(?:REF-\d+[a-z]?|SELF-\d+|ADD-\d+)"
REF_ID_RE = re.compile(_REF_ID_ALT)
# Decision lines in Section 16 of architecture.md.
SECTION16_DEC_RE = re.compile(r"^-\s*(DEC-\d+):", re.MULTILINE)
# Reference definition lines in references.md.
REF_DEF_RE = re.compile(r"^\*\*\[(" + _REF_ID_ALT + r")\]\*\*", re.MULTILINE)
# Tag lines in .py files (docstrings or comments; a line regex is enough).
IMPLEMENTS_LINE_RE = re.compile(r"@implements\s*:\s*(.*)")
GROUNDED_BY_LINE_RE = re.compile(r"@grounded_by\s*:\s*(.*)")
PARTIAL_NOTE_RE = re.compile(r"\(partial:\s*([^)]*)\)")


def tracked_files(root: Path) -> set[str] | None:
    """Relative posix paths in the git index, or None when git is unusable
    (then the filesystem scan stands alone). Untracked files must not enter
    the matrix or the gates (B55)."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return {name for name in out.decode("utf-8").split("\0") if name}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def parse_decision_ids(architecture_md: Path) -> list[str]:
    """Return DEC ids declared in Section 16 of architecture.md."""
    text = read_text(architecture_md)
    match = re.search(r"^##\s*16\..*?$", text, re.MULTILINE)
    if match:
        rest = text[match.end():]
        nxt = re.search(r"^##\s", rest, re.MULTILINE)
        section = rest[: nxt.start()] if nxt else rest
    else:
        # Fall back to the whole file (small fixture repos).
        section = text
    seen: list[str] = []
    for dec in SECTION16_DEC_RE.findall(section):
        if dec not in seen:
            seen.append(dec)
    return seen


def parse_ref_ids(references_md: Path) -> set[str]:
    """Return REF ids defined in references.md."""
    return set(REF_DEF_RE.findall(read_text(references_md)))


def iter_scan_files(
    root: Path,
    dirs: tuple[str, ...],
    suffixes: tuple[str, ...],
    tracked: set[str] | None,
):
    for d in dirs:
        base = root / d
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in suffixes:
                continue
            rel = path.relative_to(root).as_posix()
            if tracked is not None and rel not in tracked:
                continue
            rel_parts = path.relative_to(root).parts
            if any(part in EXCLUDED_DIR_NAMES for part in rel_parts):
                continue
            yield path


def scan_tags(root: Path, tracked: set[str] | None = None) -> list[dict]:
    """Scan .py files under src/ and scripts/ for @implements / @grounded_by.

    Returns one record per file that carries at least one tag with at least
    one id: {path, implements: [(dec_id, partial_note_or_None)], grounded_by:
    [ref ids]}.
    """
    records: list[dict] = []
    for path in iter_scan_files(root, TAG_SCAN_DIRS, (".py",), tracked):
        implements: list[tuple[str, str | None]] = []
        grounded_by: list[str] = []
        for line in read_text(path).splitlines():
            m = IMPLEMENTS_LINE_RE.search(line)
            if m:
                payload = m.group(1)
                pnote = PARTIAL_NOTE_RE.search(payload)
                note = pnote.group(1).strip() if pnote else None
                for dec in DEC_ID_RE.findall(payload):
                    implements.append((dec, note))
            g = GROUNDED_BY_LINE_RE.search(line)
            if g:
                grounded_by.extend(REF_ID_RE.findall(g.group(1)))
        if implements or grounded_by:
            records.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "implements": implements,
                    "grounded_by": grounded_by,
                }
            )
    return records


def discover_tests(
    root: Path, decision_ids: list[str], tracked: set[str] | None = None
) -> dict[str, list[str]]:
    """Best effort: for each DEC id, list test files under tests/ that
    mention it. Empty list when none."""
    tests_by_dec: dict[str, list[str]] = {dec: [] for dec in decision_ids}
    tests_dir = root / "tests"
    if not tests_dir.is_dir():
        return tests_by_dec
    for path in sorted(tests_dir.rglob("*.py")):
        rel_parts = path.relative_to(root).parts
        if any(part in EXCLUDED_DIR_NAMES for part in rel_parts):
            continue
        if tracked is not None and path.relative_to(root).as_posix() not in tracked:
            continue
        text = read_text(path)
        rel = path.relative_to(root).as_posix()
        for dec in decision_ids:
            if re.search(rf"\b{re.escape(dec)}\b", text):
                tests_by_dec[dec].append(rel)
    return tests_by_dec


def scan_dashes(root: Path, tracked: set[str] | None = None) -> list[str]:
    """Return failure messages for forbidden dash characters in .py and .md
    files under the dash-scan directories."""
    failures: list[str] = []
    for path in iter_scan_files(root, DASH_SCAN_DIRS, (".py", ".md"), tracked):
        for lineno, line in enumerate(read_text(path).splitlines(), start=1):
            for char in DASH_RE.findall(line):
                failures.append(
                    f"{path.relative_to(root).as_posix()}:{lineno}: "
                    f"forbidden {FORBIDDEN_DASHES[char]}"
                )
    return failures


ABS_PATH_SCAN_DIRS = ("src", "scripts", "docs")
ABS_HOME_RE = re.compile("(?:/" + "home/|/" + "Users/)")


def scan_abs_paths(root: Path, tracked: set[str] | None = None) -> list[str]:
    """Gate 5 (B53): tracked sources and docs must not hardcode absolute
    home paths; they break every machine but the author's."""
    failures: list[str] = []
    for path in iter_scan_files(root, ABS_PATH_SCAN_DIRS, (".py", ".md"), tracked):
        for lineno, line in enumerate(read_text(path).splitlines(), start=1):
            if ABS_HOME_RE.search(line):
                failures.append(
                    f"{path.relative_to(root).as_posix()}:{lineno}: "
                    "absolute home path"
                )
    return failures


def load_expected(root: Path) -> tuple[list[str], str | None]:
    """Load the expected-decision gate. Returns (expected ids, warning)."""
    config = root / "scripts" / "ci_expected_decisions.json"
    if not config.is_file():
        return [], f"warning: {config.relative_to(root).as_posix()} not found; expected-decision gate skipped"
    data = json.loads(read_text(config))
    return list(data.get("expected", [])), None


def build_matrix(
    decision_ids: list[str],
    tag_records: list[dict],
    tests_by_dec: dict[str, list[str]],
) -> dict[str, dict]:
    matrix: dict[str, dict] = {}
    for dec in decision_ids:
        code_paths: list[str] = []
        refs: list[str] = []
        partial_notes: list[str] = []
        for rec in tag_records:
            hit = [(d, note) for d, note in rec["implements"] if d == dec]
            if not hit:
                continue
            code_paths.append(rec["path"])
            for ref in rec["grounded_by"]:
                if ref not in refs:
                    refs.append(ref)
            for _, note in hit:
                if note:
                    partial_notes.append(note)
        if not code_paths:
            status = "not_started"
        elif partial_notes:
            status = "partial"
        else:
            status = "implemented"
        matrix[dec] = {
            "grounded_by": refs,
            "code_paths": code_paths,
            "test_ids": tests_by_dec.get(dec, []),
            "status": status,
            "partial_notes": partial_notes,
        }
    return matrix


def write_traceability_md(root: Path, matrix: dict[str, dict]) -> Path:
    out = root / "docs" / "traceability.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Traceability matrix",
        "",
        "> GENERATED by scripts/check_traceability.py. Never hand-edit this",
        "> file; it is rebuilt in CI from @implements / @grounded_by tags.",
        "",
        "| decision_id | grounded_by | code_paths | test_ids | status |",
        "| --- | --- | --- | --- | --- |",
    ]
    for dec, row in matrix.items():
        status = row["status"]
        if row["partial_notes"]:
            status += " (" + "; ".join(row["partial_notes"]) + ")"
        lines.append(
            "| {} | {} | {} | {} | {} |".format(
                dec,
                ", ".join(row["grounded_by"]),
                ", ".join(row["code_paths"]),
                ", ".join(row["test_ids"]),
                status,
            )
        )
    lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TERE4AI v2 CI traceability checker")
    default_root = Path(__file__).resolve().parent.parent
    parser.add_argument(
        "--root",
        type=Path,
        default=default_root,
        help="repository root to check (default: the parent of scripts/)",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()

    architecture_md = root / "docs" / "architecture.md"
    references_md = root / "docs" / "references.md"
    for required in (architecture_md, references_md):
        if not required.is_file():
            print(f"FAIL [setup] missing required file: {required}")
            return 1

    decision_ids = parse_decision_ids(architecture_md)
    ref_ids = parse_ref_ids(references_md)
    tracked = tracked_files(root)
    if tracked is None:
        print("WARN [setup] not a git checkout; scanning the filesystem instead")
    tag_records = scan_tags(root, tracked)
    tests_by_dec = discover_tests(root, decision_ids, tracked)
    expected, expected_warning = load_expected(root)

    failures: list[str] = []

    # Gate 1: every cited REF id must exist in references.md.
    for rec in tag_records:
        for ref in rec["grounded_by"]:
            if ref not in ref_ids:
                failures.append(
                    f"FAIL [unknown-ref] {rec['path']}: @grounded_by cites {ref}, "
                    "which is not defined in docs/references.md"
                )

    # Gate 2: every implemented DEC id must exist in Section 16.
    known_decs = set(decision_ids)
    for rec in tag_records:
        for dec, _note in rec["implements"]:
            if dec not in known_decs:
                failures.append(
                    f"FAIL [unknown-dec] {rec['path']}: @implements cites {dec}, "
                    "which is not in docs/architecture.md Section 16"
                )

    # Gate 3: every expected decision must be implemented by at least one tag.
    implemented_decs = {dec for rec in tag_records for dec, _ in rec["implements"]}
    for dec in expected:
        if dec not in implemented_decs:
            failures.append(
                f"FAIL [missing-expected] {dec} is expected at this milestone "
                "(scripts/ci_expected_decisions.json) but has no @implements tag"
            )

    # Gate 4: no em dashes or en dashes in .py or .md files.
    for msg in scan_dashes(root, tracked):
        failures.append(f"FAIL [dash] {msg}")

    # Gate 5: no absolute home paths in tracked sources and docs (B53).
    for msg in scan_abs_paths(root, tracked):
        failures.append(f"FAIL [abs-path] {msg}")

    # Generate the matrix even when gates fail, so the report aids debugging.
    matrix = build_matrix(decision_ids, tag_records, tests_by_dec)
    out_path = write_traceability_md(root, matrix)

    counts = {"implemented": 0, "partial": 0, "not_started": 0}
    for row in matrix.values():
        counts[row["status"]] += 1

    print(f"root: {root}")
    print(
        f"decisions: {len(decision_ids)} "
        f"(implemented {counts['implemented']}, partial {counts['partial']}, "
        f"not_started {counts['not_started']})"
    )
    print(f"references defined: {len(ref_ids)}")
    print(f"tagged files: {len(tag_records)}")
    print(f"expected at this milestone: {len(expected)}")
    print(f"generated: {out_path.relative_to(root).as_posix()}")
    if expected_warning:
        print(expected_warning)

    if failures:
        print(f"\n{len(failures)} failure(s):")
        for msg in failures:
            print(msg)
        return 1
    print("traceability check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
