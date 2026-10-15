"""Build PDF versions of the Markdown reports, run as ``python -m taxcap.build_pdfs``.

Converts reports/working_paper.md and reports/policy_brief.md to A4 PDFs with markdown and xhtml2pdf
(install with ``pip install -e .[reports]``). Images referenced in the Markdown are resolved relative to the
Markdown file and fitted to the text width. DejaVu Sans (shipped with matplotlib) is embedded, because the
built-in PDF fonts have no naira sign.
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ["working_paper", "policy_brief"]


def _font_paths() -> dict[str, Path]:
    import matplotlib
    base = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    return {"regular": base / "DejaVuSans.ttf", "bold": base / "DejaVuSans-Bold.ttf",
            "italic": base / "DejaVuSans-Oblique.ttf", "bolditalic": base / "DejaVuSans-BoldOblique.ttf"}


def _css() -> str:
    f = {k: v.as_posix() for k, v in _font_paths().items()}
    return f"""
@font-face {{ font-family: Body; src: url("{f['regular']}"); }}
@font-face {{ font-family: Body; src: url("{f['bold']}"); font-weight: bold; }}
@font-face {{ font-family: Body; src: url("{f['italic']}"); font-style: italic; }}
@font-face {{ font-family: Body; src: url("{f['bolditalic']}"); font-weight: bold; font-style: italic; }}
@page {{ size: a4 portrait; margin: 2.2cm 2.2cm 2.2cm 2.2cm;
        @frame footer {{ -pdf-frame-content: footer; bottom: 1cm; margin-left: 2.2cm; margin-right: 2.2cm; height: 1cm; }} }}
body {{ font-family: Body; font-size: 10pt; line-height: 1.4; color: #1a1a1a; }}
h1 {{ font-size: 17pt; margin: 0 0 8pt 0; }}
h2 {{ font-size: 13pt; margin: 14pt 0 4pt 0; }}
h3 {{ font-size: 11pt; margin: 10pt 0 3pt 0; }}
p {{ margin: 0 0 6pt 0; }}
li {{ margin: 0 0 3pt 0; }}
img {{ width: 16.4cm; }}
table {{ border-collapse: collapse; margin: 4pt 0 8pt 0; }}
th, td {{ border-bottom: 0.5pt solid #bbbbbb; padding: 2pt 4pt; font-size: 8.5pt; text-align: left; vertical-align: top; }}
th {{ font-weight: bold; }}
em {{ color: #444444; }}
code {{ font-family: Body; font-size: 9pt; }}
#footer {{ font-size: 8pt; color: #666666; text-align: center; }}
"""


def markdown_to_html(text: str, title: str) -> str:
    import markdown
    body = markdown.markdown(text, extensions=["tables", "sane_lists"])
    meta_title = title.replace("₦", "NGN ")   # the metadata title uses a built-in font without the naira sign
    return (f"<html><head><meta charset='utf-8'><title>{meta_title}</title><style>{_css()}</style></head><body>"
            f"{body}<div id='footer'>{title} &#8212; page <pdf:pagenumber/></div></body></html>")


def embed_images(html: str, base: Path) -> str:
    """Inline each <img src> as a base64 JPEG data URI. With PNG input, xhtml2pdf drew the first image in
    place of every later one; JPEG images are embedded separately."""
    import base64
    import io
    import re

    from PIL import Image

    def inline(m: re.Match) -> str:
        p = Path(m.group(2))
        p = p if p.is_absolute() else (base / p).resolve()
        if not p.exists():
            raise FileNotFoundError(f"image not found: {p}")
        buf = io.BytesIO()
        with Image.open(p) as im:
            im.convert("RGB").save(buf, "JPEG", quality=92)
        return f'{m.group(1)}data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode("ascii")}"'

    return re.sub(r'(<img[^>]*?src=")([^"]+)"', inline, html)


def build(md_path: Path, pdf_path: Path | None = None) -> Path:
    from xhtml2pdf import pisa
    md_path = Path(md_path)
    pdf_path = Path(pdf_path) if pdf_path else md_path.with_suffix(".pdf")
    text = md_path.read_text(encoding="utf-8")
    title = next((ln[2:].strip() for ln in text.splitlines() if ln.startswith("# ")), md_path.stem)
    html = embed_images(markdown_to_html(text, title), md_path.parent)

    def link_callback(uri: str, rel: str) -> str:
        if uri.startswith("data:"):
            return uri
        p = Path(uri)
        if p.is_absolute() and p.exists():
            return str(p)
        return str((md_path.parent / uri).resolve())

    with open(pdf_path, "wb") as out:
        status = pisa.CreatePDF(html, dest=out, link_callback=link_callback, encoding="utf-8")
    if status.err:
        raise RuntimeError(f"PDF conversion failed for {md_path}")
    return pdf_path


def page_count(pdf_path: Path) -> int:
    from pypdf import PdfReader
    return len(PdfReader(str(pdf_path)).pages)


def run(report_dir: Path | None = None) -> dict[str, int]:
    report_dir = Path(report_dir) if report_dir else ROOT / "reports"
    pages = {}
    for name in REPORTS:
        pdf = build(report_dir / f"{name}.md")
        pages[pdf.name] = page_count(pdf)
    return pages


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", dest="report_dir", default=None)
    args = ap.parse_args(argv)
    for name, n in run(args.report_dir).items():
        print(f"{name}: {n} pages")


if __name__ == "__main__":
    main()
