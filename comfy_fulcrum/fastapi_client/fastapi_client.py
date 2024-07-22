# -*- coding: utf-8 -*-

# SPDX-License-Identifier: MIT
#
# The Comfy Fulcrum project requires contributions made to this file be licensed
# under the MIT license or a compatible open source license. See LICENSE.md for
# the license text.

from typing import Any, List, Optional, Type, Union

import aiohttp
from pydantic import BaseModel
from typing_extensions import TypeVar

from ..base import base as _base
from ..base import fastapi_server_base as _server_base
from ..private.utilities import JoinURL as _JoinURL
from ..private.utilities import to_thread as _to_thread

_T = TypeVar('_T')


def _RaiseAPIError(*, endpoint: str, url: str,
                   error: _server_base._ResponseErrorBase):
  if error.error is not None:
    raise _server_base.ReconstructedException(
        f'API call to {endpoint} failed at {url}', error.error)
  else:
    raise _server_base.APIErrorException(
        f'API call to {endpoint} failed at {url}: {error.msg}')


class FulcrumClient(_base.FulcrumBase):

  def __init__(
      self,
      *,
      fulcrum_api_url: str,
      endpoints: _server_base.FulcrumServerRoutesBase.Endpoints = _server_base.
      FulcrumServerRoutesBase.DEFAULT_ENDPOINTS):
    self._server_url = fulcrum_api_url
    self._endpoints = endpoints

  async def _APICall(self, *, endpoint: str, req: BaseModel, res_type: Type[
      _server_base._ResponseBase[_server_base._SuccessT, _server_base._ErrorT]],
                     suc_type: Type[_T]) -> _T:
    async with aiohttp.ClientSession() as session:
      url = _JoinURL(self._server_url, endpoint)
      req_json: str = await _to_thread(
          req.model_dump_json,
          by_alias=True,
          round_trip=True,
      )
      async with session.post(url,
                              data=req_json,
                              headers={'Content-Type':
                                       'application/json'}) as resp:
        res_str: str = await resp.text()
    res = await _to_thread(res_type.model_validate_json, res_str)
    if res.error is not None:
      return _RaiseAPIError(endpoint=endpoint, url=url, error=res.error)

    if res.success is None:
      raise Exception(
          f'API call to {endpoint} at {url} failed: no success or error')
    if not isinstance(res.success, suc_type):
      raise Exception(
          f'API call to {endpoint} at {url} failed: success is not of type {suc_type}'
      )
    return res.success

  async def Get(self, *, client_name: _base.ClientName,
                channels: List[_base.ChannelID],
                priority: int) -> Union[_base.Lease, _base.Ticket]:
    req = _server_base.GetReq(client_name=client_name,
                              channels=channels,
                              priority=priority)
    success: _server_base.GetResSuccess = await self._APICall(
        endpoint=self._endpoints.get,
        req=req,
        res_type=_server_base.GetRes,
        suc_type=_server_base.GetResSuccess)
    return success.ticket

  async def TouchTicket(
      self, *, id: _base.LeaseID) -> Union[_base.Lease, _base.Ticket, None]:
    req = _server_base.TouchTicketReq(id=id)
    success: _server_base.TouchTicketResSuccess = await self._APICall(
        endpoint=self._endpoints.touch_ticket,
        req=req,
        res_type=_server_base.TouchTicketRes,
        suc_type=_server_base.TouchTicketResSuccess)
    return success.ticket

  async def TouchLease(self, *, id: _base.LeaseID) -> Optional[_base.Lease]:
    req = _server_base.TouchLeaseReq(id=id)
    success: _server_base.TouchLeaseResSuccess = await self._APICall(
        endpoint=self._endpoints.touch_lease,
        req=req,
        res_type=_server_base.TouchLeaseRes,
        suc_type=_server_base.TouchLeaseResSuccess)
    return success.lease

  async def Release(self, *, id: _base.LeaseID,
                    report: Optional[_base.ReportType],
                    report_extra: Optional[Any]):
    req = _server_base.ReleaseReq(id=id,
                                  report=report,
                                  report_extra=report_extra)
    await self._APICall(endpoint=self._endpoints.release,
                        req=req,
                        res_type=_server_base.ReleaseRes,
                        suc_type=_server_base.ReleaseResSuccess)

  async def RegisterResource(self, *, resource_id: _base.ResourceID,
                             channels: List[_base.ChannelID], data: str):
    req = _server_base.RegisterResourceReq(resource_id=resource_id,
                                           channels=channels,
                                           data=data)
    await self._APICall(endpoint=self._endpoints.register_resource,
                        req=req,
                        res_type=_server_base.RegisterResourceRes,
                        suc_type=_server_base.RegisterResourceResSuccess)

  async def RemoveResource(self, *, resource_id: _base.ResourceID):
    req = _server_base.RemoveResourceReq(resource_id=resource_id)
    await self._APICall(endpoint=self._endpoints.remove_resource,
                        req=req,
                        res_type=_server_base.RemoveResourceRes,
                        suc_type=_server_base.RemoveResourceResSuccess)

  async def ListResources(self) -> List[_base.ResourceMeta]:
    req = _server_base.ListResourcesReq()
    success: _server_base.ListResourcesResSuccess = await self._APICall(
        endpoint=self._endpoints.list_resources,
        req=req,
        res_type=_server_base.ListResourcesRes,
        suc_type=_server_base.ListResourcesResSuccess)
    return success.resources

  async def Stats(self) -> _base.Stats:
    req = _server_base.StatsReq()
    success: _server_base.StatsResSuccess = await self._APICall(
        endpoint=self._endpoints.stats,
        req=req,
        res_type=_server_base.StatsRes,
        suc_type=_server_base.StatsResSuccess)
    return success.stats

  def close(self):
    pass

  async def aclose(self):
    pass
