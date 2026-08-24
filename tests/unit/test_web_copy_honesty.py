"""Structural honesty guards for the demo web UI.

The server side has a scoped banned-term contract (DEC-08) and a dash
gate; until this file existed, nothing scanned the UI's own copy. These
guards walk web/src so a hand-typed em dash or claim term can never ship.
Word-boundary matching keeps the mandated caveat legal ("certify",
"compliance" are not the banned claim terms).
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
WEB_SRC = ROOT / "web" / "src"
BANNED = re.compile(r"\b(compliant|certified|legally approved)\b", re.IGNORECASE)
DASHES = re.compile("[\u2014\u2013]")  # em dash, en dash, written as
# escapes so this line itself does not trip the repo's own dash gate
# (scripts/check_traceability.py), which scans tests/*.py for the literal chars


SCANNED_SUFFIXES = {".tsx", ".ts", ".css"}


def _web_files():
    files = [
        p for p in WEB_SRC.rglob("*")
        if p.suffix in SCANNED_SUFFIXES and p.is_file()
    ]
    assert files, "web/src scan found no files; layout changed?"
    return files


def test_web_src_has_no_unscanned_file_suffixes():
    # _web_files() only walks .tsx/.ts/.css. This guards the scan itself: if
    # a future file type carrying copy (.mdx, .svg with inline text, and so
    # on) ever lands under web/src, it must be added to SCANNED_SUFFIXES (and
    # therefore to the dash and banned-term scans above) rather than slipping
    # past both honesty guards unnoticed.
    offenders = sorted(
        str(p.relative_to(ROOT))
        for p in WEB_SRC.rglob("*")
        if p.is_file() and p.suffix not in SCANNED_SUFFIXES
    )
    assert offenders == [], f"unscanned file suffixes under web/src: {offenders}"


def test_web_copy_has_no_em_or_en_dashes():
    offenders = [
        str(p.relative_to(ROOT))
        for p in _web_files()
        if DASHES.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_web_copy_has_no_banned_claim_terms():
    offenders = []
    for p in _web_files():
        for m in BANNED.finditer(p.read_text(encoding="utf-8")):
            offenders.append(f"{p.relative_to(ROOT)}: {m.group(0)}")
    assert offenders == []


def test_ui_data_serves_the_recorded_chain_id_and_schema_flags():
    ui = json.loads((ROOT / "web" / "public" / "ui_data.json").read_text())
    current = (
        (ROOT / "data" / "graph_dumps" / "BUILD_CHAIN_CURRENT.txt")
        .read_text()
        .strip()
    )
    assert ui["build"]["chain_id"] == current
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from tere4ai.elicit_features.elicitor import schema_flag_names

    assert ui["schema_flags"] == schema_flag_names()


def test_pending_review_tile_shows_true_total():
    """The "Pending human review" tile must show every kind of item still
    awaiting a human, not cross-references alone. The served total has to equal
    norms_needing_review + alignment_pending_total + crossref_pending_total, and
    the page tile must be driven by review.total_pending_review, never by
    review_queue_count (which counts cross-references only).
    """
    ui = json.loads((ROOT / "web" / "public" / "ui_data.json").read_text())
    review = ui["review"]
    norms = len(review["norms_needing_review"])
    alignments = review["alignment_pending_total"]
    crossrefs = review["crossref_pending_total"]
    assert review["total_pending_review"] == norms + alignments + crossrefs, (
        "review.total_pending_review does not equal norms + alignments + "
        f"crossrefs ({norms} + {alignments} + {crossrefs})"
    )
    # crossref_pending_total is the cross-references-only figure that the tile
    # used to (wrongly) show; the honest total must be at least as large.
    assert review["total_pending_review"] >= crossrefs

    page_text = (WEB_SRC / "app" / "(demo)" / "coverage" / "page.tsx").read_text(encoding="utf-8")
    assert "reviewCount={data.review.total_pending_review}" in page_text, (
        "the Pending human review tile is not fed review.total_pending_review; "
        "it must not understate the queue by showing cross-references only"
    )
    assert "reviewCount={data.review_queue_count}" not in page_text, (
        "the Pending human review tile still reads review_queue_count "
        "(cross-references only), which understates the true pending total"
    )


def test_page_does_not_claim_a_startup_chain_verification():
    """The served demo runs the HTTP facade, which performs no chain
    verification at startup (only the MCP server verifies). The coverage page
    must not claim a runtime startup verification it does not do; it may only
    state that the chain id is recorded by the build and shown from the served
    artifact.
    """
    offenders = [
        str(p.relative_to(ROOT))
        for p in _web_files()
        if "verified at server startup" in p.read_text(encoding="utf-8")
    ]
    assert offenders == [], (
        "web copy still claims the chain is 'verified at server startup', but "
        f"the served facade performs no such verification: {offenders}"
    )


def test_evidence_graph_svg_scales_to_its_frame():
    """The evidence subgraph is the demo centerpiece (docs/DEMO.md step 3).
    It used to render onto a fixed 1400px canvas sized by node count, which
    in the ~800px content column drew the cluster half outside the frame:
    the reader saw whitespace and a sliced-off graph until they scrolled
    sideways. The SVG must therefore carry no pixel width or height (a
    viewBox plus a full-width class scales it to whatever frame it is in),
    and the viewBox must be the one fitted to the settled node positions,
    never a bare "0 0 width height" canvas.
    """
    text = (WEB_SRC / "app" / "(demo)" / "assess" / "evidence-graph.tsx").read_text(
        encoding="utf-8"
    )
    match = re.search(r"<svg\b(?![^>]*aria-hidden)[^>]*>", text, re.DOTALL)
    assert match, "the graph <svg> element was not found, has it been rewritten?"
    svg_tag = match.group(0)
    assert "viewBox={layout.viewBox}" in svg_tag, (
        "the graph <svg> no longer uses the fitted viewBox from layoutGraph; a "
        "canvas-sized viewBox reintroduces the empty-margin and clipping bug"
    )
    assert not re.search(r"\bwidth=\{(?!10\b)", svg_tag), (
        "the graph <svg> sets an explicit width again; a pixel width stops it "
        "scaling to the content column and clips the graph out of view"
    )
    assert "w-full" in svg_tag, (
        "the graph <svg> must be full width so the viewBox scales it to the frame"
    )


def test_presets_cover_every_schema_flag():
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from tere4ai.elicit_features.elicitor import schema_flag_names

    presets_text = (WEB_SRC / "app" / "(demo)" / "assess" / "presets.ts").read_text()
    missing = [f for f in schema_flag_names() if f'"{f}"' not in presets_text]
    assert missing == [], f"presets.ts missing schema flags: {missing}"


def test_flag_panel_covers_every_schema_flag():
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from tere4ai.elicit_features.elicitor import schema_flag_names

    page_text = (WEB_SRC / "app" / "(demo)" / "assess" / "page.tsx").read_text()
    missing = [f for f in schema_flag_names() if f'"{f}"' not in page_text]
    assert missing == [], f"page.tsx flag panel missing schema flags: {missing}"


# --- fresh-clone demo blocker guards ---------------------------------------
#
# public/ui_data.json is generated by scripts/export_ui_data.py and is
# gitignored, never committed. A fresh clone in dev mode has no ui_data.json
# until that script runs. The three guards below hold the fix in place:
# page.tsx and review/page.tsx must catch the missing-file case rather than
# crash (this file's honesty guards check the code, not a live render), and
# both the npm predev hook and the DEMO.md dev-mode walkthrough must actually
# tell someone (a script, a presenter) to generate the file.


def _load_data_body(text: str, rel: str) -> str:
    match = re.search(r"function loadData\(\)[^{]*\{(.*?)\n\}\n", text, re.DOTALL)
    assert match, f"{rel}: loadData() function not found, has it been renamed?"
    return match.group(1)


def test_ui_data_read_is_guarded_against_a_missing_file():
    """page.tsx and review/page.tsx read public/ui_data.json at request time.
    A missing or unparsable file must not crash the page: the read has to sit
    inside a try/catch whose catch branch reports absence (returns null) so
    the component can render an honest setup notice instead of a 500.
    """
    for rel in ("app/(demo)/coverage/page.tsx", "app/(demo)/review/page.tsx"):
        path = WEB_SRC / rel
        text = path.read_text(encoding="utf-8")
        body = _load_data_body(text, rel)
        assert "fs.readFileSync" in body, (
            f"{rel}: loadData() no longer reads ui_data.json, update this guard"
        )
        try_idx = body.find("try")
        read_idx = body.find("fs.readFileSync")
        catch_idx = body.find("catch")
        assert 0 <= try_idx < read_idx < catch_idx, (
            f"{rel}: fs.readFileSync in loadData() is not wrapped in a try/catch, "
            "a missing ui_data.json will throw and 500 the page"
        )
        assert "return null" in body, (
            f"{rel}: loadData()'s catch branch must return null on failure, "
            "never a fabricated payload"
        )
        assert "if (!data)" in text and "SetupNotice" in text, (
            f"{rel}: the page does not branch on a null loadData() result into "
            "an honest setup notice"
        )


def test_web_package_json_predev_regenerates_ui_data():
    pkg = json.loads((ROOT / "web" / "package.json").read_text(encoding="utf-8"))
    scripts = pkg.get("scripts", {})
    assert "predev" in scripts, (
        "web/package.json has no predev script; npm run dev will not "
        "regenerate public/ui_data.json before the server starts"
    )
    # The hook may call the export script directly or through a wrapper (the
    # wrapper exists so the interpreter choice stays portable between a local
    # .venv and CI's system python). Either way the chain must end at the
    # export script, so follow one level of indirection.
    command = scripts["predev"]
    if "export_ui_data.py" not in command:
        referenced = [
            token
            for token in command.split()
            if token.endswith((".mjs", ".js", ".cjs", ".sh"))
        ]
        assert referenced, (
            f"predev is {command!r}: it neither calls export_ui_data.py nor "
            "references a wrapper script that could"
        )
        wrapper = ROOT / "web" / referenced[0]
        assert wrapper.is_file(), f"predev references a missing wrapper: {wrapper}"
        command = wrapper.read_text(encoding="utf-8")
    assert "export_ui_data.py" in command, (
        "the predev chain no longer reaches scripts/export_ui_data.py, so a "
        "fresh clone would start the demo with no coverage data"
    )


def test_demo_md_dev_setup_documents_ui_data_generation():
    demo_md = (ROOT / "docs" / "DEMO.md").read_text(encoding="utf-8")
    start = demo_md.find("Dev mode (recommended")
    end = demo_md.find("## The 7-minute talk")
    assert start != -1 and end != -1 and start < end, (
        "DEMO.md dev-mode setup section not found, has it been renamed?"
    )
    dev_mode_block = demo_md[start:end]
    assert "export_ui_data.py" in dev_mode_block, (
        "DEMO.md's dev-mode setup no longer tells the presenter to generate "
        "web/public/ui_data.json; a fresh clone in dev mode 500s on the "
        "coverage page (step 1 of the talk) without this step"
    )
    py_idx = dev_mode_block.find("export_ui_data.py")
    npm_idx = dev_mode_block.find("npm run dev")
    assert npm_idx != -1 and py_idx < npm_idx, (
        "DEMO.md must document generating ui_data.json before starting the "
        "web dev server, not after"
    )
