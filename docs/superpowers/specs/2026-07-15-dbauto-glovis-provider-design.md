# DB Auto Glovis Provider Design

**Date:** 2026-07-15

**Status:** Approved for implementation planning

**Repositories:** `korean-auctions` and `autobazaapp`

## Summary

AutoBaza currently presents Hyundai Glovis inventory sourced from SSANCAR. The
replacement will use the public DB Auto Glovis catalog at
`https://cars.dbauto.kr/en/glovis` and its same-origin JSON API.

The implementation will add a canonical `/api/v1/glovis` backend, migrate the
website to that contract, keep the existing SSANCAR backend temporarily for
compatibility, and route every DB Auto upstream request through a Korean proxy.
The browser will never call DB Auto directly.

## Goals

- Replace SSANCAR as the data source for the production Glovis list and detail
  pages.
- Discover active Glovis auctions dynamically instead of deriving Tuesday and
  Friday week numbers.
- Support exact server pagination for unfiltered and filtered results.
- Support DB Auto's working dependent and advanced filters and its sort orders.
- Render the richer DB Auto detail response, including inspection, insurance,
  accident, option, legal, and document data.
- Preserve content parity with the DB Auto detail page: every meaningful,
  non-null provider field must remain available end to end and be rendered in
  an understandable section.
- Deliver a polished responsive catalog and detail experience from 320-pixel
  mobile screens through large desktop screens.
- Preserve whole KRW as the canonical price unit.
- Keep authentication cookies, fingerprint headers, and API requests on the
  same Korean proxy session.
- Preserve structured loading, empty, unavailable, retryable, and terminal
  frontend states.
- Avoid breaking unknown users of the existing `/api/v1/ssancar` routes during
  the migration.

## Non-goals

- The website will not call `cars.dbauto.kr` from the browser.
- The backend will not fall back to direct, non-Korean egress.
- The backend will not silently fall back to SSANCAR when DB Auto is
  unavailable.
- The task will not delete the complete SSANCAR implementation.
- The task will not locally scrape every DB Auto car detail to emulate filters
  that DB Auto itself does not currently honor.
- The task will not redesign unrelated auction pages or shared visual systems.

## Research Findings

### Existing AutoBaza flow

The active website flow is:

`/auctions/glovis -> /api/v1/ssancar -> SSANCARService -> ssancar.com`

The frontend uses a separately fetched total count, hard-coded auction week
values `2` and `5`, static make/model metadata, and a numeric SSANCAR
`car_no`. Filtered results currently stop after the first page.

The old Glovis utilities and `gn`-based detail branch still exist in
`autobazaapp`, but there is no active `/api/v1/glovis` backend router.

### DB Auto endpoints

The delivered production client and read-only live probes established these
same-origin endpoints:

- `POST /api/auth/token`
- `GET /api/auctions/glovis/auctions?lang=en`
- `GET /api/auctions/glovis/cars`
- `GET /api/auctions/glovis/brands`
- `GET /api/auctions/glovis/models`
- `GET /api/auctions/glovis/submodels`
- `GET /api/auctions/glovis/search-form`
- `GET /api/auctions/glovis/car`

List requests accept `atn`, `acc`, `page`, `page_size`, `lang`, and
`sort_order`. Optional filters include:

- `brand`, `model`, and `submodel`
- `year_from` and `year_to`
- `mileage_from` and `mileage_to`
- `price_from` and `price_to`
- `transmission`, `fuel_type`, and `color`
- repeated `options`
- `insurance_damage`
- repeated `usage_history`
- `accident_history`
- `room`, `lane`, and `bid_status`

The list response contains an exact `total` and an `items` array. A
`page_size` of 100 and larger values were accepted during research, but the
AutoBaza public endpoint will impose a smaller limit to control response size
and upstream cost.

### Authentication lifecycle

DB Auto's production client:

1. Computes a SHA-256 browser fingerprint.
2. Posts `{"fingerprint": "..."}` to `/api/auth/token`.
3. Receives a short-lived `x-api-token` cookie.
4. Adds the same value as the `X-Fingerprint` header on API calls.
5. Refreshes the token every 120 seconds.
6. Refreshes once and retries after an API 401 or 403.

The token endpoint issued a cookie with a 180-second lifetime during research.
An initial catalog document can also issue a longer unbound token, but the
backend integration will follow the explicit production-client token flow.

### Verified filter behavior

Live probes verified that these behaviors affect the returned data:

- auction, brand, model, and submodel
- year and mileage ranges
- fuel, transmission, and color
- room and lane
- usage history, accident history, and insurance damage
- sort order
- page number and page size

The current upstream appeared to ignore `price_from`, `price_to`, repeated
`options`, and arbitrary lot-number parameters. The website will not pretend
those controls work. Price, equipment-option, and lot-number controls will be
visibly disabled with concise upstream-unavailable copy. Price and option
parameters will remain typed and forwardable in the backend contract so they
can be enabled only after a future live contract test proves the upstream
applies them. Lot number will not be forwarded because DB Auto exposes no
corresponding catalog parameter.

### Proxy verification

The repository's configured proxy was verified as Korean egress. A single
`requests.Session` using that proxy successfully fetched the DB Auto catalog
document, retained its token cookie, and fetched the Glovis cars JSON.

## Chosen Approach

### Canonical Glovis provider with temporary compatibility

A new DB Auto-specific backend boundary will be introduced under
`/api/v1/glovis`. The frontend will migrate to this boundary. Existing
`/api/v1/ssancar` routes will remain available but will not be used by the
production Glovis page or its warm-up job.

This approach was selected over:

1. Replacing internals behind the misleading `/api/v1/ssancar` name. That
   minimizes edits but cannot cleanly represent dynamic auctions, DB Auto's
   `gn` identity, submodels, or rich detail data.
2. Calling DB Auto directly from the frontend. That would expose token and
   fingerprint behavior to users, bypass the required Korean proxy, create
   CORS and rate-limit risk, and remove centralized validation and caching.

## Backend Architecture

### Modules

The backend will add focused DB Auto modules:

- `app/models/glovis.py`: public request/response and normalized provider
  models.
- `app/services/glovis_transport.py`: Korean proxy sessions, fingerprint
  token lifecycle, deadlines, failover, and safe diagnostics.
- `app/services/glovis_service.py`: parameter construction, semantic
  validation, caching, and provider operations.
- `app/routes/glovis.py`: FastAPI validation, public response contracts, and
  structured error mapping.

`main.py` will include the new router. The existing SSANCAR router will remain
registered.

### Transport and Korean egress

Every request to `cars.dbauto.kr`, including token acquisition, will use a
configured Korean proxy. There will be no direct candidate.

The transport will:

- obtain candidates from an injectable proxy pool;
- fail closed when no Korean proxy is configured;
- set `Session.trust_env = False`;
- apply the selected proxy to both HTTP and HTTPS;
- retain one fingerprint, cookie jar, and token timestamp per session;
- keep token acquisition and API requests on the same session and proxy;
- refresh a token after 110 seconds, below the production client's 120-second
  refresh interval and the observed 180-second cookie lifetime;
- refresh once and retry on 401 or 403;
- rotate the complete proxy session on proxy authentication failure, rate
  limiting, transport failure, timeout, or retryable 5xx responses;
- use a pool of at most four concurrent sessions so one session's cookie jar is
  never mutated concurrently;
- use separate connect/read timeouts and a 24-second hard wall-clock deadline;
- never log proxy URLs, credentials, fingerprints, cookies, token values, or
  complete sensitive headers.

The normal request headers will include stable browser-compatible
`Accept`, `Accept-Language`, `User-Agent`, `Referer`, and
`X-Fingerprint` values. Browser client-hint headers will not be copied unless
live verification proves they are required.

