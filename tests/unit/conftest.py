"""B164 (ruling R9): the unit suite runs the paid terminal commands at one
model call in flight.

Every command's default is tere4ai.parallel_calls.DEFAULT_MAX_IN_FLIGHT (8).
The tests written before B164 pin each command's behaviour with one call at a
time, the behaviour a run at setting 1 keeps byte for byte, and some of their
scripted models answer by call order or by a text two items share; so each
test runs with the default set to 1. B164's own tests pass --max-in-flight or
max_in_flight explicitly, and a test marked default_max_in_flight sees the
shipped default."""

import pytest

from tere4ai import parallel_calls


@pytest.fixture(autouse=True)
def _one_call_in_flight_unless_marked(request, monkeypatch):
    if request.node.get_closest_marker("default_max_in_flight") is None:
        monkeypatch.setattr(parallel_calls, "DEFAULT_MAX_IN_FLIGHT", 1)
