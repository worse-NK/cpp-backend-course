-- Run once in a new isolated course database, not in production.
CREATE TABLE parking (
    id integer PRIMARY KEY,
    available integer NOT NULL CHECK (available >= 0)
);
INSERT INTO parking VALUES (1, 1);
