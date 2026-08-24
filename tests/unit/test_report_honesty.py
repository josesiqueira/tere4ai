"""Honesty gates for the tere4ai.report HTML output.

These tests pin the anti-grading, anti-claim guardrails of the session
report renderer: calibrated vocabulary only, banned claim terms only inside
byte-exact verbatim quotes, mandatory notices that cannot be hidden or
toggled off, no scores, checkmarks, or legal-certification framing.

Markup contract (given to the report author verbatim):
- envelope-carried text sits in elements with data-envelope-field="<name>";
- fields in VERBATIM_QUOTE_FIELDS additionally carry data-verbatim="true";
- status badges are elements with data-status="<one of the 7>";
- sections carry data-section (alignment blocks start with "alignment",
  the matrix is "trace_matrix"); matrix rows carry data-trace-row.
"""

from __future__ import annotations

import inspect
import json
import re
from functools import cache
from html.parser import HTMLParser
from pathlib import Path

import pytest

report = pytest.importorskip("tere4ai.report")

from tere4ai.mcp_server.explain import HLEG_MAPPING_CAVEAT  # noqa: E402
from tere4ai.mcp_server.tools import (  # noqa: E402
    NON_LEGAL_ADVICE_NOTICE,
    STATUS_VOCABULARY,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "demo_sessions"
REPORT_SRC_DIR = REPO_ROOT / "src" / "tere4ai" / "report"

ALL_FIXTURES = (
    "spamguard-classify",
    "moodwatch-prohibited",
    "credscore-highrisk",
    "shopbot-transparency",
)

# Word-boundary, case-insensitive claim terms that may never occur in
# system-generated (non-verbatim) text.
CLAIM_TERM_RES = (
    re.compile(r"\bcompliant\b", re.IGNORECASE),
    re.compile(r"\bcertified\b", re.IGNORECASE),
    re.compile(r"\blegally\s+approved\b", re.IGNORECASE),
)

# Forbidden framing for the document itself.
FRAMING_RES = (
    re.compile(r"\bcompliance\s+report\b", re.IGNORECASE),
    re.compile(r"\bconformity\s+assessment\b", re.IGNORECASE),
    re.compile(r"\bcertificat\w*", re.IGNORECASE),
    re.compile(r"\battestation\b", re.IGNORECASE),
    re.compile(r"\bdeclaration\s+of\s+conformity\b", re.IGNORECASE),
    re.compile(r"\blegal\s+opinion\b", re.IGNORECASE),
    re.compile(r"\baudit\s+report\b", re.IGNORECASE),
)

# Forbidden aggregation phrasing (grading dressed up as prose).
AGGREGATION_RES = (
    re.compile(r"\bcompliance\s+score\b", re.IGNORECASE),
    re.compile(r"\breadiness\s+score\b", re.IGNORECASE),
    re.compile(r"\boverall\s+(?:status|grade)\b", re.IGNORECASE),
    re.compile(r"\bon\s+track\b", re.IGNORECASE),
    re.compile(r"\b(?:grade|graded|rating)\s*:?\s*[A-F][+-]?(?![\w'])", re.IGNORECASE),
)

GRADED_CLASS_RE = re.compile(r"status-(ok|pass|fail|good|bad|green|red|amber)")
GLYPH_RE = re.compile("[✓✔✅❌✗⚠]")
DASH_RE = re.compile("[\u2014\u2013]")  # em dash, en dash
PERCENT_RE = re.compile(r"\d{1,3}\s*%")
STATUS_WORD_RE = re.compile(
    r"\b(status|statuses|satisfied|applicable|traced|untraced|coverage|requirements?)\b",
    re.IGNORECASE,
)
HIDDEN_CSS_RE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.IGNORECASE)

FURNITURE_TOGGLES = {
    "include_notice",
    "show_caveats",
    "clean",
    "executive",
    "minimal",
    "hide_notices",
}

VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}


def _flex(phrase: str) -> re.Pattern[str]:
    """Whitespace-tolerant, case-insensitive matcher for a prose phrase."""
    return re.compile(r"\s+".join(re.escape(w) for w in phrase.split()), re.IGNORECASE)


NOTICE_RE = _flex(NON_LEGAL_ADVICE_NOTICE)
CAVEAT_RE = _flex(HLEG_MAPPING_CAVEAT)
TRACE_CLAIM_RE = _flex("a trace is a developer claim, not evidence")


