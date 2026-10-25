-- Run as the application/database owner during initialization, never per request.
-- This is a first schema, not an idempotent migration or an upgrade framework.
BEGIN;
CREATE TABLE public.tasks (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY CHECK (id > 0),
    title text NOT NULL CHECK (octet_length(title) BETWEEN 1 AND 200),
    done boolean NOT NULL,
    version bigint NOT NULL DEFAULT 1 CHECK (version >= 1)
);
COMMIT;
