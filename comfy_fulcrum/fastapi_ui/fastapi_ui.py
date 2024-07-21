# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
# The Snipinator project requires contributions made to this file be licensed
# under the MIT license or a compatible open source license. See LICENSE.md for
# the license text.

import datetime
import logging
from pathlib import Path
from typing import List, Union

import fastapi
from fastapi import HTTPException, Request
from fastapi.datastructures import FormData
from fastapi.templating import Jinja2Templates
from humanize import naturaldelta
from pydantic import TypeAdapter
from starlette.datastructures import UploadFile

from ..base import base as _base
from ..base import fastapi_server_base as _server_base
from ..fastapi_client import fastapi_client as _fastapi_client

TEMPLATE_MGMT_PATH = Path(__file__).parent / 'templates/mgmt.html'
assert TEMPLATE_MGMT_PATH.exists(), f'{TEMPLATE_MGMT_PATH} does not exist'

logger = logging.getLogger(__name__)


class FulcrumUIRoutes(_server_base.FulcrumUIRoutesBase):

  def __init__(self,
               *,
               fulcrum_api_url: str,
               templates: Jinja2Templates,
               endpoints: _server_base.FulcrumUIRoutesBase.
               Endpoints = _server_base.FulcrumUIRoutesBase.DEFAULT_ENDPOINTS):
    self._templates = templates
    self._fulcrum_api_url = fulcrum_api_url
    self._fulcrum = _fastapi_client.FulcrumClient(
        fulcrum_api_url=self._fulcrum_api_url)

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

  def Router(self) -> fastapi.APIRouter:
    return self._router

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

  async def UIResourceAddPost(self, request: Request):
    resource_id_ta = TypeAdapter(_base.ResourceID)
    channels_ta = TypeAdapter(List[_base.ChannelID])

    form: FormData = await request.form()

    resource_id: Union[UploadFile, str] = form['resource_id']
    channels_json: Union[UploadFile, str] = form['channels']
    data: Union[UploadFile, str] = form['data']

    if isinstance(resource_id, UploadFile):
      raise HTTPException(status_code=400, detail='resource_id is not a string')
    if isinstance(channels_json, UploadFile):
      raise HTTPException(status_code=400, detail='channels is not a string')
    if isinstance(data, UploadFile):
      raise HTTPException(status_code=400, detail='data is not a string')
    try:
      resource_id = resource_id_ta.validate_python(resource_id)
    except Exception as e:
      logger.exception('Invalid input: resource_id')
      raise HTTPException(status_code=400,
                          detail='Invalid input: resource_id') from e

    try:
      channels: List[_base.ChannelID] = channels_ta.validate_json(channels_json)
    except Exception as e:
      logger.exception('Invalid input: channels')
      raise HTTPException(status_code=400,
                          detail='Invalid input: channels') from e

    try:
      await self._fulcrum.RegisterResource(resource_id=resource_id,
                                           channels=channels,
                                           data=data)
    except _server_base.ReconstructedException as e:
      if e.info.type == 'IntegrityError':
        raise HTTPException(
            status_code=409,
            detail=
            'Resource violates DB integrity (e.g it already exists, or a submitted value is bad)'
        ) from e
      logger.exception('Failed to register resource')
      raise HTTPException(status_code=500,
                          detail='Failed to register resource') from e
    except Exception as e:
      logger.exception('Failed to register resource')
      raise HTTPException(status_code=500,
                          detail='Failed to register resource') from e

    # Redirect back to the management page without any post params:
    return fastapi.responses.RedirectResponse(self._endpoints.mgmt,
                                              status_code=303)
