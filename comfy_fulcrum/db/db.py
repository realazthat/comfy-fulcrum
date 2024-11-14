# -*- coding: utf-8 -*-

# SPDX-License-Identifier: MIT
#
# The Comfy Fulcrum project requires contributions made to this file be licensed
# under the MIT license or a compatible open source license. See LICENSE.md for
# the license text.

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import (Any, Awaitable, Callable, Dict, List, Optional, Union,
                    overload)

import sqlalchemy
from asyncpg import SerializationError
from pydantic import TypeAdapter
from sqlalchemy import (TIMESTAMP, Boolean, Column, Float, Index, MetaData,
                        Result, String, Table, bindparam, cast, func, text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine.row import RowMapping
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (AsyncEngine, AsyncResult, AsyncSession,
                                    async_sessionmaker)
from sqlalchemy.schema import PrimaryKeyConstraint
from sqlalchemy.sql.expression import distinct, select, update
from tenacity import (retry_any, retry_if_exception_cause_type,
                      retry_if_exception_type, retry_if_result,
                      wait_exponential_jitter)
from typing_extensions import Literal

from ..base import base as _base
from ..private.utilities import (NormalizeDatetime, UTCNaiveDatetime, UTCNow,
                                 instance_retry)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _AutoCommit(session: AsyncSession, *,
                      sanity: Optional[Callable[[AsyncSession],
                                                Awaitable[None]]]):

  async with session.begin():

    if sanity is not None:
      await sanity(session)
    yield session
    if sanity is not None:
      await sanity(session)


METADATA = MetaData()
RESOURCES = Table(
    'resources',
    METADATA,
    Column('channels', JSONB, nullable=False),
    Column('id', String, primary_key=True),
    Column('inserted',
           TIMESTAMP(timezone=False),
           nullable=False,
           server_default=cast(func.timezone('UTC', func.now()), TIMESTAMP)),
    Column('updated',
           TIMESTAMP(timezone=False),
           nullable=False,
           server_default=cast(func.timezone('UTC', func.now()), TIMESTAMP)),
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
           server_default=cast(func.timezone('UTC', func.now()), TIMESTAMP)),
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
           server_default=cast(func.timezone('UTC', func.now()), TIMESTAMP)),
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
           server_default=cast(func.timezone('UTC', func.now()), TIMESTAMP)),
    Column('updated',
           TIMESTAMP(timezone=False),
           nullable=False,
           server_default=cast(func.timezone('UTC', func.now()), TIMESTAMP)),
    Column('client_name', String, nullable=False),
    Column('channels', JSONB, nullable=False),
    Column('priority', Float, nullable=False),
    Column('resource_id', String, nullable=True),
    Column('data', String, nullable=True),
    Column('lease_timeout', Float, nullable=False),
    Column('ends', TIMESTAMP(timezone=False), nullable=False),
    Column('tombstone', Boolean, nullable=False, server_default='FALSE'),
    Index('leases_tombstone_idx', 'tombstone', 'ends'),
    Index('leases_tombstone_resource_ends_idx', 'tombstone', 'resource_id',
          'ends'),
    Index('leases_resource_idx', 'resource_id'),
)

# TODO: Add an index on (channel, priority DESC, t ASC), as it is ordered by
# this in the queries.
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


async def _IsGenUUIDAvailable(engine: AsyncEngine, uuid_gen_func: str) -> bool:
  session_maker = async_sessionmaker(engine,
                                     expire_on_commit=False,
                                     class_=AsyncSession)
  async with session_maker() as session:
    async with session.begin():
      try:
        result = await session.execute(text(f'SELECT {uuid_gen_func}'))
        result.fetchone()
      except Exception:
        return False
      return True


def _IsSerializationError(exception: BaseException) -> bool:
  if isinstance(exception, SerializationError):
    return True
  if isinstance(exception, DBAPIError):
    if exception.__cause__ is not None:
      if _IsSerializationError(exception.__cause__):
        return True
    if exception.orig is not None:
      if _IsSerializationError(exception.orig):
        return True

  return False


