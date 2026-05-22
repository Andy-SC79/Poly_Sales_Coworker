-- Enable the pgvector extension
create extension if not exists vector;

-- 1. CATALOG TABLE (Para productos y políticas)
create table if not exists catalog (
  id uuid primary key default gen_random_uuid(),
  content text,
  metadata jsonb,
  embedding vector(1536) -- Dimensión para text-embedding-3-small
);

-- Función de búsqueda de similitud para el catálogo
create or replace function match_catalog (
  query_embedding vector(1536),
  match_count int DEFAULT null,
  filter jsonb DEFAULT '{}'
) returns table (
  id uuid,
  content text,
  metadata jsonb,
  similarity float
)
language plpgsql
as $$
#variable_conflict use_column
begin
  return query
  select
    id,
    content,
    metadata,
    1 - (catalog.embedding <=> query_embedding) as similarity
  from catalog
  where metadata @> filter
  order by catalog.embedding <=> query_embedding
  limit match_count;
end;
$$;


-- 2. EPISODIC MEMORIES TABLE (Para los recuerdos compactados de los clientes)
create table if not exists episodic_memories (
  id uuid primary key default gen_random_uuid(),
  customer_phone text not null,
  content text,
  metadata jsonb,
  embedding vector(1536)
);

-- Índice para búsquedas más rápidas por cliente
create index if not exists idx_episodic_memories_phone on episodic_memories(customer_phone);

-- Función de búsqueda de similitud para las memorias episódicas
create or replace function match_memories (
  query_embedding vector(1536),
  match_count int DEFAULT null,
  filter jsonb DEFAULT '{}'
) returns table (
  id uuid,
  content text,
  metadata jsonb,
  similarity float
)
language plpgsql
as $$
#variable_conflict use_column
begin
  return query
  select
    id,
    content,
    metadata,
    1 - (episodic_memories.embedding <=> query_embedding) as similarity
  from episodic_memories
  where metadata @> filter
  order by episodic_memories.embedding <=> query_embedding
  limit match_count;
end;
$$;
