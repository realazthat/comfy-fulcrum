# -*- coding: utf-8 -*-

# SPDX-License-Identifier: MIT
#
# The Comfy Fulcrum project requires contributions made to this file be licensed
# under the MIT license or a compatible open source license. See LICENSE.md for
# the license text.

import asyncio
import datetime
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Union, overload

import sqlalchemy
from pydantic import TypeAdapter
from sqlalchemy import (TIMESTAMP, Boolean, Column, Float, Index, MetaData,
                        Result, String, Table, func, text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine.row import RowMapping
from sqlalchemy.ext.asyncio import (AsyncEngine, AsyncResult, AsyncSession,
                                    async_sessionmaker)
from sqlalchemy.schema import PrimaryKeyConstraint
from sqlalchemy.sql.expression import distinct, insert, select, update
from typing_extensions import Literal

from ..base import base as _base

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _AutoCommit(session: AsyncSession):
  async with session.begin():
    yield session
    await session.commit()


METADATA = MetaData()
RESOURCES = Table(
    'resources',
    METADATA,
    Column('channels', JSONB, nullable=False),
    Column('id', String, primary_key=True),
    Column('inserted',
           TIMESTAMP(timezone=False),
           nullable=False,
           server_default=func.now()),
    Column('updated',
           TIMESTAMP(timezone=False),
           nullable=False,
           server_default=func.now()),
    Column('data', String, nullable=False),
    Column('lease_id', String, nullable=True),
    Column('tombstone', Boolean, nullable=False, server_default=text('FALSE')),
    Index('resources_channel_live_resources_idx', 'tombstone', 'lease_id'),
)

RESOURCE_FREE_QUEUE = Table(
    'resource_free_queue',
    METADATA,
    Column('inserted',
           TIMESTAMP(timezone=False),
           nullable=False,
           server_default=func.now()),
    Column('channel', String, nullable=False),
    Column('resource_id', String, nullable=False),
    PrimaryKeyConstraint('resource_id', 'channel'),
    Index('resource_free_queue_resource_id_idx', 'resource_id'),
    Index('resource_free_queue_resource_channel_id_idx', 'channel',
          'resource_id'),
)

REPORTS = Table(
    'reports',
    METADATA,
    Column('id', String, primary_key=True),
    # UTC
    Column('inserted',
           TIMESTAMP(timezone=False),
           nullable=False,
           server_default=func.now()),
    Column('resource_id', String, nullable=False),
    Column('lease_id', String, nullable=True),
    Column('report', String, nullable=False),
    Column('extra', JSONB, nullable=True),
)

LEASES = Table(
    'leases',
    METADATA,
    Column('id', String, primary_key=True),
    Column('inserted',
           TIMESTAMP(timezone=False),
           nullable=False,
           server_default=func.now()),
    Column('updated',
           TIMESTAMP(timezone=False),
           nullable=False,
           server_default=func.now()),
    Column('client_name', String, nullable=False),
    Column('channels', JSONB, nullable=False),
    Column('priority', Float, nullable=False),
    Column('resource_id', String, nullable=True),
    Column('data', String, nullable=True),
    Column('lease_timeout', Float, nullable=False),
    Column('ends', TIMESTAMP(timezone=False), nullable=False),
    Column('tombstone', Boolean, nullable=False, server_default='FALSE'),
    Index('leases_expired_idx', 'tombstone', 'ends'),
    Index('leases_resource_idx', 'resource_id'),
)

CHANNEL_TICKET_QUEUE = Table(
    'channel_ticket_queue',
    METADATA,
    Column('channel', String, nullable=False),
    Column('lease_id', String, nullable=False),
    Column('priority', Float, nullable=False),
    Column('t', TIMESTAMP(timezone=False), nullable=False),
    PrimaryKeyConstraint('channel', 'lease_id'),
    Index('channel_ticket_queue_lease_id_t_idx', 'channel', 'lease_id'),
    Index('channel_ticket_queue_priority_t_idx', 'channel', 'priority', 't'),
)


class DBFulcrum(_base.FulcrumBase):

  def __init__(self, *, engine: AsyncEngine, lease_timeout: float,
               service_sleep_interval: float):
    self._engine = engine
    self._lease_timeout = lease_timeout

    self._async_session_maker = async_sessionmaker(self._engine,
                                                   expire_on_commit=False,
                                                   class_=AsyncSession)
    self._service_sleep_interval = service_sleep_interval
    self._service_task: Optional[asyncio.Task] = None

  def close(self):
    if self._service_task is None:
      return
    self._service_task.cancel()

  async def aclose(self):
    if self._service_task is None:
      return
    self._service_task.cancel()
    try:
      await self._service_task
    except asyncio.CancelledError:
      pass

  async def Initialize(self):
    async with self._engine.begin() as conn:
      await conn.run_sync(METADATA.create_all)
    self._service_task = asyncio.create_task(
        self._Service(), name=f'{self.__class__.__name__}._Service')

  async def DropAll(self):
    async with self._engine.begin() as conn:
      await conn.run_sync(METADATA.drop_all)

  def _GetSession(self) -> AsyncSession:
    return self._async_session_maker()

  async def _GetChannels(self, session: AsyncSession) -> List[_base.ChannelID]:
    channel_id_ta = TypeAdapter[_base.ChannelID](_base.ChannelID)

    stmt = select(CHANNEL_TICKET_QUEUE.c.channel).distinct()
    result: AsyncResult = await session.stream(stmt)
    row: RowMapping
    channels: List[_base.ChannelID] = []
    async for row in result.mappings():
      channels.append(channel_id_ta.validate_python(row.channel))
    return channels

  async def _ServiceChannelOnce(self, session: AsyncSession,
                                channel: _base.ChannelID):

    # Allocate some free resources to open tickets.
    #
    # 1. Find any free resources for this channel.
    # 2. Find the highest priority ticket for this channel.
    # 3. Match them.
    # 4. Remove the ticket from the ticket queue.
    # 5. Remove the resource from the free queue.
    # 6. Update the lease.
    # 7. Update the resource.

    sql = """
WITH free_resources AS (
  SELECT resource_id, ROW_NUMBER() OVER (ORDER BY RANDOM()) AS rn
  FROM resource_free_queue
  WHERE channel = :channel
), queued_tickets AS (
  SELECT lease_id, ROW_NUMBER() OVER (ORDER BY priority DESC, t ASC) AS rn
  FROM channel_ticket_queue
  WHERE channel = :channel
  ORDER BY priority DESC, t ASC
), matches_ AS (
  SELECT queued_tickets.lease_id, free_resources.resource_id, resources.data
  FROM queued_tickets
    INNER JOIN free_resources USING (rn)
    INNER JOIN resources ON resources.id = free_resources.resource_id
), remove_ticket_from_queue AS (
  DELETE FROM channel_ticket_queue
  WHERE lease_id IN (SELECT lease_id FROM matches_)
), remove_resource_from_queue AS (
  DELETE FROM resource_free_queue
  WHERE resource_id IN (SELECT resource_id FROM matches_)
), update_leases AS (
  UPDATE leases
  SET resource_id = matches_.resource_id,
      updated = now(),
      data = matches_.data
  FROM matches_
  WHERE id = matches_.lease_id
), updated_resources AS (
  UPDATE resources
  SET lease_id = matches_.lease_id
  FROM matches_
  WHERE id = matches_.resource_id
)
SELECT 1
"""
    stmt = sqlalchemy.text(sql)
    await session.execute(stmt, {'channel': channel})

  async def _ServiceTimedoutLeases(self, session: AsyncSession,
                                   now: datetime.datetime):
    # Update all leases that have timed out.
    # 1. Find all expired leases.
    # 2. Mark the expired leases as tombstoned.
    # 2. Remove the expired leases from the channel_ticket_queue.
    # 3. Add the newly free resources to the resource_free_queue.

    sql = """
WITH expired_leases AS (
  UPDATE leases
  SET tombstone = TRUE
  WHERE ends < :now
    AND tombstone IS FALSE
  RETURNING id as lease_id, resource_id
), expired_channel_ticket_queue AS (
  DELETE FROM channel_ticket_queue
  WHERE lease_id IN (SELECT lease_id FROM expired_leases)
  RETURNING *
), newly_free_resource_items AS (
  SELECT channel, resource_id
  FROM expired_leases INNER JOIN resources ON resources.id = expired_leases.resource_id
  CROSS JOIN jsonb_array_elements_text(resources.channels) AS channel
  WHERE resources.tombstone IS FALSE
), inserted_resource_items AS (
  INSERT INTO resource_free_queue(channel, resource_id)
  SELECT channel, resource_id
  FROM newly_free_resource_items
  ON CONFLICT DO NOTHING
), updated_resource AS (
  UPDATE resources
  SET lease_id = NULL
  FROM expired_leases
  WHERE id = expired_leases.resource_id
    -- This is redundant, but stricter. It should always be true.
    AND resources.lease_id = expired_leases.lease_id
), inserted_reports AS (
  INSERT INTO reports(id, resource_id, lease_id, report, extra)
  SELECT md5(random()::text || clock_timestamp()::text) AS report_id,
         expired_leases.resource_id as resource_id,
         expired_leases.lease_id AS lease_id,
         'timeout' AS report,
         '{}'::jsonb AS extra
  FROM expired_leases
  WHERE expired_leases.resource_id IS NOT NULL
)
  
SELECT 1
"""
    stmt = sqlalchemy.text(sql)
    await session.execute(stmt, {'now': now})

  async def _ServiceOnce(self):
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    async with self._GetSession() as session:
      async with _AutoCommit(session):
        channels: List[_base.ChannelID] = await self._GetChannels(session)
        await self._ServiceTimedoutLeases(session, now)
        for channel in channels:
          await self._ServiceChannelOnce(session, channel)

  async def _Service(self):
    while True:
      try:
        await self._ServiceOnce()
        await asyncio.sleep(self._service_sleep_interval)
      except asyncio.CancelledError:
        return
      except Exception:
        logger.exception('Error in DBFulcrum._Service, retrying')

  async def Get(self, *, client_name: _base.ClientName,
                channels: List[_base.ChannelID],
                priority: int) -> Union[_base.Lease, _base.Ticket]:
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

    async with self._GetSession() as session:
      async with _AutoCommit(session):
        ticket = _base.Ticket(id=_base.LeaseID(uuid.uuid4().hex),
                              client_name=client_name,
                              lease_timeout=self._lease_timeout,
                              ends=now +
                              datetime.timedelta(seconds=self._lease_timeout))

        stmt = insert(LEASES).values(
            id=ticket.id,
            client_name=client_name,
            channels=channels,
            priority=priority,
            resource_id=None,
            data=None,
            lease_timeout=self._lease_timeout,
            ends=now + datetime.timedelta(seconds=self._lease_timeout),
        )
        await session.execute(stmt)

        for channel in channels:
          stmt = insert(CHANNEL_TICKET_QUEUE).values(
              channel=channel,
              lease_id=ticket.id,
              priority=priority,
              t=now,
          )
        await session.execute(stmt)

        return ticket
      # TODO: If the resource can be immediately allocated, return a Lease.

  @overload
  async def _Touch(self, *, id: _base.LeaseID,
                   type: Literal['lease']) -> Optional[_base.Lease]:
    ...

  @overload
  async def _Touch(
      self, *, id: _base.LeaseID, type: Literal['ticket_or_lease']
  ) -> Union[_base.Ticket, _base.Lease, None]:
    ...

  async def _Touch(
      self, *, id: _base.LeaseID, type: Literal['lease', 'ticket_or_lease']
  ) -> Union[_base.Ticket, _base.Lease, None]:

    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    async with self._GetSession() as session:
      async with _AutoCommit(session):

        where_clauses = [LEASES.c.id == id, LEASES.c.tombstone.is_(False)]

        stmt = update(LEASES).where(*where_clauses).values(
            updated=now,
            lease_timeout=self._lease_timeout,
            ends=now + datetime.timedelta(seconds=self._lease_timeout),
        ).returning(*LEASES.c)

        result: AsyncResult = await session.stream(stmt)

        row: Optional[RowMapping] = await result.mappings().first()
        if row is None:
          return None

        lease_id: _base.LeaseID = row.id
        client_name: _base.ClientName = row.client_name
        resource_id: Optional[_base.ResourceID] = row.resource_id
        data: Optional[str] = row.data
        ends: datetime.datetime = row.ends
        tombstone: bool = row.tombstone
        lease_timeout: float = row.lease_timeout

        if now > ends:
          return None
        if tombstone:
          return None

        if type == 'lease':
          if resource_id is None:
            return None
          if data is None:
            raise AssertionError(
                'Expected data to be set on a lease with a resource id set')

          return _base.Lease(id=lease_id,
                             client_name=client_name,
                             resource_id=resource_id,
                             data=data,
                             lease_timeout=lease_timeout,
                             ends=ends)
        elif type == 'ticket_or_lease':
          if resource_id is None:
            return _base.Ticket(id=lease_id,
                                client_name=client_name,
                                lease_timeout=lease_timeout,
                                ends=ends)
          if data is None:
            raise AssertionError(
                'Expected data to be set on a lease with a resource id set')
          return _base.Lease(id=lease_id,
                             client_name=client_name,
                             resource_id=resource_id,
                             data=data,
                             lease_timeout=lease_timeout,
                             ends=ends)
        else:
          raise ValueError(f'Unexpected type: {type}')

      # TODO: If the resource can be immediately allocated, return a Lease.

  async def TouchTicket(
      self, *, id: _base.LeaseID) -> Union[_base.Lease, _base.Ticket, None]:
    return await self._Touch(id=id, type='ticket_or_lease')

  async def TouchLease(self, *, id: _base.LeaseID) -> Optional[_base.Lease]:
    return await self._Touch(id=id, type='lease')

  async def Release(self, *, id: _base.LeaseID,
                    report: Optional[_base.ReportType],
                    report_extra: Optional[Any]):
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    async with self._GetSession() as session:
      async with _AutoCommit(session):
        lease_update_stmt = update(LEASES).where(LEASES.c.id == id).values(
            tombstone=True,
        ).returning(*LEASES.c)
        result: AsyncResult = await session.stream(lease_update_stmt)
        row: Optional[RowMapping] = await result.mappings().first()
        if row is None:
          return
        resource_id: Optional[_base.ResourceID] = row.resource_id
        if resource_id is None:
          return
        lease_id: _base.LeaseID = row.id

        # Save reports.
        report_insert_stmt = insert(REPORTS).values(
            id=uuid.uuid4().hex,
            resource_id=resource_id,
            lease_id=lease_id,
            report=report,
            extra=report_extra,
        )
        await session.execute(report_insert_stmt)

        # Update the resource.
        resource_update_stmt = update(RESOURCES) \
            .where(RESOURCES.c.id == resource_id, RESOURCES.c.lease_id==lease_id) \
            .values(updated=now, lease_id=None)
        await session.execute(resource_update_stmt)

        # Update the resource queue.
        sql = """
WITH inserted_resource_items AS (
  INSERT INTO resource_free_queue(channel, resource_id)
  SELECT channel, resources.id
  FROM resources
  CROSS JOIN jsonb_array_elements_text(resources.channels) AS channel
  WHERE resources.id = :resource_id
    AND resources.tombstone IS FALSE
)
SELECT 1
"""
        stmt = sqlalchemy.text(sql)
        await session.execute(stmt, {'resource_id': resource_id})

  async def RegisterResource(self, *, resource_id: _base.ResourceID,
                             channels: List[_base.ChannelID], data: str):
    async with self._GetSession() as session:
      async with _AutoCommit(session):
        sql = """

WITH inserted_resource AS (
  INSERT INTO resources(id, channels, data)
  VALUES (:id, :channels, :data)
  RETURNING *
), newly_free_resource_items AS (
  SELECT channel, inserted_resource.id AS resource_id
  FROM inserted_resource
    CROSS JOIN jsonb_array_elements_text(inserted_resource.channels) AS channel
), inserted_resource_items AS (
  INSERT INTO resource_free_queue(channel, resource_id)
  SELECT channel, resource_id
  FROM newly_free_resource_items
)
SELECT 1
"""
        stmt = sqlalchemy.text(sql)
        stmt = stmt.bindparams(sqlalchemy.bindparam('channels', type_=JSONB))
        await session.execute(stmt, {
            'id': resource_id,
            'channels': channels,
            'data': data,
        })

  async def RemoveResource(
      self, *, resource_id: _base.ResourceID) -> _base.RemovedResourceInfo:
    async with self._GetSession() as session:
      async with _AutoCommit(session):
        sql = """
WITH removed_resource AS (
  UPDATE resources
  SET tombstone = TRUE
  WHERE id = :resource_id
  RETURNING *
), removed_resource_items AS (
  DELETE FROM resource_free_queue
  WHERE resource_id = :resource_id
  RETURNING *
), stale_leases AS (
  UPDATE leases
  SET tombstone = TRUE
  WHERE resource_id = :resource_id
  RETURNING *
)
SELECT (SELECT COUNT(*) FROM removed_resource) as removed_resource_count,
       (SELECT COUNT(*) FROM removed_resource_items) as removed_resource_items_count,
       (SELECT COUNT(*) FROM stale_leases) as stale_leases_count
"""
        stmt = sqlalchemy.text(sql)
        stmt = stmt.bindparams(sqlalchemy.bindparam('resource_id',
                                                    type_=String))
        stmt = stmt.bindparams(resource_id=resource_id)

        result = await session.execute(stmt)
        row = result.mappings().first()
        if row is None:
          raise AssertionError('Expected a row, got None')
        removed_resource_count = row.removed_resource_count
        removed_resource_items_count = row.removed_resource_items_count
        stale_leases_count = row.stale_leases_count
        return _base.RemovedResourceInfo(
            removed_resource_count=removed_resource_count,
            removed_resource_items_count=removed_resource_items_count,
            stale_leases_count=stale_leases_count,
        )

  async def _ResourceCount(self, *, session: AsyncSession) -> int:
    stmt = select(func.count(distinct(RESOURCES.c.id)).label('count')).where(
        RESOURCES.c.tombstone.is_(False))

    result: Result = await session.execute(stmt)
    queue_size = result.scalar()
    if not isinstance(queue_size, int):
      raise ValueError(f'Expected int, got {type(queue_size)}: {queue_size}')
    return queue_size

  async def _ChannelResourceCounts(
      self, *, session: AsyncSession) -> Dict[_base.ChannelID, int]:
    channel_id_ta = TypeAdapter[_base.ChannelID](_base.ChannelID)

    sql = """

SELECT channel, count(*) AS count
FROM resources, jsonb_array_elements_text(resources.channels) AS channel
WHERE tombstone IS FALSE
GROUP BY channel
"""
    stmt = sqlalchemy.text(sql)
    result = await session.stream(stmt)
    channel_resource_counts: Dict[_base.ChannelID, int] = {}
    async for row in result.mappings():
      channel = channel_id_ta.validate_python(row.channel)
      if not isinstance(channel, str):
        raise ValueError(f'Expected str, got {type(channel)}: {channel}')
      count = row.count
      if not isinstance(count, int):
        raise ValueError(f'Expected int, got {type(count)}: {count}')
      channel_resource_counts[channel] = count
    return channel_resource_counts

  async def _QueueSize(self, *, session: AsyncSession) -> int:
    stmt = select(
        func.count(distinct(CHANNEL_TICKET_QUEUE.c.lease_id)).label('count'))

    result: Result = await session.execute(stmt)
    queue_size = result.scalar()
    if not isinstance(queue_size, int):
      raise ValueError(f'Expected int, got {type(queue_size)}: {queue_size}')
    return queue_size

  async def _ChannelQueueSize(
      self, *, session: AsyncSession) -> Dict[_base.ChannelID, int]:
    channel_id_ta = TypeAdapter[_base.ChannelID](_base.ChannelID)

    stmt = select(
        CHANNEL_TICKET_QUEUE.c.channel,
        func.count(distinct(
            CHANNEL_TICKET_QUEUE.c.lease_id).label('count'))).group_by(
                CHANNEL_TICKET_QUEUE.c.channel)
    result = await session.stream(stmt)
    channel_queue_sizes: Dict[_base.ChannelID, int] = {}
    async for row in result.mappings():
      channel = channel_id_ta.validate_python(row.channel)
      count = row.count
      if not isinstance(count, int):
        raise ValueError(f'Expected int, got {type(count)}: {count}')
      channel_queue_sizes[channel] = count
    return channel_queue_sizes

  async def ListResources(self) -> List[_base.ResourceMeta]:
    async with self._GetSession() as session:
      async with _AutoCommit(session):
        stmt = select(RESOURCES.c.id, RESOURCES.c.channels, RESOURCES.c.data,
                      RESOURCES.c.inserted).where(
                          RESOURCES.c.tombstone.is_(False))
        result: AsyncResult = await session.stream(stmt)

        resources: List[_base.ResourceMeta] = []
        row: RowMapping
        async for row in result.mappings():
          resource_id: _base.ResourceID = row.id
          channels: List[_base.ChannelID] = row.channels
          data: str = row.data
          inserted: datetime.datetime = row.inserted
          resources.append(
              _base.ResourceMeta(id=resource_id,
                                 channels=channels,
                                 data=data,
                                 inserted=inserted))
        return resources

  async def Stats(self) -> _base.Stats:
    async with self._GetSession() as session:
      async with _AutoCommit(session):
        queue_size = await self._QueueSize(session=session)
        channel_queue_sizes = await self._ChannelQueueSize(session=session)
        resource_count = await self._ResourceCount(session=session)
        channel_resource_counts = await self._ChannelResourceCounts(
            session=session)

        return _base.Stats(queue_size=queue_size,
                           channel_queue_sizes=channel_queue_sizes,
                           resource_count=resource_count,
                           channel_resource_counts=channel_resource_counts)
