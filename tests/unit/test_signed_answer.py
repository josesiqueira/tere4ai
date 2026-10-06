"""DEC-24 (spec G D-G74 (3), rulings S52, S70, S71): the signed record of a
generator-only answer, its canonical bytes and its HMAC, pinned by the test
vectors shared word for word with the dashboard."""

import copy
import json
import uuid
from pathlib import Path

import pytest

from tere4ai.http_facade import signed
from tere4ai.http_facade.signed import (
    FORMAT,
    RecordError,
    build_record,
    canonical_bytes,
    check_record,
    sign,
    verify,
)

VECTORS = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "signed_answer_vectors.json").read_text(encoding="utf-8"))
KEY = bytes.fromhex(VECTORS["key"])


def _reordered(value):
    """The same value with every object's keys in reverse order, as a jsonb
    store may give them back."""
    if isinstance(value, dict):
        return {key: _reordered(value[key]) for key in reversed(list(value))}
    if isinstance(value, list):
        return [_reordered(item) for item in value]
    return value


@pytest.mark.parametrize("vector", VECTORS["vectors"], ids=lambda v: v["name"])
def test_each_vector_gives_its_bytes_and_its_signature(vector):
    assert canonical_bytes(vector["record"]) == vector["bytes"].encode("utf-8")
    assert sign(vector["record"], KEY) == vector["signature"]
    assert verify(vector["record"], vector["signature"], KEY)


@pytest.mark.parametrize("vector", VECTORS["vectors"], ids=lambda v: v["name"])
def test_a_record_whose_keys_come_back_in_another_order_gives_the_same_bytes(vector):
    assert canonical_bytes(_reordered(vector["record"])) == vector["bytes"].encode("utf-8")


def test_the_bytes_keep_non_ascii_as_utf8_and_have_no_spaces_between_tokens():
    record = VECTORS["vectors"][0]["record"]
    text = canonical_bytes(record).decode("utf-8")
    assert "Gr\xf6\xdfe" in text and "\\u00f6" not in text
    assert text.startswith('{"caller":{"document":')
    assert json.dumps(json.loads(text), sort_keys=True, separators=(",", ":"), ensure_ascii=False) == text


def test_any_change_to_the_record_or_the_signature_does_not_verify():
    vector = VECTORS["vectors"][0]
    for path, value in ((("core", "assessment"), "satisfied"), (("caller", "project"), "another"), (("generation_id",), str(uuid.uuid4())),
                        (("generator_model",), "gpt-6-sol")):
        changed = copy.deepcopy(vector["record"])
        target = changed
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        assert not verify(changed, vector["signature"], KEY), path
    assert not verify(vector["record"], "0" * 64, KEY)
    assert not verify(vector["record"], vector["signature"].upper(), KEY)
    assert not verify(vector["record"], vector["signature"][:-1], KEY)
    assert not verify(vector["record"], vector["signature"], bytes(32))


@pytest.mark.parametrize("change, message", [
    (lambda r: r.pop("judge_prompt"), "exactly the fields"),
    (lambda r: r.update(extra=1), "exactly the fields"),
    (lambda r: r.update(format="tere4ai.signed_answer.v0"), "format"),
    (lambda r: r.update(route="/api/elicit"), "route"),
    (lambda r: r.update(norm_ids=["norm:b", "norm:a"]), "sorted"),
    (lambda r: r["core"].update(assessment=0.5), "floating-point"),
    (lambda r: r["caller"].pop("document"), "caller"),
])
def test_a_record_not_of_this_format_is_refused_and_never_verifies(change, message):
    record = copy.deepcopy(VECTORS["vectors"][0]["record"])
    change(record)
    with pytest.raises(RecordError, match=message):
        check_record(record)
    assert not verify(record, VECTORS["vectors"][0]["signature"], KEY)


def test_a_built_record_draws_a_version_4_generation_id_and_sorts_the_norm_ids():
    record = build_record(route="/api/backlog", caller={"project": "p", "repository_run": "r"}, norm_ids=["b", "a"],
                          graph_version="g", norms_build="n", generator_model="m", generator_prompt={"name": "generate_backlog", "version": "v2"},
                          judge_prompt={"name": "runtime_grounding", "version": "v2"}, untrusted_text="ctx", core={"items": []})
    assert record["format"] == FORMAT and record["norm_ids"] == ["a", "b"] and record["caller"]["document"] is None
    assert uuid.UUID(record["generation_id"]).version == 4
    assert verify(record, sign(record, KEY), KEY)


# Ruling R68 (review I1): wrong kinds and unwritable characters are refused by
# the check and never raise out of verify.
def test_wrong_kinds_and_a_lone_surrogate_are_refused_and_never_raise_out_of_verify():
    record = signed.build_record(route="/api/evidence", caller={"project": "p", "repository_run": "r", "document": "d"}, norm_ids=["n"],
                                 graph_version="g", norms_build="b", generator_model="gpt-gen",
                                 generator_prompt={"name": "evaluate_evidence", "version": "v1"},
                                 judge_prompt={"name": "runtime_grounding", "version": "v1"}, untrusted_text="t",
                                 core={field: None for field in signed.EVIDENCE_CORE_FIELDS})
    key = bytes(range(32))
    signature = signed.sign(record, key)
    for bad in ({**record, "norm_ids": [1, "n"]}, {**record, "route": ["/api/evidence"]}, {**record, "generation_id": 7},
                {**record, "caller": {**record["caller"], "document": 3}}, {**record, "core": {**record["core"], "rationale": "\ud800"}},
                {**record, "judge_prompt": {"name": "runtime_grounding", "version": None}}):
        with pytest.raises(signed.RecordError):
            signed.check_record(bad)
        assert signed.verify(bad, signature, key) is False
    with pytest.raises(signed.RecordError):
        signed.build_record(route="/api/evidence", caller={"project": "p\ud800"}, norm_ids=["n"], graph_version="g", norms_build="b",
                            generator_model="m", generator_prompt={"name": "a", "version": "1"}, judge_prompt={"name": "b", "version": "1"},
                            untrusted_text="t", core={})