class DBFulcrum(_base.FulcrumBase):

  def __init__(self, *, engine: AsyncEngine, lease_timeout: float,
               service_sleep_interval: float, retry: bool):
    self._engine = engine
    self._lease_timeout = lease_timeout

    self._async_session_maker = async_sessionmaker(self._engine,
                                                   expire_on_commit=False,
                                                   class_=AsyncSession)
    self._service_sleep_interval = service_sleep_interval
    self._service_task: Optional[asyncio.Task] = None
    self.debug = False
    self._uuid_gen_func: Optional[str] = None
    self._initialized = False

    if retry:
      self.tenacity_kwargs = {}
    else:
      self.tenacity_kwargs = {
          'retry':
          retry_any(
              retry_if_exception_type((SerializationError, )),
              retry_if_exception_cause_type((SerializationError, )),
              retry_if_result(_IsSerializationError),
          ),
          # 'stop': stop_after_attempt(3),
          'wait':
          wait_exponential_jitter(initial=1.0),
      }

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
    uuid_gen_funcs = {
        'gen_random_uuid': 'gen_random_uuid',
        'uuid_generate_v4': 'uuid_generate_v4',
        'md5': 'md5(random()::text || clock_timestamp()::text)'
    }
    for _, uuid_gen_func in uuid_gen_funcs.items():
      if await _IsGenUUIDAvailable(self._engine, uuid_gen_func):
        self._uuid_gen_func = uuid_gen_func
        break
    if self._uuid_gen_func is None:
      raise RuntimeError(
          'No UUID generator function available, somehow failed to fallback to md5+random+clock_timestamp'
      )

    async with self._engine.begin() as conn:
      await conn.run_sync(METADATA.create_all)
    self._service_task = asyncio.create_task(
        self._Service(), name=f'{self.__class__.__name__}._Service')
    self._initialized = True

  async def DropAll(self):
    async with self._engine.begin() as conn:
      await conn.run_sync(METADATA.drop_all)

  async def _GetSession(self) -> AsyncSession:
    return self._async_session_maker()

  async def _GetChannels(self, session: AsyncSession) -> List[_base.ChannelID]:
    channel_id_ta = TypeAdapter(_base.ChannelID)

    stmt = select(CHANNEL_TICKET_QUEUE.c.channel).distinct()
    result: AsyncResult = await session.stream(stmt)
    row: RowMapping
    channels: List[_base.ChannelID] = []
    async for row in result.mappings():
      channels.append(channel_id_ta.validate_python(row.channel))
    return channels

  @instance_retry()
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
), queued_channel_ticket_items AS (
  SELECT lease_id, ROW_NUMBER() OVER (ORDER BY priority DESC, t ASC) AS rn
  FROM channel_ticket_queue
  WHERE channel = :channel
  ORDER BY priority DESC, t ASC
), potential_matches_ AS (
  SELECT
    queued_channel_ticket_items.lease_id,
    free_resources.resource_id,
    resources.data
  FROM leases
  INNER JOIN channel_ticket_queue ON channel_ticket_queue.lease_id = leases.id
    INNER JOIN queued_channel_ticket_items ON queued_channel_ticket_items.lease_id = leases.id
    INNER JOIN free_resources ON free_resources.rn = queued_channel_ticket_items.rn
    INNER JOIN resources ON resources.id = free_resources.resource_id
    INNER JOIN resource_free_queue ON resource_free_queue.resource_id = free_resources.resource_id
  WHERE 1=1
    -- Redudant checks, because only locking now.
    AND resources.tombstone IS FALSE
    -- Redudant checks, because only locking now.
    AND resources.lease_id IS NULL
    -- Redudant checks, because only locking now.
    AND leases.tombstone IS FALSE
    -- Redudant checks, because only locking now.
    AND leases.tombstone IS FALSE
  ORDER BY queued_channel_ticket_items.lease_id
), locked_matches_ AS (
  SELECT potential_matches_.lease_id, potential_matches_.resource_id, potential_matches_.data
  FROM potential_matches_
    INNER JOIN leases ON leases.id = potential_matches_.lease_id
    INNER JOIN channel_ticket_queue ON channel_ticket_queue.lease_id = potential_matches_.lease_id
    INNER JOIN resources ON resources.id = potential_matches_.resource_id
    INNER JOIN resource_free_queue ON resource_free_queue.resource_id = potential_matches_.resource_id
  FOR UPDATE OF leases, channel_ticket_queue, resources, resource_free_queue SKIP LOCKED
), delete_ticket_from_queue AS (
  DELETE FROM channel_ticket_queue
  WHERE lease_id IN (SELECT lease_id FROM locked_matches_)
), delete_resource_from_queue AS (
  DELETE FROM resource_free_queue
  WHERE resource_id IN (SELECT resource_id FROM locked_matches_)
), update_leases AS (
  UPDATE leases
  SET resource_id = locked_matches_.resource_id,
      updated = (NOW() AT TIME ZONE 'UTC')::timestamp, 
      data = locked_matches_.data
  FROM locked_matches_
  WHERE id = locked_matches_.lease_id
    AND leases.tombstone IS FALSE
), updated_resources AS (
  UPDATE resources
  SET lease_id = locked_matches_.lease_id,
      updated = (NOW() AT TIME ZONE 'UTC')::timestamp
  FROM locked_matches_
  WHERE id = locked_matches_.resource_id
    AND resources.tombstone IS FALSE
)
SELECT 1
"""
    stmt = sqlalchemy.text(sql)
    await session.execute(stmt, {'channel': channel})

  @instance_retry()
  async def _ServiceTimedoutLeases(self, session: AsyncSession,
                                   now: UTCNaiveDatetime):
    # Update all leases that have timed out.
    # 1. Find all expired leases.
    # 2. Mark the expired leases as tombstoned.
    # 2. Remove the expired leases from the channel_ticket_queue.
    # 3. Add the newly free resources to the resource_free_queue.

    sql = f"""
