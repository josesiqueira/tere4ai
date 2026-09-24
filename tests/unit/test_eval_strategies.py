"""GraphStrategy.models reports the runtime judge's effort (spec F D-F22, B84).

Offline only: stub clients, no model, no network. Pins existing behaviour
(src/tere4ai/eval/strategies.py GraphStrategy.models already read
getattr(self._runtime_judge, "effort", "not configured") before this test
was added); this test only closes the coverage gap the whole-branch review
found (finding G4).
"""

from __future__ import annotations

from tere4ai.eval.strategies import GraphStrategy


class _StubClient:
    """Minimal ModelClient stub: a model id, optionally a learned effort."""

    def __init__(self, model: str, effort: str | None = None):
        self.model = model
        if effort is not None:
            self.effort = effort

    def complete(self, system: str, user: str) -> str:  # pragma: no cover - unused
        return ""


def _strategy(*, runtime_judge=None) -> GraphStrategy:
    return GraphStrategy(
        name="graph_build_judge",
        generator=_StubClient("gpt-6-astra"),
        dump={"nodes": []},
        norms_payload={"norms": []},
        judged_only=False,
        runtime_judge=runtime_judge,
    )


def test_models_reports_the_runtime_judges_effort():
    judge = _StubClient("claude-opus-5-5", effort="xhigh")
    strategy = _strategy(runtime_judge=judge)
    assert strategy.models["judge_effort"] == "xhigh"


def test_models_has_no_judge_effort_key_without_a_runtime_judge():
    strategy = _strategy(runtime_judge=None)
    assert "judge_effort" not in strategy.models
