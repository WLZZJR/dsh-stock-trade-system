"""Request context: trace_id, access logging and the last-resort 500 handler (P1-20).

A pure ASGI middleware (not ``BaseHTTPMiddleware``) so the trace id reaches every response and
every log line, including the one for an unhandled exception. Unhandled errors are logged here
through the redacting formatter and answered with a generic problem+json, so no traceback or
exception text reaches the client or the server's own unredacted error log.
"""

from __future__ import annotations

import logging
import time

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api.problem_http import problem_response
from application import problems
from application.observability import new_trace_id, trace_id_var, valid_trace_id

logger = logging.getLogger("gei.api")

TRACE_HEADER = "X-Trace-Id"


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        inbound = Headers(scope=scope).get(TRACE_HEADER)
        trace_id = inbound if inbound and valid_trace_id(inbound) else new_trace_id()
        scope.setdefault("state", {})["trace_id"] = trace_id
        token = trace_id_var.set(trace_id)
        status = 500
        started = False
        began = time.perf_counter()

        async def send_with_trace(message: Message) -> None:
            nonlocal status, started
            if message["type"] == "http.response.start":
                started = True
                status = message["status"]
                MutableHeaders(scope=message)[TRACE_HEADER] = trace_id
            await send(message)

        try:
            try:
                await self.app(scope, receive, send_with_trace)
            except Exception:
                logger.exception("unhandled_error")
                if started:  # cannot replace a response that is already on the wire
                    raise
                response = problem_response(
                    problems.INTERNAL_ERROR, "An internal error occurred.", trace_id
                )
                await response(scope, receive, send_with_trace)
        finally:
            # Method and path only: never headers, query string or body, which may hold secrets.
            logger.info(
                "request",
                extra={
                    "fields": {
                        "method": scope["method"],
                        "path": scope["path"],
                        "status": status,
                        "duration_ms": round((time.perf_counter() - began) * 1000, 2),
                    }
                },
            )
            trace_id_var.reset(token)
