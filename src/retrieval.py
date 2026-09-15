"""Hybrid retrieval over ingested BIS chunks: ChromaDB vector search plus BM25 keyword search.

How the hybrid ranking works (Reciprocal Rank Fusion, RRF):
1. If the query names an IS number that is in the index ("IS 14543 labelling"),
   both searches below are limited to that standard.
2. Vector search returns candidates ranked by cosine similarity of embeddings.
3. BM25 returns candidates ranked by keyword score. BM25 catches exact IS numbers
   ("IS 7098") and clause numbers ("5.1.2") that embeddings tend to blur.
4. Each candidate gets 1 / (RRF_K + rank) from every list it appears in (rank starts at 1).
   Scores are summed, so a chunk found by both methods appears once and ranks higher.
5. Results are sorted by that sum. The raw vector and BM25 scores are kept for inspection.

RRF uses ranks, not raw scores, so cosine similarities and BM25 scores never need to be
put on the same scale.

Run from the project root:
    python -m src.retrieval --rebuild                  # ingest data/raw and rebuild the index
    python -m src.retrieval "packaged drinking water"  # search
"""

import argparse
import json
import logging
import re
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

import chromadb
from chromadb.config import Settings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_huggingface import HuggingFaceEmbeddings
from rank_bm25 import BM25Okapi

import config
from src.ingestion import FileReport, IngestionResult, ingest_pdfs

logger = logging.getLogger(__name__)

# Standard RRF constant. Larger values flatten the gap between neighbouring ranks.
RRF_K = 60
# Each method returns this many candidates per requested result before fusion.
CANDIDATE_MULTIPLIER = 4
# Chunks written to Chroma per call.
BATCH_SIZE = 500
# Dropped from BM25 queries and text. "is" is here so that "IS 14543" searches on the number.
STOPWORDS = frozenset("a an and are as at be by for from in is it of on or that the this to with".split())
# A number with optional dotted parts ("5.1.2", "0.5"), or a run of letters.
TOKEN_PATTERN = re.compile(r"\d+(?:\.\d+)*|[^\W\d_]+")
# An IS number in a query, title or file name: "IS 14543", "IS:7098", "is.14543.2004.pdf".
IS_NUMBER_PATTERN = re.compile(r"\bIS\s*[:.\-]?\s*(\d+)", re.IGNORECASE)


@dataclass
class SearchResult:
    """One retrieved chunk with its citation metadata and scores."""

    text: str
    source: str
    source_path: str
    page: int
    title: str
    doc_id: str
    chunk_index: int
    score: float  # the ranking score: raw score for single-method search, RRF score for hybrid
    methods: list[str]  # "vector", "bm25" or both
    vector_score: float | None = None  # cosine similarity; higher is closer
    bm25_score: float | None = None

    @property
    def chunk_id(self) -> str:
        return make_chunk_id(self.doc_id, self.page, self.chunk_index)


@dataclass
class BM25Index:
    """BM25 over chunk text. `chunks[i]` is the chunk behind BM25 document i."""

    chunks: list[Document]
    bm25: BM25Okapi | None  # None when there is nothing to index


def make_chunk_id(doc_id: str, page: int, chunk_index: int) -> str:
    """Stable chunk ID. The same file content, page and chunk position always give the same ID."""
    return f"{doc_id}-p{page}-c{chunk_index}"


def tokenize(text: str) -> list[str]:
    """Lowercase word and number tokens for BM25.

    "IS 14543:2004" gives ["14543", "2004"], "IS14543" gives ["14543"], and "5.1.2" stays one token.
    """
    return [token for token in TOKEN_PATTERN.findall(text.lower()) if token not in STOPWORDS]


@lru_cache(maxsize=1)
def get_embeddings() -> HuggingFaceEmbeddings:
    """Load the local embedding model once per process. The first call downloads it."""
    return HuggingFaceEmbeddings(
        model_name=config.EMBEDDING_MODEL,
        model_kwargs={"device": config.EMBEDDING_DEVICE},
        encode_kwargs={"normalize_embeddings": True},
    )


