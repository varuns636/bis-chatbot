"""Phase 2 tests for PDF ingestion. Test PDFs are generated in temporary directories."""

import shutil
from pathlib import Path

from src.ingestion import (
    classify_document,
    content_title,
    discover_pdf_files,
    document_standards,
    extract_pdf_pages,
    heading_lines,
    ingest_pdfs,
    split_documents,
)

LINE = "Packaged drinking water shall comply with the requirements of this standard."


def _pdf_string(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(path: Path, pages: list[str], title: str | None = None) -> Path:
    """Write a minimal text PDF. Each item is one page; "" gives a blank page."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{' '.join(f'{5 + 2 * i} 0 R' for i in range(len(pages)))}] /Count {len(pages)} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for i, text in enumerate(pages):
        lines = " ".join(f"({_pdf_string(line)}) Tj T*" for line in text.splitlines())
        stream = f"BT /F1 10 Tf 14 TL 50 800 Td {lines} ET".encode("latin-1")
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {4 + 2 * i} 0 R >>".encode()
        )
    info = ""
    if title:
        objects.append(f"<< /Title ({_pdf_string(title)}) >>".encode())
        info = f" /Info {len(objects)} 0 R"

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{offset:010d} 00000 n \n" for offset in offsets).encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R{info} >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))
    return path


def long_page(lines: int = 40) -> str:
    return "\n".join(f"{i}. {LINE}" for i in range(lines))


def sources(chunks) -> set[str]:
    return {chunk.metadata["source"] for chunk in chunks}


def test_discover_pdf_files_sorted_recursive_and_filtered(tmp_path):
    for name in ["b.pdf", "a.PDF", "notes.txt", ".hidden.pdf", "sub/c.pdf"]:
        file = tmp_path / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"")

    found = discover_pdf_files(tmp_path)

    assert [path.relative_to(tmp_path).as_posix() for path in found] == ["a.PDF", "b.pdf", "sub/c.pdf"]


def test_discover_pdf_files_empty_and_missing_directory(tmp_path):
    assert discover_pdf_files(tmp_path) == []
    assert discover_pdf_files(tmp_path / "missing") == []


def test_extract_pdf_pages_text_and_page_numbers(tmp_path):
    pdf = make_pdf(tmp_path / "std.pdf", ["First page about cement grades.", "", "Third page about steel bars."])

    pages = extract_pdf_pages(pdf)

    assert [page.metadata["page"] for page in pages] == [1, 2, 3]
    assert "cement grades" in pages[0].page_content
    assert pages[1].page_content == ""
    assert "steel bars" in pages[2].page_content


def test_extract_pdf_pages_metadata(tmp_path):
    pdf = make_pdf(tmp_path / "is.123.pdf", ["Scope of this standard covers helmets."], title="IS 123: Helmets")

    page = extract_pdf_pages(pdf)[0]

    assert page.metadata["source"] == "is.123.pdf"
    assert page.metadata["source_path"] == str(pdf.resolve())
    assert page.metadata["title"] == "IS 123: Helmets"
    assert page.metadata["page_char_count"] == len(page.page_content)
    assert len(page.metadata["doc_id"]) == 16


def test_title_falls_back_to_file_name(tmp_path):
    pdf = make_pdf(tmp_path / "is.456.pdf", ["Some text on this page."])

    assert extract_pdf_pages(pdf)[0].metadata["title"] == "is.456"


def test_title_that_is_a_file_name_is_read_from_the_page(tmp_path):
    pdf = make_pdf(tmp_path / "BIS-Act-2016.pdf", ["The Bureau of Indian Standards Act, 2016."], title="5296GI.p65")

    page = extract_pdf_pages(pdf)[0]

    assert page.metadata["title"] == "The Bureau of Indian Standards Act, 2016."
    assert page.metadata["doc_type"] == "act"


# The heading rules are tested on page text: make_pdf's generator cannot write blank lines
# or Devanagari, and both matter here.
PRODUCT_MANUAL_PAGE = (
    "BUREAU OF INDIAN STANDARDS\n"
    "Manak Bhawan, 9, Bahadur Shah Zafar Marg\n"
    "\u0909\u0924\u094d\u092a\u093e\u0926 \u092e\u0948\u0928\u094d\u092f\u0941\u0905\u0932\n"
    "PRODUCT MANUAL FOR\n"
    "SAFETY OF HOUSEHOLD AND SIMILAR ELECTRICAL APPLIANCES\n"
    "ACCORDING TO IS 302-1 : 2008\n"
    "\n"
    "Plugs shall be as per IS 1293 and cables as per IS 694, tested by the licensee."
)
PRESS_RELEASE_PAGE = (
    "BUREAU OF INDIAN STANDARDS\n"
    "FOR IMMEDIATE RELEASE\n"
    "Press Note: PRD/Press Note/12/2022-23 31-Aug-2022\n"
    "\n"
    "Milestones in Hallmark Scheme\n"
    "\n"
    "Gold is too soft to withstand wear and tear, so it is always alloyed with another metal."
)


def test_heading_skips_the_letterhead_and_the_hindi_half():
    assert heading_lines(PRODUCT_MANUAL_PAGE) == [
        "PRODUCT MANUAL FOR",
        "SAFETY OF HOUSEHOLD AND SIMILAR ELECTRICAL APPLIANCES",
        "ACCORDING TO IS 302-1 : 2008",
    ]


def test_heading_stops_at_the_blank_line_before_the_body():
    assert heading_lines(PRESS_RELEASE_PAGE) == ["Milestones in Hallmark Scheme"]
    assert content_title(PRESS_RELEASE_PAGE, "fallback") == "Milestones in Hallmark Scheme"


def test_content_title_joins_a_title_that_runs_over_several_lines():
    assert content_title(PRODUCT_MANUAL_PAGE, "fallback") == (
        "PRODUCT MANUAL FOR SAFETY OF HOUSEHOLD AND SIMILAR ELECTRICAL APPLIANCES ACCORDING TO IS 302-1 : 2008"
    )


def test_standards_come_from_the_heading_not_the_body():
    """A product manual that names IS 1293 for its plugs is not a copy of IS 1293."""
    heading = "\n".join(heading_lines(PRODUCT_MANUAL_PAGE))

    assert document_standards("PRODUCT MANUAL FOR ...", "PM_302-1.pdf", heading) == ["302"]
    assert document_standards("IS 14543 (2004): Packaged Drinking Water", "is.14543.2004.pdf") == ["14543"]


def test_classify_document_reads_the_type_from_title_file_name_or_heading():
    assert classify_document("IS 14543 (2004): Packaged Drinking Water", "is.14543.2004.pdf") == "standard"
    assert classify_document("PRODUCT MANUAL FOR ...", "PM_302-1.pdf") == "product_manual"
    assert classify_document("Milestones in Hallmark Scheme", "Press_Release_Hallmark.pdf") == "press_release"
    assert classify_document("Summary of Indian Standards IS 1417:2016", "tbl5.pdf") == "summary"
    assert classify_document("The Bureau of Indian Standards Act, 2016", "BIS-Act-2016.pdf") == "act"
    assert classify_document("Notes on testing", "notes.pdf") == "document"


def test_split_documents_preserves_page_metadata(tmp_path):
    pdf = make_pdf(tmp_path / "long.pdf", ["Short first page with enough text to keep.", long_page()])
    pages = extract_pdf_pages(pdf)

    chunks = split_documents(pages, chunk_size=300, chunk_overlap=50)

    page_two = [chunk for chunk in chunks if chunk.metadata["page"] == 2]
    assert len(page_two) > 1
    assert [chunk.metadata["chunk_index"] for chunk in page_two] == list(range(len(page_two)))
    assert all(len(chunk.page_content) <= 300 for chunk in chunks)
    for chunk in chunks:
        page = pages[chunk.metadata["page"] - 1]
        assert page.metadata.items() <= chunk.metadata.items()


def test_ingest_pdfs_returns_cited_chunks(tmp_path):
    make_pdf(tmp_path / "good.pdf", [long_page()], title="IS 1: Good")

    result = ingest_pdfs(tmp_path, chunk_size=300, chunk_overlap=50)

    assert result.reports[0].status == "ok"
    assert result.reports[0].chunks == len(result.chunks) > 1
    assert sources(result.chunks) == {"good.pdf"}
    assert {chunk.metadata["page"] for chunk in result.chunks} == {1}


def test_ingest_pdfs_continues_after_bad_files(tmp_path):
    (tmp_path / "corrupt.pdf").write_bytes(b"%PDF-1.4 this is not really a pdf")
    (tmp_path / "empty.pdf").write_bytes(b"")
    make_pdf(tmp_path / "blank.pdf", ["", "", ""])
    make_pdf(tmp_path / "good.pdf", [long_page()])

    result = ingest_pdfs(tmp_path)

    statuses = {report.path.name: report.status for report in result.reports}
    assert statuses == {"blank.pdf": "skipped", "corrupt.pdf": "failed", "empty.pdf": "failed", "good.pdf": "ok"}
    assert sources(result.chunks) == {"good.pdf"}


def test_ingest_pdfs_directory_without_pdfs(tmp_path):
    (tmp_path / "readme.txt").write_text("not a pdf")

    result = ingest_pdfs(tmp_path)

    assert result.chunks == []
    assert result.reports == []


def test_ingest_pdfs_skips_duplicates(tmp_path):
    original = make_pdf(tmp_path / "a.pdf", [long_page()])
    shutil.copy(original, tmp_path / "b_copy.pdf")

    result = ingest_pdfs(tmp_path)

    first, copy = result.reports
    assert first.status == "ok"
    assert copy.status == "skipped"
    assert copy.reason == "duplicate of a.pdf"
    assert sources(result.chunks) == {"a.pdf"}


def test_ingest_pdfs_drops_rti_cover_page(tmp_path):
    cover = "Disclosure to Promote the Right To Information\nWhereas the Parliament of India has set out"
    make_pdf(tmp_path / "rti.pdf", [cover, long_page()])

    result = ingest_pdfs(tmp_path)

    assert {chunk.metadata["page"] for chunk in result.chunks} == {2}


def test_ingest_pdfs_warns_on_scanned_and_thin_documents(tmp_path):
    make_pdf(tmp_path / "scanned.pdf", ["Only the cover page has a text layer.", "", "", ""])

    report = ingest_pdfs(tmp_path).reports[0]

    assert report.status == "ok"
    assert (report.pages_used, report.pages_total) == (1, 4)
    assert any("OCR" in warning for warning in report.warnings)
    assert any("very little text" in warning for warning in report.warnings)