The upstream language is fixed to `en` so provider field values remain stable;
AutoBaza's existing translation layer owns user-interface labels.

### Semantic validation

HTTP 200 alone is not a valid provider response.

The service will validate:

- JSON content and expected top-level shape;
- auction identifiers and dates;
- list totals, array shape, and required car identity fields;
- exact `gn`, `rc`, `acc`, and `atn` identity on detail responses;
- meaningful detail content such as title plus vehicle, price, or image data;
- option/filter array item shapes;
- HTTPS image URLs and expected scalar types.

The empty placeholder detail that DB Auto returns for an unknown `gn` will be
mapped to a terminal `car_unavailable` response instead of being accepted as a
valid vehicle.

## Public Backend Contract

All routes use the `/api/v1/glovis` prefix.

### Auctions

`GET /auctions`

Returns validated active/upcoming auction records containing:

- `number` as the `atn`;
- `acc`;
- title;
- ISO date.

When the frontend has no valid selected auction, it selects the first returned
auction. The backend does not synthesize week numbers.

### Cars

`GET /cars`

Required or resolved fields:

- `atn` and `acc`;
- one-based `page`;
- `page_size`, default 15 and capped at 60;
- `sort_order`, default `01`.

Working optional filters are forwarded through a strict allowlist. Repeated
filters remain repeated query parameters.

The response contains:

- `success`;
- `total`;
- validated `items`;
- `page`;
- `page_size`;
- exact `has_next_page = page * page_size < total`;
- selected auction identity;
- timestamp.

No second total-count request is required.

### Filter metadata

- `GET /brands?atn=&acc=`
- `GET /models?brand=&atn=&acc=`
- `GET /submodels?brand=&model=&atn=&acc=`
- `GET /filters/options?atn=&acc=`

Brand, model, and submodel items retain DB Auto's `value`, `label`, and live
`count`. The options response normalizes colors, equipment options, lanes,
transmissions, fuels, insurance damage, usage history, accident history, sort
orders, rooms, and bid statuses.

### Car detail

`GET /car-detail?gn=&rc=&acc=&atn=`

The route validates the base64 `gn` and numeric provider identifiers before
performing network work. The normalized response retains:

- `main` identity, specifications, dates, status, and prices;
- properties and performance fields;
- total and summary tables;
- options;
- legal status;
- insurance history and accident records;
- inspection data;
- gallery and inspection images;
- performance and registration-certificate images;
- remarks.

### Health

- `GET /health`: validates token acquisition, auctions, and a one-item list
  through Korean egress.
- `GET /health/detail`: additionally validates one real detail response within
  a shared hard deadline.

Health responses expose only safe egress labels and counts. They never expose
proxy addresses, provider cookies, fingerprints, or sample vehicle secrets.

## Public Data Model

### List identity

A DB Auto car is uniquely keyed by `gn` plus `rc`; `acc` and `atn`
identify the auction context. The frontend deduplication key will be
`${gn}-${rc}`.

List prices are whole KRW. Displacement is cubic centimeters and mileage is
kilometers.

### Detail route encoding

Raw `gn` is standard base64 and is not path safe. Frontend paths will use the
same reversible transformation as DB Auto:

- `+` becomes `-`;
- `/` becomes `_`;
- `=` becomes `~`.

The public detail URL remains:

`/auctions/glovis/car/{encodedGn}?rc={rc}&acc={acc}&atn={atn}`

The frontend decodes the path value only for the same-origin backend request.

## Frontend Design

### Catalog state

`GlovisAuction` will use DB Auto-specific API helpers and types. It will no
longer call SSANCAR list, count, metadata, search, detail-health, or schedule
helpers.

Catalog state will include:

- selected auction `atn` and its `acc`;
- brand, model, and submodel codes;
- verified advanced filters;
- sort order;
- current requested page;
- accumulated deduplicated cars;
- exact total and next-page state;
- loading, empty, retryable unavailable, and terminal states.

