"""
Persistent file-based data store for HeyDealer auction data.

Stores all HeyDealer data as JSON files in cache/heydealer/ directory.
Used by the background sync service (writer) and route handlers (reader).
"""

import json
import os
import tempfile
import threading
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


class HeyDealerDataStore:
    """File-based data store for HeyDealer auction data with in-memory index."""

    def __init__(self):
        self.data_dir = settings.heydealer_data_dir
        self._write_lock = threading.Lock()
        self._cars_cache: List[Dict[str, Any]] = []
        self._cars_raw: List[Dict[str, Any]] = []
        os.makedirs(self.data_dir, exist_ok=True)
        self._load_cars_index()

    def _file_path(self, filename: str) -> str:
        return os.path.join(self.data_dir, filename)

    def _atomic_write(self, filename: str, data: Any) -> None:
        """Write JSON data atomically using temp file + rename."""
        filepath = self._file_path(filename)
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=self.data_dir, suffix=".tmp", prefix=".write_"
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, default=str)
            os.replace(tmp_path, filepath)
        except Exception as e:
            logger.error(f"Error writing {filename}: {e}")
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def _read_file(self, filename: str) -> Optional[Any]:
        """Read JSON data from a file. Returns None if file doesn't exist."""
        filepath = self._file_path(filename)
        try:
            if not os.path.exists(filepath):
                return None
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading {filename}: {e}")
            return None

    def _load_cars_index(self) -> None:
        """Load all cars into memory for fast filtering/pagination."""
        cars = self._read_file("all_cars.json")
        if cars and isinstance(cars, list):
            self._cars_cache = cars
            logger.info(f"Loaded {len(cars)} cars into memory index")
        raw = self._read_file("all_cars_raw.json")
        if raw and isinstance(raw, list):
            self._cars_raw = raw
            logger.info(f"Loaded {len(raw)} raw cars into memory")

    # ========== WRITE METHODS (used by sync service) ==========

    def save_cars(self, cars: List[Dict[str, Any]]) -> None:
        """Save all normalized car listings."""
        with self._write_lock:
            self._atomic_write("all_cars.json", cars)
            self._cars_cache = cars
            logger.info(f"Saved {len(cars)} normalized cars to store")

    def save_cars_raw(self, cars_raw: List[Dict[str, Any]]) -> None:
        """Save all raw API car listings (for endpoints that need raw data)."""
        with self._write_lock:
            self._atomic_write("all_cars_raw.json", cars_raw)
            self._cars_raw = cars_raw
            logger.info(f"Saved {len(cars_raw)} raw cars to store")

    def save_car_detail(self, hash_id: str, data: Dict[str, Any]) -> None:
        """Save a single car's detail response."""
        with self._write_lock:
            self._atomic_write(f"car_detail_{hash_id}.json", data)

    def save_accident_repairs(self, hash_id: str, data: Any) -> None:
        """Save accident repairs data for a car."""
        with self._write_lock:
            self._atomic_write(f"accident_{hash_id}.json", data)

    def save_brands(self, data: Any) -> None:
        """Save all brands metadata."""
        with self._write_lock:
            self._atomic_write("brands.json", data)

    def save_brand_models(self, brand_hash_id: str, data: Any) -> None:
        """Save models for a specific brand."""
        with self._write_lock:
            self._atomic_write(f"brand_{brand_hash_id}.json", data)

    def save_model_generations(self, model_group_hash_id: str, data: Any) -> None:
        """Save generations for a model group."""
        with self._write_lock:
            self._atomic_write(f"model_group_{model_group_hash_id}.json", data)

    def save_model_configurations(self, model_hash_id: str, data: Any) -> None:
        """Save configurations (grades) for a model."""
        with self._write_lock:
            self._atomic_write(f"model_{model_hash_id}.json", data)

    def save_filters(self, data: Any) -> None:
        """Save available filter options."""
        with self._write_lock:
            self._atomic_write("filters.json", data)

    def save_sync_metadata(self, metadata: Dict[str, Any]) -> None:
        """Save sync status metadata."""
        with self._write_lock:
            self._atomic_write("sync_metadata.json", metadata)

    # ========== READ METHODS (used by route handlers) ==========

    def get_cars_raw(self) -> List[Dict[str, Any]]:
        """Get all raw API car data."""
        return list(self._cars_raw)

    def get_cars_normalized(self) -> List[Dict[str, Any]]:
        """Get all normalized car data."""
        return list(self._cars_cache)

    def get_car_detail(self, hash_id: str) -> Optional[Dict[str, Any]]:
        """Get a single car's detail data."""
        return self._read_file(f"car_detail_{hash_id}.json")

    def get_accident_repairs(self, hash_id: str) -> Optional[Any]:
        """Get accident repairs data for a car."""
        return self._read_file(f"accident_{hash_id}.json")

    def get_brands(self) -> Optional[Any]:
        """Get all brands metadata."""
        return self._read_file("brands.json")

    def get_brand_models(self, brand_hash_id: str) -> Optional[Any]:
        """Get models for a specific brand."""
        return self._read_file(f"brand_{brand_hash_id}.json")

    def get_model_generations(self, model_group_hash_id: str) -> Optional[Any]:
        """Get generations for a model group."""
        return self._read_file(f"model_group_{model_group_hash_id}.json")

    def get_model_configurations(self, model_hash_id: str) -> Optional[Any]:
        """Get configurations for a model."""
        return self._read_file(f"model_{model_hash_id}.json")

    def get_filters(self) -> Optional[Any]:
        """Get available filter options."""
        return self._read_file("filters.json")

    def get_sync_metadata(self) -> Dict[str, Any]:
        """Get sync status metadata."""
        data = self._read_file("sync_metadata.json")
        if data:
            return data
        return {
            "last_sync_at": None,
            "status": "never_synced",
            "total_cars": 0,
            "total_pages": 0,
            "details_fetched": 0,
            "details_failed": 0,
            "sync_duration_seconds": 0,
        }

    def is_data_available(self) -> bool:
        """Check if the store has car data."""
        return len(self._cars_raw) > 0

    def get_data_age_seconds(self) -> int:
        """How many seconds since the last successful sync."""
        meta = self.get_sync_metadata()
        last_sync = meta.get("last_sync_at")
        if not last_sync:
            return 999999
        try:
            sync_time = datetime.fromisoformat(last_sync)
            return int((datetime.now() - sync_time).total_seconds())
        except Exception:
            return 999999

    def reload_index(self) -> None:
        """Reload the in-memory index from disk (called after sync)."""
        self._load_cars_index()

    def cleanup_stale_details(self, active_hash_ids: set) -> int:
        """Remove detail/accident files for cars no longer in listings."""
        removed = 0
        try:
            for filename in os.listdir(self.data_dir):
                if filename.startswith("car_detail_") and filename.endswith(".json"):
                    hash_id = filename[len("car_detail_"):-len(".json")]
                    if hash_id not in active_hash_ids:
                        os.unlink(self._file_path(filename))
                        removed += 1
                elif filename.startswith("accident_") and filename.endswith(".json"):
                    hash_id = filename[len("accident_"):-len(".json")]
                    if hash_id not in active_hash_ids:
                        os.unlink(self._file_path(filename))
                        removed += 1
            if removed:
                logger.info(f"Cleaned up {removed} stale detail/accident files")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
        return removed


# Global singleton
heydealer_data_store = HeyDealerDataStore()
