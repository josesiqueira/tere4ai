"""Regression tests for the extraction CLI (the lost-run bug of 2026-07-08)."""

import json

from tere4ai.extract_norms.__main__ import _slug


def test_slug_never_exceeds_filename_limits():
    core = [f"eu-ai-act:article-{n}" for n in [3, 5, 6, 7] + list(range(8, 28)) + [50, 72, 73]]
    core += ["eu-ai-act:annex-iii", "eu-ai-act:annex-iv"]
    slug = _slug(core)
    assert len(f"norms_{slug}.json") < 100, slug
    # stable across calls (hash-based, not order of a set)
    assert slug == _slug(core)
    # distinct node lists give distinct slugs
    assert slug != _slug(core[:-1])


def test_slug_readable_for_small_runs():
    assert _slug(["eu-ai-act:article-9"]).startswith("article-9")


def test_checkpoint_resume_skips_done_groups(tmp_path, monkeypatch):
    """Drive main() with fakes: crash after group 1, resume completes group 2
    without re-calling models for group 1."""
    import tere4ai.extract_norms.__main__ as cli

    fake_dump = {"build": {"build_id": "b"}, "nodes": [], "edges": []}
    dump_path = tmp_path / "layer1.json"
    dump_path.write_text(json.dumps(fake_dump))
    out = tmp_path / "norms_test.json"

    calls: list[str] = []

    def fake_extract(dump, node_ids, generator, judge, prompt_version="v1"):
        calls.append(node_ids[0])
        return {
            "norms": [{"norm_id": f"norm:{node_ids[0]}:n1"}],
            "judge_runs": [],
            "stats": {"source_units": 1, "candidates": 1,
                      "verdicts": {"accepted": 1}, "nodes_failed": [], "invalid_norms": []},
        }

    class FakeCfg:
        def as_public_dict(self):
            return {"generator_model": "g", "judge_model": "j"}

    monkeypatch.setattr(cli, "extract_norms", fake_extract)
    monkeypatch.setattr(cli, "load_model_config", lambda: FakeCfg())
    monkeypatch.setattr(cli, "OpenAIGenerator", lambda cfg: None)
    monkeypatch.setattr(cli, "AnthropicJudge", lambda cfg: None)

    # simulate a prior partial run: group A already checkpointed
    ckpt = out.with_suffix(".checkpoint.jsonl")
    ckpt.write_text(json.dumps({"group": "eu-ai-act:article-9", "result": {
        "norms": [{"norm_id": "norm:eu-ai-act:article-9:n1"}], "judge_runs": [],
        "stats": {"source_units": 1, "candidates": 1, "verdicts": {"accepted": 1},
                  "nodes_failed": [], "invalid_norms": []},
    }}) + "\n")

    rc = cli.main([
        "--nodes", "eu-ai-act:article-9,eu-ai-act:article-10",
        "--dump", str(dump_path), "--out", str(out), "--resume",
    ])
    assert rc == 0
    assert calls == ["eu-ai-act:article-10"], "checkpointed group must not re-run"
    payload = json.loads(out.read_text())
    ids = {n["norm_id"] for n in payload["norms"]}
    assert ids == {"norm:eu-ai-act:article-9:n1", "norm:eu-ai-act:article-10:n1"}
    assert payload["stats"]["source_units"] == 2
    assert not ckpt.exists(), "checkpoint cleaned up after successful final write"
