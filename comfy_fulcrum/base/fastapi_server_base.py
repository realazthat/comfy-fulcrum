# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
# The Comfy Fulcrum project requires contributions made to this file be licensed
# under the MIT license or a compatible open source license. See LICENSE.md for
# the license text.

import json
import textwrap
import traceback
from abc import ABC
from typing import Any, Generic, List, NamedTuple, Optional, Union

import yaml
from pydantic import BaseModel, Field
from typing_extensions import TypeVar

from . import base as _base


class ExceptionInfo(BaseModel):
  type: str
  msg: str
  tb: List[str]
  args: Optional[List[str]]
  cause: Optional['ExceptionInfo']
  doc: Optional[str]

  @classmethod
  def from_exception(cls, e: Exception):
    cause: Optional[Exception] = getattr(e, '__cause__', None)
    args: Optional[List[Any]] = getattr(e, 'args', None)
    args_: Optional[List[str]] = None
    if args is not None:
      args_ = [repr(arg) for arg in args]
    doc: Optional[str] = getattr(e, '__doc__', None)

    return cls(
        type=type(e).__name__,
        msg=str(e),
        tb=traceback.format_exception(type(e), e, e.__traceback__),
        args=args_,
        cause=cls.from_exception(cause) if cause is not None else None,
        doc=doc,
    )

  @staticmethod
  def GetMSG(e: Exception) -> str:
    return f'Error: {type(e).__name__}: {str(e)}'

  def GetLongMSG(self, *, source: str) -> str:
    cause: str = 'N/A'
    if self.cause is not None:
      cause = f"\n{textwrap.indent(self.cause.GetLongMSG(source=source), '    ')}"
    tb: str = '\n'.join(self.tb)
    tb = f"\n{textwrap.indent(tb, '    ')}"
    doc: str = 'N/A'
    if self.doc is not None:
      doc = f"\n{textwrap.indent(self.doc, '    ')}"
    args: str = 'N/A'
    if self.args is not None:
      args = f"\n{textwrap.indent(yaml.dump(self.args), '    ')}"
    return (f'Error occured in/from {source}:'
            f'\n  type: {json.dumps(self.type)}'
            f'\n  msg:\n{textwrap.indent(self.msg, "    ")}'
            f'\n  traceback: {tb}'
            f'\n  args: {args}'
            f'\n  cause: {cause}'
            f'\n  doc: {doc}')


class APIErrorException(Exception):
  pass


class ReconstructedException(APIErrorException):

  def __init__(self, source: str, info: ExceptionInfo):
    super().__init__(info.GetLongMSG(source=source))
    self.info = info


class _ResponseErrorBase(BaseModel):
  msg: str
  error: Optional[ExceptionInfo]

  error_id: str = Field(
      ...,
      description=
      'The error id. Can be used to match up against logs or identify/report the incident to the API provider.'
  )
  status_code: Optional[int] = Field(
      ..., description='The error status code. To be used in HTTP responses.')
  name: str = Field(..., description='The error name.')
  context: dict = Field(..., description='The error context.')


_SuccessT = TypeVar('_SuccessT', bound=BaseModel)
_ErrorT = TypeVar('_ErrorT', bound=_ResponseErrorBase)


class _ResponseBase(BaseModel, Generic[_SuccessT, _ErrorT]):
  success: Optional[_SuccessT]
  error: Optional[_ErrorT]


class GetReq(BaseModel):
  client_name: _base.ClientName
  channels: List[_base.ChannelID]
  priority: int


class GetResSuccess(BaseModel):
  ticket: Union[_base.Lease, _base.Ticket]


class GetResError(_ResponseErrorBase):
  pass


class GetRes(_ResponseBase[GetResSuccess, GetResError]):
  pass


class TouchTicketReq(BaseModel):
  id: _base.LeaseID


class TouchTicketResSuccess(BaseModel):
  ticket: Union[_base.Lease, _base.Ticket, None]


class TouchTicketResError(_ResponseErrorBase):
  pass


class TouchTicketRes(_ResponseBase[TouchTicketResSuccess, TouchTicketResError]):
  pass


class TouchLeaseReq(BaseModel):
  id: _base.LeaseID


class TouchLeaseResSuccess(BaseModel):
  lease: Optional[_base.Lease]


class TouchLeaseResError(_ResponseErrorBase):
  pass


class TouchLeaseRes(_ResponseBase[TouchLeaseResSuccess, TouchLeaseResError]):
  pass


class ReleaseReq(BaseModel):
  id: _base.LeaseID
  report: Optional[_base.ReportType]
  report_extra: Optional[Any]


class ReleaseResSuccess(BaseModel):
  pass


class ReleaseResError(_ResponseErrorBase):
  pass


class ReleaseRes(_ResponseBase[ReleaseResSuccess, ReleaseResError]):
  pass


class RegisterResourceReq(BaseModel):
  resource_id: _base.ResourceID
  channels: List[_base.ChannelID]
  data: str


class RegisterResourceResSuccess(BaseModel):
  pass


class RegisterResourceResError(_ResponseErrorBase):
  pass


class RegisterResourceRes(_ResponseBase[RegisterResourceResSuccess,
                                        RegisterResourceResError]):
  pass


class RemoveResourceReq(BaseModel):
  resource_id: _base.ResourceID


class RemoveResourceResSuccess(BaseModel):
  pass


class RemoveResourceResError(_ResponseErrorBase):
  pass


class RemoveResourceRes(_ResponseBase[RemoveResourceResSuccess,
                                      RemoveResourceResError]):
  pass


class ListResourcesReq(BaseModel):
  pass


class ListResourcesResSuccess(BaseModel):
  resources: List[_base.ResourceMeta]


class ListResourcesResError(_ResponseErrorBase):
  pass


class ListResourcesRes(_ResponseBase[ListResourcesResSuccess,
                                     ListResourcesResError]):
  pass


class StatsReq(BaseModel):
  pass


class StatsResSuccess(BaseModel):
  stats: _base.Stats


class StatsResError(_ResponseErrorBase):
  pass


class StatsRes(_ResponseBase[StatsResSuccess, StatsResError]):
  pass


class FulcrumServerRoutesBase(ABC):

  class Endpoints(NamedTuple):
    get: str
    touch_ticket: str
    touch_lease: str
    release: str
    register_resource: str
    remove_resource: str
    list_resources: str
    stats: str

  DEFAULT_ENDPOINTS = Endpoints(
      get='/fulcrum/get',
      touch_ticket='/fulcrum/touch_ticket',
      touch_lease='/fulcrum/touch_lease',
      release='/fulcrum/release',
      register_resource='/fulcrum/register_resource',
      remove_resource='/fulcrum/remove_resource',
      list_resources='/fulcrum/list_resources',
      stats='/fulcrum/stats',
  )


class FulcrumUIRoutesBase(ABC):

  class Endpoints(NamedTuple):
    mgmt: str
    resource_add: str
    resource_remove: str

  DEFAULT_ENDPOINTS = Endpoints(mgmt='/fulcrum/ui/mgmt',
                                resource_add='/fulcrum/ui/resource_add',
                                resource_remove='/fulcrum/ui/resource_remove')
