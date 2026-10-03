"""The names and counts rules on prose (DEC-22).

Pure functions over text. The prose of a Markdown file is its text without
fenced code blocks, inline code spans, HTML comments and the generated
regions; the prose of a .tsx file is its JSX text children, each run its own
text, so class names, constants, comments and code never join a sentence.
Two rules read that prose: count_hits finds a sentence that pairs a count
with tools, free or paid (a count drifts the day a tool is added), and
code_names lists the backticked names a test compares with what the code
knows. A third rule, link_problems, reads the whole Markdown text of a
docs/server page: a relative link may only name one of the site's own pages
and only outside the README part, every image is an absolute URL, and
nothing names the private research repository.

@implements: DEC-22
@grounded_by: REF-31
"""

from __future__ import annotations

import re

_FENCE = re.compile(r"^[ \t]*(```|~~~).*?^[ \t]*\1[^\n]*$", re.MULTILINE | re.DOTALL)
_GENERATED = re.compile(
    r"<!--\s*generated:\s*([\w.-]+)\s*-->.*?<!--\s*end generated:\s*\1\s*-->",
    re.DOTALL,
)
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_LINK_TARGET = re.compile(r"\]\([^)\s]*\)")
_BARE_URL = re.compile(r"\bhttps?://\S+")
_LIST_MARKER = re.compile(r"^[ \t]*(?:\d+\.|[-*])[ \t]+", re.MULTILINE)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\s*\|\s*")

_TS_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_TS_LINE_COMMENT = re.compile(r"(?<![:\w\"'`])//[^\n]*")
# A JSX tag opens where "<" is followed by a name or "/" or ">" and does not
# follow an identifier or a closing bracket (which would make it a type
# argument such as useState<string> or a comparison such as i<n).
_JSX_TAG_START = re.compile(r"(?<![\w$.)\]])<(?=[A-Za-z/>])")

_NUMBER_WORDS = frozenset(
    (
        "one two three four five six seven eight nine ten eleven twelve thirteen "
        "fourteen fifteen sixteen seventeen eighteen nineteen twenty"
    ).split()
)
# A number after one of these words names a provision or a layer; it is not
# a count. "Layer" joins the plan's list for "Layer 2/3".
_CITED_NUMBER = re.compile(
    r"\b(?:Article|Section|Annex|Chapter|Regulation|point|paragraph|Layer)s?"
    r"\s+\d+(?:/\d+)*(?:\(\w+\))*",
    re.IGNORECASE,
)
_YEAR_SLASH_NUMBER = re.compile(r"\b\d{4}/\d{4}\b")
_WORD = re.compile(r"\w+")
_COUNTED_WORDS = frozenset({"tool", "tools", "free", "paid"})
# How many words after a count may hold the counted word: "twelve tools",
# "two generative tools", "Eight are free", "eight of them are free".
_WINDOW = 4

