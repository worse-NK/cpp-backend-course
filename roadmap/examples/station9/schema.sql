-- Run only in a newly created, isolated cpp_course9 database.
-- No DROP/IF NOT EXISTS: an accidental repeated run must fail visibly.
BEGIN;
CREATE TABLE users (id bigint PRIMARY KEY, name text NOT NULL);
CREATE TABLE tasks (
    id bigint PRIMARY KEY,
    owner_id bigint NOT NULL REFERENCES users(id),
    title text NOT NULL CHECK (char_length(title) > 0),
    done boolean NOT NULL DEFAULT false,
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0)
);
INSERT INTO users VALUES (1, 'Анна'), (2, 'Борис'), (3, 'Вера');
INSERT INTO tasks (id, owner_id, title, done) VALUES
    (10, 1, 'Написать тест', false),
    (11, 1, 'Обновить README', true),
    (12, 2, 'Проверить API', false);
COMMIT;
