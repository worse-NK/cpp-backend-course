-- Continue in the same session after model.sql.
CREATE TEMP TABLE gd_task_event (
    org_id bigint,
    task_id bigint,
    event_no bigint,
    actor_id bigint REFERENCES gd_person ON DELETE SET NULL,
    actor_name_at_event text NOT NULL,
    kind text NOT NULL,
    occurred_at timestamptz NOT NULL,
    PRIMARY KEY (org_id, task_id, event_no),
    FOREIGN KEY (org_id, task_id)
        REFERENCES gd_task ON DELETE RESTRICT
);

BEGIN;
INSERT INTO gd_task_event
SELECT 1,100,1,person_id,name,'created',TIMESTAMPTZ '2026-01-02 10:00:00+00'
FROM gd_person WHERE person_id=10;
COMMIT;

UPDATE gd_person SET name='Anna New' WHERE person_id=10;
UPDATE gd_member SET active=false WHERE org_id=1 AND person_id=10;

SELECT p.name AS current_name, e.actor_name_at_event, m.active
FROM gd_task_event e
JOIN gd_person p ON p.person_id=e.actor_id
JOIN gd_member m ON m.org_id=e.org_id AND m.person_id=e.actor_id
WHERE e.org_id=1 AND e.task_id=100 AND e.event_no=1;

-- An application workflow can lock this membership before checking activity.
-- Both assignment and deactivation must follow the same locking protocol.
BEGIN;
SELECT active FROM gd_member WHERE org_id=1 AND person_id=10 FOR UPDATE;
INSERT INTO gd_task (org_id,task_id,project_id,assignee_id,title)
SELECT 1,102,7,10,'Another task'
FROM gd_member WHERE org_id=1 AND person_id=10 AND active;
SELECT count(*) AS new_task_count FROM gd_task WHERE org_id=1 AND task_id=102;
COMMIT;