class ReportScan(HTMLParser):
    """Walks rendered report HTML, splitting text into verbatim and
    non-verbatim buckets and collecting the markup-contract handles."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[dict] = []
        self.doc_text_parts: list[str] = []
        self.doc_len = 0
        self.first_h1_pos: int | None = None
        self.nonverbatim_parts: list[str] = []
        self.verbatim_elements: list[list[str]] = []
        self._open_verbatim: list[int] = []
        self.section_text: dict[str, list[str]] = {}
        self.section_nonverbatim: dict[str, list[str]] = {}
        self._open_sections: list[str] = []
        self.trace_rows: list[list[str]] = []
        self._open_trace_rows: list[int] = []
        self.status_values: list[str] = []
        self.classes: set[str] = set()
        self.style_attrs: list[str] = []
        self.style_css_parts: list[str] = []
        self.title_parts: list[str] = []
        self.tags_seen: set[str] = set()
        self._in_style = 0
        self._in_script = 0
        self._in_title = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: (v if v is not None else "") for k, v in attrs}
        self.tags_seen.add(tag)
        if "class" in a:
            self.classes.update(a["class"].split())
        if "style" in a:
            self.style_attrs.append(a["style"])
        if "data-status" in a:
            self.status_values.append(a["data-status"])
        if tag == "h1" and self.first_h1_pos is None:
            self.first_h1_pos = self.doc_len
        rec = {
            "tag": tag,
            "verbatim": False,
            "section": None,
            "trace": False,
            "style": tag == "style",
            "script": tag == "script",
            "title": tag == "title",
        }
        if a.get("data-verbatim") == "true":
            self.verbatim_elements.append([])
            self._open_verbatim.append(len(self.verbatim_elements) - 1)
            rec["verbatim"] = True
        sec = a.get("data-section")
        if sec:
            self.section_text.setdefault(sec, [])
            self.section_nonverbatim.setdefault(sec, [])
            self._open_sections.append(sec)
            rec["section"] = sec
        if "data-trace-row" in a:
            self.trace_rows.append([])
            self._open_trace_rows.append(len(self.trace_rows) - 1)
            rec["trace"] = True
        if rec["style"]:
            self._in_style += 1
        if rec["script"]:
            self._in_script += 1
        if rec["title"]:
            self._in_title += 1
        if tag not in VOID_TAGS:
            self.stack.append(rec)
        elif rec["verbatim"] or rec["section"] or rec["trace"]:
            self._close(rec)  # a void tag cannot hold children

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID_TAGS:
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i]["tag"] == tag:
                for rec in reversed(self.stack[i:]):
                    self._close(rec)
                del self.stack[i:]
                return

    def _close(self, rec: dict) -> None:
        if rec["verbatim"] and self._open_verbatim:
            self._open_verbatim.pop()
        if rec["section"] and self._open_sections:
            self._open_sections.pop()
        if rec["trace"] and self._open_trace_rows:
            self._open_trace_rows.pop()
        if rec["style"]:
            self._in_style -= 1
        if rec["script"]:
            self._in_script -= 1
        if rec["title"]:
            self._in_title -= 1

    def handle_data(self, data: str) -> None:
        if self._in_style:
            self.style_css_parts.append(data)
            return
        if self._in_script:
            return
        if self._in_title:
            self.title_parts.append(data)
            self.nonverbatim_parts.append(data)
            return
        self.doc_text_parts.append(data)
        self.doc_len += len(data)
        if self._open_verbatim:
            for idx in self._open_verbatim:
                self.verbatim_elements[idx].append(data)
        else:
            self.nonverbatim_parts.append(data)
        for sec in set(self._open_sections):
            self.section_text[sec].append(data)
            if not self._open_verbatim:
                self.section_nonverbatim[sec].append(data)
        for idx in self._open_trace_rows:
            self.trace_rows[idx].append(data)

    # Convenience views -------------------------------------------------
    @property
    def doc_text(self) -> str:
        return "".join(self.doc_text_parts)

    @property
    def nonverbatim_text(self) -> str:
        return " ".join(self.nonverbatim_parts)

    @property
    def title_text(self) -> str:
        return re.sub(r"\s+", " ", "".join(self.title_parts)).strip()

    @property
    def css_text(self) -> str:
        return "".join(self.style_css_parts)

    def verbatim_texts(self) -> list[str]:
        return ["".join(parts) for parts in self.verbatim_elements]

    def section(self, name: str) -> str:
        return "".join(self.section_text.get(name, []))

    def css_rules(self) -> list[tuple[str, str]]:
        """Naive (selector, body) pairs from all <style> blocks."""
        rules: list[tuple[str, str]] = []
        css = re.sub(r"/\*.*?\*/", " ", self.css_text, flags=re.DOTALL)
        for chunk in css.split("}"):
            selector, sep, body = chunk.partition("{")
            if sep:
                rules.append((selector.strip(), body.strip()))
        return rules


def _render_fn():
    for name in ("render_report", "render", "render_html", "render_session"):
        fn = getattr(report, name, None)
        if callable(fn):
            return fn
    for name in sorted(dir(report)):
        if name.startswith("render") and callable(getattr(report, name)):
            return getattr(report, name)
    pytest.fail("tere4ai.report exports no render function")


def _load_exchanges(fixture: str) -> list[dict]:
    path = FIXTURE_DIR / f"{fixture}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


@cache
def _html(fixture: str) -> str:
    from tere4ai.report import render_report_from_paths

    result = render_report_from_paths([FIXTURE_DIR / f"{fixture}.jsonl"])
    assert isinstance(result, str)
    return result


@cache
def _scan(fixture: str) -> ReportScan:
    scan = ReportScan()
    scan.feed(_html(fixture))
    scan.close()
    return scan


def _masked_nonverbatim(scan: ReportScan) -> str:
    """Non-verbatim text with the mandatory notice masked out, so scans for
    framing terms do not trip over the disclaimer's own negated wording."""
    return NOTICE_RE.sub(" ", scan.nonverbatim_text)


