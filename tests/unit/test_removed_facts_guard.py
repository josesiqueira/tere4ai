"""No tracked file outside the records names a fact the schema refused in B184 (DEC-32, spec G D-G91 (10), ruling R11).

Seven fact names left the features schema in B184: the six broad Annex III
facts and the combined Article 6(3) fact. Records made with the facts of tag
v2.0.0-beta.1 stay as records and are not adapted, and some files name a
removed fact on purpose (a test that it is refused, a script that translates
it). ALLOWED lists each such file with its reason; every other file that git
tracks and that names one of the seven, as a whole word, fails the guard.
gold_seed.json is not a record: its facts were rewritten in the new facts
(B184 task 9), and its classification items must validate against the schema.

@implements: DEC-32
@grounded_by: REF-01
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
GOLD_SEED_PATH = ROOT / "eval" / "gold" / "gold_seed.json"
SCHEMA_PATH = ROOT / "schema" / "json_schemas" / "system_features.schema.json"

REMOVED = ("education_scoring_or_access", "employment_decisions", "essential_services_access", "law_enforcement_use",
           "migration_asylum_border_use", "justice_democratic_use", "preparatory_or_narrow_procedural_task")

_RECORD_OF_THE_TAG = "a record made with the facts of tag v2.0.0-beta.1 (R11: records stay as records)"

# Records of tag v2.0.0-beta.1 and files that name a removed fact by design (DEC-32), each with its reason.
ALLOWED: dict[str, str] = {
    "CHANGELOG.md": "the release notes name the removed facts in B184's entry and keep earlier entries",
    "docs/architecture.md": "the decision record keeps the history of the facts (DEC-18, DEC-32 and earlier entries)",
    "eval/gold/benchmark_features.json": _RECORD_OF_THE_TAG + ": the benchmark sample's facts elicited by prompt v1",
    "eval/gold/benchmark_features_full.json": _RECORD_OF_THE_TAG + ": the full benchmark's facts elicited by prompt v2",
    "eval/gold/draft_candidates.json": _RECORD_OF_THE_TAG + ": the drafts written by scripts/draft_gold_candidates.py",
    "eval/results/ELICITATION_ERRORS.md": _RECORD_OF_THE_TAG + ": the report prints the facts as recorded",
    "eval/results/ablation_checkpoint.jsonl": _RECORD_OF_THE_TAG + ": the checkpoint of ablation run 2",
    "eval/results/ablation_full_checkpoint.jsonl": _RECORD_OF_THE_TAG + ": the checkpoint of the full ablation run",
    "eval/results/ablation_variance_checkpoint.jsonl": _RECORD_OF_THE_TAG + ": the checkpoint of the variance runs",
    **{f"prompts/elicit_features/v{n}.md": "a prompt of record before v9 (v8 is the prompt of the tag)"
       for n in range(1, 9)},
    "scripts/draft_gold_candidates.py": "its candidate tables hold the facts of the tag, the drafting of the "
                                        "record eval/gold/draft_candidates.json; its draft mode refuses at this "
                                        "commit (exit code 2) and is run at the tag",
    "scripts/elicitation_error_report.py": "it reads records made with the facts of the tag and translates the "
                                           "removed facts for its offline re-runs, each translation listed in "
                                           "FACTS_READ_TODAY",
    "tests/fixtures/legacy/moodwatch-prohibited-pre-b118.jsonl": "a recorded session kept as it was recorded "
                                                                 "before B118, a record",
    "tests/unit/flags_of_record.py": "the facts and rule tables of the tag, frozen for the tests of prompts v5 "
                                     "to v8 (ruling P15)",
    "tests/unit/test_removed_facts_guard.py": "this guard names the seven facts",
    "tests/unit/test_listed_uses.py": "it tests that each removed fact is refused by name",
    "tests/unit/test_article_6_3_split.py": "it tests that the combined Article 6(3) fact left the schema",
    "tests/unit/test_fact_entailments.py": "it tests that an input with a removed fact is refused by name",
    "tests/unit/test_elicit_envelope.py": "it tests that a proposed removed fact is not kept and is named in a note",
    "tests/unit/test_http_facade.py": "it tests that the facade's elicitation drops a proposed removed fact "
                                      "with a note",
    "tests/unit/test_elicit_prompt_v9.py": "it tests that a removed fact proposed under prompt v9 is dropped as "
                                           "outside the schema",
    "tests/unit/test_web_copy_honesty.py": "it tests that the demo site's assess page drops a stored removed fact",
    "tests/unit/test_run_ablations_stored_facts.py": "it tests that the ablation harness stops on stored facts that carry a removed fact",
}

_WORD = re.compile(rb"\b(?:" + b"|".join(name.encode() for name in REMOVED) + rb")\b")


def _names_a_removed_fact(path: Path) -> bool:
    """True when the text file names a removed fact as a whole word; a binary file (a NUL byte) never does."""
    if not path.is_file():
        return False
    data = path.read_bytes()
    if b"\0" in data[:8192]:
        return False
    return _WORD.search(data) is not None


def _tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    return [p for p in out.decode("utf-8").split("\0") if p]


def _gold() -> dict:
    return json.loads(GOLD_SEED_PATH.read_text(encoding="utf-8"))


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_no_tracked_file_outside_the_records_names_a_removed_fact():
    offenders = sorted(p for p in _tracked() if p not in ALLOWED and _names_a_removed_fact(ROOT / p))
    assert offenders == []


def test_every_allowed_file_exists():
    """A misspelt path on the list allows nothing; it says nothing about a file that no longer names a removed
    fact, which the next test catches."""
    assert sorted(p for p in ALLOWED if not (ROOT / p).is_file()) == []


def test_every_allowed_file_still_names_a_removed_fact():
    """An allowance whose file no longer names any of the seven facts is stale: its reason is no longer true."""
    assert sorted(p for p in ALLOWED if not _names_a_removed_fact(ROOT / p)) == []


def test_the_guard_finds_a_removed_fact_as_a_whole_word_only(tmp_path):
    named = tmp_path / "named.json"
    named.write_text('{"flags": {"employment_decisions": true}}', encoding="utf-8")
    longer = tmp_path / "longer.txt"
    longer.write_text("employment_decisions_of_record", encoding="utf-8")
    binary = tmp_path / "binary.bin"
    binary.write_bytes(b"\0law_enforcement_use")
    assert _names_a_removed_fact(named)
    assert not _names_a_removed_fact(longer)
    assert not _names_a_removed_fact(binary)


def test_the_gold_seed_classification_items_validate_against_the_schema():
    validator = Draft202012Validator(_schema())
    for item in _gold()["items"]:
        if item["kind"] == "classification":
            assert list(validator.iter_errors(item["system_features"])) == [], item["id"]
