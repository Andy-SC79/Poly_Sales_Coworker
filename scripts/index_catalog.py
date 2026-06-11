"""
scripts/index_catalog.py
-------------------------
Sync products from Supabase catalog table into the vector index.
Run this whenever you need to re-synchronize the vector index.
"""
import asyncio
import structlog
from langchain_core.documents import Document

from core.knowledge.catalog import index_documents
from integrations.supabase_client import get_supabase

log = structlog.get_logger()

async def main():
    client = get_supabase()
    
    log.info("catalog.loading_from_supabase")
    
    # Load all products from Supabase catalog table
    resp = client.table("catalog").select("content, metadata").execute()
    rows = resp.data or []
    
    if not rows:
        log.warning("catalog.empty", source="supabase")
        return
    
    # Convert Supabase rows to Document objects
    documents = [
        Document(
            page_content=row.get("content", ""),
            metadata=row.get("metadata", {})
        )
        for row in rows
    ]
    
    log.info("catalog.indexing", count=len(documents))
    
    # Re-index all documents into vector store
    await index_documents(documents)
    log.info("catalog.success", indexed_count=len(documents))

if __name__ == "__main__":
    asyncio.run(main())
