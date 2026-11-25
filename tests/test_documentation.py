"""Execute self-contained console examples from the maintained documentation."""

import re
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/src/content/docs"
PAGES = [
    *sorted((ROOT / "packages").glob("*/README.md")),
    DOCS / "reference/python-api.mdx",
    DOCS / "getting-started/plugins.mdx",
    DOCS / "tutorials/python-translation.mdx",
]
RUNNER = """
import doctest
import sys
example = doctest.DocTestParser().get_doctest(sys.stdin.read(), {}, sys.argv[1], sys.argv[1], 0)
assert example.examples, "No console examples discovered"
runner = doctest.DocTestRunner()
result = runner.run(example)
assert result.attempted > 0
raise SystemExit(bool(result.failed))
"""


@pytest.mark.parametrize("path", PAGES, ids=lambda path: str(path.relative_to(ROOT)))
def test_console_examples(path: Path) -> None:
    """Use fresh sessions because transform packages register overlapping getters."""
    blocks = re.findall(r"^```pycon\n(.*?)^```", path.read_text(), re.MULTILINE | re.DOTALL)
    assert blocks, f"No executable console examples found in {path}"
    if path.name == "python-translation.mdx":
        blocks = ["\n\n".join(blocks)]
    for number, block in enumerate(blocks, start=1):
        result = subprocess.run(
            [sys.executable, "-c", RUNNER, f"{path.relative_to(ROOT)} block {number}"],
            input=block,
            text=True,
            capture_output=True,
            cwd=ROOT,
            timeout=60,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("href", "valid"),
    [("#local", True), ("?preview=1#local", True), ("#home", False), ("?preview=1#home", False)],
)
def test_non_index_page_fragments(tmp_path: Path, href: str, valid: bool) -> None:
    """Check the owning page, even when a matching anchor exists on the homepage."""
    (tmp_path / "index.html").write_text('<h1 id="home">Home</h1>')
    (tmp_path / "404.html").write_text(f'<h1 id="local">Missing page</h1><a href="{href}">Jump</a>')
    check_site = runpy.run_path(str(ROOT / "docs/check_site.py"))["check_site"]
    if valid:
        check_site(tmp_path)
    else:
        with pytest.raises(AssertionError, match=re.escape("404.html: missing fragment")):
            check_site(tmp_path)
