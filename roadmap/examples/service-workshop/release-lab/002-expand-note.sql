-- Apply once, only to the new release-lab database, under its administrator.
-- SET ROLE makes the separate schema owner perform the actual migration.
BEGIN;
SET LOCAL lock_timeout = '2000ms';
SET LOCAL statement_timeout = '5000ms';
SET LOCAL ROLE release_owner;
ALTER TABLE release_lab.tasks
    ADD COLUMN note text CHECK (note IS NULL OR char_length(note) <= 200);
GRANT SELECT (note), UPDATE (note) ON release_lab.tasks TO release_app;
INSERT INTO release_lab.schema_migrations VALUES (2, 'optional note; keep V1 compatible');
COMMIT;
