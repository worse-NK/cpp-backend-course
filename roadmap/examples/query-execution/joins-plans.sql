-- The flags are teaching controls, not production tuning advice.
-- case: nested_loop
BEGIN;
SET LOCAL statement_timeout='20s';
SET LOCAL enable_hashjoin=off;
SET LOCAL enable_mergejoin=off;
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON)
SELECT t.task_id,p.name
FROM gj_tasks t JOIN gj_people p ON p.person_id=t.owner_id
ORDER BY t.task_id;
COMMIT;
-- case: hash_join
BEGIN;
SET LOCAL statement_timeout='20s';
SET LOCAL enable_nestloop=off;
SET LOCAL enable_mergejoin=off;
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON)
SELECT t.task_id,p.name
FROM gj_tasks t JOIN gj_people p ON p.person_id=t.owner_id
ORDER BY t.task_id;
COMMIT;
-- case: merge_join
BEGIN;
SET LOCAL statement_timeout='20s';
SET LOCAL enable_nestloop=off;
SET LOCAL enable_hashjoin=off;
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON)
SELECT t.task_id,p.name
FROM gj_tasks t JOIN gj_people p ON p.person_id=t.owner_id
ORDER BY t.task_id;
COMMIT;
