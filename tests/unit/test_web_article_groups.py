"""The demo assess page groups backlog items by Article in the Act's order (B132).

web/src/lib/articleGroups.ts is run under Node with its type annotations
stripped (Node 22's --experimental-strip-types), so the page's own
functions are what is tested. Article 4a, inserted by the Digital Omnibus,
is its own group between Articles 4 and 5 (final review of plan A,
Important 4, second half). Skipped where Node is absent.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "web" / "src" / "lib" / "articleGroups.ts"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

SCRIPT = """
import { articleGroupOf, compareArticleGroups } from "MODULE";
const ids = ["norm:eu-ai-act:article-50:paragraph-1:n1", "norm:eu-ai-act:article-4a:paragraph-1:n2",
             "norm:eu-ai-act:annex-iii:point-4:n1", "norm:eu-ai-act:article-5:paragraph-1:n1",
             "norm:eu-ai-act:article-4:paragraph-1:n1", "norm:eu-ai-act:article-10:paragraph-2:n1", "other"];
const groups = ids.map(articleGroupOf);
const sorted = [...new Set(groups.filter((g) => g !== null))].sort(compareArticleGroups);
console.log(JSON.stringify({ groups, sorted }));
"""


def test_article_4a_is_its_own_group_between_4_and_5():
    out = subprocess.run(
        [NODE, "--experimental-strip-types", "--no-warnings", "--input-type=module", "-e",
         SCRIPT.replace("MODULE", MODULE.as_uri())],
        capture_output=True, text=True, check=True, timeout=60,
    )
    result = json.loads(out.stdout)
    assert result["groups"][1] == "eu-ai-act:article-4a"
    assert result["groups"][6] is None
    assert result["sorted"] == [
        "eu-ai-act:article-4", "eu-ai-act:article-4a", "eu-ai-act:article-5", "eu-ai-act:article-10",
        "eu-ai-act:article-50", "eu-ai-act:annex-iii",
    ]
