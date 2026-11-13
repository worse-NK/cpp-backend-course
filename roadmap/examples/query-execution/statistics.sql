-- case: uniform
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON)
SELECT task_id FROM gm_tasks WHERE owner_id=42;
-- case: skew_before_analyze
UPDATE gm_tasks SET owner_id=42 WHERE task_id<=90000;
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON)
SELECT task_id FROM gm_tasks WHERE owner_id=42;
-- case: skew_after_analyze
ANALYZE gm_tasks;
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON)
SELECT task_id FROM gm_tasks WHERE owner_id=42;
