#!/bin/bash
# https://gist.github.com/mohanpedala/1e2ff5661761d3abd0385e8223e16425
set -e -x -v -u -o pipefail


PG_PORT=41003 \
PG_USER=user \
PG_PWD=password \
PG_SUPER_PWD=123 \
PG_DB_NAME=db-name \
PG_DOCKER_NAME=fulcrum-pg-instance \
bash scripts/pg.sh
