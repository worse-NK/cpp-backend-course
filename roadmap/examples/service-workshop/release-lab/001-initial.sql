\getenv app_password APP_DB_PASSWORD
BEGIN;
CREATE ROLE release_owner NOLOGIN;
CREATE ROLE release_app LOGIN PASSWORD :'app_password';
CREATE SCHEMA release_lab AUTHORIZATION release_owner;
GRANT USAGE ON SCHEMA release_lab TO release_app;
SET LOCAL ROLE release_owner;
CREATE TABLE release_lab.tasks (
    id bigint PRIMARY KEY CHECK (id = 1),
    title text NOT NULL CHECK (char_length(title) BETWEEN 1 AND 200),
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0)
);
CREATE TABLE release_lab.schema_migrations (
    version integer PRIMARY KEY,
    description text NOT NULL
);
INSERT INTO release_lab.tasks VALUES (1, 'Original', 1);
INSERT INTO release_lab.schema_migrations VALUES (1, 'initial task');
GRANT SELECT (id, title, version), UPDATE (title, version)
    ON release_lab.tasks TO release_app;
COMMIT;
