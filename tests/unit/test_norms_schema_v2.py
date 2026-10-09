"""B145 (spec G D-G80 (4), (21); brief R47): norms schema version 2, a new
file beside version 1, which is never edited. Version 2 is version 1 with
the addressee's settled names, the enum actParty holding the Act's parties,
and the stored value with its stamp and its outcome."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from tere4ai import act_parties

ROOT = Path(__file__).resolve().parents[2]
V1_PATH = ROOT / "schema" / "json_schemas" / "norms.schema.json"
V2_PATH = ROOT / "schema" / "json_schemas" / "norms.v2.schema.json"
# norms.schema.json at tere4ai2 8440c99: version 1 is the contract of every
# file written before B145 and of every v1 to v4 run (brief R47, R20).
V1_SHA256 = "47c159fd6031b425953910bc811f5a3f6f4a1e1472d82cb7c3ceef228648e0a7"

RENAMES = {
    "actor_explicit": "addressee_explicit",
    "actor_inferred": "addressee_inferred",
    "actor_inference_source_node_id": "addressee_inference_source_node_id",
}


def expected_v2() -> dict:
    """Version 2 as built from version 1; the file must equal this."""
    v1 = json.loads(V1_PATH.read_text(encoding="utf-8"))
    v2 = copy.deepcopy(v1)
    v2["$id"] = "https://tere4ai.org/schema/norms.v2.schema.json"
    v2["title"] = "TERE4AI v2 Layer 2 normative statement, norms schema version 2"
    v2["description"] = v1["description"].replace("actor = Attribute", "addressee = Attribute") + (
        " Version 2 (B145, spec G D-G80 (21)): a norms file that names norms_schema_version 2 at its top level"
        " holds norms in these names; a file without it is version 1 (norms.schema.json)."
    )
    defs = {}
    for key, value in v2["$defs"].items():
        if key == "actorRole":
            defs["actParty"] = {
                "description": "The Act's parties (schema/act_parties.json, DEC-27); never extended ad hoc",
                "enum": list(act_parties.values()),
            }
        else:
            defs[key] = value
    v2["$defs"] = defs
    v2["required"] = [RENAMES.get(k, k) for k in v1["required"]] + ["addressee", "addressee_method", "addressee_placement"]
    props = {}
    for key, value in v1["properties"].items():
        if key == "actor_explicit":
            props["addressee_explicit"] = {"type": ["string", "null"],
                                           "description": "The addressee as the text literally names it, null when absent"}
        elif key == "actor_inferred":
            props["addressee_inferred"] = {"anyOf": [{"$ref": "#/$defs/actParty"}, {"type": "null"}]}
        elif key == "actor_inference_source_node_id":
            props["addressee_inference_source_node_id"] = {
                "type": ["string", "null"],
                "description": "Required when addressee_inferred is set: the node that licenses the inference"}
            props["addressee"] = {"$ref": "#/$defs/actParty",
                                  "description": "The stored value: addressee_inferred, else the written words placed on the Act's parties, else unspecified_needs_review (D-G80 (4))"}
            props["addressee_method"] = {"const": "act_parties_v1"}
            props["addressee_placement"] = {"enum": ["inferred", "placed", "unplaced"]}
        else:
            props[key] = value
    v2["properties"] = props
    v2["allOf"] = [{
        "if": {"properties": {"addressee_inferred": {"type": "string"}}, "required": ["addressee_inferred"]},
        "then": {"properties": {"addressee_inference_source_node_id": {"type": "string", "minLength": 1}},
                 "required": ["addressee_inference_source_node_id"]},
    }]
    return v2


def render_v2() -> str:
    return json.dumps(expected_v2(), ensure_ascii=False, indent=2) + "\n"


def test_version_1_is_never_edited():
    assert hashlib.sha256(V1_PATH.read_bytes()).hexdigest() == V1_SHA256


def test_version_2_is_version_1_in_the_settled_names():
    assert V2_PATH.read_text(encoding="utf-8") == render_v2()


def test_the_enum_is_the_acts_parties():
    v2 = json.loads(V2_PATH.read_text(encoding="utf-8"))
    assert v2["$defs"]["actParty"]["enum"] == list(act_parties.values())
    assert "actorRole" not in v2["$defs"]


def _norm(**over):
    norm = {"norm_id": "norm:eu-ai-act:article-72:paragraph-2:n1", "source_node_id": "eu-ai-act:article-72:paragraph-2",
            "source_span_id": "span:072.002", "deontic_type": "obligation", "modal": "shall",
            "addressee_explicit": None, "addressee_inferred": "provider",
            "addressee_inference_source_node_id": "eu-ai-act:article-72:paragraph-1",
            "addressee": "provider", "addressee_method": "act_parties_v1", "addressee_placement": "inferred",
            "action": "collect, document and analyse", "object": "relevant data", "extraction_method": "llm_extract_v1",
            "extractor_model": "g", "confidence": 0.9, "judge_verdict": "accepted", "review_status": "accepted"}
    norm.update(over)
    return norm


def test_a_version_2_norm_validates_and_version_1_names_do_not():
    validator = Draft202012Validator(json.loads(V2_PATH.read_text(encoding="utf-8")))
    assert list(validator.iter_errors(_norm())) == []
    assert list(validator.iter_errors(_norm(addressee_inferred="chief_officer")))
    assert list(validator.iter_errors(_norm(addressee_inference_source_node_id=None)))
    assert list(validator.iter_errors(_norm(addressee="that system")))
    v1_named = {k: v for k, v in _norm().items() if not k.startswith("addressee")}
    v1_named.update({"actor_explicit": None, "actor_inferred": "provider",
                     "actor_inference_source_node_id": "eu-ai-act:article-72:paragraph-1"})
    assert list(validator.iter_errors(v1_named))