# ---------------------------------------------------------------------------
# Gate 1: banned claim terms live only inside byte-exact verbatim quotes.
# ---------------------------------------------------------------------------


def test_banned_claim_terms_absent_from_nonverbatim_text():
    """Guardrail: 'compliant'/'certified'/'legally approved' never appear in system-composed report text."""
    for fixture in ALL_FIXTURES:
        scan = _scan(fixture)
        text = scan.nonverbatim_text
        for pattern in CLAIM_TERM_RES:
            match = pattern.search(text)
            assert match is None, (
                f"{fixture}: banned claim term {match.group(0)!r} in non-verbatim text"
            )


def test_regulatory_compliant_wording_survives_byte_exact_in_verbatim():
    """Guardrail: the statute's own 'compliant with the requirements' wording is preserved byte-exact inside data-verbatim, and only there."""
    # credscore-highrisk carries the real Article 8(2)/Article 16 wording in
    # its deontic 'object' fields; those are VERBATIM_QUOTE_FIELDS content.
    expected = set()
    for exchange in _load_exchanges("credscore-highrisk"):

        def collect(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key == "object" and isinstance(value, str) and "compliant" in value:
                        expected.add(value)
                    else:
                        collect(value)
            elif isinstance(obj, list):
                for item in obj:
                    collect(item)

        collect(exchange["envelope"])
    assert expected, "fixture lost its 'compliant' regulatory wording"

    scan = _scan("credscore-highrisk")
    verbatim = scan.verbatim_texts()
    for source_string in expected:
        assert any(source_string in text for text in verbatim), (
            "regulatory wording containing 'compliant' must appear byte-exact "
            f"inside a data-verbatim subtree: {source_string[:80]!r}"
        )
    # The exemption path is real: 'compliant' occurs in the document, yet
    # never outside data-verbatim subtrees.
    assert re.search(r"\bcompliant\b", scan.doc_text, re.IGNORECASE)
    assert not re.search(r"\bcompliant\b", scan.nonverbatim_text, re.IGNORECASE)


# ---------------------------------------------------------------------------
# Gate 2: no em/en dashes in non-verbatim text.
# ---------------------------------------------------------------------------


def test_no_em_or_en_dash_in_nonverbatim_text():
    """Guardrail: system-composed report text contains no U+2014 or U+2013."""
    for fixture in ALL_FIXTURES:
        scan = _scan(fixture)
        match = DASH_RE.search(scan.nonverbatim_text)
        assert match is None, f"{fixture}: dash {match.group(0)!r} in non-verbatim text"


# ---------------------------------------------------------------------------
# Gate 3: the non-legal-advice notice is present, early, and never hidden.
# ---------------------------------------------------------------------------


def test_notice_twice_first_before_h1_and_never_hidden():
    """Guardrail: the non-legal-advice notice appears at least twice, opens the document before the first h1, and no CSS hides it."""
    for fixture in ALL_FIXTURES:
        scan = _scan(fixture)
        occurrences = list(NOTICE_RE.finditer(scan.doc_text))
        assert len(occurrences) >= 2, (
            f"{fixture}: notice appears {len(occurrences)} time(s), need >= 2"
        )
        assert scan.first_h1_pos is not None, f"{fixture}: report has no <h1>"
        assert occurrences[0].start() < scan.first_h1_pos, (
            f"{fixture}: first notice occurrence must precede the first <h1>"
        )
        for style in scan.style_attrs:
            assert not HIDDEN_CSS_RE.search(style), (
                f"{fixture}: hiding style attribute {style!r}"
            )
        for selector, body in scan.css_rules():
            if "notice" in selector.lower():
                assert not HIDDEN_CSS_RE.search(body), (
                    f"{fixture}: notice-related CSS rule {selector!r} hides content"
                )


# ---------------------------------------------------------------------------
# Gate 4: the HLEG mapping caveat rides with every alignment presentation.
# ---------------------------------------------------------------------------


def test_hleg_caveat_inside_every_alignment_section():
    """Guardrail: every alignment section, and the trace matrix when it shows alignments, carries the HLEG not-expert-validated caveat."""
    for fixture in ALL_FIXTURES:
        scan = _scan(fixture)
        for name in scan.section_text:
            if name.startswith("alignment"):
                assert CAVEAT_RE.search(scan.section(name)), (
                    f"{fixture}: section {name!r} lacks the HLEG mapping caveat"
                )
        matrix = scan.section("trace_matrix")
        if matrix and re.search(r"\bhleg\b", matrix, re.IGNORECASE):
            assert CAVEAT_RE.search(matrix), (
                f"{fixture}: trace_matrix renders HLEG alignments without the caveat"
            )


# ---------------------------------------------------------------------------
# Gate 5: the trace matrix disclaims itself and never grades with statuses.
# ---------------------------------------------------------------------------


def test_trace_matrix_disclaims_developer_claims_and_rows_carry_no_status():
    """Guardrail: the trace matrix states that a trace is a developer claim, not evidence, and its rows never carry status-vocabulary verdicts."""
    matrix_seen = False
    for fixture in ALL_FIXTURES:
        scan = _scan(fixture)
        matrix = scan.section("trace_matrix")
        if matrix:
            matrix_seen = True
            assert TRACE_CLAIM_RE.search(matrix), (
                f"{fixture}: trace_matrix lacks 'a trace is a developer claim, "
                "not evidence'"
            )
        for row_parts in scan.trace_rows:
            row_text = "".join(row_parts)
            for status in STATUS_VOCABULARY:
                assert status not in row_text, (
                    f"{fixture}: status value {status!r} inside a data-trace-row"
                )
    assert matrix_seen, "no fixture rendered a data-section='trace_matrix'"


# ---------------------------------------------------------------------------
# Gate 6: no grading furniture of any kind.
# ---------------------------------------------------------------------------


def test_no_grading_classes_glyphs_progress_or_traffic_light_css():
    """Guardrail: no pass/fail classes, checkmark or warning glyphs, progress bars, or green/red/amber status CSS anywhere in the report."""
    for fixture in ALL_FIXTURES:
        scan = _scan(fixture)
        for cls in scan.classes:
            assert not GRADED_CLASS_RE.search(cls), (
                f"{fixture}: grading class {cls!r}"
            )
        match = GLYPH_RE.search(scan.nonverbatim_text)
        assert match is None, (
            f"{fixture}: grading glyph {match.group(0)!r} in non-verbatim text"
        )
        assert "progress" not in scan.tags_seen, f"{fixture}: <progress> element"
        for selector, body in scan.css_rules():
            if ".status" in selector or "[data-status" in selector:
                color = re.search(r"\b(green|red|amber)\b", body, re.IGNORECASE)
                assert color is None, (
                    f"{fixture}: traffic-light word {color.group(0)!r} in status "
                    f"CSS rule {selector!r}"
                )


def test_no_aggregate_scores_percentages_or_grades():
    """Guardrail: no compliance/readiness scores, overall grades, 'on track', letter grades, or percentages over statuses."""
    for fixture in ALL_FIXTURES:
        scan = _scan(fixture)
        text = _masked_nonverbatim(scan)
        for pattern in AGGREGATION_RES:
            match = pattern.search(text)
            assert match is None, (
                f"{fixture}: forbidden aggregation phrasing {match.group(0)!r}"
            )
        # Percentages: banned outright in any summary band.
        for name, parts in scan.section_nonverbatim.items():
            if "summary" in name.lower():
                section_text = "".join(parts)
                match = PERCENT_RE.search(section_text)
                assert match is None, (
                    f"{fixture}: percentage {match.group(0)!r} in summary "
                    f"section {name!r}"
                )
        # Elsewhere: banned within reach of status words.
        for match in PERCENT_RE.finditer(text):
            window = text[max(0, match.start() - 100) : match.end() + 100]
            assert not STATUS_WORD_RE.search(window), (
                f"{fixture}: percentage {match.group(0)!r} adjacent to status "
                f"wording: {window!r}"
            )


# ---------------------------------------------------------------------------
# Gate 7: framing. The document presents engineering requirements, nothing
# resembling a certification or legal instrument.
# ---------------------------------------------------------------------------


def test_title_engineering_requirements_and_no_certification_framing():
    """Guardrail: the title says engineering requirements and no non-verbatim text frames the document as a compliance/certification/legal artifact."""
    for fixture in ALL_FIXTURES:
        scan = _scan(fixture)
        assert "engineering requirements" in scan.title_text.lower(), (
            f"{fixture}: <title> {scan.title_text!r} lacks 'engineering "
            "requirements'"
        )
        text = _masked_nonverbatim(scan)
        for pattern in FRAMING_RES:
            match = pattern.search(text)
            assert match is None, (
                f"{fixture}: forbidden framing term {match.group(0)!r} in "
                "non-verbatim text"
            )


# ---------------------------------------------------------------------------
# Gate 8: every status badge uses the calibrated vocabulary.
# ---------------------------------------------------------------------------


def test_every_data_status_value_is_in_calibrated_vocabulary():
    """Guardrail: every data-status attribute value is one of the 7 calibrated statuses."""
    any_status = False
    for fixture in ALL_FIXTURES:
        scan = _scan(fixture)
        for value in scan.status_values:
            any_status = True
            assert value in STATUS_VOCABULARY, (
                f"{fixture}: data-status {value!r} outside the calibrated "
                "vocabulary"
            )
    assert any_status, "no fixture rendered any data-status badge"


# ---------------------------------------------------------------------------
# Gate 9: the renderer exposes no notice/caveat furniture toggles.
# ---------------------------------------------------------------------------


def test_render_function_has_no_furniture_toggles():
    """Guardrail: the render signature offers no way to suppress notices or caveats."""
    signature = inspect.signature(_render_fn())
    offending = FURNITURE_TOGGLES & set(signature.parameters)
    assert not offending, f"render function exposes furniture toggles: {offending}"


# ---------------------------------------------------------------------------
# Gate 10: determinism. Regenerate-and-diff is a verification move.
# ---------------------------------------------------------------------------


def test_rendering_is_deterministic_byte_for_byte():
    """Guardrail: rendering the same session twice yields byte-identical HTML, so anyone can regenerate and diff the report."""
    from tere4ai.report import render_report_from_paths

    for fixture in ("credscore-highrisk", "moodwatch-prohibited"):
        path = FIXTURE_DIR / f"{fixture}.jsonl"
        first = render_report_from_paths([path])
        second = render_report_from_paths([path])
        assert first == second, f"{fixture}: two renders differ"


# ---------------------------------------------------------------------------
# Gate 11: the renderer's own source ships none of the banned language.
# ---------------------------------------------------------------------------


def test_report_source_files_free_of_banned_terms_and_dashes():
    """Guardrail: no claim terms, dashes, or certification framing in the report package's own source, outside its guard constants."""
    assert REPORT_SRC_DIR.is_dir(), f"missing {REPORT_SRC_DIR}"
    suffixes = {".py", ".html", ".css", ".j2", ".jinja", ".jinja2"}
    files = [p for p in REPORT_SRC_DIR.rglob("*") if p.suffix in suffixes]
    assert files, f"no source files under {REPORT_SRC_DIR}"
    violations: list[str] = []
    for path in files:
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if "BANNED" in line or "FORBIDDEN" in line:
                continue  # the renderer's own guard constants and regexes
            for pattern in (*CLAIM_TERM_RES, *FRAMING_RES, DASH_RE):
                match = pattern.search(line)
                if match:
                    violations.append(
                        f"{path.relative_to(REPO_ROOT)}:{lineno}: {match.group(0)!r}"
                    )
    assert not violations, "banned language in report source:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# Gate 12: prohibited tier. No backlog, no traces, no principle grading.
# ---------------------------------------------------------------------------


def test_prohibited_tier_report_offers_no_backlog_and_no_trace_rows():
    """Guardrail: a prohibited-practice session states that no requirement backlog can make the system permissible, lists no violated-principles grading, and renders zero trace rows."""
    scan = _scan("moodwatch-prohibited")
    assert _flex("no requirement backlog can make the system permissible").search(
        scan.doc_text
    ), "prohibited report lacks the no-backlog-can-permit statement"
    assert not _flex("violated principles").search(scan.doc_text), (
        "prohibited report must not speak of 'violated principles'"
    )
    assert not scan.trace_rows, "prohibited report renders data-trace-row elements"
