"""scripts/run_ablations.py never spends past --max-usd, prints a priced plan
with --dry-run, and reads the served build unless a directory is named (DEC-29).
Offline: the fixture of test_run_ablations_record replaces the model clients."""

from __future__ import annotations

import json

import pytest
from tests.unit.test_run_ablations_record import _argv, runner  # noqa: F401

from tere4ai.eval.evaluation_record import EvaluationRecordStore
from tere4ai.graph_store.served_build import Resolution


def _priced(monkeypatch, runner, generator=None, judge=None):  # noqa: F811
    """Price rows for the fixture's two models, USD per million tokens."""
    rows = {"g": generator or {"input": 10.0, "output": 50.0}, "j": judge or {"input": 5.0, "output": 25.0}}
    monkeypatch.setattr(runner, "load_model_prices", lambda: rows)


def _no_client(*_args, **_kwargs):
    raise AssertionError("a model client was built")


def test_max_usd_is_required_and_positive(runner, tmp_path, capsys):  # noqa: F811
    without = [a for a in _argv(tmp_path) if a not in ("--max-usd", "1000")]
    for argv in (without, [*without, "--max-usd", "0"], [*without, "--max-usd", "ten"]):
        with pytest.raises(SystemExit) as stop:
            runner.main(argv)
        assert stop.value.code == 2
    err = capsys.readouterr().err
    assert "--max-usd" in err and "'ten' is not a positive amount in USD" in err


def test_a_dry_run_prints_the_priced_plan_and_calls_nothing(runner, tmp_path, monkeypatch, capsys):  # noqa: F811
    _priced(monkeypatch, runner)
    monkeypatch.setattr(runner, "OpenAIGenerator", _no_client)
    monkeypatch.setattr(runner, "AnthropicJudge", _no_client)

    def gate():
        raise AssertionError("the live gate was asked for")

    monkeypatch.setattr(runner.harness, "_require_live_gate", gate)
    assert runner.main([*_argv(tmp_path), "--dry-run", "--max-usd", "8"]) == 0
    out = capsys.readouterr().out
    assert "dry run, no model call made: 1 unit(s) to run, 2 item answers over 1 condition(s)" in out
    # the fixture's condition calls the generator once per item with no text: 2 calls, 2,200 assumed output tokens
    assert "  generator (g): 2 calls; about 0 input tokens" in out and "2200 output tokens" in out
    assert "at 50.0 USD per million: about 0.1100 USD" in out
    assert "  judge (j): 0 calls;" in out
    assert "total: about 0.1100 USD at list price; ceiling 8.0000 USD" in out
    assert not (tmp_path / "results").exists() and not (tmp_path / "evaluation_records").exists()


def test_a_dry_run_leaves_out_the_units_a_checkpoint_holds(runner, tmp_path, monkeypatch, capsys):  # noqa: F811
    # a run stopped by its ceiling after one of two units, then the plan of its resume
    _priced(monkeypatch, runner, generator={"input": 1_000_000.0, "output": 0.0})
    monkeypatch.setattr(runner, "BATCH_SIZE", 1)
    assert runner.main([*_argv(tmp_path), "--max-usd", "5"]) == 6
    records = tmp_path / "evaluation_records"
    before = sorted(path.name for path in records.iterdir())
    capsys.readouterr()
    assert runner.main([*_argv(tmp_path), "--dry-run"]) == 0
    assert "dry run, no model call made: 1 unit(s) to run, 1 item answers over 1 condition(s)" in capsys.readouterr().out
    assert sorted(path.name for path in records.iterdir()) == before, "a dry run writes no record"


def test_the_run_stops_before_the_unit_that_would_pass_the_ceiling(runner, tmp_path, monkeypatch, capsys):  # noqa: F811
    # each call reports 3 input tokens: 3 USD a unit at this price, one item a unit
    _priced(monkeypatch, runner, generator={"input": 1_000_000.0, "output": 0.0})
    monkeypatch.setattr(runner, "BATCH_SIZE", 1)
    argv = [*_argv(tmp_path), "--max-usd", "5"]
    assert runner.main(argv) == 6
    err = capsys.readouterr().err
    assert "stopped: cost stop: spent 3.0000 USD of 5.0000 USD, with the reserve for the next unit counted" in err
    assert "this run spent 3.0000 USD at list price" in err
    assert "is kept (1 unit(s) done); continue with:" in err
    checkpoint = tmp_path / "results" / "ablation_checkpoint.jsonl"
    assert [json.loads(line)["unit"] for line in checkpoint.read_text().splitlines()] == ["plain_llm:batch0"]
    assert not (tmp_path / "results" / "ablation_summary.json").exists()
    (rec,) = [r for r in EvaluationRecordStore(tmp_path, create=False).list_records() if not r.get("unreadable")]
    assert rec["outcome"]["status"] == "partial" and rec["outcome"]["error"].startswith("cost stop: spent 3.0000")
    assert rec["usage"]["generator"]["calls"] == 1


def test_a_run_under_the_ceiling_prints_its_spend(runner, tmp_path, monkeypatch, capsys):  # noqa: F811
    _priced(monkeypatch, runner, generator={"input": 1_000_000.0, "output": 0.0})
    assert runner.main([*_argv(tmp_path), "--max-usd", "50"]) == 0
    assert "spent 6.0000 USD at list price of 50.0000 USD" in capsys.readouterr().out


def test_a_model_without_a_price_row_refuses_the_run(runner, tmp_path, monkeypatch, capsys):  # noqa: F811
    monkeypatch.setattr(runner, "load_model_prices", lambda: {"g": {"input": 1.0, "output": 1.0}})
    monkeypatch.setattr(runner, "OpenAIGenerator", _no_client)
    for extra in ([], ["--dry-run"]):
        assert runner.main([*_argv(tmp_path), *extra]) == 2
        assert ("refusing to run: config/model_prices.json has no price row for the judge model 'j', so the spend "
                "cannot be known; no model call made") in capsys.readouterr().out
    assert not (tmp_path / "evaluation_records").exists()


def test_without_dump_dir_the_run_reads_the_served_build(runner, tmp_path, monkeypatch, capsys):  # noqa: F811
    asked = []

    def resolve(explicit=None):
        asked.append(explicit)
        return Resolution(tmp_path, "newest", None, None)

    monkeypatch.setattr(runner, "resolve_served", resolve)
    argv = [a for a in _argv(tmp_path) if a not in ("--dump-dir", str(tmp_path))]
    assert runner.main(argv) == 0
    assert asked == [None]
    assert f"build directory: {tmp_path.name} (newest)" in capsys.readouterr().out
    assert EvaluationRecordStore(tmp_path, create=False).list_records(), "the record is written beside the build"

    monkeypatch.setattr(runner, "resolve_served", lambda explicit=None: Resolution(
        tmp_path, "newest", None, "no published build in the builds directory builds"))
    assert runner.main(argv) == 2
    assert ("refusing to run: no build is served: no published build in the builds directory builds"
            in capsys.readouterr().out)


def test_a_named_directory_older_than_the_newest_build_is_said(runner, tmp_path, monkeypatch, capsys):  # noqa: F811
    newer = tmp_path / "2026-10-16-newer"
    monkeypatch.setattr(runner, "resolve_served", lambda explicit=None: Resolution(
        explicit, "explicit", type("B", (), {"dump_dir": newer})(), None))
    assert runner.main(_argv(tmp_path)) == 0
    assert (f"note: the newest published build is 2026-10-16-newer; this run reads {tmp_path.name} because it was "
            "named (explicit)") in capsys.readouterr().out
