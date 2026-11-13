#!/bin/sh
set -eu
COURSE_PATH_API_PASSWORD="$(cat /run/secrets/api_password)"
COURSE_PATH_RELAY_PASSWORD="$(cat /run/secrets/relay_password)"
COURSE_PATH_CONSUMER_PASSWORD="$(cat /run/secrets/consumer_password)"
export COURSE_PATH_API_PASSWORD COURSE_PATH_RELAY_PASSWORD COURSE_PATH_CONSUMER_PASSWORD
psql -X --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --file=/opt/production-path/schema.sql
unset COURSE_PATH_API_PASSWORD COURSE_PATH_RELAY_PASSWORD COURSE_PATH_CONSUMER_PASSWORD
