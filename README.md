<!--

WARNING: This file is auto-generated by snipinator. Do not edit directly.
SOURCE: `.github/README.md.jinja2`.

-->
<!--










-->

# <div align="center">[![ComfyUI Fulcrum][1]][2]</div>

<div align="center">

<!-- Icons from https://lucide.dev/icons/users -->
<!-- Icons from https://lucide.dev/icons/laptop-minimal -->

![**Audience:** Developers][3] ![**Platform:** Linux][4]

</div>

<p align="center">
  <strong>
    <a href="https://github.com/realazthat/comfy-fulcrum">🏠Home</a>
    &nbsp;&bull;&nbsp;
    <a href="#-features">🎇Features</a>
    &nbsp;&bull;&nbsp;
    <a href="#-install">🔨Install</a>
    &nbsp;&bull;&nbsp;
    <a href="#-usage">🚜Usage</a>
    &nbsp;&bull;&nbsp;
    <a href="#-command-line-options">💻CLI</a>
    &nbsp;&bull;&nbsp;
    <a href="#-examples">💡Examples</a>
  </strong>
</p>
<p align="center">
  <strong>
    <a href="#-jinja2-api">🤖Jinja2 API</a>
    &nbsp;&bull;&nbsp;
    <a href="#-requirements">✅Requirements</a>
    &nbsp;&bull;&nbsp;
    <a href="#-docker-image">🐳Docker</a>
    &nbsp;&bull;&nbsp;
    <a href="#-gotchas-and-limitations">🚸Gotchas</a>
  </strong>
</p>

<div align="center">

![Top language][5] [![GitHub License][6]][7] [![PyPI - Version][8]][9]
[![Python Version][10]][9]

**Load balancer for ComfyUI instances**

</div>

<div align="center">

|                   | Status                      | Stable                    | Unstable                  |                          |
| ----------------- | --------------------------- | ------------------------- | ------------------------- | ------------------------ |
| **[Master][11]**  | [![Build and Test][12]][13] | [![since tagged][14]][15] |                           | [![last commit][16]][17] |
| **[Develop][18]** | [![Build and Test][19]][13] | [![since tagged][20]][21] | [![since tagged][22]][23] | [![last commit][24]][25] |

</div>

<img src="./.github/demo.gif" alt="Demo" width="100%">

## ❔ What

What it does: **ComfyUI Fulcrum** lets you manage exclusive access to
multiple resources (ComfyUI API URLs).

## 🎇 Features

- Channels.
- Priority: Clients can specify priority for a lease request.
- Expiry: Clients can specify how long they need the lease; if they fail to
  "touch" the lease before expiry, it is released.

## 🔨 Install

- **cli**: CLI that gives access to **fastapi\_{server, client}**, backed by
  **db**, from the command line.
- **fastapi_client**: Client, library. Install this if you want to use the API
  _from python_.
- **fastapi_server**: Server, library. Install this if you want to serve the API
  _from python_.
- **fastapi_mgmt_ui**: Management UI, library. Install this if you want to serve
  the management UI _from python_.
- **db**: DB implementation, library. Can be combined with fastapi_server as a
  serving solution, from python.
- **base**: Interfaces library. Install this if you want to implement your own
  implementations.

```bash
# Install from pypi (https://pypi.org/project/comfy-fulcrum/)
pip install comfy-fulcrum[cli,db,fastapi_server,fastapi_mgmt_ui,fastapi_client]

# Install from git (https://github.com/realazthat/comfy-fulcrum)
pip install git+https://github.com/realazthat/comfy-fulcrum.git@v0.0.1[cli,db,fastapi_server,fastapi_mgmt_ui,fastapi_client]
```

## 🚜 Usage

Server via CLI:

<!---->
```bash


# NOTE: You must have PostgreSQL's uuid-ossp or pgcrypto extension installed.
# psql ${PG_CLI_OPTS} --dbname="${PG_DB_NAME}" -c 'CREATE EXTENSION IF NOT EXISTS "pgcrypto";' || true
# psql ${PG_CLI_OPTS} --dbname="${PG_DB_NAME}" -c 'CREATE EXTENSION IF NOT EXISTS "uuid-ossp";' || true

python -m comfy_fulcrum.cli server \
  --dsn "${DSN}" \
  --host 0.0.0.0 --port "${FULCRUM_PORT}"
```
<!---->

Client via CLI:

