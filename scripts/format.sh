#!/bin/bash
# https://gist.github.com/mohanpedala/1e2ff5661761d3abd0385e8223e16425
set -e -x -v -u -o pipefail

SCRIPT_DIR=$(realpath "$(dirname "${BASH_SOURCE[0]}")")
source "${SCRIPT_DIR}/utilities/common.sh"

VENV_PATH="${PWD}/.cache/scripts/.cli-dev-venv" source "${PROJ_PATH}/scripts/utilities/ensure-venv.sh"
TOML="${PROJ_PATH}/pyproject.toml" EXTRAS=cli,dev PIN=cli_dev_pinned \
  DEV_VENV_PATH="${PWD}/.cache/scripts/.venv" \
  TARGET_VENV_PATH="${PWD}/.cache/scripts/.cli-dev-venv" \
  bash "${PROJ_PATH}/scripts/utilities/ensure-reqs2.sh"


python -m mdreftidy.cli "${PWD}/.github/README.md.jinja2" \
  --renumber --remove-unused --move-to-bottom --sort-ref-blocks --inplace
bash scripts/utilities/prettier.sh --parser markdown "${PWD}/.github/README.md.jinja2" --write

python -m yapf -r ./comfy_fulcrum ./scripts -i
python -m autoflake --remove-all-unused-imports --in-place --recursive ./comfy_fulcrum
python -m isort ./comfy_fulcrum ./scripts 
if toml-sort "${PROJ_PATH}/pyproject.toml" --sort-inline-arrays --ignore-case --check; then
  :
else
  toml-sort --in-place "${PROJ_PATH}/pyproject.toml" --sort-inline-arrays --ignore-case
fi

# vulture ./comfy_fulcrum ./examples
