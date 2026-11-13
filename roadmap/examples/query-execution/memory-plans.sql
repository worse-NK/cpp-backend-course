-- case: sort_small
BEGIN;
SET LOCAL statement_timeout='20s';
SET LOCAL work_mem='64kB';
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON)
SELECT task_id,payload FROM gm_tasks ORDER BY payload DESC,task_id DESC;
COMMIT;
-- case: sort_large
BEGIN;
SET LOCAL statement_timeout='20s';
SET LOCAL work_mem='32MB';
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON)
SELECT task_id,payload FROM gm_tasks ORDER BY payload DESC,task_id DESC;
COMMIT;
-- case: hash_small
BEGIN;
SET LOCAL statement_timeout='20s';
SET LOCAL work_mem='256kB';
SET LOCAL hash_mem_multiplier=1;
SET LOCAL enable_sort=off;
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON)
SELECT task_id,count(*) FROM gm_tasks GROUP BY task_id;
COMMIT;
-- case: hash_large
BEGIN;
SET LOCAL statement_timeout='20s';
SET LOCAL work_mem='32MB';
SET LOCAL hash_mem_multiplier=1;
SET LOCAL enable_sort=off;
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON)
SELECT task_id,count(*) FROM gm_tasks GROUP BY task_id;
COMMIT;
