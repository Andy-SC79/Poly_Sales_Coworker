"""
core/knowledge/catalog.py
--------------------------
RAG (Retrieval-Augmented Generation) engine for the product catalog.
Uses Qdrant as the vector store and OpenAI embeddings for similarity search.

Products, PDFs, and documents are indexed here and retrieved by agents
when answering product-related questions.
"""
import structlog
from pathlib import Path
from langchain_qdrant import QdrantVectorStore
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from config.settings import get_settings

settings = get_settings()
log = structlog.get_logger()

EMBEDDING_DIM = 1536  # text-embedding-3-small


def _get_embeddings() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=settings.openai_api_key,
    )


async def get_vector_store() -> QdrantVectorStore:
    """Return a Qdrant vector store connected to the catalog collection."""
    # Use synchronous client for initialization (better compatibility with LangChain wrapper)
    client = QdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
    )

    # Create collection if it doesn't exist
    existing = client.get_collections()
    names = [c.name for c in existing.collections]
    if settings.qdrant_collection_name not in names:
        client.create_collection(
            collection_name=settings.qdrant_collection_name,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )
        log.info("qdrant.collection_created", name=settings.qdrant_collection_name)

    return QdrantVectorStore(
        client=client,
        collection_name=settings.qdrant_collection_name,
        embedding=_get_embeddings(),
    )


async def search_products(query: str, k: int = 3) -> list[Document]:
    """
    Search the product catalog for documents relevant to the query.
    Used by the Presentation Agent to build personalized recommendations.
    """
    store = await get_vector_store()
    results = await store.asimilarity_search(query, k=k)
    log.info("catalog.search", query=query, results=len(results))
    return results


async def index_documents(documents: list[Document]) -> None:
    """
    Add documents to the vector store.
    Called by the worker when the admin uploads a PDF or product list.
    """
    store = await get_vector_store()
    await store.aadd_documents(documents)
    log.info("catalog.indexed", count=len(documents))


async def index_text(text: str, metadata: dict | None = None) -> None:
    """Convenience wrapper: index a raw text string."""
    doc = Document(page_content=text, metadata=metadata or {})
    await index_documents([doc])
