"""
Service to map model_group to generation IDs for HeyDealer filtering
"""

import logging
import requests
from typing import List, Optional
from app.services.heydealer_auth_service import heydealer_auth

logger = logging.getLogger(__name__)


class HeyDealerModelMapper:
    """Maps model groups to generation IDs for proper filtering"""
    
    @staticmethod
    def get_generation_ids_for_model_group(model_group_hash_id: str) -> List[str]:
        """
        Get all generation (model) IDs for a given model group
        
        Args:
            model_group_hash_id: The model group hash ID (e.g., "lMgGzM" for Mohave)
            
        Returns:
            List of generation hash IDs that belong to this model group
        """
        try:
            # Get session
            cookies, headers = heydealer_auth.get_valid_session()
            
            if not cookies or not headers:
                logger.error("Failed to get HeyDealer session for model mapping")
                return []
            
            # Fetch model group details
            params = {
                "type": "auction",
                "is_subscribed": "false",
                "is_retried": "false", 
                "is_previously_bid": "false",
                "model_group": model_group_hash_id,
            }
            
            response = requests.get(
                f"https://api.heydealer.com/v2/dealers/web/car_meta/model_groups/{model_group_hash_id}/",
                params=params,
                headers=headers,
                cookies=cookies,
                timeout=10,
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch model group details: {response.status_code}")
                return []
            
            data = response.json()
            models = data.get("models", [])
            
            # Extract generation IDs
            generation_ids = [model.get("hash_id") for model in models if model.get("hash_id")]
            
            logger.info(f"Found {len(generation_ids)} generations for model_group {model_group_hash_id}: {generation_ids}")
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