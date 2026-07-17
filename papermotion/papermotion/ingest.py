"""Ingestion stage.

Normalizes three kinds of input into a `Paper` (see models.py):

1. arXiv id / URL       -> fetch metadata via the `arxiv` package, download the
                            PDF, then run the PDF pipeline on it.
2. Local PDF path       -> extract text with pymupdf, split into sections with
                            font-size/bold heading heuristics (numbered-heading
                            regex as fallback), extract embedded images.
3. Local .txt/.md path  -> parse markdown-ish (#, ##, ...) headings.

Robustness > precision: if heading detection fails or a PDF is malformed, we
fall back to progressively dumber strategies and, worst case, a single
section holding the whole body text. This function should not raise on a
"weird" document; it only raises for input it truly cannot resolve at all
(nonexistent local path with no arXiv-id shape).
"""

from __future__ import annotations

import re
import statistics
import urllib.request
from pathlib import Path

from .models import Paper, Section

# ---------------------------------------------------------------------------
# input classification

ARXIV_ID_RE = re.compile(r"\d{4}\.\d{4,5}(v\d+)?")
ARXIV_OLD_ID_RE = re.compile(r"[a-z-]+(\.[A-Za-z-]+)?/\d{7}(v\d+)?")
ARXIV_URL_RE = re.compile(r"arxiv\.org/(abs|pdf)/([^\s?#]+?)(\.pdf)?/?$")

TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".rst"}


def ingest(input_str: str, work_dir: Path | None = None) -> Paper:
    """Normalize `input_str` (arXiv id/URL | PDF path | txt/md path) into a Paper."""
    work_dir = Path(work_dir) if work_dir is not None else Path("work")
    work_dir.mkdir(parents=True, exist_ok=True)

    input_str = input_str.strip()
    path = Path(input_str)

    if path.is_file():
        if path.suffix.lower() == ".pdf":
            return _ingest_pdf(path, work_dir)
        if path.suffix.lower() in TEXT_SUFFIXES:
            return _ingest_text(path, work_dir)
        # Unknown suffix on an existing file: sniff it.
        head = path.read_bytes()[:5]
        if head.startswith(b"%PDF"):
            return _ingest_pdf(path, work_dir)
        return _ingest_text(path, work_dir)

    if ARXIV_URL_RE.search(input_str) or ARXIV_ID_RE.fullmatch(input_str) or \
            ARXIV_OLD_ID_RE.fullmatch(input_str) or "arxiv.org" in input_str:
        return _ingest_arxiv(input_str, work_dir)

    raise ValueError(
        f"Could not resolve input {input_str!r}: not an existing file and "
        "doesn't look like an arXiv id/URL"
    )


# ---------------------------------------------------------------------------
# 1. arXiv

def _extract_arxiv_id(s: str) -> str:
    m = ARXIV_URL_RE.search(s)
    if m:
        return m.group(2)
    m = ARXIV_ID_RE.search(s)
    if m:
        return m.group(0)
    m = ARXIV_OLD_ID_RE.search(s)
    if m:
        return m.group(0)
    return s


def _ingest_arxiv(input_str: str, work_dir: Path) -> Paper:
    import arxiv

    arxiv_id = _extract_arxiv_id(input_str)
    client = arxiv.Client()
    search = arxiv.Search(id_list=[arxiv_id])
    try:
        result = next(client.results(search))
    except StopIteration:
        raise ValueError(f"No arXiv result found for id {arxiv_id!r}")

    pdf_path = work_dir / f"{arxiv_id.replace('/', '_')}.pdf"
    if result.pdf_url:
        urllib.request.urlretrieve(result.pdf_url, pdf_path)
    else:
        raise ValueError(f"arXiv result {arxiv_id!r} has no PDF link")

    paper = _ingest_pdf(pdf_path, work_dir)
    if result.title.strip():
        paper.title = result.title.strip()
    if result.authors:
        paper.authors = [a.name for a in result.authors]
    if result.summary.strip():
        paper.abstract = result.summary.strip()
    paper.source = arxiv_id
    return paper


# ---------------------------------------------------------------------------
# 2. PDF

HEADING_KEYWORDS = {
    "abstract", "introduction", "related work", "background",
    "method", "methods", "methodology", "approach", "model",
    "architecture", "model architecture", "experiments", "experiment",
    "experimental setup", "results", "evaluation", "discussion",
    "conclusion", "conclusions", "limitations", "future work",
    "acknowledgments", "acknowledgements", "references", "appendix",
}

NUMBERED_HEADING_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s+([A-Z].{0,90})\s*$")
KEYWORD_HEADING_RE = re.compile(
    r"^\s*(" + "|".join(re.escape(k) for k in sorted(HEADING_KEYWORDS, key=len, reverse=True))
    + r")\s*[:.]?\s*$",
    re.IGNORECASE,
)


