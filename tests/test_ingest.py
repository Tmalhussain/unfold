import textwrap

from unfold.ingest import parse_latex


def test_parse_latex_sections_equations_macros(tmp_path):
    tex = tmp_path / "main.tex"
    tex.write_text(
        textwrap.dedent(
            r"""
        \documentclass{article}
        \newcommand{\R}{\mathbb{R}}
        \title{A Tiny Paper}
        \begin{document}
        \begin{abstract} We show a thing. \end{abstract}
        \section{Intro}
        Consider % a comment with \begin{equation} inside
        \begin{equation} x^2 + y^2 = 1 \label{eq:circle} \end{equation}
        \section{Method}
        \begin{align} a &= b \\ c &= d \nonumber \end{align}
        and \[ e = mc^2 \]
        \end{document}
    """
        )
    )
    p = parse_latex(tex, tmp_path)
    assert p["title_tex"] == "A Tiny Paper"
    assert [s["title"] for s in p["sections"]] == ["Front matter", "Intro", "Method"]
    assert [e["label"] for e in p["equations"]] == ["eq:circle", None, None]
    assert p["equations"][0]["tex"] == "x^2 + y^2 = 1"
    assert "nonumber" not in p["equations"][1]["tex"]
    assert p["macros"] == [r"\newcommand{\R}{\mathbb{R}}"]
    assert "[eq1]" in p["markdown"]


def test_pdf_title_from_largest_text(tmp_path):
    import pymupdf

    from unfold.ingest import pdf_title

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "A Big Title", fontsize=24)
    page.insert_text((72, 140), "small body text", fontsize=10)
    path = tmp_path / "p.pdf"
    doc.save(path)
    assert pdf_title(path) == "A Big Title"
