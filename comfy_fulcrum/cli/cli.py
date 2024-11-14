# -*- coding: utf-8 -*-

# SPDX-License-Identifier: MIT
#
# The Comfy Fulcrum project requires contributions made to this file be licensed
# under the MIT license or a compatible open source license. See LICENSE.md for
# the license text.
"""
CLI to run the Comfy Fulcrum server, client, via the DB backend.
"""

import argparse
import asyncio
import json
import os
import pathlib
import sys
import warnings
from pprint import pformat
from shutil import get_terminal_size
from typing import Any, List, Optional, Union

import colorama
import fastapi
import hypercorn
import hypercorn.asyncio
import yaml
from pydantic import TypeAdapter
from rich.console import Console
from rich_argparse import RichHelpFormatter
from sqlalchemy.ext.asyncio import create_async_engine
from typing_extensions import Literal

from .. import _build_version as _build_version
from ..base.base import Lease, ResourceMeta, Ticket
from ..base.fastapi_server_base import (GetReq, RegisterResourceReq,
                                        ReleaseReq, RemoveResourceReq,
                                        TouchTicketReq)
from ..db.db import DBFulcrum
from ..fastapi_client.fastapi_client import FulcrumClient
from ..fastapi_mgmt_ui.fastapi_mgmt_ui import FulcrumUIRoutes
from ..fastapi_server.fastapi_server import FulcrumAPIState

DEFAULT_SERVICE_SLEEP_INTERVAL = 0.5
DEFAULT_LEASE_TIMEOUT = 60.0 * 3

CommandType = Literal['server', 'client']
CommandTA = TypeAdapter[CommandType](CommandType)
ClientCommandType = Literal['list', 'register', 'remove', 'get', 'touch',
                            'release', 'stats']
ClientCommandTA = TypeAdapter[ClientCommandType](ClientCommandType)
FormatType = Literal['json', 'yaml', 'pformat']
FormatTa = TypeAdapter[FormatType](FormatType)


def _GetProgramName() -> str:
  if __package__:
    # Use __package__ to get the base package name
    base_module_path = __package__
    # Infer the module name from the file path, with assumptions about the structure
    module_name = pathlib.Path(__file__).stem
    # Construct what might be the intended full module path
    full_module_path = f'{base_module_path}.{module_name}' if base_module_path else module_name
    return f'python -m {full_module_path}'
  else:
    return sys.argv[0]


class _CustomRichHelpFormatter(RichHelpFormatter):

  def __init__(self, *args, **kwargs):
    if kwargs.get('width') is None:
      width, _ = get_terminal_size()
      if width == 0:
        warnings.warn('Terminal width was set to 0, using default width of 80.',
                      RuntimeWarning,
                      stacklevel=0)
        # This is the default in get_terminal_size().
        width = 80
      # This is what HelpFormatter does to the width returned by
      # `get_terminal_size()`.
      width -= 2
      kwargs['width'] = width
    super().__init__(*args, **kwargs)


async def _ServeCommand(*, dsn: str, host: str, port: int, lease_timeout: float,
                        service_sleep_interval: float):

  db_engine = create_async_engine(dsn, isolation_level='READ COMMITTED')
  db_fulcrum = DBFulcrum(engine=db_engine,
                         lease_timeout=lease_timeout,
                         service_sleep_interval=service_sleep_interval,
                         retry=True)
  await db_fulcrum.Initialize()

  app = fastapi.FastAPI()
  await FulcrumAPIState.InitializeFulcrumAPI(app, fulcrum=db_fulcrum)

  ui_router = FulcrumUIRoutes(fulcrum=db_fulcrum, debug=app.debug)
  app.include_router(ui_router.Router())

  hypercorn_config = hypercorn.Config()
  hypercorn_config.bind = [f'{host}:{port}']
  hypercorn_config.use_reloader = True
  hypercorn_config.loglevel = 'debug'
  hypercorn_config.accesslog = '-'
  hypercorn_config.errorlog = '-'
  hypercorn_config.debug = True

  await hypercorn.asyncio.serve(app, hypercorn_config)  # type: ignore


