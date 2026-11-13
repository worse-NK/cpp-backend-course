\set ON_ERROR_STOP on
\getenv api_password COURSE_PATH_API_PASSWORD
\getenv relay_password COURSE_PATH_RELAY_PASSWORD
\getenv consumer_password COURSE_PATH_CONSUMER_PASSWORD
CREATE ROLE path_owner NOLOGIN;
CREATE ROLE path_api LOGIN PASSWORD :'api_password';
CREATE ROLE path_relay LOGIN PASSWORD :'relay_password';
CREATE ROLE path_consumer LOGIN PASSWORD :'consumer_password';
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA course_path AUTHORIZATION path_owner;
SET ROLE path_owner;
SET search_path=course_path,pg_temp;

CREATE TABLE users (
    user_id bigint PRIMARY KEY,
    username text NOT NULL UNIQUE,
    password_verifier text NOT NULL
);
CREATE TABLE sessions (
    token_digest text PRIMARY KEY CHECK (token_digest ~ '^[0-9a-f]{64}$'),
    user_id bigint NOT NULL UNIQUE REFERENCES users,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    last_seen_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    CHECK (expires_at>created_at)
);
CREATE TABLE tasks (
    task_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_id bigint NOT NULL REFERENCES users,
    title text NOT NULL CHECK (octet_length(title) BETWEEN 1 AND 200),
    version bigint NOT NULL DEFAULT 1 CHECK (version>0)
);
CREATE TABLE commands (
    user_id bigint NOT NULL REFERENCES users,
    command_key text NOT NULL CHECK (command_key ~ '^[A-Za-z0-9_-]{1,64}$'),
    request_title text NOT NULL,
    task_id bigint REFERENCES tasks,
    PRIMARY KEY (user_id,command_key)
);
-- The API reserves a command and fills task_id in the SAME transaction. NULL
-- is an internal uncommitted state; direct trusted writers must not commit it.
CREATE TABLE outbox (
    event_id text PRIMARY KEY CHECK (event_id ~ '^[0-9a-f]{64}$'),
    task_id bigint NOT NULL REFERENCES tasks,
    payload text NOT NULL CHECK (octet_length(payload)<=4096),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    sent_at timestamptz,
    UNIQUE(task_id)
);
CREATE TABLE receipts (
    consumer text NOT NULL,
    event_id text NOT NULL CHECK (event_id ~ '^[0-9a-f]{64}$'),
    processed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (consumer,event_id)
);
CREATE TABLE creation_totals (
    user_id bigint PRIMARY KEY REFERENCES users,
    total bigint NOT NULL CHECK (total>=0)
);
RESET ROLE;
GRANT USAGE ON SCHEMA course_path TO path_api,path_relay,path_consumer;
GRANT SELECT ON course_path.users TO path_api;
GRANT SELECT,INSERT ON course_path.sessions,course_path.commands,course_path.tasks TO path_api;
GRANT UPDATE(token_digest,created_at,last_seen_at,expires_at,revoked_at) ON course_path.sessions TO path_api;
GRANT UPDATE(task_id) ON course_path.commands TO path_api;
GRANT UPDATE(title,version) ON course_path.tasks TO path_api;
GRANT USAGE ON SEQUENCE course_path.tasks_task_id_seq TO path_api;
GRANT INSERT ON course_path.outbox TO path_api;
GRANT SELECT ON course_path.creation_totals TO path_api;
GRANT SELECT,UPDATE(sent_at) ON course_path.outbox TO path_relay;
GRANT SELECT,INSERT ON course_path.receipts TO path_consumer;
GRANT SELECT,INSERT,UPDATE(total) ON course_path.creation_totals TO path_consumer;
ALTER ROLE path_api SET search_path=course_path,pg_temp;
ALTER ROLE path_relay SET search_path=course_path,pg_temp;
ALTER ROLE path_consumer SET search_path=course_path,pg_temp;