Changing the auction or any filter resets the accumulated pages and invalidates
older in-flight generations. Filtered and unfiltered results use the same GET
endpoint and both support Load More.

### URL state

The catalog URL will persist `atn`, brand/model/submodel, verified advanced
filters, and sort order. Page accumulation itself will not be persisted.

Old `week_number=2` or `week_number=5` URLs will be canonicalized to the
first active DB Auto auction when they do not contain a valid `atn`. The old
week parameter will then be removed.

### Filter panel

The visible, enabled controls will include:

- auction;
- make;
- model;
- submodel/generation;
- year range;
- mileage range;
- fuel;
- transmission;
- color;
- usage history;
- accident history;
- insurance damage;
- room;
- lane;
- bid status;
- sort order.

The price, equipment-option, and lot-number controls will be disabled with
concise copy explaining that the upstream auction currently does not apply
those filters. No page-only client filtering will be used because that would
produce incorrect totals and skipped matches.

Dependent selections are reset in order:

- changing auction resets make, model, and submodel;
- changing make resets model and submodel;
- changing model resets submodel.

On desktop, filters remain in a readable sidebar beside the catalog. On mobile
and narrow tablet widths, filters move into an accessible sheet/drawer with
clear Apply, Reset, active-filter count, and close controls. Applying a filter
returns focus to the results heading and never traps the user in the drawer.

### Cards

Cards will render:

- thumbnail;
- brand, model/submodel, and configuration;
- year, mileage, fuel, transmission, and displacement;
- rating;
- lot, lane, and room;
- whole-KRW starting price converted by the existing live currency pipeline.

A missing or zero price is shown as price pending; it does not make an otherwise
valid DB Auto car unclickable.

### Detail page

The existing `rc + acc + atn` detail branch will become the canonical DB Auto
branch. It will use a typed DB Auto detail response rather than the obsolete
legacy Glovis shape.

The page will retain and render every meaningful non-null field exposed by DB
Auto. Known fields will use deliberate translated labels and section placement;
unexpected future keys in `properties`, `performance`, `total_table`,
`summary_table`, or `inspection_record` will be preserved in a supplemental
details section instead of being silently dropped.

The page will render:

- title, auction identity, location, and start price;
- responsive gallery and fullscreen image view;
- lot number, lane, room, plate, VIN, year, mileage, displacement, fuel,
  transmission, color, vehicle type, make, model, submodel, first registration,
  and registration date;
- starting, sold, and hoped-for prices plus auction and absentee-bid times when
  present;
- rating/frame information;
- all product, seating, usage, engine, storage, inspection, lot-position, and
  document-completeness properties;
- every performance result and its remarks/changes;
- all total-table, summary-table, and inspection-record values;
- enabled and unavailable equipment options;
- seizures, mortgages, owner changes, plate changes, rental/commercial history,
  and every special-accident count available from the provider;
- every accident claim with date, status, type, parts, labor, paint, repair, and
  insurance-paid amounts;
- gallery images, inspection images, performance diagram, and registration
  certificate;
- remarks;
- the existing contact and calculator actions where their required fields are
  available.

Technical transport identifiers such as raw `gn` are retained for identity
and diagnostics but are not presented as vehicle facts unless DB Auto itself
labels them for users.

Back navigation preserves the selected `atn` and catalog query state.

### Responsive and visual behavior

The new surfaces will follow the existing AutoBaza visual language while
matching DB Auto's information completeness and hierarchy. They will not be a
pixel-for-pixel clone.

- At 320-479 pixels, the catalog is one column, filters use the mobile drawer,
  gallery controls remain reachable, metadata stacks without clipping, and
  actions use full-width or safely wrapping layouts.
- At 480-767 pixels, cards may expand to two columns only when their minimum
  readable width is preserved.
- At 768-1023 pixels, catalog and detail sections use balanced tablet grids;
  long records remain readable without shrinking text.