<!---->
```bash

python -m comfy_fulcrum.cli client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  --data '' \
  stats

RESOURCE_A_ID=a
python -m comfy_fulcrum.cli client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  --data '{"resource_id": "'"${RESOURCE_A_ID}"'","channels": ["main"], "data": "{\"comfy_api_url\": \"url\"}"}' \
  register

python -m comfy_fulcrum.cli client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  list

python -m comfy_fulcrum.cli client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  --data '' \
  stats

TICKET=$(python -m comfy_fulcrum.cli client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  --data '{"client_name": "me","channels": ["main"], "priority": "1"}' \
  get)

# Example TICKET:
# {"id": "4fe26e1fe5974e68b788f82cc9460b0b", "client_name": "me", "lease_timeout": 180.0, "ends": "2024-07-21T01:18:16.317032"}
echo "TICKET: ${TICKET}"

TICKET_ID=$(echo "${TICKET}" | jq -r '.id')
echo "TICKET_ID: ${TICKET_ID}"

RESOURCE_ID=
while [[ -z "${RESOURCE_ID}" ]]; do
  echo -e "${BLUE}Checking if resource is ready${NC}"
  TICKET=$(python -m comfy_fulcrum.cli client \
    --fulcrum_api_url "${FULCRUM_API_URL}" \
    --data '{"id": "'"${TICKET_ID}"'"}' \
    touch)
  echo "TICKET: ${TICKET}"
  RESOURCE_ID=$(echo "${TICKET}" | jq -r '.resource_id')
  echo "RESOURCE_ID: ${RESOURCE_ID}"
  sleep 2
done

RESOURCE_DATA=$(echo "${TICKET}" | jq -r '.data')
COMFY_API_URL=$(echo "${RESOURCE_DATA}" | jq -r '.comfy_api_url')

echo -e "${BLUE}COMFY_API_URL: ${COMFY_API_URL}${NC}"

python -m comfy_fulcrum.cli client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  --data '' \
  stats

sleep 2
python -m comfy_fulcrum.cli client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  --data '{"id": "'"${TICKET_ID}"'", "report": "success", "report_extra": {}}' \
  release

python -m comfy_fulcrum.cli client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  --data '{"resource_id": "'"${RESOURCE_A_ID}"'"}' \
  remove

python -m comfy_fulcrum.cli client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  --data '' \
  stats
```
<!---->

Server via Python:

<!---->
```py

  app = fastapi.FastAPI()

  db_engine: AsyncEngine = create_async_engine(
      dsn,
      echo=False,
      pool_size=10,
      max_overflow=20,
      pool_timeout=5,
      pool_recycle=1800,
      isolation_level='REPEATABLE READ')
  fulcrum = DBFulcrum(engine=db_engine,
                      lease_timeout=60. * 5,
                      service_sleep_interval=1.0)
  await fulcrum.Initialize()
  routes = FulcrumServerRoutes(fulcrum=fulcrum)
  app.include_router(routes.Router())

  hypercorn_config = hypercorn.Config()
  hypercorn_config.bind = [f'0.0.0.0:{port}']
  hypercorn_config.use_reloader = True
  hypercorn_config.loglevel = 'debug'
  hypercorn_config.accesslog = '-'
  hypercorn_config.errorlog = '-'
  hypercorn_config.debug = True

  await hypercorn.asyncio.serve(app, hypercorn_config)  # type: ignore
```
<!---->

Client (resource provider) via Python:

<!---->
```py


  client = FulcrumClient(fulcrum_api_url=fulcrum_api_url)

  print(await client.Stats(), file=sys.stderr)

  print(await client.RegisterResource(channels=[ChannelID('main')],
                                      resource_id=ResourceID(uuid.uuid4().hex),
                                      data=json.dumps(
                                          {'comfy_api_url': comfy_api_url})),
        file=sys.stderr)
  print(await client.ListResources(), file=sys.stderr)
```
<!---->

Client (resource consumer) via Python:

<!---->
```py

  client = FulcrumClient(fulcrum_api_url=fulcrum_api_url)

  print(await client.Stats(), file=sys.stderr)

  lease: Union[Lease, Ticket] = await client.Get(client_name=ClientName('test'),
                                                 channels=[ChannelID('main')],
                                                 priority=1)
  print(lease, file=sys.stderr)

  async def WaitForResource(id: LeaseID) -> Lease:
    while True:
      lease_or = await client.TouchTicket(id=id)
      if isinstance(lease_or, Lease):
        return lease_or
      elif isinstance(lease_or, Ticket):
        await asyncio.sleep(1)
      elif lease_or is None:
        print('Lease has expired', file=sys.stderr)
        exit(1)

      await asyncio.sleep(1)

  lease = await WaitForResource(id=lease.id)

  print(lease, file=sys.stderr)

  print(await client.Stats(), file=sys.stderr)

  # Now that we have the lease, let's get the data, which we happen to know is
  # json with the comfy_api_url as {'comfy_api_url': <url>}.
  resource_data = json.loads(lease.data)
  comfy_api_url = resource_data['comfy_api_url']

  # Do something with the comfy_api_url here:
  print(comfy_api_url, file=sys.stderr)
  await asyncio.sleep(1)

  # Don't forget to touch the lease occasionally, otherwise it will expire.
  await client.TouchLease(id=lease.id)
  await asyncio.sleep(1)

  # Once done with the lease, release it.
  await client.Release(id=lease.id, report='success', report_extra=None)

  print(await client.Stats(), file=sys.stderr)
```
<!---->

## 💻 Command Line Options

<!---->
<img src=".github/README.help.generated.svg" alt="Output of `python -m comfy_fulcrum.cli --help`" />
<!---->

<!---->
<img src=".github/README.server.help.generated.svg" alt="Output of `python -m comfy_fulcrum.cli server --help`" />
<!---->

<!---->
<img src=".github/README.client.help.generated.svg" alt="Output of `python -m comfy_fulcrum.cli client --help`" />
<!---->

## 🐳 Docker Image

Docker images are published to [ghcr.io/realazthat/comfy-fulcrum][23] at each
tag.

Gotcha: `--tty` will output extra hidden characters.

<!---->
```bash


# NOTE: You must have PostgreSQL's uuid-ossp or pgcrypto extension installed.
# psql ${PG_CLI_OPTS} --dbname="${PG_DB_NAME}" -c 'CREATE EXTENSION IF NOT EXISTS "pgcrypto";' || true
# psql ${PG_CLI_OPTS} --dbname="${PG_DB_NAME}" -c 'CREATE EXTENSION IF NOT EXISTS "uuid-ossp";' || true

docker run --rm --network="host" \
  -v "${PWD}:/data" \
  ghcr.io/realazthat/comfy_fulcrum:v0.0.1 server \
  --dsn "${DSN}" \
  --host 0.0.0.0 --port "${FULCRUM_PORT}"
```
<!---->

<!---->
```bash

docker run --rm --network="host" \
  -v "${PWD}:/data" \
  ghcr.io/realazthat/comfy_fulcrum:v0.0.1 client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  --data '' \
  stats

RESOURCE_A_ID=a
docker run --rm --network="host" \
  -v "${PWD}:/data" \
  ghcr.io/realazthat/comfy_fulcrum:v0.0.1 client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  --data '{"resource_id": "'"${RESOURCE_A_ID}"'","channels": ["main"], "data": "{\"comfy_api_url\": \"url\"}"}' \
  register

docker run --rm --network="host" \
  -v "${PWD}:/data" \
  ghcr.io/realazthat/comfy_fulcrum:v0.0.1 client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  list

docker run --rm --network="host" \
  -v "${PWD}:/data" \
  ghcr.io/realazthat/comfy_fulcrum:v0.0.1 client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  --data '' \
  stats

TICKET=$(docker run --rm --network="host" \
  -v "${PWD}:/data" \
  ghcr.io/realazthat/comfy_fulcrum:v0.0.1 client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  --data '{"client_name": "me","channels": ["main"], "priority": "1"}' \
  get)

# Example TICKET:
# {"id": "4fe26e1fe5974e68b788f82cc9460b0b", "client_name": "me", "lease_timeout": 180.0, "ends": "2024-07-21T01:18:16.317032"}
echo "TICKET: ${TICKET}"

TICKET_ID=$(echo "${TICKET}" | jq -r '.id')
echo "TICKET_ID: ${TICKET_ID}"

RESOURCE_ID=
while [[ -z "${RESOURCE_ID}" ]]; do
  echo -e "${BLUE}Checking if resource is ready${NC}"
  TICKET=$(docker run --rm --network="host" \
  -v "${PWD}:/data" \
  ghcr.io/realazthat/comfy_fulcrum:v0.0.1 client \
    --fulcrum_api_url "${FULCRUM_API_URL}" \
    --data '{"id": "'"${TICKET_ID}"'"}' \
    touch)
  echo "TICKET: ${TICKET}"
  RESOURCE_ID=$(echo "${TICKET}" | jq -r '.resource_id')
  echo "RESOURCE_ID: ${RESOURCE_ID}"
  sleep 2
done

RESOURCE_DATA=$(echo "${TICKET}" | jq -r '.data')
COMFY_API_URL=$(echo "${RESOURCE_DATA}" | jq -r '.comfy_api_url')

echo -e "${BLUE}COMFY_API_URL: ${COMFY_API_URL}${NC}"

docker run --rm --network="host" \
  -v "${PWD}:/data" \
  ghcr.io/realazthat/comfy_fulcrum:v0.0.1 client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  --data '' \
  stats

sleep 2
docker run --rm --network="host" \
  -v "${PWD}:/data" \
  ghcr.io/realazthat/comfy_fulcrum:v0.0.1 client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  --data '{"id": "'"${TICKET_ID}"'", "report": "success", "report_extra": {}}' \
  release

docker run --rm --network="host" \
  -v "${PWD}:/data" \
  ghcr.io/realazthat/comfy_fulcrum:v0.0.1 client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  --data '{"resource_id": "'"${RESOURCE_A_ID}"'"}' \
  remove

docker run --rm --network="host" \
  -v "${PWD}:/data" \
  ghcr.io/realazthat/comfy_fulcrum:v0.0.1 client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  --data '' \
  stats
```
<!---->

