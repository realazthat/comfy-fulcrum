# -*- coding: utf-8 -*-

# SPDX-License-Identifier: MIT
#
# The Comfy Fulcrum project requires contributions made to this file be licensed
# under the MIT license or a compatible open source license. See LICENSE.md for
# the license text.

import asyncio
import json
import os
import random
import sys
import uuid
from typing import List, Optional, Union

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from comfy_fulcrum.base.base import (ChannelID, ClientName, FulcrumBase, Lease, ResourceID,
                         Ticket)
from comfy_fulcrum.db.db import DBFulcrum


async def ResourceOwnerThread(fulcrum: FulcrumBase, channels: List[ChannelID]):
  while True:
    channels = random.sample(channels, k=random.randint(1, len(channels)))

    resource_id = ResourceID(uuid.uuid4().hex)
    await fulcrum.RegisterResource(resource_id=resource_id,
                                   channels=channels,
                                   data='data')

    await asyncio.sleep(random.uniform(60, 60 * 2))
    await fulcrum.RemoveResource(resource_id=resource_id)


async def ConsumerThread(fulcrum: FulcrumBase, channels: List[ChannelID]):
  client_name = uuid.uuid4().hex
  while True:
    channels = random.sample(channels, k=random.randint(1, len(channels)))
    priority = random.randint(0, 4)
    ticket: Union[Lease, Ticket, None]
    ticket = await fulcrum.Get(client_name=ClientName(client_name),
                               channels=channels,
                               priority=priority)
    while ticket is not None and isinstance(ticket, Ticket):
      ticket = await fulcrum.TouchTicket(id=ticket.id)
      await asyncio.sleep(1)
    while ticket is not None and isinstance(ticket, Lease):
      action: str
      action, = random.choices(['wait', 'touch', 'release'],
                              weights=[1, 0.2, 0.1],
                              k=1)
      if action == 'wait':
        await asyncio.sleep(random.uniform(1, 5))
      elif action == 'touch':
        ticket = await fulcrum.TouchLease(id=ticket.id)
      elif action == 'release':
        await fulcrum.Release(id=ticket.id, report='success', report_extra=None)
        ticket = None
      await asyncio.sleep(1)
    await asyncio.sleep(1)

async def StatsThread(fulcrum: FulcrumBase):
  while True:
    stats = await fulcrum.Stats()
    print(json.dumps(stats.model_dump(), indent=2))
    await asyncio.sleep(5)

async def amain():
  dsn: Optional[str] = os.environ.get('FULCRUM_TEST_DSN')
  if dsn is None:
    print('Please set the FULCRUM_TEST_DSN environment variable', file=sys.stderr)
    exit(1)

  db_engine: AsyncEngine = create_async_engine(dsn,
                                               echo=False,
                                               pool_size=10,
                                               max_overflow=20,
                                               pool_timeout=5,
                                               pool_recycle=1800,
                                               isolation_level='REPEATABLE READ')
  fulcrum = DBFulcrum(engine=db_engine,
                      lease_timeout=60. * 5,
                      service_sleep_interval=1.0)
  await fulcrum.DropAll()
  await fulcrum.Initialize()

  channels = [ChannelID(f'channel_{i}') for i in range(20)]
  resources = 20
  consumers = 200

  consumer_tasks = [
      asyncio.create_task(ConsumerThread(fulcrum=fulcrum, channels=channels))
      for _ in range(consumers)
  ]
  resource_owner_tasks = [
      asyncio.create_task(ResourceOwnerThread(fulcrum=fulcrum, channels=channels))
      for _ in range(resources)
  ]

  stats_task = asyncio.create_task(StatsThread(fulcrum=fulcrum))

  try:
    await asyncio.wait_for(asyncio.gather(stats_task, *consumer_tasks, *resource_owner_tasks),  timeout=5 * 60)
  except asyncio.TimeoutError:
    pass

if __name__ == '__main__':
  asyncio.run(amain())
