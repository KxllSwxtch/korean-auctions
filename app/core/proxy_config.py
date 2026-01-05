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
    - PROXY_HOST: Proxy host and port (default: 'pr.oxylabs.io:7777')
    - PROXY_AUTH: Proxy authentication (default: Oxylabs credentials)

    Returns:
        Dict with 'http' and 'https' proxy URLs, or None if proxy is disabled
    """
    use_proxy = os.getenv("USE_PROXY", "false").lower() == "true"

    if not use_proxy:
        return None

    # Default proxy configuration (Oxylabs - Korean targeting)
    proxy_host = os.getenv("PROXY_HOST", "pr.oxylabs.io:7777")
    proxy_auth = os.getenv("PROXY_AUTH", "customer-arman_zVdZn-cc-kr:~eEYPgwRzO+I2")

    if proxy_host and proxy_auth:
        proxy_url = f"http://{proxy_auth}@{proxy_host}"
        return {"http": proxy_url, "https": proxy_url}

    return None
