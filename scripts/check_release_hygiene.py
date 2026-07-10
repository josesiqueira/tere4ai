#!/usr/bin/env python3
"""CI release-hygiene gate: CHANGELOG discipline and license readiness.

@implements: DEC-10 (partial: release hygiene gate)
@grounded_by: REF-27

Checks (stdlib only, exit 1 on failure):
  H1 CHANGELOG.md exists and has at least one "## [<version>]" entry.
  H2 The newest CHANGELOG entry names a version that has a matching git tag
     when tags are available (skipped with a notice in tag-less checkouts,
     e.g. shallow CI clones).
  H3 License readiness: while OPEN-LICENSE (architecture.md Section 15) is
     unresolved, a missing LICENSE file is reported as a NOTICE, never a
     failure. Once a LICENSE file lands, it must be non-empty and every
     release after it must keep it; per-file headers stay out of scope until
     the license decision is made.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ENTRY_RE = re.compile(r"^##\s*\[(?P<version>[^\]]+)\]", re.MULTILINE)


def newest_changelog_version(text: str) -> str | None:
    match = ENTRY_RE.search(text)
    return match.group("version") if match else None


def all_changelog_versions(text: str) -> list[str]:
    return [m.group("version") for m in ENTRY_RE.finditer(text)]


def git_tags(root: Path) -> list[str] | None:
    try:
        out = subprocess.run(
            ["git", "tag", "-l"], cwd=root, capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return [t for t in out.stdout.splitlines() if t.strip()]


def main() -> int:
    failures: list[str] = []
    notices: list[str] = []

    changelog = ROOT / "CHANGELOG.md"
    if not changelog.is_file():
        failures.append("H1 CHANGELOG.md is missing")
        version = None
    else:
        version = newest_changelog_version(changelog.read_text(encoding="utf-8"))
        if version is None:
            failures.append("H1 CHANGELOG.md has no '## [<version>]' entry")

    if version:
        tags = git_tags(ROOT)
        if version.lower() == "unreleased":
            # Keep a Changelog convention: [Unreleased] collects work ahead
            # of the next tag and never has one; H2 applies to the first
            # TAGGED entry below it instead.
            versions = all_changelog_versions(changelog.read_text(encoding="utf-8"))
            tagged = [v for v in versions if v.lower() != "unreleased"]
            version = tagged[0] if tagged else version
        if version.lower() == "unreleased":
            notices.append("H2 skipped: only an [Unreleased] entry exists, no tagged release yet")
            tags = None
        if tags is None or not tags:
            notices.append(
                "H2 skipped: no git tags visible in this checkout "
                "(shallow clone or archive)"
            )
        elif f"v{version}" not in tags and version not in tags:
            failures.append(
                f"H2 newest CHANGELOG entry [{version}] has no matching git tag "
                f"(tags: {', '.join(sorted(tags))})"
            )

    license_file = next(
        (p for p in (ROOT / "LICENSE", ROOT / "LICENSE.md") if p.is_file()), None
    )
    if license_file is None:
        notices.append(
            "H3 notice: no LICENSE file yet (OPEN-LICENSE unresolved, "
            "architecture.md Section 15); decide before public release"
        )
    elif not license_file.read_text(encoding="utf-8").strip():
        failures.append(f"H3 {license_file.name} exists but is empty")

    for notice in notices:
        print(notice)
    if failures:
        print(f"{len(failures)} failure(s):")
        for failure in failures:
            print(f"FAIL {failure}")
        return 1
    print("release hygiene check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