def _ingest_pdf(pdf_path: Path, work_dir: Path) -> Paper:
    try:
        import fitz
    except Exception as e:  # pragma: no cover - dependency should always be present
        raise RuntimeError("pymupdf (fitz) is required to ingest PDFs") from e

    try:
        doc = fitz.open(pdf_path)
    except Exception:
        # Totally unreadable PDF: don't crash the pipeline.
        return Paper(title=pdf_path.stem, sections=[Section("Body", "")],
                     source=str(pdf_path))

    try:
        title = _pdf_title(doc, pdf_path, fitz)
        lines = _pdf_lines(doc, fitz)
        sections = _split_sections_by_font(lines)
        if not _sections_look_reasonable(sections):
            full_text = "\n".join(l["text"] for l in lines).strip()
            sections = _split_sections_by_regex(full_text)
        if not _sections_look_reasonable(sections):
            full_text = "\n".join(page.get_text() for page in doc).strip()
            sections = [Section("Body", full_text)]

        # Drop a leading section whose heading is just the title/byline
        # (font-based split often peels the title line off as a "heading").
        if sections and _normalize(sections[0].heading) == _normalize(title):
            sections = sections[1:]

        abstract, sections = _pop_abstract(sections)
        figures = _extract_figures(doc, work_dir, fitz)
    except Exception:
        # Something in our heuristics choked on this PDF's structure.
        # Fall back to the dumbest possible thing that still works.
        try:
            full_text = "\n".join(page.get_text() for page in doc).strip()
        except Exception:
            full_text = ""
        title = pdf_path.stem
        abstract = ""
        sections = [Section("Body", full_text)]
        figures = []
    finally:
        doc.close()

    return Paper(title=title or pdf_path.stem, authors=[], abstract=abstract,
                 sections=sections, figures=figures, source=str(pdf_path))


def _pdf_lines(doc, fitz) -> list[dict]:
    """Flatten the doc into per-line records: text, max font size, bold flag."""
    lines = []
    for page in doc:
        d = page.get_text("dict")
        for block in d.get("blocks", []):
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                text = "".join(sp.get("text", "") for sp in spans).strip()
                if not text:
                    continue
                size = max(sp.get("size", 0.0) for sp in spans)
                bold = any(int(sp.get("flags", 0)) & fitz.TEXT_FONT_BOLD for sp in spans)
                lines.append({"text": text, "size": size, "bold": bold})
    return lines


def _pdf_title(doc, pdf_path: Path, fitz) -> str:
    meta_title = (doc.metadata or {}).get("title") or ""
    meta_title = meta_title.strip()
    if meta_title and len(meta_title) > 3 and not meta_title.lower().endswith(".pdf"):
        return meta_title
    # Fallback: the largest-font line on the first page is usually the title.
    try:
        page = doc[0]
        d = page.get_text("dict")
        best_text, best_size = "", 0.0
        for block in d.get("blocks", []):
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                text = "".join(sp.get("text", "") for sp in spans).strip()
                if len(text) <= 3:
                    continue
                size = max(sp.get("size", 0.0) for sp in spans)
                if size > best_size:
                    best_size, best_text = size, text
        if best_text:
            return best_text
    except Exception:
        pass
    return pdf_path.stem


def _split_sections_by_font(lines: list[dict]) -> list[Section]:
    if not lines:
        return []
    long_sizes = [round(l["size"], 1) for l in lines if len(l["text"]) > 40]
    try:
        body_size = statistics.mode(long_sizes) if long_sizes else \
            statistics.median(round(l["size"], 1) for l in lines)
    except statistics.StatisticsError:
        body_size = round(lines[0]["size"], 1)

    sections: list[Section] = []
    cur_heading: str | None = None
    cur_body: list[str] = []

    def flush():
        if cur_heading is not None:
            sections.append(Section(cur_heading, "\n".join(cur_body).strip()))

    for l in lines:
        text, size, bold = l["text"], l["size"], l["bold"]
        plausible_heading = (
            len(text) < 100
            and not text.endswith((".", ",", ";"))
        )
        is_heading = plausible_heading and (
            size > body_size + 0.8
            or (bold and size >= body_size - 0.2 and len(text) < 80)
        )
        if is_heading:
            flush()
            cur_heading = text
            cur_body = []
        elif cur_heading is not None:
            cur_body.append(text)
        # else: text before the first detected heading is dropped (usually
        # running headers/byline noise); real content should still surface
        # in the regex fallback if this heuristic under-performs.
    flush()
    return sections


def _split_sections_by_regex(full_text: str) -> list[Section]:
    lines = full_text.splitlines()
    idx = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue
        if NUMBERED_HEADING_RE.match(s) or KEYWORD_HEADING_RE.match(s):
            idx.append(i)
    if not idx:
        return []
    sections = []
    for n, i in enumerate(idx):
        heading = lines[i].strip()
        end = idx[n + 1] if n + 1 < len(idx) else len(lines)
        body = "\n".join(lines[i + 1:end]).strip()
        sections.append(Section(heading, body))
    return sections


