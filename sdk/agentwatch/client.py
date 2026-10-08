"""Watcher, API client, and background sender.

Secrets: the plaintext API_Key is hashed on entry and never stored. The Key_Hash is kept
only in private fields that are excluded from repr, and is never passed to the logger.
"""

from __future__ import annotations

import atexit
import functools
import hashlib
import inspect
import json as _json
import logging
import os
import queue
import threading
import time
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from .guardrails import blocked_entry_for

REQUEST_TIMEOUT_S = 2.0
_log = logging.getLogger("agentwatch")


def key_hash(api_key: str) -> str:
    """Key_Hash = lowercase hex SHA-256 of the UTF-8 API_Key. The server only ever sees this."""
    if not isinstance(api_key, str) or not api_key:
        raise ValueError("api_key must be a non-empty string")
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


class GuardrailBlocked(Exception):
    """Raised before a blocked action runs. `violation_type` is "spend_cap" or "blocked_path"."""

    def __init__(self, violation_type: str, detail: str) -> None:
        super().__init__(f"agentwatch blocked ({violation_type}): {detail}")
        self.violation_type = violation_type
        self.detail = detail


class SpendCapExceeded(GuardrailBlocked):
    def __init__(self, detail: str) -> None:
        super().__init__("spend_cap", detail)


class PathBlocked(GuardrailBlocked):
    def __init__(self, detail: str) -> None:
        super().__init__("blocked_path", detail)


@dataclass(frozen=True)
class Credentials:
    """ownerId plus Key_Hash. The plaintext key is never kept; repr hides the hash."""

    owner_id: str
    key_hash: str = field(repr=False)

    @classmethod
    def from_api_key(cls, owner_id: str, api_key: str) -> "Credentials":
        return cls(owner_id, key_hash(api_key))


# ---- HTTP transport and ApiClient (task 3.3) ----


class TransportError(Exception):
    """Network-level failure: connection error or timeout. Carries no request data."""


@dataclass(frozen=True)
class Response:
    status: int
    body: Any  # parsed JSON, or None if the body was not JSON


class Transport(Protocol):
    def request(self, method: str, url: str, *, headers: dict, json: Any = None, timeout: float) -> Response: ...


class RequestsTransport:
    """Default transport over a requests.Session (connection reuse across events)."""

    def __init__(self, session=None) -> None:
        if session is None:
            import requests

            session = requests.Session()
        self.session = session

    def request(self, method, url, *, headers, json=None, timeout):
        import requests

        try:
            r = self.session.request(method, url, headers=headers, json=json, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout) as e:
            # Type name only: requests' messages can include the full URL and headers.
            raise TransportError(type(e).__name__) from None
        try:
            body = _json.loads(r.text) if r.text else None
        except ValueError:
            body = None
        return Response(r.status_code, body)


class ApiClient:
    """Thin HTTP client for the Ingestion_API. Every request carries the credential headers."""

    def __init__(self, endpoint: str, owner_id: str, key_hash: str, transport: Transport | None = None) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.owner_id = owner_id
        self._key_hash = key_hash
        self.transport = transport if transport is not None else RequestsTransport()

    def __repr__(self) -> str:
        return f"ApiClient(endpoint={self.endpoint!r}, owner_id={self.owner_id!r})"

    def _headers(self) -> dict:
        return {"X-Agentwatch-Owner": self.owner_id, "X-Agentwatch-Key-Hash": self._key_hash}

    def _call(self, method: str, path: str, body=None) -> Response:
        return self.transport.request(method, self.endpoint + path, headers=self._headers(),
                                      json=body, timeout=REQUEST_TIMEOUT_S)

    def post_event(self, event: dict) -> Response:
        return self._call("POST", "/events", event)

    def get_config(self, agent_id: str) -> Response:
        return self._call("GET", f"/agents/{agent_id}/config")

    def get_spend(self, agent_id: str) -> Response:
        return self._call("GET", f"/agents/{agent_id}/spend")


# ---- retry policy (task 3.4) ----

BACKOFF_S = (0.5, 1, 2)  # 3 retries after the first attempt
AUTH_FAILED_MSG = "agentwatch: authorization failed (check owner_id/api_key)"
_auth_warned = False  # per process: a wrong key would otherwise log on every event


def _retryable(resp: Response) -> bool:
    return resp.status == 429 or resp.status >= 500


