#!/bin/bash
# https://gist.github.com/mohanpedala/1e2ff5661761d3abd0385e8223e16425
set -e -x -v -u -o pipefail

################################################################################
SCRIPT_DIR=$(realpath "$(dirname "${BASH_SOURCE[0]}")")
source "${SCRIPT_DIR}/common.sh"
################################################################################
BUMP=${BUMP:-""}
DEVELOP_BRANCH=${DEVELOP_BRANCH:-"develop"}
MASTER_BRANCH=${MASTER_BRANCH:-"master"}
DRY=${DRY:-"true"}
TOML=${TOML:-"./pyproject.toml"}
################################################################################
if [[ "${BUMP}" != "major" && "${BUMP}" != "minor" && "${BUMP}" != "patch" && "${BUMP}" != "prerelease" && "${BUMP}" != "build" ]]; then
  echo -e "${RED}BUMP is not set. Please set it to one of the following: major, minor, patch, prerelease, or build.${NC}"
  exit 1
fi
if [[ "${DRY}" != "true" && "${DRY}" != "false" ]]; then
  echo -e "${RED}DRY must be either true or false.${NC}"
  exit 1
fi
################################################################################
_TMP_DIR=$(mktemp -d)
trap 'rm -rf "${_TMP_DIR}"||true' EXIT
################################################################################
(

LOCAL_COMMIT=$(git rev-parse "${DEVELOP_BRANCH}")
REMOTE_COMMIT=$(git ls-remote origin -h "refs/heads/${DEVELOP_BRANCH}" | awk '{print $1}')
if [ "${LOCAL_COMMIT}" != "${REMOTE_COMMIT}" ]; then
  echo -e "${RED}Local ${DEVELOP_BRANCH} is not up to date, or has unpushed changes.${NC}"
  exit 1
fi

################################################################################
REPO_URL=$(git remote get-url origin)
################################################################################
TMP_DIR=$(mktemp -d)
trap 'chmod -R +w "${TMP_DIR}" && rm -rf "${TMP_DIR}"' EXIT

cd "${TMP_DIR}"
git clone "${REPO_URL}" "${TMP_DIR}/cloned-project"

cd "${TMP_DIR}/cloned-project"
git checkout "${MASTER_BRANCH}"
git pull origin "${MASTER_BRANCH}"
git fetch --tags

git checkout "${DEVELOP_BRANCH}"
git pull origin "${DEVELOP_BRANCH}"
git fetch --tags

echo -e "${BLUE}Current Branch: $(git branch)${NC}"
OLD_VERSION=$(tomlq -r -e '.["project"]["version"]' "${TOML}")

echo -e "${BLUE}Current Version: ${OLD_VERSION}${NC}"

echo -e "${BLUE}Bumping Version${NC}"
python "${PROJ_PATH}/scripts/utilities/bump.py" \
  --bump-type "${BUMP}" \
  --toml "${TOML}"
git --no-pager status
VERSION=$(tomlq -r -e '.["project"]["version"]' "${TOML}")
GIT_TAG="v${VERSION}"
echo -e "${BLUE}New Version: ${VERSION}${NC}"
echo -e "${BLUE}${OLD_VERSION} -> ${VERSION}${NC}"

git --no-pager diff

bash scripts/generate.sh
git --no-pager status
# bash scripts/pre.sh

# Stage all changes, but not untracked files.
git add -u
git --no-pager status

git commit -m "Prepare Release ${VERSION}"

echo -e "${BLUE}Merging ${DEVELOP_BRANCH} into ${MASTER_BRANCH}${NC}"
git checkout "${MASTER_BRANCH}"
git merge --no-edit "${DEVELOP_BRANCH}" --no-ff

echo -e "${BLUE}Tagging ${MASTER_BRANCH} with ${GIT_TAG}${NC}"
git tag -a "${GIT_TAG}" -m "Version ${VERSION}"


if [[ "${DRY}" == "false" ]]; then
  echo -e "${BLUE}Pushing to origin${NC}"
  git push origin "${MASTER_BRANCH}"
  echo -e "${BLUE}Pushing tags to origin${NC}"
  git push --tags
fi

echo -e "${BLUE}Merging ${MASTER_BRANCH} back into ${DEVELOP_BRANCH}${NC}"
git checkout "${DEVELOP_BRANCH}"
git merge --no-edit "${MASTER_BRANCH}"

if [[ "${DRY}" == "false" ]]; then
  git push origin "${DEVELOP_BRANCH}"
fi


echo "export GIT_TAG=${GIT_TAG}" > "${_TMP_DIR}/.env"

echo -e "${BLUE}GIT_TAG=\"${GIT_TAG}\"${NC}"

echo -e "${GREEN}Success: bump-n-tag.sh ${OLD_VERSION} -> ${VERSION}${NC}"
)

################################################################################
source "${_TMP_DIR}/.env"
export GIT_TAG
