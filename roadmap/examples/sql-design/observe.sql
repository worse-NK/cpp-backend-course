SELECT org_id, task_id, project_id, assignee_id, title
FROM gd_task ORDER BY org_id, task_id;

SELECT org_id, person_id FROM gd_member ORDER BY org_id, person_id;