If you want to build the image yourself, you can use the Dockerfile in the
repository.

Build:

<!---->
```bash

docker build -t my-comfy_fulcrum-image .

```
<!---->

Server:

<!---->
```bash


# NOTE: You must have PostgreSQL's uuid-ossp or pgcrypto extension installed.
# psql ${PG_CLI_OPTS} --dbname="${PG_DB_NAME}" -c 'CREATE EXTENSION IF NOT EXISTS "pgcrypto";' || true
# psql ${PG_CLI_OPTS} --dbname="${PG_DB_NAME}" -c 'CREATE EXTENSION IF NOT EXISTS "uuid-ossp";' || true

docker run --rm --network="host" \
  -v "${PWD}:/data" \
  my-comfy_fulcrum-image server \
  --dsn "${DSN}" \
  --host 0.0.0.0 --port "${FULCRUM_PORT}"

```
<!---->

Client:

<!---->
```bash

docker run --rm --network="host" \
  -v "${PWD}:/data" \
  my-comfy_fulcrum-image client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  --data '' \
  stats

RESOURCE_A_ID=a
docker run --rm --network="host" \
  -v "${PWD}:/data" \
  my-comfy_fulcrum-image client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  --data '{"resource_id": "'"${RESOURCE_A_ID}"'","channels": ["main"], "data": "{\"comfy_api_url\": \"url\"}"}' \
  register

docker run --rm --network="host" \
  -v "${PWD}:/data" \
  my-comfy_fulcrum-image client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  list

docker run --rm --network="host" \
  -v "${PWD}:/data" \
  my-comfy_fulcrum-image client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  --data '' \
  stats

TICKET=$(docker run --rm --network="host" \
  -v "${PWD}:/data" \
  my-comfy_fulcrum-image client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  --data '{"client_name": "me","channels": ["main"], "priority": "1"}' \
  get)

# Example TICKET:
# {"id": "4fe26e1fe5974e68b788f82cc9460b0b", "client_name": "me", "lease_timeout": 180.0, "ends": "2024-07-21T01:18:16.317032"}
echo "TICKET: ${TICKET}"

TICKET_ID=$(echo "${TICKET}" | jq -r '.id')
echo "TICKET_ID: ${TICKET_ID}"

RESOURCE_ID=
while [[ -z "${RESOURCE_ID}" ]]; do
  echo -e "${BLUE}Checking if resource is ready${NC}"
  TICKET=$(docker run --rm --network="host" \
  -v "${PWD}:/data" \
  my-comfy_fulcrum-image client \
    --fulcrum_api_url "${FULCRUM_API_URL}" \
    --data '{"id": "'"${TICKET_ID}"'"}' \
    touch)
  echo "TICKET: ${TICKET}"
  RESOURCE_ID=$(echo "${TICKET}" | jq -r '.resource_id')
  echo "RESOURCE_ID: ${RESOURCE_ID}"
  sleep 2
done

RESOURCE_DATA=$(echo "${TICKET}" | jq -r '.data')
COMFY_API_URL=$(echo "${RESOURCE_DATA}" | jq -r '.comfy_api_url')

echo -e "${BLUE}COMFY_API_URL: ${COMFY_API_URL}${NC}"

docker run --rm --network="host" \
  -v "${PWD}:/data" \
  my-comfy_fulcrum-image client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  --data '' \
  stats

sleep 2
docker run --rm --network="host" \
  -v "${PWD}:/data" \
  my-comfy_fulcrum-image client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  --data '{"id": "'"${TICKET_ID}"'", "report": "success", "report_extra": {}}' \
  release

docker run --rm --network="host" \
  -v "${PWD}:/data" \
  my-comfy_fulcrum-image client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  --data '{"resource_id": "'"${RESOURCE_A_ID}"'"}' \
  remove

docker run --rm --network="host" \
  -v "${PWD}:/data" \
  my-comfy_fulcrum-image client \
  --fulcrum_api_url "${FULCRUM_API_URL}" \
  --data '' \
  stats

```
<!---->