async def _ExecuteClientCommand(*, fulcrum_api_url: str,
                                client_command: ClientCommandType,
                                data_json: str) -> Any:
  fulcrum = FulcrumClient(fulcrum_api_url=fulcrum_api_url)
  if client_command == 'list':
    resources = await fulcrum.ListResources()
    ta = TypeAdapter[List[ResourceMeta]](List[ResourceMeta])
    return ta.dump_python(resources,
                          mode='json',
                          by_alias=True,
                          round_trip=True)
  elif client_command == 'register':
    register_req = RegisterResourceReq.model_validate_json(data_json)
    await fulcrum.RegisterResource(resource_id=register_req.resource_id,
                                   channels=register_req.channels,
                                   data=register_req.data)
    return None
  elif client_command == 'remove':
    remove_req = RemoveResourceReq.model_validate_json(data_json)
    await fulcrum.RemoveResource(resource_id=remove_req.resource_id)
    return None
  elif client_command == 'get':
    get_req = GetReq.model_validate_json(data_json)
    lease_or_ticket: Union[Lease, Ticket] = await fulcrum.Get(
        client_name=get_req.client_name,
        channels=get_req.channels,
        priority=get_req.priority)
    return lease_or_ticket.model_dump(mode='json',
                                      by_alias=True,
                                      round_trip=True)
  elif client_command == 'touch':
    touch_req = TouchTicketReq.model_validate_json(data_json)
    lease_or_ticket_or: Union[Lease, Ticket,
                              None] = await fulcrum.TouchTicket(id=touch_req.id)
    if lease_or_ticket_or is None:
      return None
    return lease_or_ticket_or.model_dump(mode='json',
                                         by_alias=True,
                                         round_trip=True)
  elif client_command == 'release':
    release_req = ReleaseReq.model_validate_json(data_json)
    await fulcrum.Release(id=release_req.id,
                          report=release_req.report,
                          report_extra=release_req.report_extra)
    return None
  elif client_command == 'stats':
    stats = await fulcrum.Stats()
    return stats.model_dump(mode='json', by_alias=True, round_trip=True)
  else:
    raise ValueError(f'Unknown command: {client_command}')


async def _ClientCommand(*, fulcrum_api_url: str, client_command: str,
                         data_json: str, format: Literal['json', 'yaml',
                                                         'pformat'],
                         indent: Optional[int]) -> None:

  result = await _ExecuteClientCommand(
      fulcrum_api_url=fulcrum_api_url,
      client_command=ClientCommandTA.validate_python(client_command),
      data_json=data_json)
  if format == 'json':
    print(json.dumps(result, indent=indent))
  elif format == 'yaml':
    print(yaml.dump(result, indent=indent))
  elif format == 'pformat':
    indent = 1 if indent is None else indent
    print(pformat(result, indent=indent))
  else:
    raise ValueError(f'Unknown format: {format}')