def open_vector_store(
    persist_dir: Path = config.CHROMA_DIR,
    collection: str = config.CHROMA_COLLECTION,
    embeddings: Embeddings | None = None,
) -> Chroma:
    """Open (or create) the persistent Chroma collection. New collections use cosine distance."""
    client = chromadb.PersistentClient(path=str(persist_dir), settings=Settings(anonymized_telemetry=False))
    return Chroma(
        collection_name=collection,
        embedding_function=embeddings or get_embeddings(),
        client=client,
        collection_configuration={"hnsw": {"space": "cosine"}},
    )


def build_vector_index(chunks: list[Document], store: Chroma | None = None) -> Chroma:
    """Make the Chroma collection hold exactly these chunks. Safe to run repeatedly.

    Chunks are upserted under stable IDs, so a rerun overwrites entries instead of duplicating them.
    Entries whose IDs are not in `chunks` (from removed or changed PDFs) are deleted.
    """
    store = store or open_vector_store()
    ids = [make_chunk_id(c.metadata["doc_id"], c.metadata["page"], c.metadata["chunk_index"]) for c in chunks]

    stale = set(store.get(include=[])["ids"]) - set(ids)
    if stale:
        store.delete(ids=list(stale))
    for start in range(0, len(chunks), BATCH_SIZE):
        store.add_documents(chunks[start : start + BATCH_SIZE], ids=ids[start : start + BATCH_SIZE])
    return store


def load_indexed_chunks(store: Chroma) -> list[Document]:
    """Read every chunk back from Chroma, sorted by source, page and chunk index."""
    data = store.get(include=["documents", "metadatas"])
    chunks = [Document(page_content=text, metadata=meta) for text, meta in zip(data["documents"], data["metadatas"])]
    return sorted(chunks, key=lambda c: (c.metadata["source"], c.metadata["page"], c.metadata["chunk_index"]))


def build_bm25_index(chunks: list[Document]) -> BM25Index:
    """Build a BM25 index over each chunk's title and text.

    The title carries the IS number, so "IS 7098" also matches chunks whose text does not repeat it.
    """
    corpus = [tokenize(f"{chunk.metadata.get('title', '')}\n{chunk.page_content}") for chunk in chunks]
    return BM25Index(chunks=list(chunks), bm25=BM25Okapi(corpus) if any(corpus) else None)


def named_standard_doc_ids(query: str, chunks: list[Document]) -> set[str]:
    """Return the doc_ids of indexed standards whose IS number appears in the query.

    Returns an empty set when the query names no IS number, or only IS numbers that are not indexed.
    """
    numbers = set(IS_NUMBER_PATTERN.findall(query))
    if not numbers:
        return set()
    return {
        chunk.metadata["doc_id"]
        for chunk in chunks
        if numbers & set(IS_NUMBER_PATTERN.findall(f"{chunk.metadata['title']} {chunk.metadata['source']}"))
    }


def _to_result(chunk: Document, score: float, method: str) -> SearchResult:
    meta = chunk.metadata
    return SearchResult(
        text=chunk.page_content,
        source=meta["source"],
        source_path=meta["source_path"],
        page=meta["page"],
        title=meta["title"],
        doc_id=meta["doc_id"],
        chunk_index=meta["chunk_index"],
        score=score,
        methods=[method],
        vector_score=score if method == "vector" else None,
        bm25_score=score if method == "bm25" else None,
    )


def search_vector(
    store: Chroma, query: str, k: int = config.TOP_K, doc_ids: set[str] | None = None
) -> list[SearchResult]:
    """Top-k chunks by cosine similarity. A non-empty `doc_ids` limits the search to those documents."""
    if not query.strip():
        return []
    where = {"doc_id": {"$in": sorted(doc_ids)}} if doc_ids else None
    hits = store.similarity_search_with_score(query, k=k, filter=where)
    return [_to_result(chunk, 1.0 - distance, "vector") for chunk, distance in hits]


def search_bm25(
    index: BM25Index, query: str, k: int = config.TOP_K, doc_ids: set[str] | None = None
) -> list[SearchResult]:
    """Top-k chunks by BM25 score. A non-empty `doc_ids` limits the search to those documents.

    Chunks sharing no token with the query are not returned.
    """
    tokens = tokenize(query)
    if index.bm25 is None or not tokens:
        return []
    scores = index.bm25.get_scores(tokens)
    matches = [
        i for i, score in enumerate(scores)
        if score > 0 and (not doc_ids or index.chunks[i].metadata["doc_id"] in doc_ids)
    ]
    ranked = sorted(matches, key=lambda i: scores[i], reverse=True)[:k]
    return [_to_result(index.chunks[i], float(scores[i]), "bm25") for i in ranked]


