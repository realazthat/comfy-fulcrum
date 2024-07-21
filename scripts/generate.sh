#!/bin/bash
# https://gist.github.com/mohanpedala/1e2ff5661761d3abd0385e8223e16425
set -e -x -v -u -o pipefail

################################################################################
SCRIPT_DIR=$(realpath "$(dirname "${BASH_SOURCE[0]}")")
source "${SCRIPT_DIR}/utilities/common.sh"

VENV_PATH="${PWD}/.cache/scripts/.cli-dev-venv" source "${PROJ_PATH}/scripts/utilities/ensure-venv.sh"
TOML="${PROJ_PATH}/pyproject.toml" EXTRAS=cli,dev PIN=cli_dev_pinned \
  DEV_VENV_PATH="${PWD}/.cache/scripts/.venv" \
  TARGET_VENV_PATH="${PWD}/.cache/scripts/.cli-dev-venv" \
  bash "${PROJ_PATH}/scripts/utilities/ensure-reqs2.sh"
################################################################################

bash scripts/format.sh
bash scripts/run-all-examples.sh
bash scripts/generate-readme.sh
################################################################################