def send_with_retries(api, event: dict, sleep: Callable[[float], None]) -> bool:
    """POST one event. True on 2xx. Never raises; the agent always continues (Req 2.3, 2.6)."""
    global _auth_warned
    event_id = event.get("eventId")
    for attempt in range(len(BACKOFF_S) + 1):
        if attempt:
            sleep(BACKOFF_S[attempt - 1])
        try:
            resp = api.post_event(event)
        except TransportError:
            continue
        except Exception as e:  # a bug in a transport must not crash the agent
            _log.warning("agentwatch: unexpected send error %s for event %s", type(e).__name__, event_id)
            return False
        if 200 <= resp.status < 300:
            return True
        if resp.status in (401, 403):
            if not _auth_warned:
                _auth_warned = True
                _log.warning(AUTH_FAILED_MSG)
            return False
        if resp.status == 400:
            msg = resp.body.get("error") if isinstance(resp.body, dict) else None
            _log.warning("agentwatch: event %s rejected: %s", event_id, msg)
            return False
        if not _retryable(resp):  # other 4xx (404, 413...): retrying will not help
            _log.warning("agentwatch: event %s rejected with status %s", event_id, resp.status)
            return False
    _log.warning("agentwatch: giving up on event %s after %d attempts", event_id, len(BACKOFF_S) + 1)
    return False


# ---- background sender (task 3.5) ----

ATEXIT_FLUSH_S = 5.0


class Sender:
    """Queue + one daemon thread. Normal events are fire-and-forget; blocked events use send_sync
    so they reach the server before the exception is raised, even if the agent then crashes."""

    def __init__(self, api, sleep: Callable[[float], None] = time.sleep,
                 register_atexit: Callable = atexit.register) -> None:
        self._api = api
        self._sleep = sleep
        self._q: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="agentwatch-sender", daemon=True)
        self._thread.start()
        register_atexit(self._atexit_flush)

    def _run(self) -> None:
        while True:
            event = self._q.get()
            try:
                send_with_retries(self._api, event, self._sleep)
            except Exception:  # send_with_retries never raises; this is belt and braces
                pass
            finally:
                self._q.task_done()

    def enqueue(self, event: dict) -> None:
        self._q.put(event)

    def send_sync(self, event: dict) -> bool:
        return send_with_retries(self._api, event, self._sleep)

    def flush(self, timeout: float = ATEXIT_FLUSH_S) -> bool:
        """Wait until every queued event has been handled. False if `timeout` passes first."""
        deadline = time.monotonic() + timeout
        with self._q.all_tasks_done:
            while self._q.unfinished_tasks:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._q.all_tasks_done.wait(remaining)
        return True

    def _atexit_flush(self) -> None:
        self.flush(timeout=ATEXIT_FLUSH_S)


# ---- config cache and Watcher (task 3.7) ----

SYNC_INTERVAL_S = 60.0


@dataclass(frozen=True)
class ConfigResponse:
    daily_spend_cap_usd: float | None
    blocked_paths: tuple[str, ...]
    pricing: dict


# Before any successful fetch: no cap, no paths, every cost 0.0 (Req 21.4).
EMPTY = ConfigResponse(None, (), {})


def parse_config_response(body) -> ConfigResponse | None:
    """Defensive parse of a Config_Response. None if anything is malformed (treated as a failed fetch)."""
    if not isinstance(body, dict):
        return None
    g, p = body.get("guardrails"), body.get("pricing")
    if not isinstance(g, dict) or not isinstance(p, dict) or not isinstance(p.get("models", {}), dict):
        return None
    cap, paths = g.get("dailySpendCapUsd"), g.get("blockedPaths")
    if cap is not None and (isinstance(cap, bool) or not isinstance(cap, (int, float)) or cap < 0):
        return None
    if not isinstance(paths, list) or not all(isinstance(x, str) and x for x in paths):
        return None
    return ConfigResponse(None if cap is None else float(cap), tuple(paths), p)


