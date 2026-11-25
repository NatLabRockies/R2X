"""Check built documentation links and heading fragments without network access."""

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


class Page(HTMLParser):
    """Collect navigable anchors and local links from one HTML page."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.anchors: set[str] = set()
        self.links: list[str] = []
        self.feed(path.read_text())

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if anchor := values.get("id"):
            self.anchors.add(anchor)
        if tag == "a" and (href := values.get("href")):
            self.links.append(href)


def check_site(root: Path) -> None:
    """Fail on missing internal pages or fragments, including archive links."""
    root = root.resolve()
    pages = {path: Page(path) for path in root.rglob("*.html")}
    assert pages, "Build the documentation before checking links"
    failures: list[str] = []
    checked = 0
    for path, page in pages.items():
        for href in page.links:
            url = urlsplit(href)
            if url.scheme or url.netloc:
                continue
            if not url.path:
                target = path
            elif url.path.startswith("/R2X/"):
                target = root / unquote(url.path.removeprefix("/R2X/"))
            elif url.path.startswith("/"):
                failures.append(f"{path.relative_to(root)}: missing base prefix: {href}")
                continue
            else:
                target = path.parent / unquote(url.path)
            if target.is_dir():
                target /= "index.html"
            target = target.resolve()
            checked += 1
            if not target.exists():
                failures.append(f"{path.relative_to(root)}: missing target: {href}")
            elif url.fragment and target in pages and unquote(url.fragment) not in pages[target].anchors:
                failures.append(f"{path.relative_to(root)}: missing fragment: {href}")
    assert not failures, "\n".join(sorted(set(failures)))
    print(f"Checked {checked} internal links across {len(pages)} HTML pages")


if __name__ == "__main__":
    check_site(Path(__file__).resolve().parent / "dist")
