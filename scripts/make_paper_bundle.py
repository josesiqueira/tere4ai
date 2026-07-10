"""Assemble the reviewer-facing paper artifact bundle (#67).

@implements: DEC-11 (partial: paper artifact bundle)
@grounded_by: REF-15

Usage:
  .venv/bin/python scripts/make_paper_bundle.py [--out dist]

Collects everything a paper reviewer needs to check the claims into one
versioned tarball: the generated figures and tables, the analysis reports,
the census, the evaluated-config record, and the dump checksums. Everything
in the bundle is a committed, regenerable artifact; the bundle manifest
carries a sha256 for each member so a reviewer can verify integrity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Bundle members: (repo path, required). Optional members are included when
# present and listed as absent in the manifest otherwise, never silently.
MEMBERS: tuple[tuple[str, bool], ...] = (
    ("docs/paper_artifacts/fig_ablation_ladder.png", True),
    ("docs/paper_artifacts/fig_ablation_ladder.svg", True),
    ("docs/paper_artifacts/fig_run1_run2.png", True),
    ("docs/paper_artifacts/fig_run1_run2.svg", True),
    ("docs/paper_artifacts/fig_judge_funnel.png", True),
    ("docs/paper_artifacts/fig_judge_funnel.svg", True),
    ("docs/paper_artifacts/fig_graph_census.png", True),
    ("docs/paper_artifacts/fig_graph_census.svg", True),
    ("docs/paper_artifacts/tab_ablation.tex", True),
    ("docs/paper_artifacts/tab_census.tex", True),
    ("docs/paper_artifacts/tab_judges.tex", True),
    ("docs/paper_artifacts/MANIFEST.json", True),
    ("docs/graph_census.md", True),
    ("docs/norm_dedup_report.md", True),
    ("docs/traceability.md", True),
    ("docs/THESIS_MAP.md", True),
    ("eval/results/RUN2_ANALYSIS.md", True),
    ("eval/results/ELICITATION_ERRORS.md", True),
    ("eval/results/ablation_summary.json", True),
    ("eval/results/ablation_run1_summary.json", True),
    ("eval/config_evaluated.yaml", True),
    ("eval/gold/ANNOTATION_PROTOCOL.md", True),
    ("CHANGELOG.md", True),
    ("data/graph_dumps/build_chain_3982bf3d85d4.json", False),
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _version() -> str:
    try:
        out = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "untagged"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    version = _version()
    included: dict[str, str] = {}
    absent: list[str] = []
    missing_required: list[str] = []
    for rel, required in MEMBERS:
        path = ROOT / rel
        if path.is_file():
            included[rel] = _sha256(path)
        elif required:
            missing_required.append(rel)
        else:
            absent.append(rel)

    if missing_required:
        for rel in missing_required:
            print(f"MISSING required member: {rel}", file=sys.stderr)
        print(
            "regenerate with scripts/make_paper_artifacts.py, "
            "scripts/graph_census.py, scripts/norm_dedup_report.py",
            file=sys.stderr,
        )
        return 1

    manifest = {
        "bundle_version": version,
        "members": included,
        "absent_optional": absent,
    }
    manifest_path = args.out / "BUNDLE_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    tar_path = args.out / f"tere4ai2_paper_bundle_{version}.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        for rel in included:
            tar.add(ROOT / rel, arcname=f"paper_bundle/{rel}")
        tar.add(manifest_path, arcname="paper_bundle/BUNDLE_MANIFEST.json")

    print(f"bundle: {tar_path} ({len(included)} members, version {version})")
    if absent:
        print(f"absent optional members: {', '.join(absent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
