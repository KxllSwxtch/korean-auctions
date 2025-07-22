"""
Proxy configuration for auction services
"""

import os
from typing import Optional, Dict


def get_proxy_config() -> Optional[Dict[str, str]]:
    """
    Get proxy configuration from environment variables or defaults

    Environment variables:
    - USE_PROXY: Set to 'true' to enable proxy
    - PROXY_HOST: Proxy host and port (e.g., 'geo.iproyal.com:12321')
    - PROXY_AUTH: Proxy authentication (e.g., 'username:password_country-us')

    Returns:
        Dict with 'http' and 'https' proxy URLs, or None if proxy is disabled
    """
    use_proxy = os.getenv("USE_PROXY", "false").lower() == "true"

    if not use_proxy:
        return None

    # Default proxy configuration
    proxy_host = os.getenv("PROXY_HOST", "geo.iproyal.com:12321")
    proxy_auth = os.getenv("PROXY_AUTH", "oGKgjVaIooWADkOR:O8J73QYtjYWgQj4m_country-kz")

    if proxy_host and proxy_auth:
        proxy_url = f"http://{proxy_auth}@{proxy_host}"
        return {"http": proxy_url, "https": proxy_url}

    return None
