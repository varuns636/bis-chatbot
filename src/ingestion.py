"""PDF ingestion: read BIS PDFs page by page, keep citation metadata, split into chunks.

Run from the project root:  python -m src.ingestion
"""

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

import config

logger = logging.getLogger(__name__)

# pypdf logs a warning for every malformed object in scanned PDFs. Keep only real errors.
logging.getLogger("pypdf").setLevel(logging.ERROR)

# A page with less text than this is treated as blank (for example, only a page number).
MIN_PAGE_CHARS = 30
# A document with less usable text than this gets a warning.
MIN_DOC_CHARS = 500
# If more than this share of pages is blank, the PDF is probably scanned and needs OCR.
SCANNED_PAGE_RATIO = 0.5
# Public.Resource.Org adds this cover page to its RTI copies of Indian Standards.
# It is the same on every file, so it adds retrieval noise and no facts.
BOILERPLATE_PAGE_PREFIXES = ("Disclosure to Promote the Right To Information",)

# --- Title, IS numbers and document type, read from the first usable page ---
# Many BIS PDFs carry no usable metadata title: press notes, product manuals and summary
# sheets. For those, the title is read from the heading at the top of the first usable page.

# Lines of the BIS letterhead and the press-note header. They open many documents and name none.
HEADING_NOISE_PATTERN = re.compile(
    r"^(bureau of indian standards|manak bhawan\b.*|new delhi\b.*|for immediate release"
    r"|press[\s_-]?(note|release)\b.*|government of india|[\d\s,./-]+)$",
    re.IGNORECASE,
)
# A line with any Devanagari character is the Hindi half of a bilingual document.
DEVANAGARI_PATTERN = re.compile(r"[\u0900-\u097F]")
# Lines read from the top of the page: the title comes from them, and so do the document's IS numbers.
HEADING_LINES = 8
# A title stops once it is this long. Long enough for a multi-line title, short enough to drop body text.
HEADING_CHARS = 110
MIN_HEADING_LINE_CHARS = 8

# Document types, used for labels in the UI and in refusals. "standard" is an Indian Standard
# itself. The other types are BIS documents *about* standards and services.
DOC_TYPE_RULES = (
    ("standard", re.compile(r"^IS\s*[:.\-]?\s*\d+", re.IGNORECASE)),
    ("product_manual", re.compile(r"\bproduct manual\b|\bPM[/_]", re.IGNORECASE)),
    # "_" is a word character, so the match ends on a lookahead: "Press_Release_Milestones.pdf".
    ("press_release", re.compile(r"\bpress[\s_-]?(note|release)s?(?![A-Za-z])|for immediate release", re.IGNORECASE)),
    ("summary", re.compile(r"\bsummary of indian standards?\b", re.IGNORECASE)),
    ("act", re.compile(r"\bact,?\s*\d{4}\b", re.IGNORECASE)),
)
DOC_TYPE_LABELS = {
    "standard": "Indian Standard",
    "act": "Act",
    "product_manual": "Product manual",
    "press_release": "Press release",
    "summary": "Standard summary",
    "document": "BIS document",
}
DOC_TYPE_PLURALS = {
    "standard": "Indian Standards",
    "act": "Acts",
    "product_manual": "Product manuals",
    "press_release": "Press releases",
    "summary": "Standard summaries",
    "document": "BIS documents",
}
# An IS number in a title, heading or file name: "IS 14543", "IS:7098", "PM/IS 302-1", "is.14543.2004.pdf".
# The lookahead rejects a thousands separator, so "1,43,497 jewellers" is not read as "IS 1".
IS_NUMBER_PATTERN = re.compile(r"\bIS\s*[:.\-]?\s*(\d+)(?!,\d)", re.IGNORECASE)


@dataclass
class FileReport:
    """Outcome of ingesting one PDF."""

    path: Path
    status: str = "ok"  # "ok", "skipped" or "failed"
    reason: str = ""
    pages_total: int = 0
    pages_used: int = 0
    chunks: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class IngestionResult:
    """Chunks from all PDFs plus one report per discovered file."""

    chunks: list[Document] = field(default_factory=list)
    reports: list[FileReport] = field(default_factory=list)


def discover_pdf_files(directory: Path = config.RAW_DOCS_DIR) -> list[Path]:
    """Return PDF files under a directory (subfolders included), sorted by path.

    Hidden files, such as macOS "._" resource forks, are ignored. A missing directory returns [].
    """
    if not directory.is_dir():
        logger.warning("Document directory not found: %s", directory)
        return []
    return sorted(
        path
        for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() == ".pdf" and not path.name.startswith(".")
    )