def _sections_look_reasonable(sections: list[Section]) -> bool:
    if not sections:
        return False
    total_chars = sum(len(s.text) for s in sections)
    return total_chars > 50 and len(sections) <= 60


def _pop_abstract(sections: list[Section]) -> tuple[str, list[Section]]:
    for i, s in enumerate(sections):
        if s.heading.strip().lower().startswith("abstract"):
            return s.text.strip(), sections[:i] + sections[i + 1:]
    return "", sections


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def _extract_figures(doc, work_dir: Path, fitz) -> list[str]:
    out_dir = work_dir / "figures"
    figures: list[str] = []
    seen_xrefs: set[int] = set()
    for pno in range(len(doc)):
        try:
            page = doc[pno]
            images = page.get_images(full=True)
        except Exception:
            continue
        for img_index, img in enumerate(images):
            xref = img[0]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)
            try:
                base = doc.extract_image(xref)
            except Exception:
                continue
            width, height = base.get("width", 0), base.get("height", 0)
            if width < 50 or height < 50:
                continue
            ext = base.get("ext", "png")
            try:
                out_dir.mkdir(parents=True, exist_ok=True)
                fname = f"page{pno + 1:03d}_img{img_index + 1:02d}.{ext}"
                fpath = out_dir / fname
                fpath.write_bytes(base["image"])
                figures.append(str(fpath))
            except Exception:
                continue
    return figures


# ---------------------------------------------------------------------------
# 3. plain text / markdown

MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(\S.*?)\s*$")


def _ingest_text(path: Path, work_dir: Path) -> Paper:
    raw = path.read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines()

    headings = []  # (line_index, level, text)
    for i, line in enumerate(lines):
        m = MD_HEADING_RE.match(line)
        if m:
            headings.append((i, len(m.group(1)), m.group(2).strip()))

    if headings:
        title = headings[0][2]
        sections, abstract = _md_sections(lines, headings, title)
    else:
        title = next((l.strip() for l in lines if l.strip()), path.stem)
        body = "\n".join(lines[1:]).strip() if lines else ""
        abstract, remainder = _extract_abstract_paragraph(body)
        # No markdown headings: try the same numbered/keyword heuristics
        # used for PDFs before giving up and using one big section.
        sections = _split_sections_by_regex(remainder)
        if not sections and remainder:
            sections = [Section("Body", remainder)]

    return Paper(title=title or path.stem, authors=[], abstract=abstract,
                 sections=sections, figures=[], source=str(path))


def _md_sections(lines: list[str], headings: list[tuple[int, int, str]],
                  title: str) -> tuple[list[Section], str]:
    sections: list[Section] = []
    abstract = ""

    start = 1 if headings[0][2] == title else 0

    # Text before the first *content* heading may hold an abstract. If the
    # very first heading is the title itself, this is the text directly
    # under it (title headings are usually followed by an abstract
    # paragraph, then the real section headings); otherwise it's whatever
    # precedes the first heading in the file.
    preamble_start = headings[0][0] + 1 if start == 1 else 0
    preamble_end = headings[start][0] if start < len(headings) else len(lines)
    preamble = "\n".join(lines[preamble_start:preamble_end]).strip()
    if preamble:
        abs_text, rest = _extract_abstract_paragraph(preamble)
        if abs_text:
            abstract = abs_text
        elif rest:
            sections.append(Section("Preamble", rest))

    for n in range(start, len(headings)):
        i, _level, htext = headings[n]
        end = headings[n + 1][0] if n + 1 < len(headings) else len(lines)
        body = "\n".join(lines[i + 1:end]).strip()
        if htext.strip().lower().startswith("abstract") and not abstract:
            abstract = body
            continue
        sections.append(Section(htext, body))

    return sections, abstract


def _extract_abstract_paragraph(text: str) -> tuple[str, str]:
    """Find a paragraph starting with "Abstract" and split it out."""
    if not text.strip():
        return "", text
    paragraphs = re.split(r"\n\s*\n", text)
    for idx, para in enumerate(paragraphs):
        stripped = para.strip()
        if re.match(r"(?i)^abstract\b[:\-]?\s*", stripped):
            content = re.sub(r"(?i)^abstract\b[:\-]?\s*", "", stripped, count=1).strip()
            remaining = paragraphs[:idx] + paragraphs[idx + 1:]
            if not content and idx + 1 < len(paragraphs):
                content = paragraphs[idx + 1].strip()
                remaining = paragraphs[:idx] + paragraphs[idx + 2:]
            return content, "\n\n".join(p for p in remaining if p.strip()).strip()
    return "", text
