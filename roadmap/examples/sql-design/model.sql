-- PostgreSQL 18. Run in one fresh session; only session-local TEMP tables.
CREATE TEMP TABLE gd_org (
    org_id bigint PRIMARY KEY,
    name text NOT NULL
);
CREATE TEMP TABLE gd_person (
    person_id bigint PRIMARY KEY,
    name text NOT NULL
);
CREATE TEMP TABLE gd_member (
    org_id bigint REFERENCES gd_org ON DELETE RESTRICT,
    person_id bigint REFERENCES gd_person ON DELETE RESTRICT,
    active boolean NOT NULL DEFAULT true,
    PRIMARY KEY (org_id, person_id)
);
CREATE TEMP TABLE gd_project (
    org_id bigint REFERENCES gd_org ON DELETE RESTRICT,
    project_id bigint,
    title text NOT NULL,
    PRIMARY KEY (org_id, project_id)
);
CREATE TEMP TABLE gd_project_member (
    org_id bigint,
    project_id bigint,
    person_id bigint,
    PRIMARY KEY (org_id, project_id, person_id),
    FOREIGN KEY (org_id, project_id)
        REFERENCES gd_project ON DELETE RESTRICT,
    FOREIGN KEY (org_id, person_id)
        REFERENCES gd_member ON DELETE RESTRICT
);
CREATE TEMP TABLE gd_task (
    org_id bigint,
    task_id bigint,
    project_id bigint NOT NULL,
    assignee_id bigint,
    title text NOT NULL CHECK (title <> ''),
    PRIMARY KEY (org_id, task_id),
    FOREIGN KEY (org_id, project_id)
        REFERENCES gd_project ON DELETE RESTRICT,
    FOREIGN KEY (org_id, project_id, assignee_id)
        REFERENCES gd_project_member ON DELETE RESTRICT
);

INSERT INTO gd_org VALUES (1, 'North'), (2, 'South');
INSERT INTO gd_person VALUES (10, 'Anna'), (20, 'Bo');
INSERT INTO gd_member (org_id, person_id) VALUES (1,10), (1,20), (2,20);
INSERT INTO gd_project VALUES (1,7,'API'), (2,7,'Website');
INSERT INTO gd_project_member VALUES (1,7,10), (2,7,20);
INSERT INTO gd_task VALUES
    (1,100,7,10,'Review API'),
    (1,101,7,NULL,'Unassigned'),
    (2,100,7,20,'Review website');
