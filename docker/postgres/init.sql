-- Runs once on first container start (docker-entrypoint-initdb.d).
-- Enables pgvector ahead of time so the future RAG integration needs no
-- database migration to add the extension later.
CREATE EXTENSION IF NOT EXISTS vector;
