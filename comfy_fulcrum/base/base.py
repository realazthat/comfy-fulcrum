# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
# The Comfy Fulcrum project requires contributions made to this file be licensed
# under the MIT license or a compatible open source license. See LICENSE.md for
# the license text.

import datetime
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, NewType, Optional, Union

from pydantic import BaseModel
from typing_extensions import Literal

ClientName = NewType('ClientName', str)
LeaseID = NewType('LeaseID', str)
ResourceID = NewType('ResourceID', str)
ChannelID = NewType('ChannelID', str)
ReportType = Literal['success', 'permanent_failure', 'temporary_failure',
                     'user_failure', 'timeout']

logger = logging.getLogger(__name__)


class Ticket(BaseModel):
  # This is here so that pydantic can differentiate between a Ticket and a
  # Lease when deserializing.
  type: Literal['ticket'] = 'ticket'
  id: LeaseID
  client_name: ClientName
  lease_timeout: float
  ends: datetime.datetime


class Lease(BaseModel):
  # This is here so that pydantic can differentiate between a Ticket and a
  # Lease when deserializing.
  type: Literal['lease'] = 'lease'
  id: LeaseID
  client_name: ClientName
  resource_id: ResourceID
  data: str
  lease_timeout: float
  ends: datetime.datetime


class ResourceMeta(BaseModel):
  inserted: datetime.datetime
  id: ResourceID
  channels: List[ChannelID]
  data: str


class RemovedResourceInfo(BaseModel):
  removed_resources_count: int
  deleted_free_resource_items_count: int
  stale_leases_count: int
  deleted_channel_ticket_items_count: int


class Stats(BaseModel):
  active_leases: int
  queue_size: int
  channel_queue_sizes: Dict[ChannelID, int]
  resources_count: int
  channel_resources_counts: Dict[ChannelID, int]


class FulcrumBase(ABC):

  @abstractmethod
  async def Get(self, *, client_name: ClientName, channels: List[ChannelID],
                priority: int) -> Union[Lease, Ticket]:
    raise NotImplementedError()

  @abstractmethod
  async def TouchTicket(self, *, id: LeaseID) -> Union[Lease, Ticket, None]:
    raise NotImplementedError()

  @abstractmethod
  async def TouchLease(self, *, id: LeaseID) -> Optional[Lease]:
    raise NotImplementedError()

  @abstractmethod
  async def Release(self, *, id: LeaseID, report: Optional[ReportType],
                    report_extra: Optional[Any]):
    raise NotImplementedError()

  @abstractmethod
  async def RegisterResource(self, *, resource_id: ResourceID,
                             channels: List[ChannelID], data: str):
    raise NotImplementedError()

  @abstractmethod
  async def RemoveResource(self, *,
                           resource_id: ResourceID) -> RemovedResourceInfo:
    raise NotImplementedError()

  @abstractmethod
  async def ListResources(self) -> List[ResourceMeta]:
    raise NotImplementedError()

  @abstractmethod
  async def Stats(self) -> Stats:
    raise NotImplementedError()

  @abstractmethod
  def close(self):
    raise NotImplementedError()

  @abstractmethod
  async def aclose(self):
    raise NotImplementedError()

  def __enter__(self):
    return self

  def __exit__(self, exc_type, exc_value, traceback):
    self.close()

  async def __aenter__(self):
    return self

  async def __aexit__(self, exc_type, exc_value, traceback):
    await self.aclose()
