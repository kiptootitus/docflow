-- DocFlow AI — Database Initialisation
-- Runs once when the PostgreSQL container is first created.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";   -- for fast text search

-- Set timezone
SET timezone = 'UTC';