async def amain():

  # Windows<10 requires this.
  colorama.init()
  console = Console(file=sys.stderr)
  try:
    p = argparse.ArgumentParser(prog=_GetProgramName(),
                                description=__doc__,
                                formatter_class=_CustomRichHelpFormatter)

    p.add_argument('--version', action='version', version=_build_version)

    command_p = p.add_subparsers(title='command', dest='command', required=True)

    serve_p = command_p.add_parser(
        'server',
        description='Run the FastAPI server, and the DB backend.',
        help='Run the FastAPI server.',
        formatter_class=_CustomRichHelpFormatter)
    serve_p.add_argument(
        '--dsn',
        type=str,
        required=False,
        help=
        'DSN for the database. Must be an asyncio-compatible backend, e.g `postgresql+asyncpg://..`. Falls back to FULCRUM_DSN if not specified.'
    )
    serve_p.add_argument('--host',
                         type=str,
                         required=True,
                         help='Host to run the FastAPI server on.')
    serve_p.add_argument('--port',
                         type=int,
                         required=True,
                         help='Port to run the FastAPI server on.')
    serve_p.add_argument(
        '--lease-timeout',
        type=float,
        default=DEFAULT_LEASE_TIMEOUT,
        help=
        f'The lease timeout. In seconds. Default is {DEFAULT_LEASE_TIMEOUT:.2f} seconds.'
    )
    serve_p.add_argument(
        '--service-sleep-interval',
        type=float,
        default=DEFAULT_SERVICE_SLEEP_INTERVAL,
        help=
        f'The interval at which the service sleeps between iterations. In seconds. Default is {DEFAULT_LEASE_TIMEOUT:.2f} seconds.'
    )
    client_p = command_p.add_parser(
        'client',
        description=
        'Run the FastAPI client, and connect to a Fulcrum FastAPI server.',
        help='Run the FastAPI client.',
        formatter_class=_CustomRichHelpFormatter)
    client_p.add_argument('--fulcrum_api_url',
                          type=str,
                          required=True,
                          help='URL for the FastAPI server.')
    client_p.add_argument(
        '--data',
        type=str,
        default='{}',
        help=
        'JSON encoded data for the command. See base/fastapi_server_base.py for BaseModels for each command.'
    )
    client_p.add_argument('--format',
                          type=str,
                          default='json',
                          choices=['json', 'yaml', 'pformat'],
                          help='Output format.')
    client_p.add_argument(
        '--indent',
        type=int,
        default=None,
        help=
        'Indentation for output format. If not specified, the default for that format is used.'
    )
    client_cmd_p = client_p.add_subparsers(title='client command',
                                           dest='client_command',
                                           required=True)
    client_cmd_p.add_parser('list',
                            help='List resources.',
                            formatter_class=_CustomRichHelpFormatter)
    client_cmd_p.add_parser('register',
                            help='Add a resource.',
                            formatter_class=_CustomRichHelpFormatter)
    client_cmd_p.add_parser('remove',
                            help='Delete a resource.',
                            formatter_class=_CustomRichHelpFormatter)
    client_cmd_p.add_parser('get',
                            help='Get a resource.',
                            formatter_class=_CustomRichHelpFormatter)
    client_cmd_p.add_parser('touch',
                            help='Touch a ticket/lease.',
                            formatter_class=_CustomRichHelpFormatter)
    client_cmd_p.add_parser('release',
                            help='Release a ticket/lease.',
                            formatter_class=_CustomRichHelpFormatter)
    client_cmd_p.add_parser('stats',
                            help='Get stats.',
                            formatter_class=_CustomRichHelpFormatter)

    args = p.parse_args()

    command: CommandType = CommandTA.validate_python(args.command)

    if command == 'server':

      host: str = args.host
      port: int = args.port
      dsn: Optional[str] = args.dsn
      if dsn is None:
        dsn = os.environ.get('FULCRUM_DSN')
        if dsn is None:
          raise ValueError(
              '--dsn must be specified or FULCRUM_DSN must be set.')
      lease_timeout: float = args.lease_timeout
      service_sleep_interval: float = args.service_sleep_interval

      await _ServeCommand(dsn=dsn,
                          host=host,
                          port=port,
                          lease_timeout=lease_timeout,
                          service_sleep_interval=service_sleep_interval)
    elif command == 'client':

      fulcrum_api_url: str = args.fulcrum_api_url
      client_command: ClientCommandType = ClientCommandTA.validate_python(
          args.client_command)
      data_json: str = args.data
      format: FormatType = FormatTa.validate_python(args.format)
      indent: Optional[int] = args.indent
      await _ClientCommand(fulcrum_api_url=fulcrum_api_url,
                           client_command=client_command,
                           data_json=data_json,
                           format=format,
                           indent=indent)
    else:
      raise ValueError(f'Unknown command: {command}')

  except Exception:
    console.print_exception()
    sys.exit(1)


if __name__ == '__main__':
  asyncio.run(amain())
