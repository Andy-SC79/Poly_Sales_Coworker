"""
core/knowledge/catalog.py
--------------------------
RAG (Retrieval-Augmented Generation) engine for the product catalog.
Uses Supabase pgvector as the vector store and OpenAI embeddings for similarity search.

Products, PDFs, and documents are indexed here and retrieved by agents
when answering product-related questions.
"""
import structlog
from pathlib import Path
from langchain_community.vectorstores import SupabaseVectorStore
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document

from config.settings import get_settings
from integrations.supabase_client import get_supabase

settings = get_settings()
log = structlog.get_logger()

EMBEDDING_DIM = 1536  # text-embedding-3-small


def _get_embeddings() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=settings.openai_api_key,
    )


async def get_vector_store() -> SupabaseVectorStore:
    """Return a Supabase vector store connected to the catalog table."""
    client = get_supabase()
    
    return SupabaseVectorStore(
        client=client,
        embedding=_get_embeddings(),
        table_name="catalog",
        query_name="match_catalog"
    )

async def get_episodic_vector_store() -> SupabaseVectorStore:
    """Return a Supabase vector store connected to the episodic_memories table."""
    client = get_supabase()
    
    return SupabaseVectorStore(
        client=client,
        embedding=_get_embeddings(),
        table_name="episodic_memories",
        query_name="match_memories"
    )

async def search_products(query: str, k: int = 3) -> list[Document]:
    """
    Search the product catalog for documents relevant to the query.
    """
    client = get_supabase()
    embeddings = _get_embeddings()
    # Ejecutamos de manera síncrona el embedding ya que aembed_query puede ser lento o requerir loop en Langchain
    query_vector = embeddings.embed_query(query)
    
    # Llamada directa a Supabase RPC para esquivar bug de langchain_community (SyncRPCFilterRequestBuilder)
    res = client.rpc("match_catalog", {
        "query_embedding": query_vector,
        "match_count": k,
        "filter": {}
    }).execute()
    
    results = []
    if res.data:
        for row in res.data:
            results.append(Document(page_content=row.get("content", ""), metadata=row.get("metadata", {})))
            
    log.info("catalog.search", query=query, results=len(results))
    return results

async def search_episodic_memories(phone: str, query: str, k: int = 3) -> list[Document]:
    """
    Search a specific customer's past memories relevant to the query.
    """
    client = get_supabase()
    embeddings = _get_embeddings()
    query_vector = embeddings.embed_query(query)
    
    res = client.rpc("match_memories", {
        "query_embedding": query_vector,
        "match_count": k,
        "filter": {"customer_phone": phone}
    }).execute()
    
    results = []
    if res.data:
        for row in res.data:
            results.append(Document(page_content=row.get("content", ""), metadata=row.get("metadata", {})))
            
    log.info("episodic.search", phone=phone, query=query, results=len(results))
    return results


async def index_documents(documents: list[Document], ids: list[str] | None = None) -> None:
    """
    Add or update documents in the vector store.
    If ids are provided, it performs an upsert (overwrites existing with same ID).
    """
    store = await get_vector_store()
    await store.aadd_documents(documents, ids=ids)
    log.info("catalog.indexed", count=len(documents), ids=ids)


async def index_text(text: str, metadata: dict | None = None, doc_id: str | None = None) -> None:
    """Convenience wrapper: index a raw text string with an optional unique ID into the catalog."""
    doc = Document(page_content=text, metadata=metadata or {})
    ids = [doc_id] if doc_id else None
    await index_documents([doc], ids=ids)

async def index_episodic_memory(phone: str, content: str) -> None:
    """Index a new episodic memory for a customer."""
    store = await get_episodic_vector_store()
    doc = Document(
        page_content=content,
        metadata={"customer_phone": phone}
    )
    await store.aadd_documents([doc])
    log.info("episodic.indexed", phone=phone)


async def list_knowledge(limit: int = 20) -> list[dict]:
    """
    Retrieve a list of documents from the catalog for auditing purposes.
    Returns a list of dicts with content and metadata.
    """
    client = get_supabase()
    
    res = client.table("catalog").select("content, metadata").limit(limit).execute()
    
    results = []
    if res.data:
        for row in res.data:
            results.append({
                "content": row.get("content"),
                "metadata": row.get("metadata")
            })
            
    return results