class Watcher:
    """One per agent. Holds credentials, the cached config, and the sender."""

    def __init__(self, agent_id: str, owner_id: str, api: ApiClient, sender: Sender,
                 clock: Callable[[], float]) -> None:
        self.agent_id = agent_id
        self.owner_id = owner_id
        self._api = api
        self._sender = sender
        self._clock = clock
        self._lock = threading.Lock()
        self._config: ConfigResponse = EMPTY
        self._last_config_ok: float | None = None
        self._last_config_attempt: float | None = None

    def __repr__(self) -> str:
        return f"Watcher(agent_id={self.agent_id!r}, owner_id={self.owner_id!r})"

    @property
    def config(self) -> ConfigResponse:
        return self._config

    def _fetch_config(self) -> None:
        self._last_config_attempt = self._clock()
        try:
            resp = self._api.get_config(self.agent_id)
        except TransportError as e:
            _log.warning("agentwatch: config fetch failed (%s); keeping last good config", e)
            return
        except Exception as e:
            _log.warning("agentwatch: config fetch failed (%s); keeping last good config", type(e).__name__)
            return
        parsed = parse_config_response(resp.body) if 200 <= resp.status < 300 else None
        if parsed is None:
            _log.warning("agentwatch: config fetch failed (status %s); keeping last good config", resp.status)
            return
        self._config = parsed
        self._last_config_ok = self._last_config_attempt

    def _maybe_refresh_config(self) -> None:
        """Refetch when a Sync_Interval has passed since the last attempt (Req 21.2, 21.5)."""
        with self._lock:
            last = self._last_config_attempt
            if last is not None and self._clock() - last < SYNC_INTERVAL_S:
                return
            self._fetch_config()

    # ---- events (task 3.11) ----

    def _new_event(self, type_: str, **fields) -> dict:
        return {"agentId": self.agent_id, "ownerId": self.owner_id, "ts": _utc_ts(),
                "eventId": uuid.uuid4().hex, "type": type_, **fields}

    # ---- guardrail enforcement ----

    def _send_blocked_sync(self, **fields) -> None:
        """Report a block on the caller's thread before raising. Never raises itself."""
        try:
            self._sender.send_sync(self._new_event("blocked", **fields))
        except Exception:
            pass

    def _check_path(self, tool_name: str, path: str) -> None:
        self._maybe_refresh_config()  # Req 8.8
        entry = blocked_entry_for(path, self._config.blocked_paths)
        if entry is None:
            return
        # The server keeps only violationType/attemptedPath on blocked events, so context goes in meta.
        self._send_blocked_sync(violationType="blocked_path", attemptedPath=path[:1024],
                                meta={"tool": tool_name[:200], "entry": entry[:200]})
        raise PathBlocked(path)

    # ---- LLM wrapper (task 3.13) ----

    def wrap(self, client):
        """Duck-type the client: Bedrock runtime (converse) or Anthropic (messages.create)."""
        if callable(getattr(client, "converse", None)):
            return _BedrockProxy(client, self)
        messages = getattr(client, "messages", None)
        if messages is not None and callable(getattr(messages, "create", None)):
            return _AnthropicProxy(client, self)
        raise TypeError("aw.wrap expects a Bedrock runtime client (converse) or an Anthropic client "
                        "(messages.create)")

    def _record_llm(self, provider: str, model: str, in_tok: int, out_tok: int, meta: dict) -> None:
        self._sender.enqueue(self._new_event("llm_call", model=model, inputTokens=in_tok,
                                             outputTokens=out_tok, meta={"provider": provider, **meta}))

    # ---- tool wrapper ----

    def tool(self, fn=None, *, name: str | None = None, path_arg: str | None = None):
        """Decorator: @aw.tool, @aw.tool(), or @aw.tool(name=..., path_arg=...)."""
        def decorate(f):
            return self._wrap_tool(f, name or f.__name__, path_arg)
        return decorate(fn) if callable(fn) else decorate

    def tools(self, mapping: dict) -> dict:
        """Same keys; each function wrapped as a tool named by its key."""
        return {k: self._wrap_tool(f, k, None) for k, f in mapping.items()}

    def _wrap_tool(self, f, tool_name: str, path_arg: str | None):
        try:
            sig = inspect.signature(f)
        except (TypeError, ValueError):
            sig = None

        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            bound = _bind(sig, args, kwargs)
            path = _find_path(bound, path_arg)
            if path is not None:
                self._check_path(tool_name, os.fsdecode(os.fspath(path)))  # raises PathBlocked
            target = _short(os.fsdecode(os.fspath(path))) if path is not None else _first_arg_repr(args, kwargs)
            meta = {"args": _fit_args([_short(repr(a)) for a in (*args, *kwargs.values())][:MAX_ARGS])}
            try:
                return f(*args, **kwargs)
            except BaseException as e:
                meta["error"] = type(e).__name__
                raise
            finally:
                self._sender.enqueue(self._new_event("tool_call", tool=tool_name, target=target, meta=meta))

        return wrapper


# ---- event helpers ----

PATH_ARG_NAMES = ("path", "file_path", "filepath", "filename", "file")
MAX_ARGS = 10
MAX_REPR = 200


