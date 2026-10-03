"""The names and counts rules on prose, proved on mock text (DEC-22, B90).

prose.py reads the prose of a Markdown file or the JSX text of a .tsx file,
splits it into sentences, and finds two things the generated regions cannot
check: a sentence that pairs a count with tools, free or paid, and a
backticked name that the code may not know.
"""

from __future__ import annotations

from tere4ai.server_docs import prose


def _hits(markdown: str) -> list[str]:
    return prose.count_hits(prose.sentences(prose.prose_of_markdown(markdown)))


def _tsx_hits(tsx: str) -> list[str]:
    found: list[str] = []
    for run in prose.prose_of_tsx(tsx):
        found.extend(prose.count_hits(prose.sentences(run)))
    return found


def test_a_count_of_tools_and_a_count_of_free_ones_are_two_hits():
    assert len(_hits("All twelve tools run over stdio. Eight are free")) == 2


def test_a_section_number_beside_paid_is_not_a_count():
    assert _hits("paid model calls (architecture.md Section 6)") == []


def test_the_regulation_number_beside_tool_is_not_a_count():
    assert _hits("Regulation 2024/1689 inside a coding agent's tool loop.") == []


def test_a_class_name_never_joins_a_sentence():
    tsx = '<p className="mx-auto pt-18">Keys unlock the paid tools.</p>'
    assert _tsx_hits(tsx) == []


def test_a_count_in_jsx_text_is_a_hit():
    tsx = "<p>Keys unlock the two\n  generative tools.</p>"
    assert _tsx_hits(tsx) == ["Keys unlock the two generative tools."]


def test_each_jsx_text_run_is_its_own_text():
    tsx = "<p>Two</p><span>{x}</span><p>tools here</p>"
    assert prose.prose_of_tsx(tsx) == ["Two", "tools here"]
    assert _tsx_hits(tsx) == []


def test_number_words_and_digits_both_count():
    assert _hits("It serves 12 tools.") == ["It serves 12 tools."]
    assert _hits("Four are paid.") == ["Four are paid."]


def test_a_word_holding_tool_is_not_tool():
    assert _hits("The toolkit has twelve parts.") == []


def test_code_fences_comments_and_generated_regions_are_not_prose():
    text = (
        "Intro.\n\n"
        "```bash\necho twelve tools\n```\n\n"
        "<!-- twelve tools -->\n"
        "<!-- generated: tools -->\nAll twelve tools.\n<!-- end generated: tools -->\n"
        "The `twelve tools` call.\n"
    )
    assert _hits(text) == []
    assert "twelve" not in prose.prose_of_markdown(text)


def test_list_markers_are_stripped_and_whitespace_collapsed():
    text = "1. First item\n- second\n* third\n  wrapped   line\n"
    assert prose.prose_of_markdown(text) == "First item second third wrapped line"


def test_sentences_split_after_end_marks():
    assert prose.sentences("One. Two! Three? Four") == ["One.", "Two!", "Three?", "Four"]


def test_a_module_path_is_not_a_name():
    assert prose.code_names("Run `python -m tere4ai.mcp_server.server` now.") == set()


def test_a_call_gives_its_name_and_its_arguments():
    names = prose.code_names("Call `generate_control_backlog(norm_ids, system_context)`.")
    assert names == {"generate_control_backlog", "norm_ids", "system_context"}


def test_a_bare_identifier_is_a_name_and_other_spans_are_skipped():
    text = "Read `status`, `TOOL_SCOPES`, `a/b`, `x=1`, `two words`, `.env`."
    assert prose.code_names(text) == {"status"}


def test_code_names_skip_fences_and_generated_regions():
    text = (
        "```python\n`inside_fence`\n```\n"
        "<!-- generated: tools -->\n`generated_name`\n<!-- end generated: tools -->\n"
        "`kept_name`\n"
    )
    assert prose.code_names(text) == {"kept_name"}


# False positives found on today's text (Task 1 Step 2), each fixed in the
# rule and kept here as mock text.


def test_a_layer_number_beside_paid_is_not_a_count():
    text = (
        "`norms_core.json` and `alignments_core.json` come from the judged\n"
        "Layer 2/3 pipeline, which makes paid model calls (architecture.md Section\n6)."
    )
    assert _hits(text) == []


def test_one_as_a_pronoun_is_not_a_count_of_tools():
    text = (
        "HTTP tool calls require a scoped API key sent as a Bearer token; mint\n"
        "one with `scripts/mint_key.py` (scopes: read_graph, classify)."
    )
    assert _hits(text) == []


def test_one_counting_another_noun_is_not_a_count_of_tools():
    assert _hits("(PAID): assesses one artifact against one norm.") == []
    assert _hits("| One norm: actor, modal, action | free |") == []


def test_counts_of_other_things_far_from_tools_are_not_hits():
    text = (
        "Layer 1 mirror of the full Act (113 articles, 180 recitals, 13 annexes),\n"
        "crossrefs, coverage and trace tools, traceability gate."
    )
    assert _hits(text) == []


def test_type_arguments_and_comments_are_not_jsx_text():
    tsx = (
        "const [a, setA] = useState<string | null>(null);\n"
        "/* one /api/trace/batch call per assessment (free) */\n"
        "// two tools\n"
        "if (i<n) { x = 1; }\n"
    )
    assert prose.prose_of_tsx(tsx) == []


def test_jsx_text_before_an_expression_is_read():
    tsx = '<p className={cn("a", b && "c")}>Four tools are paid {x}</p>'
    assert prose.prose_of_tsx(tsx) == ["Four tools are paid"]
    assert _tsx_hits(tsx) == ["Four tools are paid"]


def test_a_url_in_jsx_text_is_not_a_comment():
    tsx = '<a href="https://example.org/x">See https://example.org/x for two tools.</a>'
    assert prose.prose_of_tsx(tsx) == ["See https://example.org/x for two tools."]


def test_a_link_target_is_not_prose():
    text = "| MCP Inspector | [docs](https://x.org/docs/2026-07-28/tools/inspector.mdx) |"
    assert _hits(text) == []
    assert "https" not in prose.prose_of_markdown(text + " see https://x.org/2/tools")


def test_a_table_cell_is_its_own_sentence():
    text = "| Requires MCP 2.0 / 2026-07-28 | [x](https://x.org) |\n| ChatGPT tools-only connector | none |"
    assert _hits(text) == []
    assert prose.sentences("| a | b. c |") == ["a", "b.", "c"]
