# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
# The Comfy Fulcrum project requires contributions made to this file be licensed
# under the MIT license or a compatible open source license. See LICENSE.md for
# the license text.

from typing import List

from asyncpg import SerializationError
from sqlalchemy import (TIMESTAMP, Boolean, Column, Index, MetaData, Result,
                        RowMapping, String, Table, cast, func, select, text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import (AsyncEngine, AsyncResult, AsyncSession,
                                    async_sessionmaker)
from tenacity import (retry_any, retry_if_exception_cause_type,
                      retry_if_exception_type, retry_if_result,
                      wait_exponential_jitter)
from typing_extensions import override

from ..base import base as _base
from ..private import utilities as priv_utils
from .private import utilities as db_priv_utils

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


class DBResourceSOT(_base.ResourceSOTBase):

  def __init__(self, db_engine: AsyncEngine, *, retry: bool):
    self._db_engine = db_engine
    self._async_session_maker = async_sessionmaker(self._db_engine,
                                                   expire_on_commit=False,
                                                   class_=AsyncSession)
    self._initialized = False

    if retry:
      self.tenacity_kwargs = {}
    else:
      self.tenacity_kwargs = {
          'retry':
          retry_any(
              retry_if_exception_type((SerializationError, )),
              retry_if_exception_cause_type((SerializationError, )),
              retry_if_result(db_priv_utils.IsSerializationError),
          ),
          # 'stop': stop_after_attempt(3),
          'wait':
          wait_exponential_jitter(initial=1.0),
      }

  async def Initalize(self):
    async with self._db_engine.begin() as conn:
      await conn.run_sync(METADATA.create_all)
    self._initialized = True

  async def DropAll(self):
    async with self._db_engine.begin() as conn:
      await conn.run_sync(METADATA.drop_all)

  async def _GetSession(self) -> AsyncSession:
    return self._async_session_maker()

  @override
  @priv_utils.instance_retry()
  async def ListResources(self) -> List[_base.ResourceMeta]:
    async with await self._GetSession() as session:
      async with db_priv_utils.AutoCommit(session, sanity=None):
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
          inserted: priv_utils.UTCNaiveDatetime = priv_utils.NormalizeDatetime(
              row.inserted)
          resources.append(
              _base.ResourceMeta(id=resource_id,
                                 channels=channels,
                                 data=data,
                                 inserted=inserted))
        return resources

  @override
  @priv_utils.instance_retry()
  async def RegisterResource(self, *, resource_id: _base.ResourceID,
                             channels: List[_base.ChannelID], data: str):
    async with await self._GetSession() as session:
      async with db_priv_utils.AutoCommit(session, sanity=None):
        stmt = RESOURCES.insert().values(
            id=resource_id,
            channels=channels,
            data=data,
        )
        await session.execute(stmt)

  @override
  @priv_utils.instance_retry()
  async def RemoveResource(
      self, *, resource_id: _base.ResourceID
  ) -> _base.ResourceSOTBase.RemovedResourceInfo:
    async with await self._GetSession() as session:
      async with db_priv_utils.AutoCommit(session, sanity=None):
        stmt = RESOURCES.update().where(RESOURCES.c.id == resource_id).values(
            tombstone=True).returning(RESOURCES.c.id)
        result: Result = await session.execute(stmt)
        count: int = 0
        for _ in result:
          count += 1

        return _base.ResourceSOTBase.RemovedResourceInfo(
            removed_resources_count=count)
