# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
# The Comfy Fulcrum project requires contributions made to this file be licensed
# under the MIT license or a compatible open source license. See LICENSE.md for
# the license text.

import asyncio
import datetime
import functools
import sys
from functools import wraps
from typing import Any, Callable, NewType, Optional, TypeVar, Union, cast

import tenacity

UTCNaiveDatetime = NewType('UTCNaiveDatetime', datetime.datetime)
UTCAwareDatetime = NewType('UTCAwareDatetime', datetime.datetime)

if sys.version_info >= (3, 9):
  to_thread = asyncio.to_thread
else:
  T = TypeVar('T')

  async def to_thread(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run a function in a separate thread."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None,
                                      functools.partial(func, *args, **kwargs))


def JoinURL(base: str, path: str) -> str:
  return f'{base.rstrip("/")}/{path.lstrip("/")}'


_F = TypeVar('_F', bound=Callable[..., Any])


def instance_retry(**retry_kwargs: Any) -> Callable[[_F], _F]:
  """
    Expects a class instance method and returns a decorated method that will
    retry the method call based on the retry_kwargs, and the class field
    `tenacity_kwargs`.
    
    retry_kwargs: follows tenacity.retry() signature.
    """

  def inner(func: _F) -> _F:
    if asyncio.iscoroutinefunction(func):

      @wraps(func)
      async def async_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        tenacity_kwargs = getattr(self, 'tenacity_kwargs', {})
        # Combine the tenacity_kwargs and retry_kwargs
        tenacity_kwargs.update(retry_kwargs)

        retry_decorator: Callable[..., _F]
        retry_decorator = tenacity.retry(**tenacity_kwargs)

        @retry_decorator
        @wraps(func)
        async def wrapped(*args: Any, **kwargs: Any) -> Any:
          return await func(self, *args, **kwargs)

        return await wrapped(*args, **kwargs)

      return cast(_F, async_wrapper)
    else:

      @wraps(func)
      def sync_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        tenacity_kwargs = getattr(self, 'tenacity_kwargs', {})
        # Combine the tenacity_kwargs and retry_kwargs
        tenacity_kwargs.update(retry_kwargs)

        retry_decorator: Callable[..., _F]
        retry_decorator = tenacity.retry(**tenacity_kwargs)

        @retry_decorator
        @wraps(func)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
          return func(self, *args, **kwargs)

        return wrapped(*args, **kwargs)

      return cast(_F, sync_wrapper)

  return inner


def ValidateUTCNaiveDatetime(d: datetime.datetime) -> UTCNaiveDatetime:
  if d.tzinfo is not None:
    raise ValueError(f'Expected a UTC naive datetime, got {d}')
  return UTCNaiveDatetime(d)


def UTCNow() -> UTCAwareDatetime:
  return UTCAwareDatetime(datetime.datetime.now(datetime.timezone.utc))


def NormalizeDatetime(
    d: Union[UTCNaiveDatetime, UTCAwareDatetime, datetime.datetime]
) -> UTCNaiveDatetime:
  if d.tzinfo is None:
    return UTCNaiveDatetime(d)
  return UTCNaiveDatetime(
      d.astimezone(datetime.timezone.utc).replace(tzinfo=None))


def NormalizeDatetimeOr(
    d: Union[UTCNaiveDatetime, UTCAwareDatetime, datetime.datetime, None]
) -> Optional[UTCNaiveDatetime]:
  if d is None:
    return None
  return NormalizeDatetime(d)


def InterpretToUTC(
    d: Union[UTCNaiveDatetime, UTCAwareDatetime, datetime.datetime]
) -> UTCAwareDatetime:
  if d.tzinfo is None:
    return UTCAwareDatetime(d.replace(tzinfo=datetime.timezone.utc))
  return UTCAwareDatetime(d.astimezone(datetime.timezone.utc))


def InterpretToUTCOr(
    d: Union[UTCNaiveDatetime, UTCAwareDatetime, datetime.datetime, None]
) -> Optional[UTCAwareDatetime]:
  if d is None:
    return None
  return InterpretToUTC(d)
