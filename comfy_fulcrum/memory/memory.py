# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
# The Comfy Fulcrum project requires contributions made to this file be licensed
# under the MIT license or a compatible open source license. See LICENSE.md for
# the license text.

import asyncio
import logging
import random
import uuid
from collections import defaultdict
from datetime import timedelta
from typing import Any, Dict, List, Optional, Set, Tuple, Union, overload

from pydantic import BaseModel
from typing_extensions import Literal, assert_never, override

from ..base import base as _base
from ..private import utilities as priv_utils

_logger = logging.getLogger(__name__)


class _TicketMeta(BaseModel):
  ticket: _base.Ticket
  channels: List[_base.ChannelID]
  priority: int


class _LeaseMeta(BaseModel):
  lease: _base.Lease
  req_channels: List[_base.ChannelID]


class InMemoryFulcrum(_base.FulcrumBase):

  def __init__(self, resource_mgr: _base.ResourceSOTBase, lease_timeout: float,
               service_sleep_interval: float):
    self._resource_mgr = resource_mgr
    self._lease_timeout = lease_timeout
    self._service_sleep_interval = service_sleep_interval

    self._lock = asyncio.Lock()
    self._resources: Dict[_base.ResourceID, _base.ResourceMeta] = {}

    self._unmatched_leases: Dict[_base.LeaseID, _TicketMeta] = {}
    self._matched_leases: Dict[_base.LeaseID, _LeaseMeta] = {}

    self._unmatched_resources: Set[_base.ResourceID] = set()

    self._service_task: Optional[asyncio.Task] = None

  async def Initialize(self):
    self._service_task = asyncio.create_task(
        self._Service(), name=f'{self.__class__.__name__}._Service')

  def close(self):
    if self._service_task is None or self._service_task.done():
      return
    self._service_task.cancel()

  async def aclose(self):
    if self._service_task is None or self._service_task.done():
      return
    self._service_task.cancel()
    try:
      await self._service_task
    except asyncio.CancelledError:
      pass

  def _IsLeaseValid(self, *, lease: _base.Lease,
                    now: priv_utils.UTCNaiveDatetime) -> bool:
    if lease.resource_id not in self._resources:
      return False
    if priv_utils.NormalizeDatetime(lease.ends) < now:
      return False
    return True

  def _ReleaseLease(self, *, lease: _base.Lease):
    if lease.resource_id in self._resources:
      self._unmatched_resources.add(lease.resource_id)
    if lease.id in self._matched_leases:
      del self._matched_leases[lease.id]

  async def _ServiceOnce(self):
    resources_sot: List[_base.ResourceMeta]
    resources_sot = await self.ListResources()

    valid_resources: Set[_base.ResourceID] = {r.id for r in resources_sot}
    now: priv_utils.UTCNaiveDatetime = priv_utils.NormalizeDatetime(
        priv_utils.UTCNow())
    async with self._lock:
      # Remove all invalid resources.
      resource_id: _base.ResourceID
      for resource_id in list(self._resources.keys()):
        if resource_id not in valid_resources:
          self._resources.pop(resource_id)
      # Remove all invalid resources.
      self._unmatched_resources = set(
          [r for r in self._unmatched_resources if r in valid_resources])

      resource: _base.ResourceMeta
      # Add all new resources.
      for resource in resources_sot:
        # If it isn't new, skip.
        if resource.id in self._resources:
          continue
        self._resources[resource.id] = resource
        self._unmatched_resources.add(resource.id)

      # Clean up any invalid leases.
      for ticket_id in list(self._unmatched_leases):
        ticket: _TicketMeta = self._unmatched_leases[ticket_id]
        if priv_utils.NormalizeDatetime(ticket.ticket.ends) < now:
          del self._unmatched_leases[ticket_id]
          continue
      # Clean up any invalid leases.
      for lease_id in list(self._matched_leases):
        lease: _LeaseMeta = self._matched_leases[lease_id]
        if not self._IsLeaseValid(lease=lease.lease, now=now):
          self._ReleaseLease(lease=lease.lease)

      # Match.
      for resource_id in list(self._unmatched_resources):
        if len(self._unmatched_leases) == 0:
          break
        resource = self._resources[resource_id]
        candidate_unmatched_leases: List[Tuple[int, _base.LeaseID]]
        candidate_unmatched_leases = [
            (lease.priority, id)
            for id, lease in self._unmatched_leases.items()
            if len(set(resource.channels) & set(lease.channels)) > 0
        ]
        if len(candidate_unmatched_leases) == 0:
          continue

        highest_priority = max([p for p, _ in candidate_unmatched_leases])
        candidate_unmatched_leases = [(p, id)
                                      for (p, id) in candidate_unmatched_leases
                                      if p == highest_priority]
        match_id: _base.LeaseID
        _, match_id = random.choice(candidate_unmatched_leases)
        match: _TicketMeta = self._unmatched_leases[match_id]

        # Move the lease to the matched leases.
        del self._unmatched_leases[match_id]
        self._matched_leases[match_id] = _LeaseMeta(lease=_base.Lease(
            id=match.ticket.id,
            client_name=match.ticket.client_name,
            resource_id=resource_id,
            data=resource.data,
            lease_timeout=match.ticket.lease_timeout,
            ends=match.ticket.ends),
                                                    req_channels=match.channels)
        # Remove the resource from the unmatched resources
        self._unmatched_resources.remove(resource_id)

  async def _Service(self):
    while True:
      try:
        await self._ServiceOnce()
        await asyncio.sleep(self._service_sleep_interval)
      except asyncio.CancelledError:
        break
      except Exception as e:
        _logger.exception('Service error: %s', e)

  @override
  async def Get(self, *, client_name: _base.ClientName,
                channels: List[_base.ChannelID],
                priority: int) -> Union[_base.Lease, _base.Ticket]:
    _logger.debug(
        f'Get: client_name={client_name}, channels={channels}, priority={priority}'
    )
    now = priv_utils.NormalizeDatetime(priv_utils.UTCNow())
    ends = now + timedelta(seconds=self._lease_timeout)
    ticket = _base.Ticket(id=_base.LeaseID(uuid.uuid4().hex),
                          client_name=client_name,
                          lease_timeout=self._lease_timeout,
                          ends=ends)
    async with self._lock:
      self._unmatched_leases[ticket.id] = _TicketMeta(ticket=ticket,
                                                      channels=channels,
                                                      priority=priority)
    return ticket

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
    now = priv_utils.NormalizeDatetime(priv_utils.UTCNow())
    async with self._lock:
      ticket_or_lease_meta: Union[_TicketMeta, _LeaseMeta, None] = None

      if type == 'lease':
        ticket_or_lease_meta = self._matched_leases.get(id)
      if type == 'ticket_or_lease':
        ticket_or_lease_meta = self._unmatched_leases.get(id)
        if ticket_or_lease_meta is None:
          ticket_or_lease_meta = self._matched_leases.get(id)

      if ticket_or_lease_meta is not None:
        ticket_or_lease: Union[_base.Ticket, _base.Lease]
        if isinstance(ticket_or_lease_meta, _TicketMeta):
          ticket_or_lease = ticket_or_lease_meta.ticket
        elif isinstance(ticket_or_lease_meta, _LeaseMeta):
          ticket_or_lease = ticket_or_lease_meta.lease
        else:
          assert_never(ticket_or_lease_meta)

        ticket_or_lease.ends = now + timedelta(
            seconds=ticket_or_lease.lease_timeout)

        # Optional sanity checks.
        if isinstance(ticket_or_lease, _base.Lease):
          if priv_utils.NormalizeDatetime(ticket_or_lease.ends) < now:
            return None
          if ticket_or_lease.resource_id not in self._resources:
            return None

        return ticket_or_lease
    return None

  @override
  async def TouchTicket(
      self, *, id: _base.LeaseID) -> Union[_base.Lease, _base.Ticket, None]:
    _logger.debug(f'TouchTicket: with id={id}')
    return await self._Touch(id=id, type='ticket_or_lease')

  @override
  async def TouchLease(self, *, id: _base.LeaseID) -> Optional[_base.Lease]:
    _logger.debug(f'TouchLease: with id={id}')
    return await self._Touch(id=id, type='lease')

  async def Release(self, *, id: _base.LeaseID,
                    report: Optional[_base.ReportType],
                    report_extra: Optional[Any]):
    _logger.debug(
        f'Release: with id={id}, report={report}, report_extra={report_extra}')

    async with self._lock:
      ticket = self._matched_leases.get(id)
      if ticket is None:
        return
      del self._matched_leases[id]

      if ticket.lease.resource_id in self._resources:
        self._unmatched_resources.add(ticket.lease.resource_id)

  @override
  async def RegisterResource(self, *, resource_id: _base.ResourceID,
                             channels: List[_base.ChannelID], data: str):
    _logger.debug(
        f'RegisterResource: resource_id={resource_id}, channels={channels}, data={data}'
    )

    await self._resource_mgr.RegisterResource(resource_id=resource_id,
                                              channels=channels,
                                              data=data)
    await self._ServiceOnce()

  @override
  async def RemoveResource(
      self, *, resource_id: _base.ResourceID) -> _base.RemovedResourceInfo:
    _logger.debug(f'RemoveResource: resource_id={resource_id}')

    await self._resource_mgr.RemoveResource(resource_id=resource_id)
    async with self._lock:
      removed: Optional[_base.ResourceMeta] = self._resources.pop(
          resource_id, None)

      deleted_free_resource_items_count = 0
      if resource_id in self._unmatched_resources:
        if removed is not None:
          deleted_free_resource_items_count += len(removed.channels)
        self._unmatched_resources.discard(resource_id)

      stale_leases: List[_base.LeaseID] = []
      deleted_channel_ticket_items_count = 0
      for lease_id, lease in self._matched_leases.items():
        if lease.lease.resource_id == resource_id:
          stale_leases.append(lease_id)
          deleted_channel_ticket_items_count += len(lease.req_channels)
      for lease_id in stale_leases:
        self._matched_leases.pop(lease_id)

    return _base.RemovedResourceInfo(
        removed_resources_count=(1 if removed is not None else 0),
        deleted_free_resource_items_count=deleted_free_resource_items_count,
        stale_leases_count=len(stale_leases),
        deleted_channel_ticket_items_count=deleted_channel_ticket_items_count,
    )

  @override
  async def ListResources(self) -> List[_base.ResourceMeta]:
    _logger.debug('ListResources')

    return await self._resource_mgr.ListResources()

  @override
  async def Stats(self) -> _base.Stats:
    async with self._lock:
      channel_queue_sizes: Dict[_base.ChannelID, int] = defaultdict(int)
      for ticket in self._unmatched_leases.values():
        for channel in ticket.channels:
          channel_queue_sizes[channel] = channel_queue_sizes.get(channel, 0) + 1
      channel2resource: Dict[_base.ChannelID, int] = defaultdict(int)
      for resource in self._resources.values():
        for channel in resource.channels:
          channel2resource[channel] = channel2resource.get(channel, 0) + 1
      return _base.Stats(active_leases=len(self._matched_leases),
                         queue_size=len(self._unmatched_leases),
                         channel_queue_sizes=channel_queue_sizes,
                         resources_count=len(self._resources),
                         channel_resources_counts=channel2resource)
