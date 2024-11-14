# -*- coding: utf-8 -*-

# SPDX-License-Identifier: MIT
#
# The Comfy Fulcrum project requires contributions made to this file be licensed
# under the MIT license or a compatible open source license. See LICENSE.md for
# the license text.

import json
import os
import sys
from typing import Optional, Union
import uuid
import asyncio
import socket

import hypercorn
import hypercorn.asyncio
import fastapi
import aiohttp
from comfy_fulcrum.base.base import ChannelID, ClientName, Lease, LeaseID, ResourceID, Ticket
from comfy_fulcrum.fastapi_client.fastapi_client import FulcrumClient
from comfy_fulcrum.fastapi_server.fastapi_server import FulcrumServerRoutes
from comfy_fulcrum.db.db import DBFulcrum
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


async def ServerExample(*, port: int, dsn: str):
  # SERVER_SNIPPET_START
  app = fastapi.FastAPI()

  db_engine: AsyncEngine = create_async_engine(dsn,
                                               echo=False,
                                               pool_size=10,
                                               max_overflow=20,
                                               pool_timeout=5,
                                               pool_recycle=1800,
                                               isolation_level='READ COMMITTED')
  fulcrum = DBFulcrum(engine=db_engine,
                      lease_timeout=60. * 5,
                      service_sleep_interval=1.0,
                      retry=True)
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
  # SERVER_SNIPPET_END


async def WaitForServer(fulcrum_api_docs_url: str, server_task: asyncio.Task):
  while True:
    try:
      if server_task.done():
        server_task.result()
      async with aiohttp.ClientSession() as session:
        async with session.get(fulcrum_api_docs_url) as resp:
          if resp.status == 200:
            return
    except aiohttp.ClientConnectionError:
      print('Waiting for server to start', file=sys.stderr)
    await asyncio.sleep(1)


async def ProviderClientExample(fulcrum_api_url: str, comfy_api_url: str):
  # PROVIDER_CLIENT_SNIPPET_START

  client = FulcrumClient(fulcrum_api_url=fulcrum_api_url)

  print(await client.Stats(), file=sys.stderr)

  print(await client.RegisterResource(channels=[ChannelID('main')],
                                      resource_id=ResourceID(uuid.uuid4().hex),
                                      data=json.dumps(
                                          {'comfy_api_url': comfy_api_url})),
        file=sys.stderr)
  print(await client.ListResources(), file=sys.stderr)
  # PROVIDER_CLIENT_SNIPPET_END


async def ConsumerClientExample(fulcrum_api_url: str):
  # CONSUMER_CLIENT_SNIPPET_START
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
  # CONSUMER_CLIENT_SNIPPET_END


def GetFreePort() -> int:
  s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  s.bind(('localhost', 0))
  addr, port = s.getsockname()
  s.close()
  return port


async def amain():
  comfy_api_url = 'http://localhost:8188'
  dsn: Optional[str] = os.environ.get('DSN')
  if dsn is None:
    print('Please set the DSN environment variable', file=sys.stderr)
    exit(1)

  port = GetFreePort()
  server_task = asyncio.create_task(ServerExample(port=port, dsn=dsn))
  fulcrum_api_url: str = f'http://localhost:{port}'
  fulcrum_api_docs_url: str = f'http://localhost:{port}/docs'

  await WaitForServer(fulcrum_api_docs_url=fulcrum_api_docs_url,
                      server_task=server_task)
  await ProviderClientExample(fulcrum_api_url=fulcrum_api_url,
                              comfy_api_url=comfy_api_url)
  await ConsumerClientExample(fulcrum_api_url=fulcrum_api_url)

  server_task.cancel()

  try:
    await server_task
  except asyncio.CancelledError:
    pass


if __name__ == '__main__':
  asyncio.run(amain())