WITH expired_leases AS (
  SELECT leases.id AS lease_id, leases.resource_id
  FROM leases
  WHERE 1=1
    AND ends < :now
    AND tombstone IS FALSE
  FOR UPDATE OF leases SKIP LOCKED
), expired_channel_ticket_items AS (
  SELECT
    channel_ticket_queue.channel,
    channel_ticket_queue.lease_id
  FROM channel_ticket_queue
    INNER JOIN expired_leases USING (lease_id)
  FOR UPDATE OF channel_ticket_queue
), zombie_channel_ticket_items AS (
  SELECT
    channel_ticket_queue.channel,
    channel_ticket_queue.lease_id
  FROM channel_ticket_queue
    LEFT OUTER JOIN leases ON leases.id = channel_ticket_queue.lease_id
  WHERE (leases.id IS NULL OR leases.tombstone IS TRUE)
  FOR UPDATE OF channel_ticket_queue SKIP LOCKED
), expired_resources AS (
  SELECT resources.id as resource_id, resources.channels
  FROM resources
    INNER JOIN expired_leases ON expired_leases.resource_id = resources.id
  WHERE 1=1
    -- This is redundant, but stricter. It should always be true.
    AND resources.tombstone IS FALSE
    -- This is redundant, but stricter. It should always be true.
    AND resources.lease_id = expired_leases.lease_id
  FOR UPDATE OF resources
), expired_resource_free_queue AS (
  SELECT
    resource_free_queue.channel,
    resource_free_queue.resource_id
  FROM resource_free_queue
    INNER JOIN expired_resources USING (resource_id)
  FOR UPDATE OF resource_free_queue
), zombie_resource_free_queue AS (
  SELECT
    resource_free_queue.channel,
    resource_free_queue.resource_id
  FROM resource_free_queue
    LEFT OUTER JOIN resources ON resources.id = resource_free_queue.resource_id
  WHERE (resources.id IS NULL OR resources.tombstone IS TRUE)
  FOR UPDATE OF resource_free_queue SKIP LOCKED
), newly_free_resource_items AS (
  SELECT channel.value AS channel, expired_resources.resource_id
  FROM expired_resources
    CROSS JOIN LATERAL jsonb_array_elements_text(expired_resources.channels) AS channel(value)
), updated_expired_leases AS (
  UPDATE leases
  SET tombstone = TRUE,
      updated = (NOW() AT TIME ZONE 'UTC')::timestamp
  FROM expired_leases
  RETURNING *
), deleted_channel_ticket_items AS (
  DELETE FROM channel_ticket_queue
  USING expired_channel_ticket_items
  WHERE 1=1
    AND channel_ticket_queue.channel = expired_channel_ticket_items.channel
    AND channel_ticket_queue.lease_id = expired_channel_ticket_items.lease_id
  RETURNING *
), inserted_free_resource_items AS (
  INSERT INTO resource_free_queue(channel, resource_id)
  SELECT channel, resource_id
  FROM newly_free_resource_items
  RETURNING *
), updated_resources AS (
  UPDATE resources
  SET lease_id = NULL,
      updated = (NOW() AT TIME ZONE 'UTC')::timestamp
  FROM expired_resources
  WHERE id = expired_resources.resource_id
  RETURNING *
), inserted_reports AS (
  INSERT INTO reports(id, resource_id, lease_id, report, extra)
  SELECT {self._uuid_gen_func} AS report_id,
         expired_leases.resource_id as resource_id,
         expired_leases.lease_id AS lease_id,
         'timeout' AS report,
         '{{}}'::jsonb AS extra
  FROM expired_leases
  WHERE expired_leases.resource_id IS NOT NULL
  RETURNING *
), deleted_zombie_channel_ticket_items AS (
  DELETE FROM channel_ticket_queue
  USING zombie_channel_ticket_items
  WHERE 1=1
    AND channel_ticket_queue.channel = zombie_channel_ticket_items.channel
    AND channel_ticket_queue.lease_id = zombie_channel_ticket_items.lease_id
  RETURNING *
)
  
