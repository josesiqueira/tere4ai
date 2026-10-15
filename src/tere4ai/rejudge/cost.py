"""The list-price cost of what the rejudge executions spent, and the cost stop.

@implements: DEC-06 (partial: re-judging stored candidates)
@implements: DEC-07
@implements: DEC-16 (partial: the rejudge executions)
@grounded_by: REF-24, ADD-20

B173 R10 (a failure mechanic): before each group or batch the command sums
the cost, at the list prices of config/model_prices.json (USD per million
tokens, every input token at the full input rate, as
scripts/estimate_benchmark_cost.py prices a row), of every rejudge
execution already in the record plus this run's usage so far, and stops
when the sum reaches --cost-stop. The usage is what the inference backends
reported, as the execution record holds it (spec F D-F26 (g)).
"""

from __future__ import annotations

from typing import Any

from tere4ai.judge.config import ConfigurationError

REJUDGE_COMMANDS = ("rejudge_norms", "rejudge_alignments")
TOKENS_PER_PRICE_UNIT = 1_000_000


class CostStop(RuntimeError):
    """The spend reached the stop: the run ends failed with this message."""

    def __init__(self, spent: float, stop: float):
        self.spent, self.stop = spent, stop
        super().__init__(f"cost stop: spent {usd(spent)} USD of {usd(stop)} USD")


def usd(value: float) -> str:
    """A dollar amount as the command prints it: four decimals, so one call's
    spend is not printed as zero."""
    return f"{value:.4f}"


def usage_cost(usage: dict[str, Any] | None, price: dict[str, Any]) -> float:
    """USD at list price of one component's usage: input tokens at the input
    price, output tokens (reasoning included, as billed) at the output price."""
    usage = usage or {}
    return (usage.get("input_tokens", 0) * float(price["input"])
            + usage.get("output_tokens", 0) * float(price["output"])) / TOKENS_PER_PRICE_UNIT


def _tokens(usage: dict[str, Any] | None) -> int:
    usage = usage or {}
    return int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))


def execution_spend(execution: dict[str, Any], prices: dict[str, dict[str, Any]]) -> float:
    """USD at list price of one execution's usage, each component priced at its
    model's row. A component with tokens and no price row is a configuration
    error: the spend cannot be known."""
    total = 0.0
    models = execution.get("models") or {}
    for component, usage in (execution.get("usage") or {}).items():
        if not _tokens(usage):
            continue
        model = models.get(f"{component}_model")
        if model not in prices:
            raise ConfigurationError(f"configuration error: config/model_prices.json has no price row for the "
                                     f"{component} model {model!r} of run {execution.get('run_id')}")
        total += usage_cost(usage, prices[model])
    return total


def record_spend(record: dict[str, Any], prices: dict[str, dict[str, Any]], *, excluding: str | None = None) -> float:
    """USD at list price of every rejudge execution in the record, the run
    excluding (the one in progress, counted from its client) left out."""
    return sum(execution_spend(ex, prices) for ex in record.get("executions", [])
               if ex.get("command") in REJUDGE_COMMANDS and ex.get("run_id") != excluding)
