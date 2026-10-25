#!/usr/bin/env bash
# Invoked by the official PostgreSQL image ONLY for a fresh data volume.
set -eu

if [ "${POSTGRES_USER:-}" != postgres ] || [ "${POSTGRES_DB:-}" != course_tasks ]; then
    printf '%s\n' 'This bootstrap is scoped to postgres/course_tasks.' >&2
    exit 1
fi
APP_DB_PASSWORD=${APP_DB_PASSWORD:-}
if [ "${#APP_DB_PASSWORD}" -ne 64 ]; then
    printf '%s\n' 'APP_DB_PASSWORD must be 64 lowercase hexadecimal characters.' >&2
    exit 1
fi
case "$APP_DB_PASSWORD" in
    *[!0-9a-f]*)
        printf '%s\n' 'APP_DB_PASSWORD must be 64 lowercase hexadecimal characters.' >&2
        exit 1 ;;
esac

# Quoted heredoc prevents shell substitution. psql reads the environment
# directly; :'app_password' and format(%L) quote it as data, never SQL code.
# Do not enable shell tracing, psql query echo, or statement logging here.
psql -X --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
\getenv app_password APP_DB_PASSWORD
SELECT format('CREATE ROLE course_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD %L', :'app_password')
\gexec
REVOKE ALL ON DATABASE course_tasks FROM PUBLIC;
GRANT CONNECT ON DATABASE course_tasks TO course_app;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
\i /opt/course/schema.sql
GRANT USAGE ON SCHEMA public TO course_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.tasks TO course_app;
GRANT USAGE ON SEQUENCE public.tasks_id_seq TO course_app;
SQL
