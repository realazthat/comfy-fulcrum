#!/bin/bash


# NOTE: On WSL, if you are using this on a mounted NTFS volume, you may need to
# make a soft-link to somewhere on the WSL file system, because NTFS doesn't
# play well with PG ownership/permission requirements.
#
# For example:
# ```bash
# ln -s ~/.virtualenvs/example.pgdata/ .data/pgdata
# mkdir -p ~/.virtualenvs/example.pgdata
# ```
#
# Example invocation:
# # ```bash
# PG_USER=example-user \
# PG_PWD=example-password \
# PG_SUPER_PWD=123 \
# PG_DB_NAME=example-db-name \
# PG_DOCKER_NAME=example-pg-instance \
# bash scripts/pg.sh
# ```




# https://gist.github.com/mohanpedala/1e2ff5661761d3abd0385e8223e16425
# You can ignore this, it just tells bash to make the script fail on any error,
# and prints each command before running it etc. that sort of thing.
set -e -x -v -u -o pipefail

################################################################################
# Some variables YOU need to replace here, or set before running the script.

# Password for the super user. You can use `openssl rand -base64 24` to generate
# a random password. Just save it somewhere safe.
PG_SUPER_PWD=${PG_SUPER_PWD:-}
# The database user that will be created.
#
# Name it something like `example`.
PG_USER=${PG_USER:-}
# Password for the database user. You can use `openssl rand -base64 24` to
# generate a random password. Just save it somewhere safe.
PG_PWD=${PG_PWD:-''}
# The name of the database that will be created.
#
# Name it something like `example`.
PG_DB_NAME=${PG_DB_NAME:-}
# The name of the docker container that will be created.
#
# Name it something like `example-instance`.
PG_DOCKER_NAME=${PG_DOCKER_NAME:-}
# The directory where the postgres data will be stored.
PG_DIR=${PG_DIR:-"${PWD}/.data/pgdata/"}
# The port on which the postgres server will listen.
PG_PORT=${PG_PORT:-}
# If true, ends the docker container (does not delete the data) when the script
# ends. If NO, leaves the container running. If "ONLY", only ends the container.
# And doesn't run the rest of the script.
PG_GARBAGE_COLLECT=${PG_GARBAGE_COLLECT:-YES}
# The super user and database user. For most things this doesn't matter, you
# don't usually need to log in as the super user. `postgres` is the standard
# super user name.
PG_SUPER_USER=${PG_SUPER_USER:-postgres}
# The version of postgres to use. Must be a valid docker tag. See
# <https://hub.docker.com/_/postgres/tags>.
POSTGRES_VERSION=${POSTGRES_VERSION:-16.2-bookworm}
PG_READY_FILE=${PG_READY_FILE:-}
################################################################################
# Some color variables we will use for fancy output.
GRN=$'\e[1;32m'
BLU=$'\e[34m'
RED=$'\e[91m'
CLR=$'\e[0m'
################################################################################
# Some checks to make sure the variables are set.
################################################################################
if [[ -z "${PG_DIR}" ]]; then
  echo "${RED} PG_DIR must be set ${CLR}"
  exit 1
fi
if [[ -z "${PG_PORT}" ]]; then
  echo "${RED} PG_PORT must be set ${CLR}"
  exit 1
fi
if [[ -z "${PG_SUPER_USER}" ]]; then
  echo "${RED} ${PG_SUPER_USER} must be set ${CLR}"
  exit 1
fi
if [[ -z "${PG_SUPER_PWD}" ]]; then
  echo "${RED} PG_SUPER_PWD must be set ${CLR}"
  exit 1
fi
if [[ -z "${PG_USER}" ]]; then
  echo "${RED} PG_USER must be set ${CLR}"
  exit 1
fi
if [[ -z "${PG_PWD}" ]]; then
  echo "${RED} PG_PWD must be set ${CLR}"
  exit 1
fi
if [[ -z "${PG_DB_NAME}" ]]; then
  echo "${RED} PG_DB_NAME must be set ${CLR}"
  exit 1
fi
if [[ -z "${PG_DOCKER_NAME}" ]]; then
  echo "${RED} PG_DOCKER_NAME must be set ${CLR}"
  exit 1
fi
if [[ -z "${POSTGRES_VERSION}" ]]; then
  echo "${RED} POSTGRES_VERSION must be set ${CLR}"
  exit 1
fi
################################################################################
# Check if pg_isready is installed.
if ! command -v pg_isready &> /dev/null
then
    echo "${RED} pg_isready could not be found ${CLR}"
    echo "${RED} Please install postgresql-client-common ${CLR}"
    echo "${RED} sudo apt-get install postgresql-client-common ${CLR}"
    exit
fi
################################################################################

# function garbage_collect_tmp_dir {
#   echo "${BLU} Removing PG_DIR=${PG_DIR} ... ${CLR}"
#   # Comment this out if you want to save the results, i.e see screenshots, logs
#   # or whatnot.
#   rm -rf "PG_DIR"
# }

