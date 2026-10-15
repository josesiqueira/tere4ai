"""Re-judging a published build: the generator's stored output judged again by
the judge the environment names, written as a new build (card B173).

@implements: DEC-06 (partial: re-judging stored candidates)
@implements: DEC-07
@implements: DEC-16 (partial: the rejudge executions)
@grounded_by: REF-24, ADD-20

Run as `python -m tere4ai.rejudge <subcommand>`. The source build is read
with plain file reads and never written (source.py); Layer 2 judges every
stored candidate norm again with zero generator calls (norms.py); the list
price of what the rejudge executions spent is summed before each group so a
run stops at a stated limit (cost.py).
"""
