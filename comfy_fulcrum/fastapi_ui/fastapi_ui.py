# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
# The Snipinator project requires contributions made to this file be licensed
# under the MIT license or a compatible open source license. See LICENSE.md for
# the license text.

import datetime
import logging
import sys
import uuid
from pathlib import Path
from typing import Any, List, Optional, Union

import fastapi
from fastapi import HTTPException, Request
from fastapi.datastructures import FormData
from fastapi.templating import Jinja2Templates
from humanize import naturaldelta
from pydantic import TypeAdapter
from starlette.datastructures import UploadFile

if sys.version_info >= (3, 9):
  import importlib.resources as pkg_resources
else:
  import importlib_resources as pkg_resources

from ..base import base as _base
from ..base import fastapi_server_base as _server_base
from . import templates

TEMPLATES_PATH = Path(str(pkg_resources.files(templates)))
TEMPLATE_MGMT_PATH = 'mgmt.html'
assert (TEMPLATES_PATH / TEMPLATE_MGMT_PATH
        ).exists(), f'{TEMPLATES_PATH / TEMPLATE_MGMT_PATH} does not exist'

logger = logging.getLogger(__name__)


class FulcrumUIRoutes(_server_base.FulcrumUIRoutesBase):

  def __init__(
      self,
      *,
      fulcrum: _base.FulcrumBase,
      debug: bool,
      #  templates: Jinja2Templates,
      endpoints: _server_base.FulcrumUIRoutesBase.Endpoints = _server_base.
      FulcrumUIRoutesBase.DEFAULT_ENDPOINTS):
    self._templates = Jinja2Templates(directory=TEMPLATES_PATH)
    self._fulcrum = fulcrum
    self._debug = debug

    self._router = fastapi.APIRouter()
    self._endpoints = endpoints

    self._router.add_api_route(
        path=endpoints.mgmt,
        endpoint=self._UIMGMTRoute,
        response_class=fastapi.responses.HTMLResponse,
        methods=['GET'],
    )

    self._router.add_api_route(
        path=endpoints.resource_add,
        endpoint=self.UIResourceAddPost,
        response_class=fastapi.responses.RedirectResponse,
        methods=['POST'],
    )

    self._router.add_api_route(
        path=endpoints.resource_remove,
        endpoint=self.UIResourceRemovePost,
        response_class=fastapi.responses.RedirectResponse,
        methods=['POST'],
    )

  def Router(self) -> fastapi.APIRouter:
    return self._router

  def _HTTPException(self, msg: str, *, status_code: int,
                     e: Optional[Exception]) -> HTTPException:
    error_id: str = uuid.uuid4().hex
    exc_info: Any = None
    if e is None:
      exc_info = 'N/A'
    else:
      exc_info = 'N/A in production'
      if self._debug:
        exc_info = _server_base.ExceptionInfo.from_exception(e).model_dump(
            mode='json', round_trip=True, by_alias=True)
    return HTTPException(status_code=status_code,
                         detail={
                             'msg': msg,
                             'exc_info': exc_info,
                             'error_id': error_id
                         })

  async def _UIMGMTRoute(self, request: Request):
    now = datetime.datetime.now(tz=datetime.timezone.utc)

    resources: List[_base.ResourceMeta] = await self._fulcrum.ListResources()

    resources_dicts: List[dict] = []
    for resource in resources:
      resources_dicts.append({
          'id':
          resource.id,
          'started':
          resource.inserted.replace(tzinfo=datetime.timezone.utc),
          'started_ago':
          naturaldelta(now -
                       resource.inserted.replace(tzinfo=datetime.timezone.utc)),
          'channels':
          resource.channels,
          'data':
          resource.data,
      })

    return self._templates.TemplateResponse(str(TEMPLATE_MGMT_PATH), {
        'request': request,
        'resources': resources_dicts,
    })

  async def UIResourceRemovePost(self, request: Request):
    resource_id_ta = TypeAdapter(_base.ResourceID)
    form: FormData = await request.form()
    resource_id: Union[UploadFile, str] = form['resource_id']
    if isinstance(resource_id, UploadFile):
      raise self._HTTPException('resource_id is not a string',
                                status_code=400,
                                e=None)
    try:
      resource_id = resource_id_ta.validate_python(resource_id)
    except Exception as e:
      logger.exception('Invalid input: resource_id')
      raise self._HTTPException('Invalid input: resource_id',
                                status_code=400,
                                e=e) from e

    try:
      await self._fulcrum.RemoveResource(resource_id=resource_id)
    except _server_base.ReconstructedException as e:
      if e.info.type == 'IntegrityError':
        raise self._HTTPException(
            'Resource violates DB integrity (e.g it already exists, or a submitted value is bad)',
            status_code=409,
            e=e) from e
      logger.exception('Failed to register resource')
      raise self._HTTPException(msg='Failed to register resource',
                                status_code=500,
                                e=e) from e
    except Exception as e:
      logger.exception('Failed to register resource')
      raise self._HTTPException(msg='Failed to register resource',
                                status_code=500,
                                e=e) from e

    # Redirect back to the management page without any post params:
    return fastapi.responses.RedirectResponse(self._endpoints.mgmt,
                                              status_code=303)

  async def UIResourceAddPost(self, request: Request):
    resource_id_ta = TypeAdapter(_base.ResourceID)
    channels_ta = TypeAdapter(List[_base.ChannelID])

    form: FormData = await request.form()

    resource_id: Union[UploadFile, str] = form['resource_id']
    channels_json: Union[UploadFile, str] = form['channels']
    data: Union[UploadFile, str] = form['data']

    if isinstance(resource_id, UploadFile):
      raise self._HTTPException('resource_id is not a string',
                                status_code=400,
                                e=None)
    if isinstance(channels_json, UploadFile):
      raise self._HTTPException('channels is not a string',
                                status_code=400,
                                e=None)
    if isinstance(data, UploadFile):
      raise self._HTTPException('data is not a string', status_code=400, e=None)
    try:
      resource_id = resource_id_ta.validate_python(resource_id)
    except Exception as e:
      logger.exception('Invalid input: resource_id')
      raise self._HTTPException('Invalid input: resource_id',
                                status_code=400,
                                e=e) from e

    try:
      channels: List[_base.ChannelID] = channels_ta.validate_json(channels_json)
    except Exception as e:
      logger.exception('Invalid input: channels')
      raise self._HTTPException('Invalid input: channels', status_code=400,
                                e=e) from e

    try:
      await self._fulcrum.RegisterResource(resource_id=resource_id,
                                           channels=channels,
                                           data=data)
    except _server_base.ReconstructedException as e:
      if e.info.type == 'IntegrityError':
        raise self._HTTPException(
            'Resource violates DB integrity (e.g it already exists, or a submitted value is bad)',
            status_code=409,
            e=e) from e
      logger.exception('Failed to register resource')
      raise self._HTTPException(msg='Failed to register resource',
                                status_code=500,
                                e=e) from e
    except Exception as e:
      logger.exception('Failed to register resource')
      raise self._HTTPException(msg='Failed to register resource',
                                status_code=500,
                                e=e) from e

    # Redirect back to the management page without any post params:
    return fastapi.responses.RedirectResponse(self._endpoints.mgmt,
                                              status_code=303)