# Close docker container. This function is called when the script ends in a
# "trap".
function garbage_collect_pg_docker {
  echo "${BLU} Shutting down docker PG_DOCKER_NAME=${PG_DOCKER_NAME} ... ${CLR}"
  docker rm --force "${PG_DOCKER_NAME}" || true
}
# function garbage_collect_pgdata {
#   echo "${BLU} Deleting postgres data ... ${CLR}"
#   docker run --rm -it --name ${PG_DOCKER_NAME} \
#     -v "${PG_DIR}:/var/lib/postgresql/data" \
#     postgres:9.5.15 \
#     /bin/bash -c 'rm -rf /var/lib/postgresql/data/*' || true
# }

if [ "${PG_GARBAGE_COLLECT}" = "YES" ]; then
  trap 'garbage_collect_pg_docker;' EXIT
elif [ "${PG_GARBAGE_COLLECT}" = "NO" ]; then
  echo ""
elif [ "${PG_GARBAGE_COLLECT}" = "ONLY" ]; then
  garbage_collect_pg_docker
  exit 0
else
  echo "${RED} PG_GARBAGE_COLLECT must be set to one of YES|NO|ONLY; actual value is \"${PG_GARBAGE_COLLECT}\" ${CLR}"
  exit 1
fi

# Remove any previous docker container instances of the same name.
garbage_collect_pg_docker

# Make sure the directory exists. Create it if it doesn't.
mkdir -p "${PG_DIR}"
# This must be an absolute path for docker.
PG_DIR=$(realpath "${PG_DIR}")

# We need to set --user in docker, otherwise the files will be owned by root,
# which will be annoying to delete later.
UID_=$(id -u)
GID_=$(id -g)

# Run the docker container.
docker run --name "${PG_DOCKER_NAME}" \
  -e "POSTGRES_USER=${PG_SUPER_USER}" \
  -e "POSTGRES_PASSWORD=${PG_SUPER_PWD}" \
  -u "${UID_}:${GID_}" \
  -v "${PG_DIR}:/var/lib/postgresql/data" \
  -p "0.0.0.0:${PG_PORT}:5432" \
  -d "postgres:${POSTGRES_VERSION}"



# -e shoe commands being sent to the server
# -w Connection options: never prompt for password
PG_CLI_OPTS="-e -w -U ${PG_SUPER_USER} -h 127.0.0.1 -p ${PG_PORT}"

# All our commands will use our super-user password.
export PGPASSWORD="${PG_SUPER_PWD}"

# Wait until postgres is ready.
until pg_isready -U ${PG_SUPER_USER} -h 127.0.0.1 -p ${PG_PORT}; do
  echo "${BLU} Waiting for postgres container ${CLR}"
  docker logs --tail 20 "${PG_DOCKER_NAME}"
  sleep 0.5
done


################################################################################
## Set up database
################################################################################

SUPER_DSN="postgresql://${PG_SUPER_USER}:${PG_SUPER_PWD}@127.0.0.1:${PG_PORT}/postgres"
DSN="postgresql://${PG_USER}:${PG_PWD}@127.0.0.1:${PG_PORT}/${PG_DB_NAME}"

# Create user if it doesn't exist.
createuser ${PG_CLI_OPTS} "${PG_USER}" || true

# Assign password to user.
# psql ${PG_CLI_OPTS} \
#   -c "ALTER USER \"${PG_USER}\" WITH password '${PG_PWD}'"
psql "${SUPER_DSN}" -c "ALTER USER \"${PG_USER}\" WITH password '${PG_PWD}'"

# Create database, owned by our user, if it doesn't exist.
createdb ${PG_CLI_OPTS} -O "${PG_USER}" "${PG_DB_NAME}" || true

# Create extensions, if they don't exist.
# psql ${PG_CLI_OPTS} --dbname="${PG_DB_NAME}" -c 'CREATE EXTENSION pg_trgm;' || true
# psql ${PG_CLI_OPTS} --dbname="${PG_DB_NAME}" -c 'CREATE EXTENSION btree_gist;' || true
# psql ${PG_CLI_OPTS} --dbname="${PG_DB_NAME}" -c 'CREATE EXTENSION pgcrypto;' || true

# Replace schema protocol with postgresql+asyncpg://
ALCHEMY_DSN=$(echo "${DSN}" | sed 's|^postgresql://|postgresql+asyncpg://|')
# If we get this far, show success in green.
echo "${GRN} SUCCESSFULLY SETUP DOCKER PG ${CLR}"

if [[ -n "${PG_READY_FILE}" ]]; then
  touch "${PG_READY_FILE}"
fi

if [[ "${PG_GARBAGE_COLLECT}" = "YES" ]]; then
  while true; do
    if ! pg_isready -U ${PG_SUPER_USER} -h 127.0.0.1 -p ${PG_PORT}; then
      echo "${RED} PG is down ${CLR}"
      break
    fi
    echo "${GRN}} KILL THIS SCRIPT TO END PG ${CLR}"
    echo "${GRN}} DSN: ${DSN} ${CLR}"
    echo "${GRN}} ALCHEMY_DSN: ${ALCHEMY_DSN} ${CLR}"
    sleep 1
  done
fi
