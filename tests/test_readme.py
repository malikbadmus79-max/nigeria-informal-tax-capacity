import re

from taxcap.load import PROJECT_ROOT

README = PROJECT_ROOT / "README.md"
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")


def relative_targets(text: str) -> list[str]:
    """Targets of Markdown links and images that point inside the repository."""
    return [t for t in LINK.findall(text) if not re.match(r"(?i)(https?:|mailto:|#)", t)]


def test_readme_exists():
    assert README.exists()
    assert README.read_text(encoding="utf-8").startswith("# ")


def test_readme_links_and_images_resolve():
    text = README.read_text(encoding="utf-8")
    targets = relative_targets(text)
    assert targets, "README has no relative links or images"
    missing = [t for t in targets if not (PROJECT_ROOT / t.split("#")[0]).is_file()]
    assert missing == [], f"unresolved links: {missing}"
    images = [t for t in targets if t.lower().endswith(".png")]
    assert len(images) == 3


def test_relative_targets_parser():
    text = "[a](docs/x.md) ![b](outputs/f.png) [c](https://example.org) [d](#top) [e](mailto:x@y.z)"
    assert relative_targets(text) == ["docs/x.md", "outputs/f.png"]
