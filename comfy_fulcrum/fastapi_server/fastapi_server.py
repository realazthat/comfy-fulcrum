# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
# The Snipinator project requires contributions made to this file be licensed
# under the MIT license or a compatible open source license. See LICENSE.md for
# the license text.

import uuid
from asyncio.log import logger
from dataclasses import dataclass

import fastapi

from ..base import base as _base
from ..base import fastapi_server_base as _server_base
from ..private.utilities import to_thread as _to_thread


class FulcrumServerRoutes(_server_base.FulcrumServerRoutesBase):

  def __init__(
      self,
      *,
      fulcrum: _base.FulcrumBase,
      endpoints: _server_base.FulcrumServerRoutesBase.Endpoints = _server_base.
      FulcrumServerRoutesBase.DEFAULT_ENDPOINTS):
    self._fulcrum = fulcrum
    self._router = fastapi.APIRouter()
    self._endpoints = endpoints

    self._router.add_api_route(
        path=endpoints.get,
        endpoint=self._GetRoute,
        response_model=_server_base.GetRes,
        methods=['POST'],
    )
    self._router.add_api_route(
        path=endpoints.touch_ticket,
        endpoint=self._TouchTicketRoute,
        response_model=_server_base.TouchTicketRes,
        methods=['POST'],
    )
    self._router.add_api_route(
        path=endpoints.touch_lease,
        endpoint=self._TouchLeaseRoute,
        response_model=_server_base.TouchLeaseRes,
        methods=['POST'],
    )
    self._router.add_api_route(
        path=endpoints.release,
        endpoint=self._ReleaseRoute,
        response_model=_server_base.ReleaseRes,
        methods=['POST'],
    )
    self._router.add_api_route(
        path=endpoints.register_resource,
        endpoint=self._RegisterResourceRoute,
        response_model=_server_base.RegisterResourceRes,
        methods=['POST'],
    )
    self._router.add_api_route(
        path=endpoints.remove_resource,
        endpoint=self._RemoveResourceRoute,
        response_model=_server_base.RemoveResourceRes,
        methods=['POST'],
    )
    self._router.add_api_route(
        path=endpoints.list_resources,
        endpoint=self._ListResourcesRoute,
        response_model=_server_base.ListResourcesRes,
        methods=['POST'],
    )
    self._router.add_api_route(
        path=endpoints.stats,
        endpoint=self._StatsRoute,
        response_model=_server_base.StatsRes,
        methods=['POST'],
    )

  def Router(self) -> fastapi.APIRouter:
    return self._router

  async def _GetRoute(self, req: _server_base.GetReq) -> _server_base.GetRes:
    try:
      ticket = await self._fulcrum.Get(client_name=req.client_name,
                                       channels=req.channels,
                                       priority=req.priority)
      return _server_base.GetRes(
          success=_server_base.GetResSuccess(ticket=ticket), error=None)
    except Exception as e:
      logger.exception('Error in GetRoute')
      req_dict = await _to_thread(req.model_dump,
                                  mode='json',
                                  by_alias=True,
                                  round_trip=True)
      return _server_base.GetRes(
          success=None,
          error=_server_base.GetResError(
              msg=_server_base.ExceptionInfo.GetMSG(e),
              error=_server_base.ExceptionInfo.from_exception(e),
              error_id=uuid.uuid4().hex,
              status_code=500,
              name=type(e).__name__,
              context={'req': req_dict}))

  async def _TouchTicketRoute(
      self, req: _server_base.TouchTicketReq) -> _server_base.TouchTicketRes:
    try:
      ticket = await self._fulcrum.TouchTicket(id=req.id)
      return _server_base.TouchTicketRes(
          success=_server_base.TouchTicketResSuccess(ticket=ticket), error=None)
    except Exception as e:
      logger.exception('Error in TouchTicketRoute')
      req_dict = await _to_thread(req.model_dump,
                                  mode='json',
                                  by_alias=True,
                                  round_trip=True)
      return _server_base.TouchTicketRes(
          success=None,
          error=_server_base.TouchTicketResError(
              msg=_server_base.ExceptionInfo.GetMSG(e),
              error=_server_base.ExceptionInfo.from_exception(e),
              error_id=uuid.uuid4().hex,
              status_code=500,
              name=type(e).__name__,
              context={'req': req_dict}))

  async def _TouchLeaseRoute(
      self, req: _server_base.TouchLeaseReq) -> _server_base.TouchLeaseRes:
    try:
      lease = await self._fulcrum.TouchLease(id=req.id)
      return _server_base.TouchLeaseRes(
          success=_server_base.TouchLeaseResSuccess(lease=lease), error=None)
    except Exception as e:
      logger.exception('Error in TouchLeaseRoute')
      req_dict = await _to_thread(req.model_dump,
                                  mode='json',
                                  by_alias=True,
                                  round_trip=True)
      return _server_base.TouchLeaseRes(
          success=None,
          error=_server_base.TouchLeaseResError(
              msg=_server_base.ExceptionInfo.GetMSG(e),
              error=_server_base.ExceptionInfo.from_exception(e),
              error_id=uuid.uuid4().hex,
              status_code=500,
              name=type(e).__name__,
              context={'req': req_dict}))

  async def _ReleaseRoute(
      self, req: _server_base.ReleaseReq) -> _server_base.ReleaseRes:
    try:
      await self._fulcrum.Release(id=req.id,
                                  report=req.report,
                                  report_extra=req.report_extra)
      return _server_base.ReleaseRes(success=_server_base.ReleaseResSuccess(),
                                     error=None)
    except Exception as e:
      logger.exception('Error in ReleaseRoute')
      req_dict = await _to_thread(req.model_dump,
                                  mode='json',
                                  by_alias=True,
                                  round_trip=True)
      return _server_base.ReleaseRes(
          success=None,
          error=_server_base.ReleaseResError(
              msg=_server_base.ExceptionInfo.GetMSG(e),
              error=_server_base.ExceptionInfo.from_exception(e),
              error_id=uuid.uuid4().hex,
              status_code=500,
              name=type(e).__name__,
              context={'req': req_dict}))

  async def _RegisterResourceRoute(
      self, req: _server_base.RegisterResourceReq
  ) -> _server_base.RegisterResourceRes:
    try:
      await self._fulcrum.RegisterResource(resource_id=req.resource_id,
                                           channels=req.channels,
                                           data=req.data)
      return _server_base.RegisterResourceRes(
          success=_server_base.RegisterResourceResSuccess(), error=None)
    except Exception as e:
      logger.exception('Error in RegisterResourceRoute')
      req_dict = await _to_thread(req.model_dump,
                                  mode='json',
                                  by_alias=True,
                                  round_trip=True)
      return _server_base.RegisterResourceRes(
          success=None,
          error=_server_base.RegisterResourceResError(
              msg=_server_base.ExceptionInfo.GetMSG(e),
              error=_server_base.ExceptionInfo.from_exception(e),
              error_id=uuid.uuid4().hex,
              status_code=500,
              name=type(e).__name__,
              context={'req': req_dict}))

  async def _RemoveResourceRoute(
      self,
      req: _server_base.RemoveResourceReq) -> _server_base.RemoveResourceRes:
    try:
      await self._fulcrum.RemoveResource(resource_id=req.resource_id)
      return _server_base.RemoveResourceRes(
          success=_server_base.RemoveResourceResSuccess(), error=None)
    except Exception as e:
      logger.exception('Error in RemoveResourceRoute')
      req_dict = await _to_thread(req.model_dump,
                                  mode='json',
                                  by_alias=True,
                                  round_trip=True)
      return _server_base.RemoveResourceRes(
          success=None,
          error=_server_base.RemoveResourceResError(
              msg=_server_base.ExceptionInfo.GetMSG(e),
              error=_server_base.ExceptionInfo.from_exception(e),
              error_id=uuid.uuid4().hex,
              status_code=500,
              name=type(e).__name__,
              context={'req': req_dict}))

  async def _ListResourcesRoute(
      self,
      req: _server_base.ListResourcesReq) -> _server_base.ListResourcesRes:
    try:
      resources = await self._fulcrum.ListResources()
      return _server_base.ListResourcesRes(
          success=_server_base.ListResourcesResSuccess(resources=resources),
          error=None)
    except Exception as e:
      logger.exception('Error in ListResourcesRoute')
      req_dict = await _to_thread(req.model_dump,
                                  mode='json',
                                  by_alias=True,
                                  round_trip=True)
      return _server_base.ListResourcesRes(
          success=None,
          error=_server_base.ListResourcesResError(
              msg=_server_base.ExceptionInfo.GetMSG(e),
              error=_server_base.ExceptionInfo.from_exception(e),
              error_id=uuid.uuid4().hex,
              status_code=500,
              name=type(e).__name__,
              context={'req': req_dict}))

  async def _StatsRoute(self,
                        req: _server_base.StatsReq) -> _server_base.StatsRes:
    try:
      stats = await self._fulcrum.Stats()
      return _server_base.StatsRes(
          success=_server_base.StatsResSuccess(stats=stats), error=None)
    except Exception as e:
      logger.exception('Error in StatsRoute')
      req_dict = await _to_thread(req.model_dump,
                                  mode='json',
                                  by_alias=True,
                                  round_trip=True)
      return _server_base.StatsRes(
          success=None,
          error=_server_base.StatsResError(
              msg=_server_base.ExceptionInfo.GetMSG(e),
              error=_server_base.ExceptionInfo.from_exception(e),
              error_id=uuid.uuid4().hex,
              status_code=500,
              name=type(e).__name__,
              context={'req': req_dict}))


@dataclass
class FulcrumAPIState:
  fulcrum: _base.FulcrumBase

  @staticmethod
  async def InitializeFulcrumAPI(app: fastapi.FastAPI,
                                 fulcrum: _base.FulcrumBase) -> None:
    try:
      fulcrum_server_routers = FulcrumServerRoutes(fulcrum=fulcrum)
      app.include_router(fulcrum_server_routers.Router())
      app.state.fulcrum = fulcrum
    except Exception as e:
      logger.exception(e)
      raise Exception('Failed to initialize Fulcrum API.') from e

  async def aclose(self):
    await self.fulcrum.aclose()

  async def close(self):
    self.fulcrum.close()
