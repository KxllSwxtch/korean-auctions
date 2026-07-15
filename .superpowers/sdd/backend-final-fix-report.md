# Backend final security-fix report

Status: `DONE_WITH_CONCERNS`

Baseline: `bc4d8818a5e0e9c1a7c5f347286b065114d4eda8`

Implementation commit:

- `1888b6a945334ad94d03a3afbbb4254b39cd77b0` — `fix: harden Glovis proxy and cache security`

Evidence-report commit:

- `docs: record backend security fix evidence` — the commit containing this report

## Outcome

- Removed all proxy host, username, and password defaults from tracked proxy
  source. The shared legacy pool now reads `AUCTION_PROXY_HOST`,
  `AUCTION_PROXY_USERNAME`, and `AUCTION_PROXY_PASSWORD` only from the process
  environment. Glovis does not consume that generic pool.
- Added dedicated Glovis configuration through `GLOVIS_PROXY_HOST`,
  `GLOVIS_PROXY_USERNAME`, `GLOVIS_PROXY_PASSWORD`, `GLOVIS_PROXY_COUNTRY`,
  and `GLOVIS_PROXY_EGRESS_LABEL`. Missing or invalid configuration fails
  closed with `proxy_unavailable` before a session is created.
- Made the Glovis proxy invariant explicit. Candidates must normalize to
  `country == "KR"`, use an authenticated `http` or `https` proxy URL with a
  host and port, have a safe normalized `kr-*` egress label, and have a unique
  identity derived without the password. Non-KR, blank, malformed, duplicate,
  address-bearing, and credential-bearing labels are rejected before network
  work.
- Made Glovis service creation lazy and thread-safe. Missing Glovis proxy
  configuration no longer blocks `main.app` import or unrelated providers.
  Glovis requests return the stable `proxy_unavailable` 503 response with
  `Cache-Control: no-store`. A successfully created singleton is still closed
  and discarded during application shutdown.
- Kept the public `/api/v1/cache/clear` behavior for legacy services but
  removed Glovis from it. Added `/api/v1/internal/glovis/cache/clear`, gated by
  the environment-only `GLOVIS_CACHE_ADMIN_TOKEN` and
  `secrets.compare_digest`. Missing and wrong tokens return safe no-store
  responses and are never logged or returned.
- Made only the strictly required shared-pool compatibility edits: Encar's
  pool and HappyCar's service now initialize on first use, so removing the
  tracked shared credential does not break application import.

## TDD evidence

### RED 1: tracked credentials and Korean-only candidate invariants

Command:

```text
venv/bin/python -m pytest tests/test_proxy_config.py tests/test_glovis_transport.py -q
```

Result: exit `1`; `59 failed, 5 passed`.

Expected failures included literal proxy values in `app/core/proxy_config.py`,
the missing environment-only loader/candidate type, and the absence of
country, URL, duplicate-identity, and safe-label validation.

### GREEN 1

Same command after implementation:

```text
64 passed in 0.43s
```

### RED 2: lazy construction and import safety

Command:

```text
venv/bin/python -m pytest tests/test_glovis_routes.py -q
```

Result: exit `2` during collection. Importing `app.routes.glovis` eagerly
constructed `GlovisService` and raised `GlovisProxyUnavailableError` when the
dedicated environment was absent.

An explicit no-proxy `from main import app` smoke also exited `1` at the same
eager Glovis construction point.

### GREEN 2

- The explicit no-proxy `main.app` import exited `0` and printed the app title.
- The route/lifecycle checkpoint passed `39 passed` before cache-auth tests
  were added.
- The missing-config route test proved HTTP 503, code `proxy_unavailable`,
  retryable `true`, and `Cache-Control: no-store`, with no singleton retained.

### RED 3: cache isolation and authorization

Command:

```text
venv/bin/python -m pytest tests/test_glovis_routes.py -q -k 'cache_clear'
```

Result: exit `1`; `5 failed, 40 deselected`.

Expected failures proved that the public endpoint still evicted Glovis, the
internal route did not exist, and a constant-time comparison was not wired.

### GREEN 3

Same command after implementation:

```text
5 passed, 40 deselected in 24.58s
```

The tests cover public non-eviction, unconfigured admin authorization, missing
and wrong tokens, use of `secrets.compare_digest`, and authorized eviction.

## Final verification

Focused proxy/model/transport/service/route suites:

```text
venv/bin/python -m pytest tests/test_proxy_config.py tests/test_glovis_models.py tests/test_glovis_transport.py tests/test_glovis_service.py tests/test_glovis_routes.py -q
205 passed, 30 warnings in 25.07s
```

SSANCAR compatibility:

```text
venv/bin/python -m pytest tests/test_ssancar_routes.py tests/test_ssancar_transport.py -q
48 passed, 5 warnings in 0.56s
```

Full deterministic backend suite:

```text
venv/bin/python -m pytest tests -q
353 passed, 1 skipped, 30 warnings in 25.49s
```

The one skip is the opt-in live Glovis smoke; no live provider request was
made.

Exact OpenAPI smoke:

```text
venv/bin/python -c 'from main import app; paths=app.openapi()["paths"]; required=["/api/v1/glovis/auctions","/api/v1/glovis/cars","/api/v1/glovis/car-detail","/api/v1/glovis/health/detail"]; assert all(p in paths for p in required); print("glovis-openapi-ok")'
glovis-openapi-ok
```

Source/secret verification:

```text
venv/bin/python -m pytest tests/test_proxy_config.py -q
2 passed in 0.02s
strengthened-secret-scan-ok
```

The no-output scan checked the Glovis/proxy source for removed credential
setting names, removed default-entry construction, and literal credentialed
proxy URLs. It exposed no values. `git diff --check` exited `0` with no output.

## Files

- `app/core/proxy_config.py`
- `app/routes/encar_proxy.py`
- `app/routes/glovis.py`
- `app/routes/happycar.py`
- `app/services/glovis_transport.py`
- `main.py`
- `tests/test_proxy_config.py`
- `tests/test_glovis_transport.py`
- `tests/test_glovis_routes.py`
- `.superpowers/sdd/backend-final-fix-report.md`

## Concerns and external actions

- The credential that was previously committed must be revoked and rotated in
  the remote proxy provider, then supplied through the deployment secret
  manager. Remote rotation is outside repository authority and was not
  attempted. Repository cleanup alone does not invalidate the exposed value
  in Git history.
- Deployments must provision all five dedicated Glovis proxy variables plus
  `GLOVIS_CACHE_ADMIN_TOKEN`. Legacy shared-pool users additionally need the
  three `AUCTION_PROXY_*` credential variables. With missing Glovis values,
  only Glovis fails closed; application import remains available.
- The live Glovis smoke remained intentionally disabled, so this pass does not
  claim current provider reachability or credential validity.
- Existing non-Glovis `main.app` import side effects still attempt Autohub and
  KCar authentication and emitted DNS failures in the restricted environment.
  They did not affect import or OpenAPI success and were outside this focused
  pass.
- The full suite retains 30 pre-existing warnings: Pydantic configuration
  deprecations and FastAPI `regex`/`example` deprecations.