## 🤏 Versioning

We use SemVer for versioning. For the versions available, see the tags on this
repository.

## 🔑 License

This project is licensed under the MIT License - see the
[./LICENSE.md](./LICENSE.md) file for details.

[1]: ./.github/logo-exported.svg
[2]: https://github.com/realazthat/comfy-fulcrum
[3]:
  https://img.shields.io/badge/Audience-Developers-0A1E1E?style=plastic&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9ImN1cnJlbnRDb2xvciIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiIGNsYXNzPSJsdWNpZGUgbHVjaWRlLXVzZXJzIj48cGF0aCBkPSJNMTYgMjF2LTJhNCA0IDAgMCAwLTQtNEg2YTQgNCAwIDAgMC00IDR2MiIvPjxjaXJjbGUgY3g9IjkiIGN5PSI3IiByPSI0Ii8+PHBhdGggZD0iTTIyIDIxdi0yYTQgNCAwIDAgMC0zLTMuODciLz48cGF0aCBkPSJNMTYgMy4xM2E0IDQgMCAwIDEgMCA3Ljc1Ii8+PC9zdmc+
[4]:
  https://img.shields.io/badge/Platform-Linux-0A1E1E?style=plastic&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9ImN1cnJlbnRDb2xvciIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiIGNsYXNzPSJsdWNpZGUgbHVjaWRlLWxhcHRvcC1taW5pbWFsIj48cmVjdCB3aWR0aD0iMTgiIGhlaWdodD0iMTIiIHg9IjMiIHk9IjQiIHJ4PSIyIiByeT0iMiIvPjxsaW5lIHgxPSIyIiB4Mj0iMjIiIHkxPSIyMCIgeTI9IjIwIi8+PC9zdmc+
[5]:
  https://img.shields.io/github/languages/top/realazthat/comfy-fulcrum.svg?cacheSeconds=28800&style=plastic&color=0A1E1E
[6]:
  https://img.shields.io/github/license/realazthat/comfy-fulcrum?style=plastic&color=0A1E1E
[7]: ./LICENSE.md
[8]:
  https://img.shields.io/pypi/v/comfy-fulcrum?style=plastic&color=0A1E1E
[9]: https://pypi.org/project/comfy-fulcrum/
[10]:
  https://img.shields.io/pypi/pyversions/comfy-fulcrum?style=plastic&color=0A1E1E
[11]: https://github.com/realazthat/comfy-fulcrum/tree/master
[12]:
  https://img.shields.io/github/actions/workflow/status/realazthat/comfy-fulcrum/build-and-test.yml?branch=master&style=plastic
[13]:
  https://github.com/realazthat/comfy-fulcrum/actions/workflows/build-and-test.yml
[14]:
  https://img.shields.io/github/commits-since/realazthat/comfy-fulcrum/v0.0.1/master?style=plastic
[15]:
  https://github.com/realazthat/comfy-fulcrum/compare/v0.0.1...master
[16]:
  https://img.shields.io/github/last-commit/realazthat/comfy-fulcrum/master?style=plastic
[17]: https://github.com/realazthat/comfy-fulcrum/commits/master
[18]: https://github.com/realazthat/comfy-fulcrum/tree/develop
[19]:
  https://img.shields.io/github/actions/workflow/status/realazthat/comfy-fulcrum/build-and-test.yml?branch=develop&style=plastic
[20]:
  https://img.shields.io/github/commits-since/realazthat/comfy-fulcrum/v0.0.1/develop?style=plastic
[21]:
  https://github.com/realazthat/comfy-fulcrum/compare/v0.0.1...develop
[22]:
  https://img.shields.io/github/commits-since/realazthat/comfy-fulcrum/v0.0.1/develop?style=plastic
[23]:
  https://github.com/realazthat/comfy-fulcrum/compare/v0.0.1...develop
[24]:
  https://img.shields.io/github/last-commit/realazthat/comfy-fulcrum/develop?style=plastic
[25]: https://github.com/realazthat/comfy-fulcrum/commits/develop
