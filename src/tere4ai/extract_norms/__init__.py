"""M2 norm-extraction package: judged deontic extraction over the high-risk core.

@implements: DEC-03, DEC-06 (partial: extraction judge only)
@grounded_by: REF-11, REF-12, REF-13, REF-16, REF-24
"""

from tere4ai.extract_norms.pipeline import expand_source_units, extract_norms

__all__ = ["expand_source_units", "extract_norms"]