_MD_LINK = re.compile(r"(!?)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_SITE_PAGE = re.compile(r"^(?:tools\.md|sessions\.md|sessions/[a-z0-9_-]+\.html)$")
_ABSOLUTE = ("https://", "http://")
_README_START = "<!-- readme: start -->"
_README_END = "<!-- readme: end -->"
# A spec decision id, a card id, the private repository's folder and its
# plan folders.
_PRIVATE = (
    re.compile(r"D-[A-Z]+\d+"),
    re.compile(r"\bB\d{2,3}\b"),
    re.compile(r"\.\./thesis"),
    re.compile(r"\bsdd/"),
)

_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")
_CALL = re.compile(r"^([a-z_][a-z0-9_]*)\((.*)\)$")
_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _without_code_and_regions(text: str) -> str:
    """Drop fenced code blocks, the generated regions and HTML comments."""
    text = _FENCE.sub(" ", text)
    text = _GENERATED.sub(" ", text)
    return _COMMENT.sub(" ", text)


def prose_of_markdown(text: str) -> str:
    """The prose of a Markdown text: no fenced code, inline code, HTML
    comments, generated regions, link targets or URLs, no list markers,
    whitespace collapsed."""
    text = _without_code_and_regions(text)
    text = _INLINE_CODE.sub(" ", text)
    text = _LINK_TARGET.sub("]", text)
    text = _BARE_URL.sub(" ", text)
    text = _LIST_MARKER.sub("", text)
    return " ".join(text.split())


def _tag_end(text: str, start: int) -> int | None:
    """The index just past the ">" closing the JSX tag that opens at start,
    skipping quoted attribute values and braced expressions; None when the
    text ends first."""
    depth = 0
    quote: str | None = None
    i = start + 1
    while i < len(text):
        char = text[i]
        if quote:
            if char == quote:
                quote = None
        elif char in "\"'`":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth = max(depth - 1, 0)
        elif char == ">" and depth == 0:
            return i + 1
        i += 1
    return None


def prose_of_tsx(text: str) -> list[str]:
    """The JSX text children of a .tsx file, each run its own text, with
    whitespace collapsed. A run starts after a JSX tag closes and ends at the
    next "<" or "{"; comments are removed first, and runs holding no letter
    are left out."""
    text = _TS_BLOCK_COMMENT.sub(" ", text)
    text = _TS_LINE_COMMENT.sub(" ", text)
    runs: list[str] = []
    for match in _JSX_TAG_START.finditer(text):
        end = _tag_end(text, match.start())
        if end is None:
            continue
        stop = end
        while stop < len(text) and text[stop] not in "<>{}":
            stop += 1
        if stop < len(text) and text[stop] in "<{":
            run = " ".join(text[end:stop].split())
            if any(char.isalpha() for char in run):
                runs.append(run)
    return runs


def sentences(text: str) -> list[str]:
    """Split after ".", "!" or "?" followed by whitespace, and at each "|"
    of a table row, so a table cell is its own sentence."""
    return [part for part in _SENTENCE_END.split(text.strip()) if part]


def _is_count(word: str) -> bool:
    return word.isdigit() or word.lower() in _NUMBER_WORDS


def _pairs_count_and_word(sentence: str) -> bool:
    rest = _YEAR_SLASH_NUMBER.sub(" ", sentence)
    rest = _CITED_NUMBER.sub(" ", rest)
    words = _WORD.findall(rest)
    for i, word in enumerate(words):
        if _is_count(word):
            following = words[i + 1 : i + 1 + _WINDOW]
            if any(w.lower() in _COUNTED_WORDS for w in following):
                return True
    return False


def count_hits(sentence_list: list[str]) -> list[str]:
    """The sentences that pair a count with tool, tools, free or paid: the
    word is one of the four words after the count. A count is an English
    number word one to twenty, or a digit run that is not part of NNNN/NNNN
    and does not follow Article, Section, Annex, Chapter, Regulation, point,
    paragraph or Layer."""
    return [s for s in sentence_list if _pairs_count_and_word(s)]


def code_names(markdown: str) -> set[str]:
    """The names in the inline code spans of a Markdown text's prose: a span
    that is a bare identifier gives itself; a call gives its name and the
    identifiers between its parentheses; every other span is skipped."""
    names: set[str] = set()
    for span in _INLINE_CODE.findall(_without_code_and_regions(markdown)):
        span = span.strip()
        if _IDENTIFIER.match(span):
            names.add(span)
            continue
        call = _CALL.match(span)
        if call:
            names.add(call.group(1))
            names.update(t for t in _TOKEN.findall(call.group(2)) if _IDENTIFIER.match(t))
    return names


def link_problems(markdown: str) -> list[str]:
    """What breaks the link rule in a docs/server Markdown page: a relative
    link to anything but tools.md, sessions.md or sessions/<key>.html, a
    relative link inside the README part (the README is read on GitHub,
    where the site's pages do not exist), an image that is not an absolute
    URL, and any name from the private research repository."""
    problems: list[str] = []
    start = markdown.find(_README_START)
    end = markdown.find(_README_END)
    for match in _MD_LINK.finditer(markdown):
        image, target = match.group(1) == "!", match.group(2)
        if target.startswith(_ABSOLUTE):
            continue
        if image:
            problems.append(f"image {target} is not an absolute URL")
        elif not _SITE_PAGE.match(target):
            problems.append(f"relative link {target} is not one of the site's pages")
        elif start != -1 and start < match.start() < end:
            problems.append(f"relative link {target} is inside the README part")
    for pattern in _PRIVATE:
        problems += [f"{m.group(0)} names the private repository" for m in pattern.finditer(markdown)]
    return problems
