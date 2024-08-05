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
python -m snipinator.cli \
  -t "${PROJ_PATH}/.github/README.md.jinja2" \
  --rm \
  --force \
  --create \
  -o "${PROJ_PATH}/README.md" \
  --chmod-ro \
  --skip-unchanged
################################################################################
LAST_VERSION=$(tomlq -r -e '.["tool"]["comfy_fulcrum-project-metadata"]["last_stable_release"]' pyproject.toml)
python -m mdremotifier.cli \
  -i "${PROJ_PATH}/README.md" \
  --url-prefix "https://github.com/realazthat/comfy-fulcrum/blob/v${LAST_VERSION}/" \
  --img-url-prefix "https://raw.githubusercontent.com/realazthat/comfy-fulcrum/v${LAST_VERSION}/" \
  -o "${PROJ_PATH}/.github/README.remotified.md"
################################################################################
