# PROGRESS

Last updated: 2026-10-09 by Kiro session (6.5 AWS half, 6.6 checkpoint; group 6 complete)

## Done
- Group 1 (1.1–1.14) Backend foundations: pricing, demo model IDs, event validation, guardrail config, credentials, InMemoryStore, classify_cancellation, DynamoStore writes and queries, review hardening.
- Group 2 (2.1–2.8) Service layer and API: `service.py` (`Result`, `authorize`, `authorize_or_register`, `ingest_event`, `get_config`, `put_config`, `NullPublisher`) and `handlers/api.py` (route table, 401 gate, 400/404/500 mapping, structured secret-free logs). Properties 4, 5, 6 (config clause), 7, 10, 12, 14 (route clauses), 15, 28 (service clause) added. Backend suite: 370 passed.

- Group 3 (3.1–3.16) SDK: key hash and exceptions, `ApiClient`, retrying background `Sender`, cost math, `Watcher` config cache with 60 s sync, path blocklist (forms, matching, symlinks, enforcement with a synchronous blocked event), tool wrapper, LLM wrapper for Bedrock `converse` and Anthropic `messages.create` (metadata only, no prompt text), unknown-model warn-once, and a test that runs the 3-line snippet verbatim. Properties 1, 18–20, 23 (config), 24–27, 29 added. Checkpoint: SDK 136 passed, backend 381 passed.

- Group 3 review fixes (3.17–3.20), each pushed as its own `fix(sdk)` commit. The tool wrapper now checks every path-like argument and fails closed when a path can't be normalized. Matching uses NFC before casefold, name entries match any path component, and existing directory entries also match by inode. Transport sends with `allow_redirects=False` and accepts only https endpoints (loopback http allowed). A "guardrails NOT active" warning fires while no config fetch has succeeded. Req 8.6, 8.13–8.15, 14.11–14.12, 21.7, and Property 24 updated. Checkpoint: SDK 184 passed, backend 381 passed.

- 3.17 regression fix (pushed as `fix(sdk)`): fail-closed on unnormalizable values now applies only to named path args. Binary `bytes` with a NUL in another arg is skipped. Req 8.14 and design updated.
- Group 4 (4.1–4.5): `alerts.py` (`format_alert`, `publish_alert`, `SnsPublisher`) and Properties 16 and 17; step 7 of `ingest_event` publishes only for newly stored blocked events; the handler builds `SnsPublisher(TOPIC_ARN)`. `demo/bad_agent.py`, `demo/demo_agent.py` (Bedrock probe, Anthropic fallback), `demo/common.py`, `demo/notes.txt`, `demo/requirements.txt`. Checkpoint: SDK 195 passed, backend 397 on main (404 with `test_template.py` on the PR branch).

- 4.3 SAM template: PR #1 (`feat/sam-template`), approved by Tejaswi and merged into main. Backend suite: 404 passed.
- 4.6 Checkpoint, verified manually by Tejaswi:
  - Stack `agent-watch` is deployed in us-west-2. `ApiUrl`: https://ypdid9bish.execute-api.us-west-2.amazonaws.com
  - The SNS subscription email was confirmed.
  - `bad_agent.py` printed `PathBlocked`, and the alert email arrived.
  - Replaying an existing event with a wrong key returned 403, and nothing was written.
  - `demo_agent.py` events were stored.

- 5.3 CORS: added `DashboardOrigin` parameter (default `http://localhost:3000`) and an explicit `ServerlessHttpApi` resource with `CorsConfiguration` (origins localhost + `DashboardOrigin`; methods GET/PUT/POST/OPTIONS; headers content-type, x-agentwatch-owner, x-agentwatch-key-hash). `test_template.py` asserts it. Committed and pushed on main; NOT deployed (Tejaswi runs `sam deploy`).

- Group 5 dashboard (5.4–5.12): Next.js 14 App Router static-export app under `dashboard/`, TypeScript + Tailwind + hand-authored shadcn/ui (Button, Input, Table, Select, Alert), vitest + Testing Library + jsdom. `lib/types.ts` mirrors InventoryItem/TimelineItem/GuardrailConfig/ConfigResponse. `lib/credentials.ts` (SHA-256 via `crypto.subtle`, stores only {ownerId, keyHash}), `lib/api.ts` (credential headers, AuthError/ApiError, getInventory/getTimeline/getConfig/putConfig). Components: CredentialsForm, InventoryTable, AddAgentForm, Timeline (infinite scroll + type filter), RulesEditor. Pages: inventory `/` (30s polling, auth/clear handling) and agent detail `/agent?id=` (Suspense-wrapped useSearchParams). `npm run build` produces `out/` with `/` and `/agent` prerendered. Dashboard suite: 46 passed. Next bumped to 14.2.35 to clear a published advisory.

