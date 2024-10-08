#!/bin/bash
# https://gist.github.com/mohanpedala/1e2ff5661761d3abd0385e8223e16425
set -e -x -v -u -o pipefail

SCRIPT_DIR=$(realpath "$(dirname "${BASH_SOURCE[0]}")")
source "${SCRIPT_DIR}/utilities/common.sh"

TMP_DIR=$(mktemp -d)
TMP_WOKRING_DIR="${TMP_DIR}/working"
mkdir -p "${TMP_WOKRING_DIR}"
TMP_PROJ_PATH="${TMP_DIR}/project"
mkdir -p "${TMP_PROJ_PATH}"
function cleanup {
  rm -Rf "${TMP_DIR}" || true
}
trap cleanup EXIT

################################################################################
VENV_PATH="${PWD}/.cache/scripts/.venv" \
  source "${PROJ_PATH}/scripts/utilities/ensure-venv.sh"
TOML=${PROJ_PATH}/pyproject.toml EXTRA=dev \
  DEV_VENV_PATH="${PWD}/.cache/scripts/.venv" \
  TARGET_VENV_PATH="${PWD}/.cache/scripts/.venv" \
  bash "${PROJ_PATH}/scripts/utilities/ensure-reqs.sh"
################################################################################
# Build wheel


# Copy everything including hidden files, but ignore errors.
# cp -a "${PROJ_PATH}/." "${TMP_PROJ_PATH}" || true
cd "${PROJ_PATH}"
git checkout-index --all --prefix="${TMP_PROJ_PATH}/"

cd "${TMP_PROJ_PATH}"

# Make everything writable, because `python -m build` copies everything and then
# deletes it, which is a problem if something is read only.
#
# Skips the dot files.
find "${TMP_PROJ_PATH}" -type f -not -path '*/.*' -exec chmod 777 {} +


DIST="${TMP_PROJ_PATH}/dist"
rm -Rf "${DIST}" || true
# TODO: Pin/minimum rust version, because some versions of rust fail to build
# the wheel. Pydantic has some rust parts.
python -m build --outdir "${DIST}" "${TMP_PROJ_PATH}"
################################################################################
# Install comfy_fulcrum and run smoke test
cd "${TMP_WOKRING_DIR}"
cp "${PROJ_PATH}/.python-version" .
pip install virtualenv
python -m virtualenv .venv
VENV_PATH="${TMP_WOKRING_DIR}/.venv" source "${PROJ_PATH}/scripts/utilities/ensure-venv.sh"

EXIT_CODE=0
python -m comfy_fulcrum.cli --help || EXIT_CODE=$?
if [[ "${EXIT_CODE}" -eq 0 ]]; then
  echo -e "${RED}Expected comfy_fulcrum to to fail in a clean environment${NC}"
  exit 1
fi
echo -e "${GREEN}Success: comfy_fulcrum failed in a clean environment${NC}"

# For each whl file in ${DIST}, install it and run the smoke test.
for WHL in "${DIST}"/*.whl; do
  pip install "${WHL}[cli]"
  echo -e "${GREEN}Success: comfy_fulcrum installed successfully${NC}"
done

python -m comfy_fulcrum.cli --help
python -m comfy_fulcrum.cli --version
echo -e "${GREEN}Success: comfy_fulcrum smoke test ran successfully${NC}"



echo -e "${GREEN}${BASH_SOURCE[0]}: Tests ran successfully${NC}"
################################################################################
