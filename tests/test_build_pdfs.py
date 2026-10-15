import pytest

pytest.importorskip("markdown")
pytest.importorskip("xhtml2pdf")

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from pypdf import PdfReader  # noqa: E402

from taxcap import build_pdfs  # noqa: E402


@pytest.fixture
def report_dir(tmp_path):
    figs = tmp_path / "figs"
    figs.mkdir()
    for name, size in [("f.png", (6, 3)), ("g.png", (4, 4))]:   # two figures of different shapes
        fig, ax = plt.subplots(figsize=size)
        ax.plot([0, 1], [0, 1])
        fig.savefig(figs / name, dpi=50)
        plt.close(fig)
    d = tmp_path / "reports"
    d.mkdir()
    body = ("# Synthetic report\n\nShare above ₦800,000: 20%.\n\n![Figure](../figs/f.png)\n\n"
            "*Figure 1. A synthetic figure.*\n\n![Figure](../figs/g.png)\n\n*Figure 2. Another.*\n\n"
            "| a | b |\n|---|---|\n| 1 | 2 |\n")
    for name in build_pdfs.REPORTS:
        (d / f"{name}.md").write_text(body.replace("Synthetic report", f"Synthetic {name}"), encoding="utf-8")
    return d


def test_build_pdfs_produces_both_files(report_dir):
    pages = build_pdfs.run(report_dir)
    assert set(pages) == {f"{n}.pdf" for n in build_pdfs.REPORTS}
    for name in build_pdfs.REPORTS:
        pdf = report_dir / f"{name}.pdf"
        assert pdf.exists() and pdf.stat().st_size > 5_000
        assert pdf.read_bytes()[:5] == b"%PDF-"
    assert all(n >= 1 for n in pages.values())


def test_each_figure_embedded_separately(report_dir):
    build_pdfs.run(report_dir)
    sizes = set()
    for page in PdfReader(str(report_dir / "policy_brief.pdf")).pages:
        for _, v in (page["/Resources"].get("/XObject") or {}).items():
            o = v.get_object()
            sizes.add((int(o["/Width"]), int(o["/Height"])))
    assert sizes == {(300, 150), (200, 200)}