- 5.13 DONE (deployed): the dashboard is live on AWS Amplify Hosting. App id `d65rs0iutjwy8`, URL https://main.d65rs0iutjwy8.amplifyapp.com, auto-building from `main`. The repo-root `amplify.yml` is a monorepo spec (`applications:` + `appRoot: dashboard`). `backend/template.yaml` was deployed with `DashboardOrigin` set to the Amplify URL, so the API's CORS origin is that URL. `dashboard/lib/build.test.ts` reads the root file and asserts the `applications` key and `appRoot: dashboard`.

- 5.14 DONE (verified manually by Tejaswi on the deployed dashboard, 2026-10-09): `bad-bot` and `demo-bot` both show in the inventory, and `bad-bot` shows the `.env` rule and the blocked event in its timeline.
  - The original demo API key was lost. The demo data was deleted and recreated with a new key. The key now lives in a private file outside the repo. Never commit or print it.
- 5.15 DONE: inventory "Total spend" now shows 4 decimals (`$0.0006` instead of `$0.00`), and `<$0.0001` for nonzero amounts below that. Dashboard suite: 51 passed. Pushed as `fix(dashboard)`; Amplify rebuilds from `main`.

- Group 6 (6.1–6.4), each pushed as its own `feat` commit:
  - 6.1 `get_spend` + `GET /agents/{agentId}/spend` (route added to `handlers/api.py` and `template.yaml`). Window is `now - 24h < ts <= now`. Properties 11 and 6 (spend clause) added. NOT deployed.
  - 6.2 SDK Local_Spend_Total: fetched at `init`, increased by each completed LLM call's actual cost, resynced at most every 60 s; a failed or malformed sync keeps the value and warns. Properties 22 and 23 (spend clause) added.
  - 6.3 `estimate_input_tokens`, `max_output_tokens` (default 4096), `estimate_pending_cost`, `spend_decision` (block iff total + est > cap).
  - 6.4 `Watcher.check_spend` runs before every Bedrock `converse` and Anthropic `messages.create`. Over the cap it sends a `spend_cap` blocked event synchronously and raises `SpendCapExceeded`; the client is never called. Property 21 added.
  - Suites: backend 429 passed, SDK 222 passed, dashboard 51 passed.
- `GET /agents/{agentId}/spend` is deployed and verified by Tejaswi (200 with the right key, 403 with a wrong key).
- 6.5 local half: `demo/demo_agent.py --loop N` (N >= 1, default 1). Notes are read once, the question is asked up to N times, and `SpendCapExceeded` prints `run i/N: SpendCapExceeded: ...`, stops the loop, and exits 0. Tests added to `sdk/tests/test_demo_agent.py`. SDK suite: 229 passed.
- 6.5 AWS half DONE (verified manually by Tejaswi, 2026-10-09): with a `0.007` cap on `demo-bot`, `python demo/demo_agent.py --loop 5` completed runs 1 and 2. Run 3 raised `SpendCapExceeded` ($0.006012 spent + $0.001055 estimated > $0.007 cap). The `spend_cap` blocked event was stored and the alert email arrived.
- 6.6 Checkpoint DONE: backend 429 passed, SDK 229 passed, dashboard vitest 51 passed. Group 6 complete.

