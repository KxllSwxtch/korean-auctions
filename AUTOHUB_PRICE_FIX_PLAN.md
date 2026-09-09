# Autohub detail page: missing price (and lot number)

## Context

Reported: the Autohub catalog card shows a price, but the car detail page shows none —
e.g. `/auctions/autohub/car/01M1NKBJQVJYGXDET38E2CGPGW?perf_id=01M1QRWFVAMAW3V4EBNS73TKZN`.

Verified, and far broader than one car. Live measurements against production:

| Listing position | Lot | Catalog price | Detail price |
|---|---|---|---|
| 0 | 1001 | 2480 | **2480** |
| 1–4 | 1002–1005 | ✓ | **✓** |
| 5, 6, 9, 20, 50, 99 | 1006… | ✓ | **null** |

**~0.3% of the catalogue has a price on its detail page. 99.7% does not.**
The reported Jetta is lot 1497, real `starting_price` 170 manwon (₩1,700,000).

## Root cause

`AutohubService.get_car_detail` (`app/services/autohub_service.py`) recovers the price by
re-fetching the car's auction listing row:

```python
def fetch_entry_listing():
    return self._api_post("/auction/external/rest/api/v1/entry/list/paging",
                          {"tenant": "1", "carId": car_id, "pageSize": 5, "pageIndex": 1})
```

**Upstream ignores `carId`** and returns the first page of the entire 1,843-car sale.
`find_listing_entry` then scans those 5 rows for a match, so the price resolves only for cars
sitting in the first five lots. The cutoff landing exactly at position 5 is `pageSize: 5`.

This is not a regression — it's an unvalidated assumption. `carId` is the **only** payload key in
the codebase not produced by `AutohubSearchRequest.to_api_body()`, and no test or doc covers it.
The same upstream behaviour is already documented for a sibling field
(`app/models/autohub_filters.py`): *"entryNo is NOT a supported filter on the external API's paging
endpoint — it is silently ignored."* Git history shows `body["entryNo"] = self.entry_number` was
added and then deleted for exactly this reason.

### Measured upstream filter support

| Filter | Honored? | Evidence |
|---|---|---|
| `carBrand` | **Yes** | 1843 → 38 results, `total_count` correctly 38 |
| `carYearFrom/To` | **No** | identical rows + `total_count` 1843 vs. baseline |
| `mileageFrom/To` | **No** | identical rows + `total_count` 1843 vs. baseline |
| `entryNo` | No | documented in-repo; removed in git history |
| `carId` | No | this bug |

So attribute-narrowing is not viable: the only honored filter derivable for a single car is brand,
and the detail payload carries no brand ID — it would have to be guessed from the title, which
breaks on multi-word brands ("LAND ROVER", "MERCEDES-BENZ", "ALFA ROMEO").

### Two knock-on findings

1. **This also blocks the lot-number pill** just added to the detail header — it reads the same
   listing row, so it renders only for those same 5 cars. The price fix is a prerequisite.
2. **Production runs live mode only** (`AUTOHUB_SNAPSHOT_ENABLED=false` in `render.yaml`; would be
   Wednesday-only if enabled). The snapshot path resolves `car_id → listing row` correctly via the
   `cars` table's `PRIMARY KEY (snapshot_id, car_id)`, but it is dead code in production. The fix
   must work in live mode.

## Step 0 — rule out the trivial fix first (BLOCKING)

Three places in the code assert the detail endpoint carries no price, **but no captured upstream
sample exists anywhere on disk to confirm it**, and `AutohubApiCarDetail` is documentation only —
`map_car_detail` reads a plain dict, so an unmapped price field would be invisible.

If a price *is* present in the raw payload, the entire fix below is unnecessary and this becomes a
one-line addition to `map_car_detail`.

`probe_raw_detail.py` (repo root) settles it. It needs `AUTOHUB_USERNAME` / `AUTOHUB_PASSWORD` in
`korean-auctions/.env` (see `env.example` lines 35-36) and prints only field names — no
credentials, no PII:

```
cd korean-auctions && source venv/bin/activate && python probe_raw_detail.py
```

It probes a car at position ≥5 (the Jetta) — one the broken call can never reach. **Do not build
anything below until this has run.** Delete the script afterwards.

## The fix — a `car_id → listing row` index, warmed in the background

Since no per-car upstream query exists, the lookup has to be materialised locally. Building it
costs ~19 page fetches (1,843 ÷ 100 per page), so it must not sit on the request path.

### 1. Index structure — `app/services/autohub_service.py`

A dedicated attribute on the service, **not** the shared `_cache`:

```python
self._entry_index: Dict[str, AutohubCar] = {}
self._entry_index_built_at: float = 0.0
self._entry_index_lock = threading.Lock()
```

Why not `_cache`: it is bounded at `_CACHE_MAX_ENTRIES = 512` and `_evict_oldest` drops 51 entries
per trigger, so the index could be evicted at any moment — and it would evict listing pages in
turn. A dedicated attribute makes lifetime explicit. Memory is ~1,843 small objects, well under
1 MB.

### 2. Build function

Paginate via the **existing** `_fetch_car_page` (so it reuses the 600s `car_list` page cache and
respects `_OUTBOUND_LIMIT`), using the scan-parameter idiom already proven in
`_search_by_entry_number`:

```python
scan = params.model_copy()
scan.page_size = 100
scan.sort_order = AutohubSortOrder.ENTRY
scan.sort_direction = "asc"
```

