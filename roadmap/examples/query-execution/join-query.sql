SELECT t.task_id, p.name
FROM gj_tasks t JOIN gj_people p ON p.person_id=t.owner_id
ORDER BY t.task_id;
