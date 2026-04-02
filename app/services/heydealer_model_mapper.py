"""
Service to map model_group to generation IDs for HeyDealer filtering.
Reads from local data store instead of live API to avoid session conflicts.
"""

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class HeyDealerModelMapper:
    """Maps model groups to generation IDs for proper filtering"""

    @staticmethod
    def get_generation_ids_for_model_group(model_group_hash_id: str) -> List[str]:
        """
        Get all generation (model) IDs for a given model group.
        Reads from local data store (populated by background sync).

        Args:
            model_group_hash_id: The model group hash ID (e.g., "lMgGzM" for Mohave)

        Returns:
            List of generation hash IDs that belong to this model group
        """
        try:
            from app.core.heydealer_data_store import heydealer_data_store

            data = heydealer_data_store.get_model_generations(model_group_hash_id)

            if not data:
                logger.warning(f"No data found for model group {model_group_hash_id} in data store")
                return []

            models = data.get("models", [])

            if not models:
                logger.warning(f"No models found in model group {model_group_hash_id}")
                return []

            generation_ids = [model.get("hash_id") for model in models if model.get("hash_id")]

            logger.info(f"Model group {model_group_hash_id} expanded to {len(generation_ids)} generations: {generation_ids}")
            return generation_ids
            
        except Exception as e:
            logger.error(f"Error mapping model group to generations: {e}")
            return []
    
    @staticmethod
    def should_use_model_mapping(model_group: Optional[str], model: Optional[str]) -> bool:
        """
        Determine if we should use model mapping workaround
        
        Args:
            model_group: Model group parameter from request
            model: Model (generation) parameter from request
            
        Returns:
            True if we should map model_group to generation IDs
        """
        # Use mapping if model_group is provided but model is not
        return bool(model_group and not model)