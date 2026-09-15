"""Phase 3 tests for hybrid retrieval. Each test uses its own Chroma index in a temporary directory."""

import pytest
from langchain_core.documents import Document

from src.retrieval import (
    SearchResult,
    build_bm25_index,
    build_vector_index,
    fuse_results,
    get_embeddings,
    hybrid_search,
    load_indexed_chunks,
    make_chunk_id,
    open_vector_store,
    search_bm25,
    search_vector,
    tokenize,
)

WATER = ("is.14543.2004.pdf", "IS 14543 (2004): Packaged Drinking Water")
CABLE = ("is.7098.1.1988.pdf", "IS 7098-1 (1988): Crosslinked polyethylene insulated PVC sheathed cables")


def make_chunk(doc: tuple[str, str], page: int, chunk_index: int, text: str) -> Document:
    source, title = doc
    return Document(
        page_content=text,
        metadata={
            "source": source,
            "source_path": f"/data/raw/{source}",
            "page": page,
            "title": title,
            "page_char_count": len(text),
            "doc_id": source.split(".")[1],
            "chunk_index": chunk_index,
        },
    )


CHUNKS = [
    make_chunk(WATER, 5, 0, "5.1 Microbiological requirements. Packaged drinking water shall be free from E. coli and coliform bacteria."),
    make_chunk(WATER, 6, 0, "6 Packing and marking. Bottles shall be made of food grade plastic and sealed."),
    make_chunk(WATER, 6, 1, "The label shall state the batch number and the date of manufacture."),
    make_chunk(CABLE, 4, 0, "Crosslinked polyethylene (XLPE) insulated PVC sheathed cables for working voltage up to 1100 V."),
    make_chunk(CABLE, 9, 0, "7.2 Conductor resistance shall be measured at a temperature of 20 degrees Celsius."),
]


@pytest.fixture(scope="session")
def embeddings():
    return get_embeddings()


@pytest.fixture
def store(tmp_path, embeddings):
    return build_vector_index(CHUNKS, open_vector_store(tmp_path / "chroma", "test", embeddings))


@pytest.fixture
def bm25_index():
    return build_bm25_index(CHUNKS)


def stored_ids(store) -> set[str]:
    return set(store.get(include=[])["ids"])


def test_tokenize_keeps_is_and_clause_numbers():
    assert tokenize("IS 14543:2004 clause 5.1.2") == ["14543", "2004", "clause", "5.1.2"]
    assert tokenize("IS14543") == ["14543"]


def test_build_vector_index_stores_chunks_with_stable_ids(store):
    expected = {make_chunk_id(c.metadata["doc_id"], c.metadata["page"], c.metadata["chunk_index"]) for c in CHUNKS}
    assert stored_ids(store) == expected

    loaded = load_indexed_chunks(store)
    assert sorted((c.page_content, tuple(sorted(c.metadata.items()))) for c in loaded) == sorted(
        (c.page_content, tuple(sorted(c.metadata.items()))) for c in CHUNKS
    )


def test_rebuild_does_not_duplicate_and_removes_stale_chunks(store):
    build_vector_index(CHUNKS, store)
    assert len(stored_ids(store)) == len(CHUNKS)

    build_vector_index(CHUNKS[:3], store)
    assert len(stored_ids(store)) == 3


def test_build_bm25_index_keeps_chunk_order(bm25_index):
    assert bm25_index.chunks == CHUNKS
    assert bm25_index.bm25.corpus_size == len(CHUNKS)


def test_vector_search_natural_language_query(store):
    top = search_vector(store, "bacteria contamination in bottled water", k=1)[0]
    assert (top.source, top.page) == (WATER[0], 5)
    assert top.methods == ["vector"]


def test_bm25_exact_is_number(bm25_index):
    results = search_bm25(bm25_index, "IS 7098")
    assert {r.source for r in results} == {CABLE[0]}
    assert len(results) == 2


def test_bm25_clause_number(bm25_index):
    results = search_bm25(bm25_index, "clause 5.1")
    assert (results[0].source, results[0].page) == (WATER[0], 5)


def test_hybrid_search_returns_citation_metadata(store, bm25_index):
    results = hybrid_search("packaged drinking water", store, bm25_index, k=3)

    assert results[0].source == WATER[0]
    for result in results:
        assert result.source and result.source_path and result.title and result.doc_id
        assert isinstance(result.page, int) and isinstance(result.chunk_index, int)
        assert result.score > 0
        assert set(result.methods) <= {"vector", "bm25"}


def test_hybrid_search_exact_is_number(store, bm25_index):
    results = hybrid_search("IS 7098", store, bm25_index, k=2)
    assert {r.source for r in results} == {CABLE[0]}


def test_hybrid_search_limits_to_named_standard(store, bm25_index):
    results = hybrid_search("IS 14543 conductor resistance", store, bm25_index, k=5)
    assert results
    assert {r.source for r in results} == {WATER[0]}


def test_unindexed_is_number_does_not_filter(store, bm25_index):
    results = hybrid_search("IS 9999 conductor resistance", store, bm25_index, k=1)
    assert (results[0].source, results[0].page) == (CABLE[0], 9)


def test_hybrid_search_merges_chunks_found_by_both_methods(store, bm25_index):
    results = hybrid_search("microbiological requirements", store, bm25_index, k=5)

    assert len({r.chunk_id for r in results}) == len(results)
    assert results[0].methods == ["vector", "bm25"]
    assert results[0].vector_score is not None and results[0].bm25_score is not None


def test_fuse_results_sums_ranks_for_duplicates():
    def result(doc_id: str, method: str, score: float) -> SearchResult:
        return SearchResult("t", "s.pdf", "/s.pdf", 1, "T", doc_id, 0, score, [method],
                            vector_score=score if method == "vector" else None,
                            bm25_score=score if method == "bm25" else None)

    a_vector = result("A", "vector", 0.9)
    fused = fuse_results([[a_vector, result("B", "vector", 0.5)], [result("A", "bm25", 7.0), result("C", "bm25", 3.0)]], k=10)

    assert [r.doc_id for r in fused] == ["A", "B", "C"]
    assert fused[0].methods == ["vector", "bm25"]
    assert fused[0].score == pytest.approx(2 / 61)
    assert (fused[0].vector_score, fused[0].bm25_score) == (0.9, 7.0)
    assert a_vector.methods == ["vector"]  # inputs are not modified


def test_empty_query_returns_nothing(store, bm25_index):
    assert hybrid_search("   ", store, bm25_index) == []
    assert search_bm25(bm25_index, "the of and") == []


def test_no_indexed_documents(tmp_path, embeddings):
    empty_store = build_vector_index([], open_vector_store(tmp_path / "chroma", "empty", embeddings))
    empty_bm25 = build_bm25_index([])

    assert load_indexed_chunks(empty_store) == []
    assert empty_bm25.bm25 is None
    assert hybrid_search("packaged drinking water", empty_store, empty_bm25) == []