def _utc_ts() -> str:
    """Fixed-width UTC: YYYY-MM-DDTHH:MM:SS.mmmZ (24 chars)."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _short(s: str) -> str:
    return s[:MAX_REPR]


def _bind(sig, args, kwargs) -> dict:
    if sig is not None:
        try:
            return dict(sig.bind_partial(*args, **kwargs).arguments)
        except TypeError:
            pass
    return dict(kwargs)


def _is_pathlike(v) -> bool:
    return isinstance(v, (str, bytes, os.PathLike))


def _find_path(bound: dict, path_arg: str | None):
    """The path argument, or None if this tool does not touch a file path."""
    names = (path_arg,) if path_arg else PATH_ARG_NAMES
    for n in names:
        v = bound.get(n)
        if v is not None and _is_pathlike(v):
            return v
    return None


META_ARGS_BUDGET = 3072  # bytes; leaves room for "error" and keys under the server's 4096-byte meta cap


def _fit_args(reprs: list[str]) -> list[str]:
    """Drop trailing args until the UTF-8 JSON fits the budget, so the server never 400s on meta size."""
    out = list(reprs)
    while out and len(_json.dumps(out, separators=(",", ":"), ensure_ascii=False).encode("utf-8")) > META_ARGS_BUDGET:
        out.pop()
    return out


def _first_arg_repr(args, kwargs) -> str:
    if args:
        return _short(repr(args[0]))
    if kwargs:
        return _short(repr(next(iter(kwargs.values()))))
    return "()"


def init(agent_id: str, owner_id: str, api_key: str, endpoint: str | None = None, *,
         transport: Transport | None = None, clock: Callable[[], float] | None = None,
         sleep: Callable[[float], None] | None = None) -> Watcher:
    """Create a Watcher: hash the key, fetch config once, start the sender thread."""
    endpoint = endpoint or os.environ.get("AGENTWATCH_ENDPOINT")
    if not endpoint:
        raise ValueError("agentwatch.init needs endpoint= or the AGENTWATCH_ENDPOINT env var")
    api = ApiClient(endpoint, owner_id, key_hash(api_key), transport=transport)
    sender = Sender(api, sleep=sleep or time.sleep)
    w = Watcher(agent_id, owner_id, api, sender, clock or time.monotonic)
    w._maybe_refresh_config()
    return w


# ---- LLM client proxies (task 3.13) ----


def _text_chars(content) -> int:
    """Characters of text in a message's content: a string, or a list of text blocks. Never the text itself."""
    if isinstance(content, str):
        return len(content)
    n = 0
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                n += len(block["text"])
    return n


def _int_or_zero(v) -> int:
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else 0


class _Proxy:
    """Forward every attribute except the wrapped method."""

    def __init__(self, inner, watcher: Watcher) -> None:
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "_watcher", watcher)

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._inner!r})"


class _BedrockProxy(_Proxy):
    def converse(self, **kwargs):
        model = kwargs.get("modelId", "")
        msgs = kwargs.get("messages") or []
        system = kwargs.get("system") or []
        max_tokens = (kwargs.get("inferenceConfig") or {}).get("maxTokens")
        start = time.monotonic()
        resp = self._inner.converse(**kwargs)  # provider errors propagate, no event
        latency = int((time.monotonic() - start) * 1000)
        usage = resp.get("usage", {}) if isinstance(resp, dict) else {}
        self._watcher._record_llm("bedrock", model, _int_or_zero(usage.get("inputTokens")),
                                  _int_or_zero(usage.get("outputTokens")), {
            "messageCount": len(msgs),
            "promptChars": sum(_text_chars(m.get("content")) for m in msgs if isinstance(m, dict))
                           + _text_chars(system),
            "maxTokens": max_tokens,
            "stopReason": resp.get("stopReason") if isinstance(resp, dict) else None,
            "latencyMs": latency,
        })
        return resp


class _AnthropicMessagesProxy(_Proxy):
    def create(self, **kwargs):
        model = kwargs.get("model", "")
        msgs = kwargs.get("messages") or []
        start = time.monotonic()
        msg = self._inner.create(**kwargs)
        latency = int((time.monotonic() - start) * 1000)
        usage = getattr(msg, "usage", None)
        self._watcher._record_llm("anthropic", model, _int_or_zero(getattr(usage, "input_tokens", 0)),
                                  _int_or_zero(getattr(usage, "output_tokens", 0)), {
            "messageCount": len(msgs),
            "promptChars": sum(_text_chars(m.get("content")) for m in msgs if isinstance(m, dict))
                           + _text_chars(kwargs.get("system")),
            "maxTokens": kwargs.get("max_tokens"),
            "stopReason": getattr(msg, "stop_reason", None),
            "latencyMs": latency,
        })
        return msg


class _AnthropicProxy(_Proxy):
    @property
    def messages(self):
        return _AnthropicMessagesProxy(self._inner.messages, self._watcher)
