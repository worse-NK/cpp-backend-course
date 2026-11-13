CREATE TEMP TABLE gm_tasks AS
SELECT n AS task_id, n % 1000 AS owner_id,
       repeat('x',128) || lpad(n::text,6,'0') AS payload
FROM generate_series(1,100000) AS n;
CREATE INDEX ON gm_tasks(owner_id);
ANALYZE gm_tasks;
