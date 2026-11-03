# pyright: strict
import datetime
import inspect
import ssl
from collections.abc import Sequence
from typing import Literal, TypeAlias, cast

import httpx2
import mcp_types
from fastmcp import Client
from fastmcp.client.client import (
    ConnectMode,
    ElicitationHandler,
    LogHandler,
    ProgressHandler,
    RootsHandler,
    RootsList,
    SamplingHandler,
)
from fastmcp.client.messages import MessageHandler, MessageHandlerT
from fastmcp.client.transports import ClientTransport, StreamableHttpTransport
from mcp import ClientSession
from mcp.client.caching import CacheConfig
from mcp.client.extension import ClientExtension

StrandsConnection: TypeAlias = Client[ClientTransport]
OubliaiConnection: TypeAlias = StrandsConnection


def connect(
    target: StrandsConnection | str,
    *,
    name: str | None = None,
    roots: RootsList | RootsHandler[object] | None = None,
    sampling_handler: SamplingHandler[ClientSession, object] | None = None,
    sampling_capabilities: mcp_types.SamplingCapability | None = None,
    elicitation_handler: ElicitationHandler[object, object] | None = None,
    log_handler: LogHandler | None = None,
    message_handler: MessageHandlerT | MessageHandler | None = None,
    progress_handler: ProgressHandler | None = None,
    timeout: datetime.timedelta | float | int | None = None,
    auto_initialize: bool = True,
    init_timeout: datetime.timedelta | float | int | None = None,
    client_info: mcp_types.Implementation | None = None,
    auth: httpx2.Auth | Literal["oauth"] | str | None = None,
    verify: ssl.SSLContext | bool | str | None = None,
    mode: ConnectMode = "auto",
    prior_discover: mcp_types.DiscoverResult | None = None,
    input_required_max_rounds: int = 10,
    cache: CacheConfig | bool | None = None,
    extensions: Sequence[ClientExtension] | None = None,
) -> StrandsConnection:
    if isinstance(target, Client):
        configured = {
            key
            for key, value in locals().items()
            if key != "target" and value != _CONNECT_DEFAULTS[key]
        }
        if configured:
            raise TypeError(
                f"connect() received an existing Client; options {sorted(configured)} would be "
                "ignored. Configure the Client itself, or pass a URL."
            )
        return target
    transport = StreamableHttpTransport(target, auth=auth)
    return cast(
        StrandsConnection,
        Client(
            transport,
            name=name,
            roots=roots,
            sampling_handler=sampling_handler,
            sampling_capabilities=sampling_capabilities,
            elicitation_handler=elicitation_handler,
            log_handler=log_handler,
            message_handler=message_handler,
            progress_handler=progress_handler,
            timeout=timeout,
            auto_initialize=auto_initialize,
            init_timeout=init_timeout,
            client_info=client_info,
            verify=verify,
            mode=mode,
            prior_discover=prior_discover,
            input_required_max_rounds=input_required_max_rounds,
            cache=cache,
            extensions=extensions,
        ),
    )


_CONNECT_DEFAULTS = {
    name: parameter.default
    for name, parameter in inspect.signature(connect).parameters.items()
    if name != "target"
}


def server_summary(client: StrandsConnection) -> dict[str, str | None]:
    info = client.server_info
    protocol_version = client.protocol_version
    return {
        "name": info.name if info is not None else None,
        "version": info.version if info is not None else None,
        "protocol_version": (
            str(protocol_version) if protocol_version is not None else None
        ),
        "instructions": client.instructions,
    }
