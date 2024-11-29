# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
# The Comfy Fulcrum project requires contributions made to this file be licensed
# under the MIT license or a compatible open source license. See LICENSE.md for
# the license text.

from contextlib import asynccontextmanager
from typing import AsyncIterator, Awaitable, Callable, Optional

from asyncpg import SerializationError
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def AutoCommit(
    session: AsyncSession, *, sanity: Optional[Callable[[AsyncSession],
                                                        Awaitable[None]]]
) -> AsyncIterator[AsyncSession]:

  async with session.begin():

    if sanity is not None:
      await sanity(session)
    yield session
    if sanity is not None:
      await sanity(session)


def IsSerializationError(exception: BaseException) -> bool:
  if isinstance(exception, SerializationError):
    return True
  if isinstance(exception, DBAPIError):
    if exception.__cause__ is not None:
      if IsSerializationError(exception.__cause__):
        return True
    if exception.orig is not None:
      if IsSerializationError(exception.orig):
        return True

  return False