def fuse_results(result_lists: list[list[SearchResult]], k: int = config.TOP_K) -> list[SearchResult]:
    """Merge ranked lists with Reciprocal Rank Fusion. Each chunk appears once, with summed score."""
    fused: dict[str, SearchResult] = {}
    for results in result_lists:
        for rank, result in enumerate(results, start=1):
            entry = fused.get(result.chunk_id)
            if entry is None:
                entry = fused[result.chunk_id] = replace(result, score=0.0, methods=[])
            entry.score += 1.0 / (RRF_K + rank)
            entry.methods += result.methods
            if result.vector_score is not None:
                entry.vector_score = result.vector_score
            if result.bm25_score is not None:
                entry.bm25_score = result.bm25_score
    return sorted(fused.values(), key=lambda r: r.score, reverse=True)[:k]


def hybrid_search(query: str, store: Chroma, bm25_index: BM25Index, k: int = config.TOP_K) -> list[SearchResult]:
    """Vector and BM25 search fused with RRF. See the module docstring for the algorithm.

    `bm25_index` must cover the same chunks as `store`; its chunk list is used to find named standards.
    """
    candidates = k * CANDIDATE_MULTIPLIER
    doc_ids = named_standard_doc_ids(query, bm25_index.chunks)
    return fuse_results(
        [search_vector(store, query, candidates, doc_ids), search_bm25(bm25_index, query, candidates, doc_ids)], k
    )


def save_ingestion_report(reports: list[FileReport], path: Path) -> None:
    """Save one row per PDF, so the app can tell which files were skipped and why."""
    rows = [
        {"source": r.path.name, "status": r.status, "reason": r.reason,
         "pages_total": r.pages_total, "pages_used": r.pages_used, "chunks": r.chunks}
        for r in reports
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2))


def load_unavailable_files(path: Path) -> dict[str, str]:
    """Map file name to reason for PDFs the last rebuild skipped or failed. Empty if there is no report."""
    try:
        rows = json.loads(path.read_text())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        logger.warning("Cannot read ingestion report %s: %s", path, exc)
        return {}
    return {row["source"]: row["reason"] for row in rows if row["status"] != "ok"}


def rebuild_index(store: Chroma | None = None, directory: Path | None = None, report_path: Path | None = None) -> IngestionResult:
    """Ingest the PDFs, sync the vector index and save the ingestion report."""
    result = ingest_pdfs(directory or config.RAW_DOCS_DIR)
    build_vector_index(result.chunks, store)
    save_ingestion_report(result.reports, report_path or config.INGESTION_REPORT)
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Search the ingested BIS documents.")
    parser.add_argument("query", nargs="?", help="search text")
    parser.add_argument("-k", type=int, default=config.TOP_K, help="number of results (default: %(default)s)")
    parser.add_argument("--rebuild", action="store_true", help="re-ingest data/raw and rebuild the index first")
    args = parser.parse_args(argv)
    if not args.query and not args.rebuild:
        parser.error("give a query, --rebuild, or both")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    store = open_vector_store()
    if args.rebuild or not store.get(limit=1, include=[])["ids"]:
        if not args.rebuild:
            print("Index is empty. Building it from data/raw first.")
        chunks = rebuild_index(store).chunks
        print(f"Indexed {len(chunks)} chunks in {config.CHROMA_DIR} (collection '{config.CHROMA_COLLECTION}').")
    if not args.query:
        return

    results = hybrid_search(args.query, store, build_bm25_index(load_indexed_chunks(store)), args.k)
    print(f'\nTop {len(results)} results for "{args.query}":')
    if not results:
        print("  No matching chunks.")
    for rank, result in enumerate(results, start=1):
        raw = []
        if result.vector_score is not None:
            raw.append(f"vector {result.vector_score:.3f}")
        if result.bm25_score is not None:
            raw.append(f"bm25 {result.bm25_score:.2f}")
        print(f"{rank}. {result.source}  page {result.page}  score {result.score:.4f}  [{', '.join(raw)}]")
        print(f"   {' '.join(result.text.split())[:160]}")


if __name__ == "__main__":
    main()
