"""Regression tests for the alignment CLI checkpointing (same failure class
as the lost 2026-07-08 extraction run)."""

import json


def test_checkpoint_resume_skips_done_batches(tmp_path, monkeypatch):
    import tere4ai.align_hleg_altai.__main__ as cli

    norms = [
        {
            "norm_id": f"norm:eu-ai-act:article-9:paragraph-1:n{i}",
            "source_node_id": "eu-ai-act:article-9:paragraph-1",
            "deontic_type": "obligation",
            "action": "a",
            "object": "o",
            "judge_verdict": "accepted",
            "source_text": "text",
        }
        for i in range(3)
    ]
    norms_path = tmp_path / "norms_test.json"
    norms_path.write_text(json.dumps({"build": {"build_id": "b"}, "norms": norms}))
    layer1 = tmp_path / "layer1.json"
    layer1.write_text(json.dumps({"build": {}, "nodes": [], "edges": []}))
    out = tmp_path / "alignments_test.json"

    aligned_batches: list[int] = []

    def fake_align(chunk, hleg, generator, judge, prompt_version="v1", build_id="adhoc"):
        aligned_batches.append(len(chunk))
        return {
            "assertions": [{"id": f"align:{c['norm_id']}"} for c in chunk],
            "mapping_runs": [{"id": "mr"}],
            "judge_runs": [],
            "stats": {"norms_total": len(chunk), "verdicts": {"accepted": len(chunk)},
                      "mechanical_rejects": []},
        }

    class FakeCfg:
        def as_public_dict(self):
            return {}

    monkeypatch.setattr(cli, "align_norms", fake_align)
    monkeypatch.setattr(cli, "load_model_config", lambda: FakeCfg())
    monkeypatch.setattr(cli, "OpenAIGenerator", lambda cfg: None)
    monkeypatch.setattr(cli, "AnthropicJudge", lambda cfg: None)
    monkeypatch.setattr(cli, "build_hleg_nodes", lambda: [])

    # first batch (size 2) pre-checkpointed; resume must run only the second
    ckpt = out.with_suffix(".checkpoint.jsonl")
    ckpt.write_text(json.dumps({
        "batch": f"batch:0:{norms[0]['norm_id']}",
        "result": {"assertions": [{"id": "align:pre1"}, {"id": "align:pre2"}],
                   "mapping_runs": [], "judge_runs": [],
                   "stats": {"norms_total": 2, "verdicts": {"accepted": 2}}},
    }) + "\n")

    rc = cli.main([
        "--norms", str(norms_path), "--dump", str(layer1),
        "--out", str(out), "--resume", "--batch-size", "2",
    ])
    assert rc == 0
    assert aligned_batches == [1], "only the un-checkpointed batch runs"
    result = json.loads(out.read_text())
    assert len(result["assertions"]) == 3
    assert result["stats"]["norms_total"] == 3
    assert result["stats"]["verdicts"]["accepted"] == 3
    assert not ckpt.exists()
