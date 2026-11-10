"""Repository notes stay portable; published release bodies use immutable URLs."""
from pathlib import Path
import re

from scripts.render_release_notes import ROOT, render


def test_source_notes_use_existing_relative_logo_and_document_links():
    source = ROOT / "docs/2026-11-09_release-notes-1.0.md"
    text = source.read_text()
    assert 'src="assets/logo-lockup.png"' in text
    assert "raw.githubusercontent.com" not in text
    assert (source.parent / "assets/logo-lockup.png").is_file()
    assert "[README](../README.md)" in text


def test_release_render_resolves_logo_and_docs_against_release_commit():
    source = ROOT / "docs/2026-11-09_release-notes-1.0.md"
    before = source.read_bytes()
    commit = "a" * 40
    text = render(source, repository="mikkovedru/recharge-ai-task", ref=commit)
    assert f'https://raw.githubusercontent.com/mikkovedru/recharge-ai-task/{commit}/docs/assets/logo-lockup.png' in text
    assert f'https://github.com/mikkovedru/recharge-ai-task/blob/{commit}/README.md' in text
    assert f'https://github.com/mikkovedru/recharge-ai-task/blob/{commit}/README.md#compatibility-and-limits' in text
    assert 'https://github.com/mikkovedru/recharge-ai-task/issues' in text
    assert not re.search(r'\]\(\.\.?/', text)
    assert source.read_bytes() == before


def test_generated_notes_escape_ref_and_reject_paths_outside_repository(tmp_path):
    import pytest
    source = ROOT / "docs/2026-11-09_release-notes-1.0.md"
    assert '/blob/test%2Fbranch/' in render(source, repository="owner/repo", ref="test/branch")
    fixture = tmp_path / "notes.md"
    fixture.write_text('![missing](missing.png)')
    with pytest.raises(ValueError):
        render(fixture, repository="owner/repo", ref="v1.0")


def test_all_repository_markdown_images_are_relative_existing_files():
    from html.parser import HTMLParser
    from urllib.parse import urlsplit
    from markdown_it import MarkdownIt

    class Images(HTMLParser):
        def __init__(self):
            super().__init__()
            self.paths = []
        def handle_starttag(self, tag, attrs):
            if tag == "img":
                self.paths.append(dict(attrs)["src"])

    parser = MarkdownIt("commonmark", {"html": True})
    checked = []
    sources = [*ROOT.glob("*.md"), *(ROOT / "docs").rglob("*.md"), *(ROOT / "doc").rglob("*.md")]
    for source in sources:
        if source.name == "AGENTS.md" or not source.is_file():
            continue
        name = source.relative_to(ROOT).as_posix()
        html = Images()
        for token in parser.parse(source.read_text()):
            if token.type == "html_block":
                html.feed(token.content)
            for child in token.children or []:
                if child.type == "image":
                    html.paths.append(child.attrGet("src"))
                elif child.type == "html_inline":
                    html.feed(child.content)
        for target in html.paths:
            url = urlsplit(target)
            assert not url.scheme and not url.netloc and not target.startswith("/"), (name, target)
            assert (source.parent / url.path).is_file(), (name, target)
            checked.append((name, target))
    assert any(name == "README.md" for name, _ in checked)
    assert any(name == "docs/2026-11-09_release-notes-1.0.md" for name, _ in checked)
