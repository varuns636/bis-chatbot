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


def _document_title(reader: PdfReader, path: Path) -> str:
    """Title from the PDF metadata, or the file name when the PDF has no usable title.

    Metadata titles that are just a file name (for example "5296GI.p65", left by the
    authoring tool in the BIS Act PDF) are ignored.
    """
    try:
        title = reader.metadata.title if reader.metadata else None
    except Exception:  # malformed metadata is common in scanned PDFs
        title = None
    title = str(title).strip() if title else ""
    if not title or re.fullmatch(r"[\w .-]+\.\w{2,4}", title):
        return path.stem
    return title


def extract_pdf_pages(path: Path, doc_id: str | None = None) -> list[Document]:
    """Extract every page of a PDF as one Document, blank pages included.

    Page numbers start at 1. Raises an exception if the file cannot be opened as a PDF.
    """
    reader = PdfReader(path)
    if reader.is_encrypted and not reader.decrypt(""):
        raise ValueError("PDF is encrypted and needs a password")

    doc_id = doc_id or file_sha256(path)[:16]
    title = _document_title(reader, path)
    pages = []
    for number, page in enumerate(reader.pages, start=1):
        try:
            text = clean_text(page.extract_text() or "")
        except Exception as exc:  # one unreadable page must not lose the whole file
            logger.warning("%s page %d: text extraction failed (%s)", path.name, number, exc)
            text = ""
        pages.append(
            Document(
                page_content=text,
                metadata={
                    "source": path.name,
                    "source_path": str(path.resolve()),
                    "page": number,
                    "title": title,
                    "page_char_count": len(text),
                    "doc_id": doc_id,
                },
            )
        )
    return pages


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
    if result.chunks:
        sample = result.chunks[0]
        print(f"\nSample chunk metadata: {sample.metadata}")
        print(f"Sample chunk text: {sample.page_content[:200]!r}")


if __name__ == "__main__":
    main()
