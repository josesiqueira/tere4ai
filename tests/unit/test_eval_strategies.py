"""GraphStrategy.models reports the runtime judge's effort (spec F D-F22, B84).

Offline only: stub clients, no model, no network. Pins existing behaviour
(src/tere4ai/eval/strategies.py GraphStrategy.models already read
getattr(self._runtime_judge, "effort", "not configured") before this test
was added); this test only closes the coverage gap the whole-branch review
found (finding G4).

B99 (spec F D-F29): the models also carry the runtime judge's declared temperature and the generator's declared effort and temperature.
"""

from __future__ import annotations

from tere4ai.eval.strategies import GraphStrategy


class _StubClient:
    """Minimal ModelClient stub: a model id, optionally a declared effort and temperature."""

    def __init__(self, model: str, effort: str | None = None, temperature: str | None = None):
        self.model = model
        if effort is not None:
            self.effort = effort
        if temperature is not None:
            self.temperature = temperature

    def complete(self, system: str, user: str) -> str:  # pragma: no cover - unused
        return ""


def _strategy(*, runtime_judge=None, generator=None) -> GraphStrategy:
    return GraphStrategy(
        name="graph_build_judge",
        generator=generator if generator is not None else _StubClient("gpt-6-astra"),
        dump={"nodes": []},
        norms_payload={"norms": []},
        judged_only=False,
        runtime_judge=runtime_judge,
    )


def test_models_reports_the_runtime_judges_effort():
    judge = _StubClient("claude-opus-5-5", effort="xhigh", temperature="0")
    strategy = _strategy(runtime_judge=judge)
    assert strategy.models["judge_effort"] == "xhigh"
    assert strategy.models["judge_temperature"] == "0"


def test_models_has_no_judge_effort_key_without_a_runtime_judge():
    strategy = _strategy(runtime_judge=None)
    assert "judge_effort" not in strategy.models
    assert "judge_temperature" not in strategy.models


def test_every_strategys_models_carry_the_generators_declared_effort_and_temperature():
    """B99 (spec F D-F29): an evaluation record's per-strategy models state the
    generator's declared values, so the dashboard's models line prints them."""
    from tere4ai.eval.strategies import PlainLLM, VectorRag

    generator = _StubClient("gpt-6-astra", effort="xhigh", temperature="N/A")
    for strategy in (PlainLLM(generator), VectorRag(generator, {"nodes": []}), _strategy(generator=generator)):
        assert (strategy.models["generator_effort"], strategy.models["generator_temperature"]) == ("xhigh", "N/A")
    assert PlainLLM(_StubClient("gpt-6-astra")).models == {
        "generator": "gpt-6-astra", "generator_effort": "not configured", "generator_temperature": "not configured"}