- 7.1 DONE (PR #2 merged, deployed and verified by Tejaswi on 2026-10-09). Stack is UPDATE_COMPLETE, throttling 10/20 is live on the `$default` stage, and `CostBudget` was created. CORS and the API URL are unchanged. The change adds `Globals.HttpApi.DefaultRouteSettings` (rate 10, burst 20) and `CostBudget` (`AWS::Budgets::Budget`, 10 USD monthly, ACTUAL > 100% emails `AlertEmail`). Tests pin exactly six routes on the implicit API, exactly two policies with no custom Role, and the live identity: no explicit `ServerlessHttpApi`, no `TableName`, and `AlertEmail`/`DashboardOrigin` unchanged. `sam validate --lint` is clean. Backend: 434 passed.

- 7.2 DONE: `README.md` replaces the starter-kit README. It covers what Agent Watch is, the 3-line integration, deploy (`sam deploy` + Amplify), demos, tests, and Known limitations (Req 26 plus case over-blocking, hardlink/TOCTOU, first-come ids, at-most-once alerts, stage-wide throttling). `backend/tests/test_readme.py` pins the required statements. Backend: 436 passed.

- 7.3 DONE: `docs/ARCHITECTURE.md` (diagram, block sequence, routes, data model, decisions), `docs/DEMO_SCRIPT.md` (prep checklist, on-camera click-path using the real UI labels and alert subjects, troubleshooting), and `docs/SUBMISSION.md` (pitch, AWS and security choices, Kiro usage, next steps). `test_readme.py` checks headings, both demo moments, the next-steps list, and that no live key or 64-hex hash appears in README/docs. Backend: 440 passed.
- 7.4 (optional, moto tests) SKIPPED for now. It would add a new dev dependency late in the project, and `test_store_dynamo.py` already pins the exact DynamoDB request shapes. Pick it up only if time is left after 7.5.

- DEMO_SCRIPT fixes (pushed as `fix(docs)`): prep step 1 sets `AGENTWATCH_KEY="$(cat ~/.agentwatch_key)"`; on-camera step 3 lists the real inventory columns (Agent, Model, Last activity, Total spend). `test_readme.py` pins both and allows the from-file form in the secret scan.
- 7.6 DONE: `scripts/e2e.sh` pre-recording smoke test plus `backend/tests/test_e2e_script.py` (key read only from `~/.agentwatch_key`, no literal key/hash, never echoed, no xtrace). Run once on 2026-10-09 against the deployed stack, all PASS:
  - backend pytest, sdk pytest, dashboard vitest
  - bad-bot: `.env` added, `PathBlocked`
  - demo-bot: cap set to $0.009025 (24h spend + 0.003); runs 1–4 succeeded, run 5 `SpendCapExceeded` ($0.008178 spent + $0.001055 est)
  - new `blocked_path` (bad-bot) and `spend_cap` (demo-bot) events stored
  - cleanup: demo-bot cap null, `.env` removed from bad-bot
  - Email arrival not checked by the script (look at the inbox).

## In progress
- (none)

## Next step (needs Tejaswi)
- 7.5 final rehearsal on the deployed stack, following `docs/DEMO_SCRIPT.md`. Run `scripts/e2e.sh` first (covers all three suites and both guardrails, then resets the agents). Then do the on-camera click-path by hand and note block-to-email timings here.
- After rehearsal: record the demo video and submit using `docs/SUBMISSION.md`.

## Blocked
- (none)

## Decisions
- 2026-10-08 firstSeen is the ts of the first event to arrive, not the earliest ts. It matches Property 12 and is a single `if_not_exists` in the transaction (no read-compare-write).
- 2026-10-08 Fields from another event type are dropped silently instead of rejected. Non-finite numbers are still rejected even in dropped fields.
- 2026-10-08 Only costs are rounded to 6 dp. Other numbers are stored exactly, so ints stay ints.
- 2026-10-08 InMemoryStore `last_sk` follows DynamoDB `LastEvaluatedKey`: it's set whenever `limit` items were read.
- 2026-10-08 `new_record(agent_id, creds, cfg)` takes agentId (tasks.md listed `new_record(creds, cfg)`, but a record needs its key).
- 2026-10-08 `authorize_or_register` is shared by ingest and put_config. It returns "created" so put_config skips a redundant update after creating the record with the submitted config.
- 2026-10-08 A duplicate event's response reports the stored costUsd (one consistent `get_item`, only on the duplicate path). Recomputing from the resubmitted body could disagree with what was stored. (Replaces the earlier "recompute, no extra read" decision, per group 2 review.)
- 2026-10-08 The handler sets the `agentwatch_api` logger to INFO; the SAM template must also set `LoggingConfig.ApplicationLogLevel: INFO` (task 4.3).
- 2026-10-08 On 401 the handler reads no body and no path; the log agentId is set by the route after the gate, and the POST body is parsed once.
- 2026-10-08 get_config and put_config validate the path agentId (400) before touching the store.
- 2026-10-08 The handler's 500 path logs only the exception type, never its message, since messages can echo inputs or secrets.

- 2026-10-08 SDK tool events trim trailing `meta.args` to fit a 3 KB UTF-8 budget. 10 args × 200 chars of wide Unicode could exceed the server's 4 KB meta cap, and the event would be lost to a 400.
- 2026-10-08 SDK config refresh is timed from the last attempt, not the last success (design), so an outage gets at most one request per 60 s.

- 2026-10-08 Blocked events carry the tool name and matching entry in `meta` (`{tool, entry}`), because backend validation drops `tool` on `blocked` events.

- 2026-10-08 The LLM wrapper doesn't add to Local_Spend_Total yet. Task 6.2 owns spend accounting, so 3.13 records events only, which matches "no spend check yet".
- 2026-10-08 `aw.wrap` raises `TypeError` for a client that has neither `converse` nor `messages.create`. Wrapping it silently would record nothing and hide the mistake.
- 2026-10-08 Unknown-model warnings run only after a successful config fetch (`_last_config_ok` is set). With EMPTY, every model is unknown, so warnings would just be noise (Req 21.4).

- 2026-10-08 (3.17) Every str/bytes/PathLike tool argument is a candidate path, so `search(".env")` is blocked too. Over-blocking is the safe direction, and the SDK can't know which strings a tool treats as paths.
- 2026-10-08 (3.17) A path whose normalization raises (e.g. a NUL byte) is blocked and reported with `meta.entry = "<unnormalizable path>"`. Fail closed.
- 2026-10-08 (3.17 regression fix) Fail-closed applies only to named path args (`PATH_ARG_NAMES` / `path_arg`). Other candidates that fail normalization are skipped, so `write_file("out.zip", data)` with NUL bytes in `data` isn't blocked. A NUL can't name a real file, so skipping it only lets non-path data through.
- 2026-10-08 (3.18) The inode match only adds blocks and runs only for directory entries that exist. Ancestor ids are computed lazily, once per attempted path.
- 2026-10-08 (3.19) The endpoint check parses with `urlsplit` instead of matching a prefix, so `http://localhost.evil.com` and `http://localhost@evil.com` are rejected.
- 2026-10-08 (3.20) While no fetch has succeeded, the "NOT active" line replaces the "keeping last good config" warning and the failure reason drops to DEBUG, so the warning text stays exact.
- 2026-10-08 Not fixed, documented instead (README in 7.2, INTERVIEW_PREP): a hardlink to a blocked file under another name, and the TOCTOU window for a swapped symlink. Both fall outside the threat model (careless agent, not a malicious one).

- 2026-10-08 (4.1) Alert email fields escape non-printable chars, so an attempted path can't forge email lines. The subject is capped at 100 chars (SNS limit). Publish failures log only the exception type.
- 2026-10-08 (4.2) Alerts are at-most-once. Publishing happens synchronously after a "stored" write, so a crash between write and publish loses the email but never duplicates it. DynamoDB Streams would make it reliable, and that's a next step.
- 2026-10-08 (4.4/4.5) Demo setup comes from env vars `AGENTWATCH_ENDPOINT`, `AGENTWATCH_OWNER`, `AGENTWATCH_KEY`. `make_client` sends a 1-token Bedrock probe so a fallback happens at startup, not mid-demo.

- 2026-10-08 (4.6) `demo/requirements.txt` pins `botocore[crt]` to the same version as `boto3`. `aws login` credentials need the CRT extra.

- 2026-10-08 (5.3) CORS is attached via an explicit `ServerlessHttpApi` resource (the default implicit API logical id) so the function's existing HttpApi events still bind to it. `DashboardOrigin` defaults to localhost and is overridden with the Amplify URL at deploy time, so no code change is needed when the URL exists.
- 2026-10-08 (5.4) Dashboard scaffolded by hand (not create-next-app) to stay offline and avoid interactive prompts. shadcn/ui components authored directly under `components/ui/` rather than via the CLI. Next bumped from 14.2.15 to 14.2.35 to clear a published security advisory while staying on Next 14.
- 2026-10-08 (5.4) vitest setup installs a minimal in-memory `localStorage` polyfill; jsdom in this Node did not expose Storage. jsdom `url` set to `http://localhost:3000`.
- 2026-10-08 (5.8) Agent links use `/agent?id=<id>` (query param) instead of a dynamic route, which is simpler for static export (no generateStaticParams needed).
- 2026-10-08 (5.10/5.12) Timeline type filter uses a native `<select>` (easy to drive with Testing Library `selectOptions`); the detail page wraps `useSearchParams` in `<Suspense>`, required by static export.
- 2026-10-08 (5.11) RulesEditor always PUTs the full GuardrailConfig (backend replaces config wholesale); an empty cap input is sent as `null`.

- 2026-10-09 (5.13 deploy) Amplify + CORS gotchas learned while deploying:
  - The root `amplify.yml` must use the monorepo `applications:` + `appRoot: dashboard` format. A flat `frontend:` spec fails with "Monorepo spec provided without 'applications' key".
  - The Amplify app platform must be `WEB` (not `WEB_COMPUTE`). `WEB_COMPUTE` fails on a static export (`output: "export"`); there is no server runtime to host.
  - CORS config must live under `Globals.HttpApi` in `template.yaml`. An explicit `ServerlessHttpApi` resource is ignored by SAM, leaving the live `CorsConfiguration` null.
  - CORS `AllowOrigins` can't contain duplicates (API Gateway: "Duplicated values are not allowed in allow-origins"), so localhost can't be listed both literally and as the `DashboardOrigin` default.
  - localhost is no longer an allowed origin: `AllowOrigins` is just `!Ref DashboardOrigin`, now set to the Amplify URL. Local dev against the deployed API needs `DashboardOrigin` overridden back to localhost and a redeploy.

- 2026-10-09 (5.15) Spend shows 4 decimals, not `<$0.01`. A `<$0.01` label would still hide demo-sized spend ($0.0006), which is the number students need to see. The floor label is `<$0.0001` so a tiny nonzero spend never reads as `$0.0000`.

- 2026-10-09 (6.1) The exclusive lower bound uses the SK suffix `#~` on both bounds of the inclusive `BETWEEN`. `~` sorts after every hex eventId, so `start#~` skips events exactly at `now - 24h` and `end#~` keeps events exactly at `now`. `now` is floored to ms to match event ts precision. The rolling sum is rounded to 6 dp like other costs.
- 2026-10-09 (6.2) Test `FakeTransport` sends `/spend` requests to their own queue and log (`spend_outcomes`, `spend_requests`; default 200 with 0.0). This way the new init-time spend fetch doesn't shift the config/event queues of ~15 older tests. Raw `ApiClient` tests pass `route_spend=False`.
- 2026-10-09 (6.2) A spend response only replaces Local_Spend_Total if `rollingSpendUsd` is a finite, non-negative, non-bool number. Anything else counts as a failed sync. A bad value could otherwise silently disable the cap.
- 2026-10-09 (6.4) Spend-cap blocked events put `{model, localSpendUsd, capUsd}` in `meta` (checked against backend validation). Check and accumulate aren't atomic across threads, so concurrent calls can overshoot by about one call each. Holding a lock across the provider call would serialize every LLM call.
- 2026-10-09 (resolved) The deployed stack used to lag `main` on the spend route; it's deployed now.
- 2026-10-09 (6.5) A spend-cap block in `--loop` exits 0, because the block is the expected outcome of the demo. The loop catches only `SpendCapExceeded`; any other error still propagates. Notes are read once outside the loop, so the run shows one `tool_call` plus N LLM calls. With a 0.001 cap, expect the block before spend itself reaches 0.001, since the SDK adds a worst-case estimate (maxTokens 200) for the next call.
- 2026-10-09 (6.5 AWS) The live run used a `0.007` cap instead of the `0.001` in tasks.md, so a couple of runs succeed before the block. Both exercise the same path. The block fired with $0.000988 of headroom left, as expected from the worst-case estimate. For the 7.5 rehearsal, size the cap above demo-bot's current rolling 24h spend.
- 2026-10-09 (7.1) Throttling goes in `Globals.HttpApi.DefaultRouteSettings`, not on an explicit API resource. That keeps `ServerlessHttpApi` implicit, so the URL survives. The SAM translator source lists `DefaultRouteSettings` as a supported HttpApi global. A local transform with SAM CLI 1.167.0's translator (no AWS calls) put the settings on `ServerlessHttpApiApiGatewayDefaultStage` with unchanged logical ids. The budget emails `AlertEmail` directly instead of going through SNS, so no topic policy is needed for budgets.amazonaws.com. Tejaswi's deploy confirmed both: the change set and live throttling.

- 2026-10-09 (7.6) `e2e.sh` makes its API calls through an inline Python helper (not curl), so the key is hashed in-process and neither key nor hash ever appears in argv, output, or files. Cleanup runs from an `EXIT` trap, so a mid-run failure still resets both demo agents. Since the cap is spend + 0.003, the block landed on run 5 of 5 this time; if a future run finishes 5 runs without a block, lower the margin.

## Open bugs
- (none known)
