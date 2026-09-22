"""Optional local document retrieval with LangChain and ChromaDB."""

import hashlib
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DEFAULT_DOCUMENTS_DIR = os.getenv("RAG_DOCUMENTS_DIR", "knowledge_base")
DEFAULT_DATABASE_DIR = os.getenv("RAG_PERSIST_DIRECTORY", "chroma_db")
DEFAULT_COLLECTION = "robot_knowledge"
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def _rag_dependencies():
    try:
        from langchain_chroma import Chroma
        from langchain_core.documents import Document
        from langchain_huggingface import HuggingFaceEmbeddings
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ImportError as error:
        raise RuntimeError("RAG packages are missing. Run: pip install -r requirements.txt") from error
    return Chroma, Document, HuggingFaceEmbeddings, RecursiveCharacterTextSplitter


@lru_cache(maxsize=1)
def _get_embeddings():
    """Load the local embedding model once and reuse it within this process."""
    _, _, HuggingFaceEmbeddings, _ = _rag_dependencies()
    return HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL_NAME)


def _load_documents(documents_dir: Path, document_class):
    documents = []
    for path in documents_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in {".txt", ".md"}:
            content = path.read_text(encoding="utf-8", errors="ignore").strip()
            if content:
                documents.append(document_class(page_content=content, metadata={"source": str(path)}))
        elif path.suffix.lower() == ".pdf":
            try:
                from langchain_community.document_loaders import PyPDFLoader

                documents.extend(PyPDFLoader(str(path)).load())
            except Exception as error:
                raise RuntimeError(f"Could not read PDF: {path}") from error
    return documents


def build_or_update_knowledge_base(
    documents_dir: str = DEFAULT_DOCUMENTS_DIR,
    persist_directory: str = DEFAULT_DATABASE_DIR,
) -> int:
    """Rebuild the local ChromaDB collection from .txt, .md, and .pdf files.

    Despite its original name, this currently replaces the existing collection;
    it does not incrementally update individual documents.
    """
    source_directory = Path(documents_dir)
    if not source_directory.is_dir():
        return 0

    Chroma, Document, _, TextSplitter = _rag_dependencies()
    documents = _load_documents(source_directory, Document)
    if not documents:
        return 0

    chunks = TextSplitter(chunk_size=800, chunk_overlap=120).split_documents(documents)
    embeddings = _get_embeddings()
    database_directory = Path(persist_directory)

    if database_directory.exists():
        existing_store = Chroma(
            collection_name=DEFAULT_COLLECTION,
            persist_directory=str(database_directory),
            embedding_function=embeddings,
        )
        try:
            existing_store.delete_collection()
        except Exception:
            pass

    ids = [
        hashlib.sha256(f"{chunk.metadata.get('source', '')}:{chunk.page_content}".encode()).hexdigest()
        for chunk in chunks
    ]
    Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        ids=ids,
        collection_name=DEFAULT_COLLECTION,
        persist_directory=str(database_directory),
    )
    return len(chunks)


def get_context(query: str, k: int = 3, persist_directory: str = DEFAULT_DATABASE_DIR) -> str:
    """Return relevant local document text, or an empty string when RAG is unavailable."""
    database_directory = Path(persist_directory)
    if not database_directory.is_dir() or not any(database_directory.iterdir()):
        return ""

    try:
        Chroma, _, _, _ = _rag_dependencies()
        embeddings = _get_embeddings()
        store = Chroma(
            collection_name=DEFAULT_COLLECTION,
            persist_directory=str(database_directory),
            embedding_function=embeddings,
        )
        documents = store.similarity_search(query, k=k)
    except Exception:
        return ""

    return "\n\n".join(document.page_content for document in documents)
