# -*- coding: utf-8 -*-

# SPDX-License-Identifier: MIT
#
# The Comfy Fulcrum project requires contributions made to this file be licensed
# under the MIT license or a compatible open source license. See LICENSE.md for
# the license text.

import asyncio
import logging
import socket
import sys
from os import environ
from typing import Any, List, Optional, Union

import fastapi
import hypercorn
from hypercorn.asyncio import serve as hypercorn_serve
from sqlalchemy.ext.asyncio import create_async_engine

from ..base.base import (ChannelID, ClientName, FulcrumBase, Lease, LeaseID,
                         ReportType, ResourceID, ResourceMeta, Stats, Ticket)
from ..db.db import METADATA, DBFulcrum
from ..fastapi_client.fastapi_client import FulcrumClient
from ..fastapi_server.fastapi_server import FulcrumServerRoutes


class FulcrumLogger(FulcrumBase):

  def __init__(self, *, fulcrum: FulcrumBase, logger: logging.Logger):
    self._fulcrum = fulcrum
    self._logger = logger

  async def Get(self, *, client_name: ClientName, channels: List[ChannelID],
                priority: int) -> Union[Lease, Ticket]:
    try:
      self._logger.debug('Fulcrum.Get(client_name=%r, channels=%r)',
                         client_name, channels)
      res = await self._fulcrum.Get(client_name=client_name,
                                    channels=channels,
                                    priority=priority)
      self._logger.debug('Fulcrum.Get(client_name=%r, channels=%r) -> %r',
                         client_name, channels, res)
      return res
    except Exception:
      self._logger.exception('Error in Get')
      raise

  async def TouchTicket(self, *, id: LeaseID) -> Union[Lease, Ticket, None]:
    try:
      self._logger.debug('Fulcrum.TouchTicket(ticket=%r)', id)
      res = await self._fulcrum.TouchTicket(id=id)
      self._logger.debug('Fulcrum.TouchTicket(ticket=%r) -> %r', id, res)
      return res
    except Exception:
      self._logger.exception('Error in TouchTicket')
      raise

  async def TouchLease(self, *, id: LeaseID) -> Optional[Lease]:
    try:
      self._logger.debug('Fulcrum.TouchLease(ticket=%r)', id)
      res = await self._fulcrum.TouchLease(id=id)
      self._logger.debug('Fulcrum.TouchLease(ticket=%r) -> %r', id, res)
      return res

    except Exception:
      self._logger.exception('Error in TouchLease')
      raise

  async def Release(self, *, id: LeaseID, report: Optional[ReportType],
                    report_extra: Optional[Any]):
    try:
      self._logger.debug(
          'Fulcrum.Release(ticket=%r, report=%r, report_extra=%r)', id, report,
          report_extra)
      res = await self._fulcrum.Release(id=id,
                                        report=report,
                                        report_extra=report_extra)
      self._logger.debug(
          'Fulcrum.Release(ticket=%r, report=%r, report_extra=%r) -> %r', id,
          report, report_extra, res)
      return res
    except Exception:
      self._logger.exception('Error in Release')
      raise

  async def RegisterResource(self, *, resource_id: ResourceID,
                             channels: List[ChannelID], data: str):
    try:
      self._logger.debug(
          'Fulcrum.RegisterResource(resource_id=%r, channels=%r, data=%r)',
          resource_id, channels, data)
      res = await self._fulcrum.RegisterResource(resource_id=resource_id,
                                                 channels=channels,
                                                 data=data)
      self._logger.debug(
          'Fulcrum.RegisterResource(resource_id=%r, channels=%r, data=%r) -> %r',
          resource_id, channels, data, res)
      return res
    except Exception:
      self._logger.exception('Error in RegisterResource')
      raise

  async def RemoveResource(self, *, resource_id: ResourceID):
    try:
      self._logger.debug('Fulcrum.RemoveResource(resource_id=%r)', resource_id)
      res = await self._fulcrum.RemoveResource(resource_id=resource_id)
      self._logger.debug('Fulcrum.RemoveResource(resource_id=%r) -> %r',
                         resource_id, res)
      return res
    except Exception:
      self._logger.exception('Error in RemoveResource')
      raise

  async def ListResources(self) -> List[ResourceMeta]:
    try:
      self._logger.debug('Fulcrum.ListResources()')
      res = await self._fulcrum.ListResources()
      self._logger.debug('Fulcrum.ListResources() -> %r', res)
      return res
    except Exception:
      self._logger.exception('Error in ListResources')
      raise

  async def Stats(self) -> Stats:
    try:
      self._logger.debug('Fulcrum.Stats()')
      res = await self._fulcrum.Stats()
      self._logger.debug('Fulcrum.Stats() -> %r', res)
      return res
    except Exception:
      self._logger.exception('Error in Stats')
      raise