Read `total_pages` from page 1, cap pages at 200 (matching `_search_by_entry_number`'s 20,000-car
sanity bound), and pace with a small sleep like the snapshot job's `_INTER_PAGE_SLEEP_SECS = 0.25`.
Build into a local dict and swap it in atomically under the lock, so readers never see a partial
index.

**On failure, keep the previous index** — a transient upstream error must not blank out every price.

### 3. Warm it on a schedule

Register a job in `app/core/scheduler.py` next to the existing `warm_rates` (hourly) and
`warm_sessions` (20 min) warmers:

- **Interval: 15 minutes.** `entryNo` and `startAmt` are static for the life of a sale; the only
  churn is cars being added as a sale is prepared.
- Also warm shortly after startup (delayed, so it doesn't slow boot).
- **Guard on credentials** being configured, or it will error every interval on a misconfigured env.
- `max_instances=1`, `coalesce=True`, consistent with the existing jobs.

Cost: 19 fetches × 2 gunicorn workers (`start.sh --workers 2`) = 38 per interval, ~150/hour. That is
far less than ordinary catalogue browsing generates.

### 4. Use it in `get_car_detail` — and delete a request

Replace the `fetch_entry_listing` task in the 6-way fanout with an O(1) index lookup:

```python
apply_listing_car(car_detail, self._entry_index.get(car_id))
```

**This removes one of the six upstream calls per detail request**, so the fix makes detail requests
*cheaper*, not more expensive, while going from 0.3% to ~100% price coverage.

`_fetch_car_page` returns mapped `AutohubCar` objects which already carry `car_id`,
`auction_number`, `starting_price`, `hope_price`, `lane`, `parking_number` — so the index needs no
raw dicts.

### 5. Keep one assignment seam — `app/parsers/autohub_parser.py`

There are now two shapes feeding the same three fields: mapped `AutohubCar` (live index) and raw
`raw_listing_json` dict (snapshot path). Keep `apply_listing_fields(detail, entry: dict)` for the
snapshot path, add `apply_listing_car(detail, car: Optional[AutohubCar])` for the live path, and
factor the actual assignment into one private helper so the two cannot drift. Both must no-op on
`None`.

`find_listing_entry` becomes unused once `fetch_entry_listing` is deleted — remove it rather than
leaving a misleading helper that implies upstream filtering works.

### 6. Frontend — never silently hide the price

`app/auctions/autohub/car/[auction_number]/AutohubCarClient.tsx` currently *removes* the whole price
tile when the value is null:

```tsx
const price = formatPrice(carDetail.starting_price)
if (!price) return null      // <- entire orange tile disappears
```

Render a "Not specified" state instead, reusing the **already-defined but unused** key
`autohub.detail.notSpecified`. This mirrors the catalog card, which already degrades properly via
`auctions.card.noPrice`. Ship this regardless of the backend outcome: it converts a silently
missing price into an honest one, and it is the safety net for any car absent from the index.

Note `formatPrice` uses a falsy check, so a genuine `0` is also hidden — use `== null` so a real
zero is distinguishable from missing.

## Out of scope (flagged, not fixed)

- `hope_price` is declared on `AutohubCarDetail` and fetched, but **never rendered** on the detail
  page. Worth a product decision, not part of this fix.
- The manwon `× 10000` conversion is duplicated three times (`AuctionCarCard.tsx`,
  `AutohubCarClient.tsx`, `lib/api/korean-auctions.ts`). Consolidating is a separate cleanup.
- Autohub is the only detail page not using the shared `CarDetailTitle` / `CarDetailLayout`, which
  is why it's the only one that hides rather than shows `₩0`. Not worth restructuring here.
- Enabling snapshot mode would also fix this, but it changes data-freshness semantics globally —
  that's a product decision, not a bug fix.

## Verification

1. **Step 0 probe** — run it first; a money-ish key in the output cancels most of this plan.
2. **Index unit test** — build the index from two synthetic pages, assert lookup by a car on
   page 2 (i.e. beyond the old 5-row window) returns the right lot and price, and that a
   failed page fetch preserves the previously built index.
3. **The regression that matters** — assert detail price for a car at listing position ≥5.
   This is exactly what no existing test covers, and it's the whole bug. Use lot 1497 /
   `01M1NKBJQVJYGXDET38E2CGPGW`, expected `starting_price == 170`.
4. **Snapshot path** — `python tests/e2e_autohub_snapshot.py` must stay green (it now also asserts
   `lot_number == "105"`). Confirms the two paths still agree after refactoring the seam.
5. **Live smoke, post-deploy** — re-run the position sweep (positions 0, 5, 20, 50, 99): every one
   should now return a non-null price matching the catalog's value for the same `car_id`.
6. **The lot pill** — with the index live, confirm `Lot 1497` renders on the reported Jetta, not
   just on the first five lots.
7. **Frontend** — `npm run lint && npx tsc --noEmit`; confirm the "Not specified" tile appears when
   price is null instead of the tile vanishing.
8. **Pre-existing failure, do not chase:** `tests/e2e_autohub_snapshot.py` throws
   `TypeError: fake_live_listings() got an unexpected keyword argument 'bypass_cache'` in its
   live-mode scenario. Confirmed present on a pristine tree (stash-verified) — an out-of-date test
   mock in `get_car_list`, unrelated to this work.
