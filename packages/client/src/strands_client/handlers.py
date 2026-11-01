from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar, cast
from urllib.parse import urlsplit

import mcp_types
from fastmcp.client.elicitation import (
    ElicitationHandler,
    ElicitRequestParams,
    ElicitResult,
)
from fastmcp.client.logging import LogMessage
from fastmcp.client.messages import MessageHandler
from fastmcp.client.sampling import (
    RequestContext,
    SamplingHandler,
    SamplingHandlerResult,
    SamplingMessage,
    SamplingParams,
)
from mcp import ClientSession

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    progress: float
    total: float | None
    message: str | None


@dataclass(slots=True)
class ProgressRecorder:
    events: list[ProgressEvent] = field(default_factory=list)

    async def __call__(
        self, progress: float, total: float | None, message: str | None
    ) -> None:
        self.events.append(ProgressEvent(progress, total, message))


@dataclass(slots=True)
class LogRecorder:
    messages: list[LogMessage] = field(default_factory=list)

    async def __call__(self, message: LogMessage) -> None:
        self.messages.append(message)


@dataclass(slots=True)
class NotificationRecorder(MessageHandler):
    notifications: list[mcp_types.ServerNotification] = field(default_factory=list)

    async def on_notification(
        self, message: mcp_types.ServerNotification
    ) -> None:
        self.notifications.append(message)


def elicitation_handler(response: T) -> ElicitationHandler:
    async def handler(
        message: str,
        response_type: type[T] | None,
        params: ElicitRequestParams,
        context: RequestContext[ClientSession, object],
    ) -> T:
        del message, response_type, params, context
        return response

    return cast(ElicitationHandler, handler)


async def decline(
    message: str,
    response_type: type[T] | None,
    params: ElicitRequestParams,
    context: RequestContext[ClientSession, object],
) -> ElicitResult[T]:
    del message, response_type, params, context
    return ElicitResult(action="decline")


async def cancel(
    message: str,
    response_type: type[T] | None,
    params: ElicitRequestParams,
    context: RequestContext[ClientSession, object],
) -> ElicitResult[T]:
    del message, response_type, params, context
    return ElicitResult(action="cancel")


def sampling_handler(response: SamplingHandlerResult) -> SamplingHandler:
    async def handler(
        messages: list[SamplingMessage],
        params: SamplingParams,
        context: RequestContext[ClientSession, object],
    ) -> SamplingHandlerResult:
        del messages, params, context
        return response

    return cast(SamplingHandler, handler)


def roots(paths: Iterable[str | Path]) -> list[str]:
    result: list[str] = []
    for path in paths:
        value = str(path)
        if urlsplit(value).scheme:
            result.append(value)
        else:
            result.append(Path(value).expanduser().resolve().as_uri())
    return result
