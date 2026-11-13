CREATE TEMP TABLE gj_people (person_id integer PRIMARY KEY, name text NOT NULL);
CREATE TEMP TABLE gj_tasks (task_id integer PRIMARY KEY, owner_id integer NOT NULL);
INSERT INTO gj_people VALUES (1,'Anna'), (2,'Bo'), (4,'Dee');
INSERT INTO gj_tasks VALUES (10,1), (11,1), (12,2), (13,3);
ANALYZE gj_people;
ANALYZE gj_tasks;
