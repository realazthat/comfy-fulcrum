# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
# The Snipinator project requires contributions made to this file be licensed
# under the MIT license or a compatible open source license. See LICENSE.md for
# the license text.

# SPDX-License-Identifier: MIT
#
# The Comfy Catapult project requires contributions made to this file be licensed
# under the MIT license or a compatible open source license. See LICENSE.md for
# the license text.

import asyncio
import functools
import sys
from typing import Any, Callable, TypeVar

if sys.version_info >= (3, 9):
  from asyncio import to_thread
else:
  T = TypeVar('T')

  async def to_thread(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run a function in a separate thread."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None,
                                      functools.partial(func, *args, **kwargs))


def JoinURL(base: str, path: str) -> str:
  return f'{base.rstrip("/")}/{path.lstrip("/")}'
