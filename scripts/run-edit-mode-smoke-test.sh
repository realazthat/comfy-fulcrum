#!/bin/bash
# https://gist.github.com/mohanpedala/1e2ff5661761d3abd0385e8223e16425
set -e -x -v -u -o pipefail

SCRIPT_DIR=$(realpath "$(dirname "${BASH_SOURCE[0]}")")
source "${SCRIPT_DIR}/utilities/common.sh"


TMP_PROJ_PATH=$(mktemp -d)
TMP_DIR=$(mktemp -d)
function cleanup {
  rm -Rf "${TMP_DIR}" || true
  rm -Rf "${TMP_PROJ_PATH}" || true
}
trap cleanup EXIT

################################################################################


# Copy everything including hidden files, but ignore errors.
cp -a "${PROJ_PATH}/." "${TMP_PROJ_PATH}" || true

# Make everything writable, because `python -m build` copies everything and then
# deletes it, which is a problem if something is read only.
#
# Skips the dot files.
find "${TMP_PROJ_PATH}" -type f -not -path '*/.*' -exec chmod 777 {} +


################################################################################
# Install comfy_fulcrum and run smoke test
cd "${TMP_DIR}"
cp "${PROJ_PATH}/.python-version" .
VENV_PATH="${TMP_DIR}/.venv" source "${PROJ_PATH}/scripts/utilities/ensure-venv.sh"
pip install -U pip

EXIT_CODE=0
python -m comfy_fulcrum.cli --help || EXIT_CODE=$?
if [[ "${EXIT_CODE}" -eq 0 ]]; then
  echo -e "${RED}Expected comfy_fulcrum to to fail in a clean environment${NC}"
  exit 1
fi
echo -e "${GREEN}Success: comfy_fulcrum failed in a clean environment${NC}"

pip install -e "${TMP_PROJ_PATH}"[cli]
echo -e "${GREEN}Success: comfy_fulcrum installed successfully${NC}"

python -m comfy_fulcrum.cli --help
python -m comfy_fulcrum.cli --version
echo -e "${GREEN}Success: comfy_fulcrum smoke test ran successfully${NC}"

echo -e "${GREEN}${BASH_SOURCE[0]}: Tests ran successfully${NC}"
################################################################################
