#!/bin/bash
# https://gist.github.com/mohanpedala/1e2ff5661761d3abd0385e8223e16425
set -e -x -v -u -o pipefail

SCRIPT_DIR=$(realpath "$(dirname "${BASH_SOURCE[0]}")")
source "${SCRIPT_DIR}/common.sh"

source scripts/utilities/bump-n-tag.sh
GIT_TAG=${GIT_TAG} bash scripts/utilities/deploy-to-pypi.sh
GIT_TAG=${GIT_TAG} IMAGE_TAG=${GIT_TAG} bash scripts/utilities/deploy-to-ghr.sh