- At 1024 pixels and above, the catalog uses a sidebar plus multi-column grid,
  and the detail hero uses a gallery/content split.
- At 1440 pixels and above, content receives a controlled maximum width so
  cards, tables, and text do not become excessively stretched.
- Tables that cannot reflow become contained horizontal scrollers with visible
  context; the document itself must never create horizontal page scrolling.
- Long VINs, Korean text, document descriptions, URLs, and remarks wrap or
  truncate with an accessible full-value affordance.
- Images preserve aspect ratio, reserve layout space, lazy-load non-primary
  media, expose meaningful alt text, and show a stable fallback on failure.
- Skeletons match the final card/detail geometry to minimize layout shift.
- Interactive targets are at least 44 by 44 CSS pixels, work by keyboard, show
  visible focus, and have programmatic labels.
- Color is never the only status indicator, contrast remains readable, and
  reduced-motion preferences disable nonessential motion.

## Caching and Freshness

DB Auto inventory changed materially during the research window, so the current
generic five-minute list cache is too long.

Backend cache targets:

- auctions: 30 seconds;
- cars: 30 seconds;
- brands/models/submodels/search form: 120 seconds;
- details: 300 seconds;
- health: 30 seconds;
- detail health: 300 seconds.

Only semantically validated successes are cached. Empty auction results are
valid and cacheable. Provider failures are not cached. Cache keys include the
complete normalized query and auction identity, and the in-process cache is
bounded to 512 entries with least-recently-used eviction.

The Next.js BFF will use matching path-aware policies:

- cars and auctions: 30-second shared cache with 60-second stale revalidation;
- metadata: 120 seconds;
- detail: 300 seconds;
- health: 30 seconds and detail health: 60 seconds;
- every non-2xx response: `no-store`.

The frontend will introduce `GLOVIS_CONTRACT_VERSION=1` on cacheable requests
so a pre-deploy payload cannot be confused with the new contract.

## Errors and Resilience

The backend will continue the existing structured FastAPI error shape:

`{"detail":{"code":"...","message":"...","retryable":true|false}}`

Expected codes include:

- `upstream_auth`;
- `upstream_invalid_response`;
- `upstream_unavailable`;
- `upstream_timeout`;
- `proxy_unavailable`;
- `invalid_identifier`;
- `car_unavailable`.

Mappings:

- exhausted token/auth failures: 502;
- provider/proxy/rate-limit failures: 502;
- hard deadline: 504;
- no usable Korean proxy: 503;
- invalid public identifiers or query relationships: 422;
- semantically empty/withdrawn detail: 404.

The frontend will:

- retry one browser network failure automatically;
- expose manual retry only for retryable failures;
- never label an upstream failure as an empty auction;
- render empty state only for a validated page-one response with
  `total == 0`;
- retain existing stale-response generation guards.

## Security and Privacy

- No DB Auto tokens, fingerprints, proxy credentials, cookies, or raw
  authentication headers are stored in source, responses, cache keys, or logs.
- Proxy URL configuration remains server-only.
- The new routes build upstream URLs from fixed constants and allowlisted
  scalar parameters; callers cannot choose an upstream host.
- Provider redirects are not followed automatically.
- Response schemas reject malformed identity and unsafe types before caching.
- Existing unused legacy Glovis login settings will be removed because DB Auto
  does not use them.
- The implementation will not copy user-supplied captured token values into
  configuration or fixtures.

## Compatibility and Rollout

1. Deploy the new backend routes first.
2. Verify `/api/v1/glovis/health` and `/health/detail` through configured
   Korean egress.
3. Deploy the frontend with `GLOVIS_CONTRACT_VERSION=1`.
4. Update the internal warm endpoint and cron assertions to use Glovis health,
   not SSANCAR health.
5. Monitor structured provider error codes, latency, token refresh failures,
   and empty-result rates.