SELECT 1
"""
    stmt = sqlalchemy.text(sql)
    await session.execute(stmt, {'now': now})

  async def _ServiceOnce(self):
    now: UTCNaiveDatetime = NormalizeDatetime(UTCNow())
    async with await self._GetSession() as session:
      async with _AutoCommit(session, sanity=None):
        await self._ServiceTimedoutLeases(session, now)
    async with await self._GetSession() as session:
      async with _AutoCommit(session, sanity=None):
        channels: List[_base.ChannelID] = await self._GetChannels(session)
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

  @instance_retry()
  async def Get(self, *, client_name: _base.ClientName,
                channels: List[_base.ChannelID],
                priority: int) -> Union[_base.Lease, _base.Ticket]:
    logger.debug(
        f'Get: client_name={client_name}, channels={channels}, priority={priority}'
    )
    if not self._initialized:
      raise RuntimeError('DBFulcrum not initialized')

    now: UTCNaiveDatetime = NormalizeDatetime(UTCNow())
    ends: UTCNaiveDatetime = now + timedelta(seconds=self._lease_timeout)

    async with await self._GetSession() as session:
      async with _AutoCommit(session, sanity=self._CheckSanityIfDebug):
        channels = list(set(channels))

        ticket = _base.Ticket(id=_base.LeaseID(uuid.uuid4().hex),
                              client_name=client_name,
                              lease_timeout=self._lease_timeout,
                              ends=NormalizeDatetime(ends))
        sql = """
        WITH inserted_lease AS (
          INSERT INTO leases(id, client_name, channels, priority, resource_id, data, lease_timeout, ends)
          VALUES (:id, :client_name, :channels, :priority, NULL, NULL, :lease_timeout, :ends)
          RETURNING *
        ), inserted_channel_ticket_items AS (
          INSERT INTO channel_ticket_queue(channel, lease_id, priority, t)
          SELECT channel, :id, :priority, :now
          FROM UNNEST(CAST(:channels_array AS text[])) AS channel
        )
        SELECT 1
        """
        stmt = sqlalchemy.text(sql)
        stmt = stmt.bindparams(bindparam('channels', type_=JSONB),
                               bindparam('channels_array'))
        await session.execute(
            stmt,
            {
                'id': ticket.id,
                'client_name': client_name,
                'channels': list(map(str,
                                     channels)),  # Convert list to JSON string
                'channels_array': list(map(str,
                                           channels)),  # Pass as list/array
                'priority': priority,
                'lease_timeout': self._lease_timeout,
                'ends': now + timedelta(seconds=self._lease_timeout),
                'now': now,
            })
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
    if not self._initialized:
      raise RuntimeError('DBFulcrum not initialized')

    now: UTCNaiveDatetime = NormalizeDatetime(UTCNow())
    async with await self._GetSession() as session:
      async with _AutoCommit(session, sanity=self._CheckSanityIfDebug):
        where_clauses = [LEASES.c.id == id, LEASES.c.tombstone.is_(False)]

        stmt = update(LEASES).where(*where_clauses).values(
            updated=now,
            lease_timeout=self._lease_timeout,
            ends=now + timedelta(seconds=self._lease_timeout),
        ).returning(*LEASES.c)

        result: AsyncResult = await session.stream(stmt)

        row: Optional[RowMapping] = await result.mappings().first()
        if row is None:
          return None

        lease_id: _base.LeaseID = row.id
        client_name: _base.ClientName = row.client_name
        resource_id: Optional[_base.ResourceID] = row.resource_id
        data: Optional[str] = row.data
        ends: UTCNaiveDatetime = NormalizeDatetime(row.ends)
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
                             ends=NormalizeDatetime(ends))
        elif type == 'ticket_or_lease':
          if resource_id is None:
            return _base.Ticket(id=lease_id,
                                client_name=client_name,
                                lease_timeout=lease_timeout,
                                ends=NormalizeDatetime(ends))
          if data is None:
            raise AssertionError(
                'Expected data to be set on a lease with a resource id set')
          return _base.Lease(id=lease_id,
                             client_name=client_name,
                             resource_id=resource_id,
                             data=data,
                             lease_timeout=lease_timeout,
                             ends=NormalizeDatetime(ends))
        else:
          raise ValueError(f'Unexpected type: {type}')

      # TODO: If the resource can be immediately allocated, return a Lease.

  @instance_retry()
  async def TouchTicket(
      self, *, id: _base.LeaseID) -> Union[_base.Lease, _base.Ticket, None]:
    logger.debug(f'TouchTicket: with id={id}')
    if not self._initialized:
      raise RuntimeError('DBFulcrum not initialized')
    return await self._Touch(id=id, type='ticket_or_lease')

  @instance_retry()
  async def TouchLease(self, *, id: _base.LeaseID) -> Optional[_base.Lease]:
    logger.debug(f'TouchLease: with id={id}')
    if not self._initialized:
      raise RuntimeError('DBFulcrum not initialized')
    return await self._Touch(id=id, type='lease')

  @instance_retry()
  async def Release(self, *, id: _base.LeaseID,
                    report: Optional[_base.ReportType],
                    report_extra: Optional[Any]):
    logger.debug(
        f'Release: lease with id={id}, report={report}, report_extra={report_extra}'
    )
    if not self._initialized:
      raise RuntimeError('DBFulcrum not initialized')
    async with await self._GetSession() as session:
      async with _AutoCommit(session, sanity=self._CheckSanityIfDebug):
        sql = f"""