def file_sha256(path: Path) -> str:
    """Hash file contents. Used to detect duplicate PDFs and as a stable document ID."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def clean_text(text: str) -> str:
    """Normalize whitespace from PDF extraction. Paragraph breaks are kept."""
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _metadata_title(reader: PdfReader) -> str:
    """Title from the PDF metadata, or "" when the PDF has no usable one.

    Metadata titles that are just a file name (for example "5296GI.p65", left by the
    authoring tool in the BIS Act PDF) are ignored.
    """
    try:
        title = reader.metadata.title if reader.metadata else None
    except Exception:  # malformed metadata is common in scanned PDFs
        title = None
    title = str(title).strip() if title else ""
    return "" if re.fullmatch(r"[\w .-]+\.\w{2,4}", title) else title


def heading_lines(text: str, limit: int = HEADING_LINES) -> list[str]:
    """The first `limit` lines of real heading text at the top of a page.

    Blank lines, Devanagari lines of a bilingual document, letterhead and press-note header
    lines, and lines too short to be a title are all dropped.
    """
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            if lines:  # a blank line after the heading ends it
                break
            continue
        if len(line) < MIN_HEADING_LINE_CHARS or DEVANAGARI_PATTERN.search(line):
            continue
        if HEADING_NOISE_PATTERN.fullmatch(line) or not re.search(r"[A-Za-z]", line):
            continue
        lines.append(line)
        if len(lines) == limit:
            break
    return lines


def content_title(text: str, fallback: str) -> str:
    """Title read from the heading at the top of a page. `fallback` is used when there is none.

    Heading lines are joined until the title reaches HEADING_CHARS, which keeps a title that
    runs over several lines ("PRODUCT MANUAL FOR / SAFETY OF ...") and stops before the body text.
    """
    title = ""
    for line in heading_lines(text):
        title = f"{title} {line}".strip()
        # A line that closes a sentence or a bracket ends the title; body text follows it.
        if len(title) >= HEADING_CHARS or line.endswith((".", "]")):
            break
    return title.rstrip(" ,-:;") or fallback


def document_standards(title: str, file_name: str, heading: str = "") -> list[str]:
    """IS numbers this document is about, from its title, file name and page heading.

    Only the heading is read, never the body, so a product manual that mentions IS 1293 for its
    plugs is not treated as a copy of IS 1293. The result is sorted, without repeats.
    """
    return sorted({n for text in (title, file_name, heading) for n in IS_NUMBER_PATTERN.findall(text)}, key=int)


def classify_document(title: str, file_name: str, heading: str = "") -> str:
    """The kind of BIS document this is: see DOC_TYPE_RULES. Falls back to "document"."""
    for doc_type, pattern in DOC_TYPE_RULES:
        if pattern.search(title) or pattern.search(file_name) or pattern.search(heading):
            return doc_type
    return "document"


def extract_pdf_pages(path: Path, doc_id: str | None = None) -> list[Document]:
    """Extract every page of a PDF as one Document, blank pages included.

    Page numbers start at 1. Raises an exception if the file cannot be opened as a PDF.
    """
    reader = PdfReader(path)
    if reader.is_encrypted and not reader.decrypt(""):
        raise ValueError("PDF is encrypted and needs a password")

    doc_id = doc_id or file_sha256(path)[:16]
    texts = []
    for number, page in enumerate(reader.pages, start=1):
        try:
            texts.append(clean_text(page.extract_text() or ""))
        except Exception as exc:  # one unreadable page must not lose the whole file
            logger.warning("%s page %d: text extraction failed (%s)", path.name, number, exc)
            texts.append("")

    # The first page that is neither blank nor a stock cover page carries the heading.
    first_text = next(
        (t for t in texts if len(t) >= MIN_PAGE_CHARS and not t.startswith(BOILERPLATE_PAGE_PREFIXES)), ""
    )
    heading = "\n".join(heading_lines(first_text))
    title = _metadata_title(reader) or content_title(first_text, path.stem)
    standards = document_standards(title, path.name, heading)
    doc_type = classify_document(title, path.name, heading)

    return [
        Document(
            page_content=text,
            metadata={
                "source": path.name,
                "source_path": str(path.resolve()),
                "page": number,
                "title": title,
                "page_char_count": len(text),
                "doc_id": doc_id,
                # Chroma metadata values must be scalars, so the IS numbers are stored as
                # a comma-separated string. Use src.retrieval.chunk_standards() to read it back.
                "standards": ",".join(standards),
                "doc_type": doc_type,
            },
        )
        for number, text in enumerate(texts, start=1)
    ]


def is_blank_page(page: Document) -> bool:
    return len(page.page_content) < MIN_PAGE_CHARS


def is_boilerplate_page(page: Document) -> bool:
    return page.page_content.startswith(BOILERPLATE_PAGE_PREFIXES)


def split_documents(
    pages: list[Document],
    chunk_size: int = config.CHUNK_SIZE,
    chunk_overlap: int = config.CHUNK_OVERLAP,
) -> list[Document]:
    """Split pages into chunks. Chunks never cross pages, so each chunk cites exactly one page.

    Every chunk keeps its page metadata and gets a "chunk_index" within that page.
    """
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks = []
    for page in pages:
        for index, chunk in enumerate(splitter.split_documents([page])):
            chunk.metadata["chunk_index"] = index
            chunks.append(chunk)
    return chunks


def _ingest_file(
    path: Path,
    report: FileReport,
    seen_hashes: dict[str, Path],
    chunk_size: int,
    chunk_overlap: int,
) -> list[Document]:
    """Ingest one PDF and fill in its report. Exceptions propagate to the caller."""
    file_hash = file_sha256(path)
    if file_hash in seen_hashes:
        report.status = "skipped"
        report.reason = f"duplicate of {seen_hashes[file_hash].name}"
        return []
    seen_hashes[file_hash] = path

    pages = extract_pdf_pages(path, doc_id=file_hash[:16])
    blank = sum(is_blank_page(page) for page in pages)
    usable = [page for page in pages if not is_blank_page(page) and not is_boilerplate_page(page)]
    report.pages_total = len(pages)
    report.pages_used = len(usable)

    if not pages:
        report.status = "skipped"
        report.reason = "PDF has no pages"
        return []
    if not usable:
        report.status = "skipped"
        report.reason = f"no usable text ({blank} of {len(pages)} pages blank; likely scanned, OCR needed)"
        return []
    if blank / len(pages) > SCANNED_PAGE_RATIO:
        report.warnings.append(f"{blank} of {len(pages)} pages have no text; likely scanned, OCR needed")
    if sum(len(page.page_content) for page in usable) < MIN_DOC_CHARS:
        report.warnings.append("very little text extracted; check the PDF")

    chunks = split_documents(usable, chunk_size, chunk_overlap)
    report.chunks = len(chunks)
    return chunks


def ingest_pdfs(
    directory: Path = config.RAW_DOCS_DIR,
    chunk_size: int = config.CHUNK_SIZE,
    chunk_overlap: int = config.CHUNK_OVERLAP,
) -> IngestionResult:
    """Ingest every PDF in a directory into page-aware chunks.

    A PDF that cannot be read is reported as failed, and the run continues with the next file.
    """
    if not 0 <= chunk_overlap < chunk_size:
        raise ValueError(f"chunk_overlap ({chunk_overlap}) must be >= 0 and less than chunk_size ({chunk_size})")

    result = IngestionResult()
    seen_hashes: dict[str, Path] = {}
    for path in discover_pdf_files(directory):
        report = FileReport(path=path)
        result.reports.append(report)
        try:
            result.chunks.extend(_ingest_file(path, report, seen_hashes, chunk_size, chunk_overlap))
        except Exception as exc:  # one bad PDF must not stop the batch
            report.status = "failed"
            report.reason = f"{type(exc).__name__}: {exc}"
        if report.status != "ok":
            logger.warning("%s %s: %s", report.status.capitalize(), path.name, report.reason)
        for warning in report.warnings:
            logger.warning("%s: %s", path.name, warning)
    return result


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    result = ingest_pdfs()

    print(f"\nDirectory: {config.RAW_DOCS_DIR}")
    for report in result.reports:
        line = f"  [{report.status}] {report.path.name}: {report.pages_used}/{report.pages_total} pages used, {report.chunks} chunks"
        print(line + (f" ({report.reason})" if report.reason else ""))
        for warning in report.warnings:
            print(f"      warning: {warning}")

    print(f"PDFs discovered: {len(result.reports)}")
    print(f"Pages extracted: {sum(r.pages_total for r in result.reports)} ({sum(r.pages_used for r in result.reports)} used)")
    print(f"Chunks created:  {len(result.chunks)}")
    documents = {}
    for chunk in result.chunks:
        meta = chunk.metadata
        documents[meta["doc_id"]] = (DOC_TYPE_LABELS[meta["doc_type"]], meta["standards"], meta["title"])
    if documents:
        print("\nDocuments:")
        for label, standards, title in sorted(documents.values()):
            covers = f" (covers IS {', IS '.join(standards.split(','))})" if standards else ""
            print(f"  [{label}]{covers} {title}")

    if result.chunks:
        sample = result.chunks[0]
        print(f"\nSample chunk metadata: {sample.metadata}")
        print(f"Sample chunk text: {sample.page_content[:200]!r}")


if __name__ == "__main__":
    main()
