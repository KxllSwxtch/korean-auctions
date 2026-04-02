"""
Background sync service for HeyDealer auction data.

Periodically fetches all HeyDealer data and stores it locally.
This eliminates the need for live API calls on every user request,
solving the session conflict where the scraper's login kicks out
the human user from dealer.heydealer.com.
"""

import os
import time
import json
import requests
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

from app.core.config import get_settings
from app.core.heydealer_data_store import heydealer_data_store
from app.services.heydealer_auth_service import heydealer_auth
from app.parsers.heydealer_parser import HeyDealerParser

logger = logging.getLogger(__name__)
settings = get_settings()

HEYDEALER_API_BASE = "https://api.heydealer.com/v2/dealers/web"


class HeyDealerSyncService:
    """Orchestrates periodic background sync of HeyDealer auction data."""

    def __init__(self):
        self.parser = HeyDealerParser()
        self.lock_file = os.path.join(settings.heydealer_data_dir, ".sync_lock")
        self._delay_page = settings.heydealer_sync_request_delay_ms / 1000.0 * 0.4
        self._delay_detail = settings.heydealer_sync_request_delay_ms / 1000.0
        os.makedirs(settings.heydealer_data_dir, exist_ok=True)

    def _acquire_lock(self) -> bool:
        """Acquire file-based lock atomically. Returns False if another worker is syncing."""
        try:
            # Check for stale lock first
            if os.path.exists(self.lock_file):
                try:
                    with open(self.lock_file, "r") as f:
                        lock_data = json.load(f)
                    lock_time = datetime.fromisoformat(lock_data.get("locked_at", ""))
                    if (datetime.now() - lock_time).total_seconds() < 600:
                        logger.info("Sync lock held by another process, skipping")
                        return False
                    logger.warning("Stale lock detected, overriding")
                    os.unlink(self.lock_file)
                except (json.JSONDecodeError, ValueError):
                    os.unlink(self.lock_file)

            # Atomic create — O_EXCL fails if file already exists
            fd = os.open(self.lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w") as f:
                json.dump(
                    {"pid": os.getpid(), "locked_at": datetime.now().isoformat()}, f
                )
            return True
        except FileExistsError:
            logger.info("Sync lock acquired by another process (race), skipping")
            return False
        except Exception as e:
            logger.error(f"Error acquiring lock: {e}")
            return False

    def _release_lock(self) -> None:
        """Release the file-based lock."""
        try:
            if os.path.exists(self.lock_file):
                os.unlink(self.lock_file)
        except Exception as e:
            logger.error(f"Error releasing lock: {e}")

    def _get_session(self) -> Tuple[Optional[Dict], Optional[Dict]]:
        """Get valid session cookies and headers via fresh login."""
        session_data = heydealer_auth.login()
        if session_data:
            return session_data.get("cookies"), session_data.get("headers")
        return None, None

    # Sentinel to distinguish auth errors from other failures
    AUTH_ERROR = "AUTH_ERROR"

    def _fetch_json(
        self,
        url: str,
        cookies: Dict,
        headers: Dict,
        params: Optional[Dict] = None,
        timeout: int = 30,
    ) -> Any:
        """Make a GET request. Returns parsed JSON, AUTH_ERROR for 401/403, or None for other failures."""
        try:
            resp = requests.get(
                url, params=params, cookies=cookies, headers=headers, timeout=timeout
            )
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code in (401, 403):
                logger.warning(f"Auth error {resp.status_code} for {url}")
                return self.AUTH_ERROR
            else:
                logger.error(f"HTTP {resp.status_code} for {url}")
                return None
        except requests.RequestException as e:
            logger.error(f"Request failed for {url}: {e}")
            return None

    def _fetch_all_car_pages(
        self, cookies: Dict, headers: Dict
    ) -> Tuple[List[Dict], int]:
        """Fetch all pages of car listings. Returns (all_cars, total_pages)."""
        all_cars = []
        page = 1
        total_pages = 0
        auth_retries = 0

        while True:
            params = {
                "page": page,
                "type": "auction",
                "is_subscribed": "false",
                "is_retried": "false",
                "is_previously_bid": "false",
                "order": "recent",
            }

            resp = requests.get(
                f"{HEYDEALER_API_BASE}/cars/",
                params=params,
                cookies=cookies,
                headers=headers,
                timeout=30,
            )

            if resp.status_code in (401, 403):
                auth_retries += 1
                if auth_retries > 3:
                    logger.error("Too many auth failures during page fetch, aborting")
                    break
                logger.warning(f"Auth expired at page {page}, re-authenticating (attempt {auth_retries}/3)...")
                cookies, headers = self._get_session()
                if not cookies:
                    logger.error("Re-authentication failed during page fetch")
                    break
                continue

            if resp.status_code != 200:
                logger.error(f"Failed to fetch page {page}: {resp.status_code}")
                break

            cars = resp.json()
            if not cars or not isinstance(cars, list) or len(cars) == 0:
                break

            all_cars.extend(cars)
            total_pages = page
            logger.info(f"Fetched page {page}: {len(cars)} cars")

            # Check pagination headers for next page
            link_header = resp.headers.get("Link", "")
            if 'rel="next"' not in link_header:
                break

            page += 1
            time.sleep(self._delay_page)

        return all_cars, total_pages

    def _fetch_car_details(
        self, cars: List[Dict], cookies: Dict, headers: Dict
    ) -> Tuple[int, int]:
        """Fetch and store detail + accident data for each car."""
        fetched = 0
        failed = 0
        consecutive_failures = 0
        max_reauths = 3

        for i, car in enumerate(cars):
            hash_id = car.get("hash_id")
            if not hash_id:
                failed += 1
                continue

            # Fetch car detail
            detail = self._fetch_json(
                f"{HEYDEALER_API_BASE}/cars/{hash_id}/",
                cookies=cookies,
                headers=headers,
            )

            # Only re-authenticate on auth errors (401/403), not on timeouts/500s
            if detail is self.AUTH_ERROR and consecutive_failures < max_reauths:
                logger.warning(f"Auth error fetching detail, trying re-auth (attempt {consecutive_failures + 1}/{max_reauths})...")
                new_cookies, new_headers = self._get_session()
                if new_cookies:
                    cookies, headers = new_cookies, new_headers
                    detail = self._fetch_json(
                        f"{HEYDEALER_API_BASE}/cars/{hash_id}/",
                        cookies=cookies,
                        headers=headers,
                    )

            # Treat AUTH_ERROR as None for downstream logic
            if detail is self.AUTH_ERROR:
                detail = None

            if detail:
                heydealer_data_store.save_car_detail(hash_id, detail)
                fetched += 1
                consecutive_failures = 0
            else:
                failed += 1
                consecutive_failures += 1
                if consecutive_failures >= 10:
                    logger.error(f"Too many consecutive failures ({consecutive_failures}), aborting detail fetch")
                    break
                time.sleep(self._delay_detail)
                continue

            # Fetch accident repairs
            accident = self._fetch_json(
                f"{HEYDEALER_API_BASE}/accident_repairs_for_auction/",
                cookies=cookies,
                headers=headers,
                params={"car": hash_id},
            )
            if accident and accident is not self.AUTH_ERROR:
                heydealer_data_store.save_accident_repairs(hash_id, accident)

            if (i + 1) % 20 == 0:
                logger.info(f"Progress: {i + 1}/{len(cars)} cars processed")

            time.sleep(self._delay_detail)

        return fetched, failed

    def _fetch_filter_metadata(self, cookies: Dict, headers: Dict) -> None:
        """Fetch and store all filter metadata (brands, models, generations, configs)."""
        base_params = {
            "type": "auction",
            "is_subscribed": "false",
            "is_retried": "false",
            "is_previously_bid": "false",
        }

        # Fetch brands
        brands_data = self._fetch_json(
            f"{HEYDEALER_API_BASE}/car_meta/brands/",
            cookies=cookies,
            headers=headers,
            params=base_params,
        )
        if brands_data and brands_data is not self.AUTH_ERROR:
            heydealer_data_store.save_brands(brands_data)
            logger.info(f"Saved {len(brands_data) if isinstance(brands_data, list) else '?'} brands")

            # Fetch models for each brand
            brand_list = brands_data if isinstance(brands_data, list) else []
            for brand in brand_list:
                brand_id = brand.get("hash_id")
                if not brand_id:
                    continue

                brand_models = self._fetch_json(
                    f"{HEYDEALER_API_BASE}/car_meta/brands/{brand_id}/",
                    cookies=cookies,
                    headers=headers,
                    params=base_params,
                )
                if brand_models and brand_models is not self.AUTH_ERROR:
                    heydealer_data_store.save_brand_models(brand_id, brand_models)

                    # Fetch generations for each model group
                    model_groups = brand_models.get("model_groups", [])
                    if isinstance(brand_models, list):
                        model_groups = brand_models
                    for mg in model_groups:
                        mg_id = mg.get("hash_id")
                        if not mg_id:
                            continue

                        generations = self._fetch_json(
                            f"{HEYDEALER_API_BASE}/car_meta/model_groups/{mg_id}/",
                            cookies=cookies,
                            headers=headers,
                            params={**base_params, "model_group": mg_id},
                        )
                        if generations and generations is not self.AUTH_ERROR:
                            heydealer_data_store.save_model_generations(
                                mg_id, generations
                            )

                            # Fetch configurations for each model/generation
                            models_list = generations.get("models", [])
                            if isinstance(generations, list):
                                models_list = generations
                            for model in models_list:
                                model_id = model.get("hash_id")
                                if not model_id:
                                    continue

                                configs = self._fetch_json(
                                    f"{HEYDEALER_API_BASE}/car_meta/models/{model_id}/",
                                    cookies=cookies,
                                    headers=headers,
                                    params={**base_params, "model": model_id},
                                )
                                if configs and configs is not self.AUTH_ERROR:
                                    heydealer_data_store.save_model_configurations(
                                        model_id, configs
                                    )

                                time.sleep(self._delay_page)
                        time.sleep(self._delay_page)
                time.sleep(self._delay_page)

        # Fetch auction filter options
        filters_data = self._fetch_json(
            f"{HEYDEALER_API_BASE}/auction_filter/",
            cookies=cookies,
            headers=headers,
        )
        if filters_data and filters_data is not self.AUTH_ERROR:
            heydealer_data_store.save_filters(filters_data)
            logger.info("Saved filter options")

    def run_sync(self) -> None:
        """Main sync entry point. Called by APScheduler."""
        if not self._acquire_lock():
            return

        start_time = time.time()
        sync_status = "completed"
        total_cars = 0
        total_pages = 0
        details_fetched = 0
        details_failed = 0

        try:
            logger.info("=" * 60)
            logger.info("Starting HeyDealer background sync...")
            logger.info("=" * 60)

            # Step 1: Login
            cookies, headers = self._get_session()
            if not cookies or not headers:
                logger.error("Failed to authenticate for sync")
                sync_status = "failed"
                heydealer_data_store.save_sync_metadata(
                    {
                        "last_sync_at": datetime.now().isoformat(),
                        "status": "failed",
                        "error": "Authentication failed",
                        "total_cars": 0,
                        "sync_duration_seconds": int(time.time() - start_time),
                    }
                )
                return

            # Step 2: Fetch all car listing pages
            logger.info("Fetching all car listing pages...")
            all_cars_raw, total_pages = self._fetch_all_car_pages(cookies, headers)
            total_cars = len(all_cars_raw)
            logger.info(
                f"Fetched {total_cars} cars across {total_pages} pages"
            )

            if total_cars == 0:
                logger.warning("No cars fetched, sync may have failed")
                sync_status = "empty"

            # Save raw car data (all endpoints read from this)
            heydealer_data_store.save_cars_raw(all_cars_raw)

            # Step 3: Fetch details and accident data for each car
            logger.info("Fetching car details and accident data...")
            details_fetched, details_failed = self._fetch_car_details(
                all_cars_raw, cookies, headers
            )
            logger.info(
                f"Details: {details_fetched} fetched, {details_failed} failed"
            )

            if details_failed > 0 and details_failed > details_fetched:
                sync_status = "partial"

            # Step 4: Fetch filter metadata
            logger.info("Fetching filter metadata...")
            self._fetch_filter_metadata(cookies, headers)

            # Step 5: Cleanup stale detail files
            active_ids = {
                car.get("hash_id") for car in all_cars_raw if car.get("hash_id")
            }
            heydealer_data_store.cleanup_stale_details(active_ids)

            # Step 6: Reload in-memory index
            heydealer_data_store.reload_index()

        except Exception as e:
            logger.error(f"Sync failed with exception: {e}")
            sync_status = "failed"

        finally:
            duration = int(time.time() - start_time)
            metadata = {
                "last_sync_at": datetime.now().isoformat(),
                "status": sync_status,
                "total_cars": total_cars,
                "total_pages": total_pages,
                "details_fetched": details_fetched,
                "details_failed": details_failed,
                "sync_duration_seconds": duration,
                "next_sync_at": (
                    datetime.now()
                    + timedelta(minutes=settings.heydealer_sync_interval_minutes)
                ).isoformat(),
            }
            heydealer_data_store.save_sync_metadata(metadata)
            self._release_lock()
            logger.info(
                f"Sync {sync_status} in {duration}s: {total_cars} cars, "
                f"{details_fetched} details, {details_failed} failures"
            )
            logger.info("=" * 60)

    def run_sync_if_stale(self) -> None:
        """Run sync if data is missing or older than the configured interval."""
        if not settings.heydealer_sync_on_startup:
            logger.info("Startup sync disabled by config")
            return

        age = heydealer_data_store.get_data_age_seconds()
        interval_seconds = settings.heydealer_sync_interval_minutes * 60

        if age > interval_seconds:
            logger.info(
                f"Data is {age}s old (max {interval_seconds}s), triggering sync..."
            )
            self.run_sync()
        else:
            logger.info(f"Data is fresh ({age}s old), skipping startup sync")