WITH selected_leases AS (
  SELECT leases.id as lease_id
  FROM leases 
  WHERE leases.id = :lease_id
    AND leases.tombstone IS FALSE
  FOR UPDATE OF leases
), selected_queued_channel_ticket_items AS (
  SELECT channel, lease_id
  FROM channel_ticket_queue INNER JOIN selected_leases USING (lease_id)
  FOR UPDATE OF channel_ticket_queue
), selected_resources AS (
  SELECT resources.id AS resource_id
  FROM resources INNER JOIN selected_leases USING (lease_id)
  WHERE resources.tombstone IS FALSE
  FOR UPDATE OF resources
), updated_leases AS (
  UPDATE leases
  SET tombstone = TRUE,
      updated = (NOW() AT TIME ZONE 'UTC')::timestamp
  FROM selected_leases
  WHERE leases.id = selected_leases.lease_id
    AND leases.tombstone IS FALSE
  RETURNING leases.id as lease_id, leases.resource_id
), updated_resource AS (
  UPDATE resources
  SET lease_id = NULL,
      updated = (NOW() AT TIME ZONE 'UTC')::timestamp
  FROM selected_resources
  WHERE resources.id = selected_resources.resource_id
    -- This is redundant, but stricter. It should always be true.
    AND resources.tombstone IS FALSE
  RETURNING resources.id as resource_id, resources.lease_id AS lease_id, resources.channels, resources.tombstone
), newly_free_resource_items AS (
  INSERT INTO resource_free_queue(channel, resource_id)
  SELECT channel.value AS channel, resource_id
  FROM updated_resource
    CROSS JOIN LATERAL jsonb_array_elements_text(updated_resource.channels) AS channel(value)
  WHERE updated_resource.tombstone IS FALSE
  RETURNING *
), deleted_channel_ticket_items AS (
  DELETE FROM channel_ticket_queue
  USING selected_queued_channel_ticket_items
  WHERE channel_ticket_queue.lease_id = selected_queued_channel_ticket_items.lease_id
  RETURNING *
), inserted_reports AS (
  INSERT INTO reports(id, resource_id, lease_id, report, extra)
  SELECT {self._uuid_gen_func} AS report_id,
          updated_leases.resource_id as resource_id,
          updated_leases.lease_id AS lease_id,
          :report AS report,
          :report_extra AS extra
  FROM updated_leases
  WHERE updated_leases.resource_id IS NOT NULL
  RETURNING *
)
SELECT (SELECT COUNT(*) FROM updated_leases) as released_leases_count,
        (SELECT COUNT(*) FROM updated_resource) as released_resource_count,
        (SELECT COUNT(*) FROM newly_free_resource_items) as newly_free_resource_items_count,
        (SELECT COUNT(*) FROM inserted_reports) as inserted_reports_count,
        (SELECT COUNT(*) FROM deleted_channel_ticket_items) as deleted_channel_ticket_items_count
"""
        stmt = sqlalchemy.text(sql)
        stmt = stmt.bindparams(
            sqlalchemy.bindparam('report', type_=String),
            sqlalchemy.bindparam('report_extra', type_=JSONB))
        await session.execute(
            stmt, {
                'lease_id':
                id,
                'report':
                report,
                'report_extra': (report_extra if report_extra is not None else
                                 json.dumps(None)),
            })

  @instance_retry()
  async def RegisterResource(self, *, resource_id: _base.ResourceID,
                             channels: List[_base.ChannelID], data: str):
    logger.debug(
        f'RegisterResource: resource_id={resource_id}, channels={channels}, data={data}'
    )
    if not self._initialized:
      raise RuntimeError('DBFulcrum not initialized')

    channels = list(set(channels))
    async with await self._GetSession() as session:
      async with _AutoCommit(session, sanity=self._CheckSanityIfDebug):
        sql = """
