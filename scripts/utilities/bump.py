# -*- coding: utf-8 -*-
import argparse
import json
from pathlib import Path
from typing import Literal

import semver
import tomlkit
import tomlkit.container
import tomlkit.items
from tomlkit.toml_document import TOMLDocument
from typing_extensions import Optional

parser = argparse.ArgumentParser(
    description='Release a new version of the project.')
parser.add_argument('--bump-type',
                    choices=['major', 'minor', 'patch', 'prerelease', 'build'],
                    required=True,
                    help='The type of bump to perform.')
parser.add_argument('--toml',
                    type=Path,
                    required=True,
                    help='Path to the pyproject.toml file')
parser.add_argument(
    '--metadata-key',
    type=str,
    required=False,
    help=
    'Key in pyproject.toml to for project metadata, e.g "tool.my-project-metadata"'
)
parser.add_argument(
    '--token',
    type=str,
    required=False,
    help=
    'The {prerelease,build} token to use when bumping a {prerelease,build} version.'
)

args = parser.parse_args()

pyproject_path: Path = args.toml
bump_type: Literal['major', 'minor', 'patch', 'prerelease',
                   'build'] = args.bump_type
token: str = args.token
metadata_key: Optional[str] = args.metadata_key

pyproject_data: TOMLDocument = tomlkit.loads(pyproject_path.read_text())

version_str: str = pyproject_data['project']['version']
project_name: str = pyproject_data['project']['name']
if metadata_key is None:
  metadata_key = f'{project_name}-project-metadata'

print(pyproject_data['tool'])
project_metadata: tomlkit.items.Table = pyproject_data['tool'][metadata_key]

version = semver.Version.parse(version_str)
if bump_type == 'major':
  next_version = version.bump_major()
elif bump_type == 'minor':
  next_version = version.bump_minor()
elif bump_type == 'patch':
  next_version = version.bump_patch()
elif bump_type == 'prerelease':
  next_version = version.bump_prerelease(token)
elif bump_type == 'build':
  next_version = version.bump_build(token)
is_stable = not next_version.prerelease and not next_version.build

if 'last_release' not in project_metadata:
  raise ValueError(
      f'last_release not found in project metadata under {json.dumps(metadata_key)}'
  )
if 'last_stable_release' not in project_metadata:
  raise ValueError(
      f'last_stable_release not found in project metadata under {json.dumps(metadata_key)}'
  )

pyproject_data['project']['version'] = str(next_version)
project_metadata['last_release'] = str(next_version)
if is_stable:
  project_metadata['last_stable_release'] = str(next_version)

################################################################################
output = tomlkit.dumps(pyproject_data)
if output == pyproject_path.read_text():
  print('No changes detected')
  exit(0)

# Write the updated pyproject.toml back to disk
pyproject_path.write_text(output)
################################################################################