async def ServerThread(*, app: fastapi.FastAPI, port: int):
  hconfig = hypercorn.Config()
  hconfig.bind = [f'0.0.0.0:{port}']
  hconfig.loglevel = 'debug'
  hconfig.workers = 10
  hconfig.debug = True

  await hypercorn_serve(app, hconfig)  # type: ignore


def GetFreePort() -> int:
  with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind(('localhost', 0))
    return s.getsockname()[1]


async def amain():

  FULCRUM_TEST_DSN: Optional[str] = environ.get('FULCRUM_TEST_DSN', None)
  if FULCRUM_TEST_DSN is None:
    raise Exception(
        'FULCRUM_TEST_DSN environment variable must be set to a valid DSN')
  port: int = GetFreePort()

  logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)

  app = fastapi.FastAPI()

  engine = create_async_engine(FULCRUM_TEST_DSN)

  async with DBFulcrum(engine=engine,
                       lease_timeout=60.,
                       service_sleep_interval=0.1) as db_fulcrum:
    async with engine.begin() as conn:
      await conn.run_sync(METADATA.drop_all)
    await db_fulcrum.Initialize()

    # fulcrum = FulcrummLogger(fulcrum=db_fulcrum, logger=logging.getLogger('FulcrummLogger'))
    fulcrum = db_fulcrum

    fulcrum_routes = FulcrumServerRoutes(fulcrum=fulcrum)
    app.include_router(fulcrum_routes.Router())

    server_task = asyncio.create_task(ServerThread(app=app, port=port))

    fulcrum_client = FulcrumClient(fulcrum_api_url=f'http://localhost:{port}')

    await fulcrum_client.RegisterResource(
        resource_id=ResourceID('resource1'),
        channels=[ChannelID('lo'), ChannelID('hi')],
        data="{'foo': 'bar'}",
    )

    ticket1 = await fulcrum_client.Get(client_name=ClientName('client1'),
                                       channels=[ChannelID('lo')],
                                       priority=0)
    ticket2 = await fulcrum_client.Get(client_name=ClientName('client2'),
                                       channels=[ChannelID('lo')],
                                       priority=0)

    async def WaitForLease(ticket: Union[Lease, Ticket, None]) -> Lease:
      while True:
        print('Waiting for lease, type(ticket):', type(ticket))
        if ticket is None:
          raise Exception('Expected ticket or lease, got None')
        if isinstance(ticket, Lease):
          return ticket
        ticket = await fulcrum_client.TouchTicket(id=ticket.id)
        await asyncio.sleep(1)

    async def EnsureStillTicket(ticket: Union[Ticket, Lease, None]) -> Ticket:
      if isinstance(ticket, Lease):
        raise Exception('Expected ticket, got lease')
      if ticket is None:
        raise Exception('Expected ticket, got None')

      ticket = await fulcrum_client.TouchTicket(id=ticket.id)
      if isinstance(ticket, Lease):
        raise Exception('Expected ticket, got lease')
      if ticket is None:
        raise Exception('Expected ticket, got None')
      return ticket

    print('waiting for lease1')
    lease1 = await WaitForLease(ticket1)

    print(lease1)
    print('sleeping for a bit')
    await asyncio.sleep(5)
    print('checking that lease2 is still a ticket')
    ticket2 = await EnsureStillTicket(ticket2)

    print('releasing lease1')
    await fulcrum_client.Release(id=lease1.id,
                                 report='success',
                                 report_extra=None)

    print('get stats')
    stats = await fulcrum_client.Stats()
    print('stats:', stats)

    print('waiting for lease2')
    lease2 = await WaitForLease(ticket2)

    print(lease2)

    print('releasing lease2')
    await fulcrum_client.Release(id=lease2.id,
                                 report='success',
                                 report_extra=None)

    print('remove resource')

    await fulcrum_client.RemoveResource(resource_id=ResourceID('resource1'))

    print('get a third ticket')
    ticket3: Union[Lease, Ticket, None]
    ticket3 = await fulcrum_client.Get(client_name=ClientName('client3'),
                                       channels=[ChannelID('lo')],
                                       priority=0)

    await asyncio.sleep(5)
    print('touch ticket3')
    ticket3 = await fulcrum_client.TouchTicket(id=ticket3.id)

    if not isinstance(ticket3, Ticket):
      raise Exception('Expected ticket, got lease')

    print('cancelling server task')
    server_task.cancel()
    try:
      await server_task
    except asyncio.CancelledError:
      pass


if __name__ == '__main__':
  asyncio.run(amain())
