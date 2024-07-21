#!/bin/bash
# https://gist.github.com/mohanpedala/1e2ff5661761d3abd0385e8223e16425
set -e -x -v -u -o pipefail

SCRIPT_DIR=$(realpath "$(dirname "${BASH_SOURCE[0]}")")
source "${SCRIPT_DIR}/utilities/common.sh"

export TOML="${PROJ_PATH}/pyproject.toml"

# This variable will be 1 when we are the ideal version in the GH action matrix.
IDEAL="0"
PYTHON_VERSION=$(cat .python-version)
if [[ "${PYTHON_VERSION}" == "3.8.0" ]]; then
  IDEAL="1"
fi

if [[ -z "${GITHUB_ACTIONS:-}" ]]; then
  if [[ "${IDEAL}" != "1" ]]; then
    echo -e "${RED}Somehow we are not 'ideal' outside of GH Action workflow. IDEAL is meant to be 1 when we are running the GH Action matrix configuration that matches the configuration outside of the GH Action workflow. But we are not in the GH Action workflow, yet it is not 1!${NC}"
    exit 1
  fi
fi

# Check that no changes occurred to files through the workflow.
if [[ "${IDEAL}" == "1" ]]; then
  STEP=pre bash scripts/utilities/changeguard.sh
fi

PIN=base_prod_pinned EXTRAS=base,prod bash scripts/utilities/pin-extra-reqs2.sh
PIN=base_dev_pinned EXTRAS=base,dev bash scripts/utilities/pin-extra-reqs2.sh

PIN=db_prod_pinned EXTRAS=db,prod bash scripts/utilities/pin-extra-reqs2.sh
PIN=db_dev_pinned EXTRAS=db,dev bash scripts/utilities/pin-extra-reqs2.sh

PIN=fastapi_server_prod_pinned EXTRAS=fastapi_server,prod bash scripts/utilities/pin-extra-reqs2.sh
PIN=fastapi_server_dev_pinned EXTRAS=fastapi_server,dev bash scripts/utilities/pin-extra-reqs2.sh

PIN=fastapi_ui_prod_pinned EXTRAS=fastapi_ui,prod bash scripts/utilities/pin-extra-reqs2.sh
PIN=fastapi_ui_dev_pinned EXTRAS=fastapi_ui,dev bash scripts/utilities/pin-extra-reqs2.sh

PIN=fastapi_client_prod_pinned EXTRAS=fastapi_client,prod bash scripts/utilities/pin-extra-reqs2.sh
PIN=fastapi_client_dev_pinned EXTRAS=fastapi_client,dev bash scripts/utilities/pin-extra-reqs2.sh

PIN=cli_prod_pinned EXTRAS=cli,prod bash scripts/utilities/pin-extra-reqs2.sh
PIN=cli_dev_pinned EXTRAS=cli,dev bash scripts/utilities/pin-extra-reqs2.sh

# Runs in generate.sh.
# bash scripts/run-all-examples.sh
# Runs in generate.sh.
# bash scripts/format.sh
bash scripts/generate.sh
bash scripts/run-all-tests.sh
bash scripts/run-wheel-smoke-test.sh
bash scripts/run-edit-mode-smoke-test.sh
bash scripts/type-check.sh
if [[ -z "${GITHUB_ACTIONS:-}" ]]; then
  bash scripts/act.sh
	bash scripts/precommit.sh
fi

# Check that no changes occurred to files throughout pre.sh to tracked files. If
# changes occurred, they should be staged and pre.sh should be run again.
if [[ "${IDEAL}" == "1" ]]; then
  STEP=post bash scripts/utilities/changeguard.sh
fi

echo -e "${GREEN}pre.sh completed successfully.${NC}"
