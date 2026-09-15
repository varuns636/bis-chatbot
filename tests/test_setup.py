"""Phase 1 checks: dependencies import and config resolves. App rendering is covered in test_app.py."""

from pathlib import Path

import config

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_maintained_langchain_apis_import():
    from langchain_chroma import Chroma  # noqa: F401
    from langchain_core.documents import Document  # noqa: F401
    from langchain_huggingface import HuggingFaceEmbeddings  # noqa: F401
    from langchain_text_splitters import RecursiveCharacterTextSplitter  # noqa: F401


def test_core_libraries_import():
    import chromadb  # noqa: F401
    import pypdf  # noqa: F401
    import rank_bm25  # noqa: F401
    import sentence_transformers  # noqa: F401


def test_config_defaults():
    assert config.BASE_DIR == PROJECT_ROOT
    assert config.RAW_DOCS_DIR == PROJECT_ROOT / "data" / "raw"
    assert config.CHROMA_DIR.is_absolute()
    assert config.EMBEDDING_MODEL
    assert config.EMBEDDING_DEVICE
    assert 0 < config.MIN_VECTOR_SCORE < 1
    assert 0 < config.MIN_KEYWORD_OVERLAP <= 1