WITH inserted_resource AS (
  INSERT INTO resources(id, channels, data)
  VALUES (:id, :channels, :data)
  RETURNING *
), newly_free_resource_items AS (
  SELECT channel.value AS channel, inserted_resource.id AS resource_id
  FROM inserted_resource
    CROSS JOIN LATERAL jsonb_array_elements_text(inserted_resource.channels) AS channel(value)
), inserted_free_resource_items AS (
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

  @instance_retry()
  async def RemoveResource(
      self, *, resource_id: _base.ResourceID) -> _base.RemovedResourceInfo:
    logger.debug(f'RemoveResource: resource_id={resource_id}')
    if not self._initialized:
      raise RuntimeError('DBFulcrum not initialized')
    async with await self._GetSession() as session:
      async with _AutoCommit(session, sanity=self._CheckSanityIfDebug):
        sql = """
-- Lock leases first, to be consistent in lock order, and to avoid deadlocks.
WITH stale_leases AS (
  SELECT leases.id as lease_id
  FROM leases
  WHERE resource_id = :resource_id
    AND tombstone IS FALSE
  FOR UPDATE OF leases
), stale_channel_ticket_items AS (
  SELECT channel, lease_id
  FROM channel_ticket_queue
    INNER JOIN stale_leases USING (lease_id)
  FOR UPDATE OF channel_ticket_queue
), stale_resources AS (
  SELECT resources.id as resource_id
  FROM resources
  WHERE id = :resource_id
    AND tombstone IS FALSE
  FOR UPDATE OF resources
), stale_free_resource_items AS (
  SELECT channel, resource_id
  FROM resource_free_queue
  WHERE resource_id = :resource_id
  FOR UPDATE OF resource_free_queue
), updated_stale_leases AS (
  UPDATE leases
  SET tombstone = TRUE,
      updated = (NOW() AT TIME ZONE 'UTC')::timestamp
  FROM stale_leases
  WHERE leases.id = stale_leases.lease_id
  RETURNING *
), deleted_channel_ticket_items AS (
  DELETE FROM channel_ticket_queue
  USING stale_channel_ticket_items
  WHERE stale_channel_ticket_items.lease_id = channel_ticket_queue.lease_id
  RETURNING *
), updated_resources AS (
  UPDATE resources
  SET tombstone = TRUE,
      updated = (NOW() AT TIME ZONE 'UTC')::timestamp
  FROM stale_resources
  WHERE resources.id = stale_resources.resource_id
  RETURNING *
), deleted_free_resource_items AS (
  DELETE FROM resource_free_queue
  WHERE resource_id = :resource_id
  RETURNING *
)

SELECT (SELECT COUNT(*) FROM updated_resources) as removed_resources_count,
       (SELECT COUNT(*) FROM deleted_free_resource_items) as deleted_free_resource_items_count,
       (SELECT COUNT(*) FROM stale_leases) as stale_leases_count,
       (SELECT COUNT(*) FROM deleted_channel_ticket_items) as deleted_channel_ticket_items_count
"""
        stmt = sqlalchemy.text(sql)
        stmt = stmt.bindparams(sqlalchemy.bindparam('resource_id',
                                                    type_=String))
        stmt = stmt.bindparams(resource_id=resource_id)

        result = await session.execute(stmt)
        row = result.mappings().first()
        if row is None:
          raise AssertionError('Expected a row, got None')
        removed_resources_count = row.removed_resources_count
        deleted_free_resource_items_count = row.deleted_free_resource_items_count
        stale_leases_count = row.stale_leases_count
        deleted_channel_ticket_items_count = row.deleted_channel_ticket_items_count
        return _base.RemovedResourceInfo(
            removed_resources_count=removed_resources_count,
            deleted_free_resource_items_count=deleted_free_resource_items_count,
            stale_leases_count=stale_leases_count,
            deleted_channel_ticket_items_count=
            deleted_channel_ticket_items_count,
        )

  @instance_retry()
  async def _ActiveLeasesCount(self, *, session: AsyncSession) -> int:
    if not self._initialized:
      raise RuntimeError('DBFulcrum not initialized')
    stmt = select(func.count(distinct(LEASES.c.id)).label('count')).where(
        LEASES.c.tombstone.is_(False), LEASES.c.resource_id.isnot(None))

    result: Result = await session.execute(stmt)
    leases = result.scalar()
    if not isinstance(leases, int):
      raise ValueError(f'Expected int, got {type(leases)}: {leases}')
    return leases

  @instance_retry()
  async def _ResourceCount(self, *, session: AsyncSession) -> int:
    if not self._initialized:
      raise RuntimeError('DBFulcrum not initialized')
    stmt = select(func.count(distinct(RESOURCES.c.id)).label('count')).where(
        RESOURCES.c.tombstone.is_(False))

    result: Result = await session.execute(stmt)
    queue_size = result.scalar()
    if not isinstance(queue_size, int):
      raise ValueError(f'Expected int, got {type(queue_size)}: {queue_size}')
    return queue_size

  @instance_retry()
  async def _ChannelResourceCounts(
      self, *, session: AsyncSession) -> Dict[_base.ChannelID, int]:
    channel_id_ta = TypeAdapter(_base.ChannelID)

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

  @instance_retry()
  async def _QueueSize(self, *, session: AsyncSession) -> int:
    if not self._initialized:
      raise RuntimeError('DBFulcrum not initialized')
    stmt = select(
        func.count(distinct(CHANNEL_TICKET_QUEUE.c.lease_id)).label('count'))

    result: Result = await session.execute(stmt)
    queue_size = result.scalar()
    if not isinstance(queue_size, int):
      raise ValueError(f'Expected int, got {type(queue_size)}: {queue_size}')
    return queue_size

  @instance_retry()
  async def _ChannelQueueSize(
      self, *, session: AsyncSession) -> Dict[_base.ChannelID, int]:
    if not self._initialized:
      raise RuntimeError('DBFulcrum not initialized')
    channel_id_ta = TypeAdapter(_base.ChannelID)

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

  @instance_retry()
  async def ListResources(self) -> List[_base.ResourceMeta]:
    if not self._initialized:
      raise RuntimeError('DBFulcrum not initialized')
    async with await self._GetSession() as session:
      async with _AutoCommit(session, sanity=self._CheckSanityIfDebug):
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
          inserted: UTCNaiveDatetime = NormalizeDatetime(row.inserted)
          resources.append(
              _base.ResourceMeta(id=resource_id,
                                 channels=channels,
                                 data=data,
                                 inserted=inserted))
        return resources

  @instance_retry()
  async def Stats(self) -> _base.Stats:
    if not self._initialized:
      raise RuntimeError('DBFulcrum not initialized')
    async with await self._GetSession() as session:
      async with _AutoCommit(session, sanity=self._CheckSanityIfDebug):
        active_leases_task = self._ActiveLeasesCount(session=session)
        queue_size_task = self._QueueSize(session=session)
        channel_queue_sizes_task = self._ChannelQueueSize(session=session)
        resource_count_task = self._ResourceCount(session=session)
        channel_resource_counts_task = self._ChannelResourceCounts(
            session=session)

        active_leases = await active_leases_task
        queue_size = await queue_size_task
        channel_queue_sizes = await channel_queue_sizes_task
        resource_count = await resource_count_task
        channel_resource_counts = await channel_resource_counts_task

        return _base.Stats(active_leases=active_leases,
                           queue_size=queue_size,
                           channel_queue_sizes=channel_queue_sizes,
                           resources_count=resource_count,
                           channel_resources_counts=channel_resource_counts)

  async def _CheckLeaseSanity(self, *, leases: List[RowMapping],
                              resources: List[RowMapping],
                              channel_ticket_queue: List[RowMapping]):
    if not self._initialized:
      raise RuntimeError('DBFulcrum not initialized')

    resource_id_2_idx = {
        resource['id']: idx
        for idx, resource in enumerate(resources)
    }
    lease_id_2_idx = {lease['id']: idx for idx, lease in enumerate(leases)}
    key_2_idx = {
        (ticket['channel'], ticket['lease_id']): idx
        for idx, ticket in enumerate(channel_ticket_queue)
    }

    lease: RowMapping
    for lease in leases:
      resource_id: Optional[str] = lease['resource_id']
      if resource_id is None:
        channels: List[str] = lease['channels']
        assert isinstance(channels, list)
        channel: str
        for channel in channels:
          assert isinstance(channel, str)
          key = (channel, lease['id'])
          if key not in key_2_idx:
            raise AssertionError(
                f'Ticket {key} is not in the channel_ticket_queue but does not have a resource_id set in the leases table'
            )
        continue

      if resource_id not in resource_id_2_idx:
        raise AssertionError(
            f'Lease {lease["id"]} has a resource_id {resource_id} that is not alive in the resources table'
        )
      resource_idx = resource_id_2_idx[lease['resource_id']]
      resource: RowMapping = resources[resource_idx]
      lease_id: Optional[str] = resource['lease_id']
      if lease_id is None:
        raise AssertionError(
            f'Lease {lease["id"]} has a resource_id {resource_id} that points at a resource that does not have a lease_id set'
        )
      if lease_id != lease['id']:
        raise AssertionError(
            f'Lease {lease["id"]} has a resource_id {resource_id} that points at a resource that has a different lease_id set'
        )

    for ticket in channel_ticket_queue:
      key = (ticket['channel'], ticket['lease_id'])
      ticket_lease_id: str = ticket['lease_id']
      if ticket_lease_id not in lease_id_2_idx:
        raise AssertionError(
            f'Ticket {key} has a lease_id {ticket_lease_id} that is not alive in the leases table'
        )
      ticket_lease_idx = lease_id_2_idx[ticket_lease_id]
      ticket_lease: RowMapping = leases[ticket_lease_idx]
      ticket_resource_id: Optional[str] = ticket_lease['resource_id']
      if ticket_resource_id is not None:
        raise AssertionError(
            f'Ticket {key} has a lease_id {ticket_lease_id} that points at a lease that has a resource_id set'
        )

  async def _CheckResourceSanity(self, *, leases: List[RowMapping],
                                 resources: List[RowMapping],
                                 resource_free_queue: List[RowMapping]):
    if not self._initialized:
      raise RuntimeError('DBFulcrum not initialized')
    lease_id_2_idx = {lease['id']: idx for idx, lease in enumerate(leases)}
    res_id_2_idx = {
        resource['id']: idx
        for idx, resource in enumerate(resources)
    }
    key_2_free_idx = {
        (resource['channel'], resource['resource_id']): idx
        for idx, resource in enumerate(resource_free_queue)
    }

    resource: RowMapping
    for resource in resources:
      lease_id: Optional[str] = resource['lease_id']
      if lease_id is None:
        channels: List[str] = resource['channels']
        assert isinstance(channels, list)
        channel: str
        for channel in channels:
          assert isinstance(channel, str)
          key = (channel, resource['id'])
          if key not in key_2_free_idx:
            raise AssertionError(
                f'Resource {key} is not in the resource_free_queue but does not have a lease_id set in the resources table'
            )
        continue

      if lease_id not in lease_id_2_idx:
        raise AssertionError(
            f'Resource {resource["id"]} has a lease_id {lease_id} that is not alive in the leases table'
        )
      lease_idx = lease_id_2_idx[resource['lease_id']]
      lease: RowMapping = leases[lease_idx]
      resource_id: Optional[str] = lease['resource_id']
      if resource_id is None:
        raise AssertionError(
            f'Resource {resource["id"]} has a lease_id {lease_id} that points at a lease that does not have a resource_id set'
        )
      if resource_id != resource['id']:
        raise AssertionError(
            f'Resource {resource["id"]} has a lease_id {lease_id} that points at a lease that has a different resource_id set'
        )

    for free_resource in resource_free_queue:
      key = (free_resource['channel'], free_resource['resource_id'])
      free_resource_res_id: str = free_resource['resource_id']
      if free_resource_res_id not in res_id_2_idx:
        raise AssertionError(
            f'Free resource {key} has a resource_id {free_resource_res_id} that is not alive in the resources table'
        )
      free_resource_idx = res_id_2_idx[free_resource_res_id]
      free_resource_resource: RowMapping = resources[free_resource_idx]
      free_resource_lease_id: Optional[str] = free_resource_resource['lease_id']
      if free_resource_lease_id is not None:
        raise AssertionError(
            f'Free resource {key} has a resource_id {free_resource_res_id} that points at a resource that has a lease_id set'
        )

  @instance_retry()
  async def _CheckSanity(self, session: AsyncSession):
    if not self._initialized:
      raise RuntimeError('DBFulcrum not initialized')
    leases: List[RowMapping] = list(
        (await
         session.execute(select(LEASES).where(LEASES.c.tombstone.is_(False))
                         )).mappings())
    resources: List[RowMapping] = list((await session.execute(
        select(RESOURCES).where(RESOURCES.c.tombstone.is_(False)))).mappings())
    resource_free_queue: List[RowMapping] = list(
        (await session.execute(select(RESOURCE_FREE_QUEUE))).mappings())
    channel_ticket_queue: List[RowMapping] = list(
        (await session.execute(select(CHANNEL_TICKET_QUEUE))).mappings())

    await self._CheckLeaseSanity(leases=leases,
                                 resources=resources,
                                 channel_ticket_queue=channel_ticket_queue)
    await self._CheckResourceSanity(leases=leases,
                                    resources=resources,
                                    resource_free_queue=resource_free_queue)

  async def _CheckSanityIfDebug(self, session: AsyncSession):
    if self.debug:
      await self._CheckSanity(session)