6. Keep SSANCAR routes for the first DB Auto deployment release. Their later
   removal is a separate task, and they are never an automatic fallback.

Rollback is a frontend deployment rollback to the prior SSANCAR client. It is
not an automatic runtime source switch.

## Testing Strategy

### Backend

New deterministic tests will cover:

- list, auction, metadata, and detail model validation;
- exact query forwarding and repeated parameters;
- one-based pagination and exact `has_next_page`;
- base64 `gn` validation and semantic missing-detail detection;
- fingerprint token acquisition and freshness;
- same-session/same-proxy cookie and header behavior;
- refresh-and-retry after 401/403;
- proxy-session rotation after retryable failures;
- no direct egress and fail-closed missing-proxy behavior;
- hard deadlines and bounded concurrency;
- cache keys, TTLs, success-only caching, and cache bounds;
- structured FastAPI status/error mappings;
- redaction of tokens, fingerprints, cookies, and proxy credentials.

Existing SSANCAR tests remain green because its compatibility router remains.

An opt-in live smoke test will validate auctions, one list page, and one detail
through the configured Korean proxy without printing sensitive values.

### Frontend

Playwright and unit-level coverage will verify:

- default dynamic auction selection and old-week URL canonicalization;
- auction/make/model/submodel dependency resets;
- advanced filter and sort query forwarding;
- disabled unsupported filters;
- default and filtered Load More without duplicates;
- stale response suppression;
- exact total and empty/unavailable distinction;
- path-safe `gn` navigation;
- rich detail rendering and missing-detail states;
- content parity for every known DB Auto detail section and preservation of
  unexpected supplemental fields;
- structured retry behavior;
- BFF cache TTL and `no-store` rules;
- internal warm-up use of the new health routes;
- responsive behavior at 320x568, 390x844, 768x1024, 1280x800, and 1440x900;
- no document-level horizontal overflow, clipped controls, overlapping content,
  unreadable tables, or inaccessible filter/gallery interactions;
- keyboard focus, labels, reduced motion, image fallback, loading, empty, and
  error-state accessibility;
- screenshot evidence for the catalog, open mobile filters, detail hero,
  accident/history content, and provider documents.

Verification commands:

- backend focused pytest suites, then the existing SSANCAR suites;
- backend snapshot/live smoke with configured provider environment;
- `npm run lint`;
- `npm run build`;
- focused Playwright Glovis, detail, and BFF suites;
- live acceptance against the locally integrated backend where the provider is
  reachable.

The in-app Browser connection was unavailable during research. Rendered
verification will try it again after implementation; if it remains unavailable,
the repository's Playwright workflow will provide DOM, interaction, console,
desktop, and mobile evidence, and the limitation will be reported.

## Acceptance Criteria

1. Production Glovis list, filters, pagination, and detail requests no longer
   call `/api/v1/ssancar`.
2. Every DB Auto token and data request uses Korean proxy egress, with no direct
   fallback.
3. Auction selection comes from DB Auto's auctions endpoint.
4. Brand, model, submodel, verified advanced filters, and sort order work and
   persist in URL state.
5. Filtered and unfiltered results both paginate using the exact provider total.
6. Price, equipment-option, and lot-number filters are not presented as
   functional while DB Auto ignores them.
7. Cards preserve whole-KRW pricing and path-safe DB Auto identity.
8. Detail pages render validated DB Auto data and reject placeholder/withdrawn
   results.
9. Every meaningful non-null DB Auto detail field and every known response
   section is visible; future supplemental keys are retained rather than
   discarded.
10. Catalog and detail pages remain polished, usable, and free of document-level
    horizontal overflow at the specified mobile, tablet, desktop, and large
    desktop viewports.
11. Empty, retryable unavailable, terminal, and loading states remain distinct.
12. Backend focused tests, existing SSANCAR tests, frontend lint/build, and
    focused Playwright E2E pass.
13. No provider token, fingerprint, cookie, or proxy credential is logged or
    committed.
