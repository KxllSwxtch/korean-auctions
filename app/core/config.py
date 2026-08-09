from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional
import os


class Settings(BaseSettings):
    """Настройки приложения"""

    # Основные настройки
    app_name: str = "AutoBaza Parser API"
    app_version: str = "1.0.0"
    debug: bool = False

    # Comma-separated list of origins allowed to call this API.
    # Replaces the previous allow_origins=["*"] + allow_credentials=True
    # combination, which made Starlette echo *any* Origin back with
    # Access-Control-Allow-Credentials: true — letting any website make
    # credentialed cross-origin calls to every endpoint.
    cors_allowed_origins: str = (
        "https://www.autobaza.vip,https://autobaza.vip,http://localhost:3000"
    )

    # Serve /docs, /redoc and /openapi.json. Off by default: they publish the
    # full route surface, including admin and debug endpoints.
    enable_api_docs: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        """cors_allowed_origins parsed into a list, blanks dropped."""
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    # Настройки для парсинга
    request_timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0

    # Настройки для Autohub
    autohub_base_url: str = "https://www.autohubauction.co.kr"
    autohub_api_base_url: str = "https://api.ahsellcar.co.kr"
    autohub_signin_url: str = "https://api.ahsellcar.co.kr/auth/rest/api/v1/auth/signin"
    autohub_product_id: str = "03db628d-2795-11ef-8342-0e80fc1e2c3f"

    # Учётные данные для Autohub
    autohub_username: Optional[str] = None
    autohub_password: Optional[str] = None
    autohub_jwt_token: Optional[str] = None

    # Настройки для Lotte
    lotte_base_url: str = "https://www.lotteautoauction.net"
    
    # Учётные данные для Lotte
    lotte_username: Optional[str] = None
    lotte_password: Optional[str] = None

    # HappyCar credentials
    happycar_username: Optional[str] = None
    happycar_password: Optional[str] = None

    # KCar credentials are provisioned only through the deployment environment.
    kcar_username: Optional[str] = None
    kcar_password: Optional[str] = None

    # SK Auction credentials. Previously hardcoded in
    # app/services/sk_auction_service.py — moved here so the value is
    # secret-managed and can be rotated without a code change.
    sk_auction_username: Optional[str] = None
    sk_auction_password: Optional[str] = None

    # HeyDealer dealer-account credentials. Previously hardcoded in
    # app/services/heydealer_auth_service.py.
    heydealer_username: Optional[str] = None
    heydealer_password: Optional[str] = None

    # Second Lotte account used by the /api/v2/lotte (enhanced) service.
    # Previously hardcoded in app/services/enhanced_lotte_service.py.
    # Falls back to lotte_username/lotte_password when unset.
    enhanced_lotte_username: Optional[str] = None
    enhanced_lotte_password: Optional[str] = None

    # On-disk store for HeyDealer model/generation mappings.
    # This field was read by app/core/heydealer_data_store.py and
    # app/services/heydealer_sync_service.py but never declared, so importing
    # either module raised AttributeError. The failure was swallowed by
    # heydealer_model_mapper, which made every model_group filter silently
    # return zero cars while still reporting success.
    heydealer_data_dir: str = "cache/heydealer"

    # Dedicated Korean proxy for DB Auto Glovis. Values remain secret-managed;
    # declaring them lets Pydantic accept the same environment used by the
    # fail-closed Glovis transport.
    glovis_proxy_host: Optional[str] = None
    glovis_proxy_username: Optional[str] = None
    glovis_proxy_password: Optional[str] = None
    glovis_proxy_country: Optional[str] = None
    glovis_proxy_egress_label: Optional[str] = None

    # Dedicated Korean residential proxy for HeyDealer (anti-throttle on the
    # single shared dealer account/IP). Values stay secret-managed in the Render
    # dashboard; declaring them lets Pydantic accept the environment. The proxy
    # itself is read via app/core/proxy_config.get_heydealer_proxies() (os.getenv
    # directly) so it is never frozen at import time. Unset -> direct egress.
    heydealer_proxy_host: Optional[str] = None
    heydealer_proxy_port: Optional[str] = None
    heydealer_proxy_username: Optional[str] = None
    heydealer_proxy_password: Optional[str] = None

    # Shared auction proxy for Encar (optional) and HappyCar (required).
    # Values stay secret-managed; declaring them lets Pydantic accept the
    # deployment environment and lets startup validation report which names
    # are missing. app/core/proxy_config.py deliberately keeps reading
    # os.getenv directly — get_settings() is lru_cache'd with a module-level
    # instance built at import, so routing it through Settings would freeze
    # the configuration at import time. These declarations are for validation
    # and reporting only.
    use_proxy: bool = False
    auction_proxy_host: Optional[str] = None
    auction_proxy_username: Optional[str] = None
    auction_proxy_password: Optional[str] = None
    auction_proxy_name: str = "auction-proxy"
    auction_proxy_supports_sticky: bool = False

    # User Agent для запросов
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    # Настройки логирования
    log_level: str = "INFO"
    log_file: str = "logs/app.log"

    # Настройки для cache
    cache_ttl: int = 300  # 5 минут (default, backward compat)
    cache_ttl_static: int = 86400       # 24h - manufacturers, models, generations
    cache_ttl_auction_date: int = 43200  # 12h - auction dates
    cache_ttl_car_list: int = 600        # 10min - car listings
    cache_ttl_car_detail: int = 3600     # 1h - car details
    cache_ttl_filters: int = 7200        # 2h - filter metadata
    cache_ttl_exchange_rate: int = 900   # 15min - exchange rates

    # Autohub Wednesday-snapshot mode
    # Tuesday 22:00 KST snapshots the catalogue; Wednesday serves it without
    # touching api.ahsellcar.co.kr. See plans/wednesday-snapshot-mode.md.
    autohub_snapshot_enabled: bool = False
    # Comma-separated weekday numbers (Mon=0 ... Sun=6) when snapshot mode is active.
    # "2" = Wednesday only. "" disables snapshot mode entirely. "0,1,2,3,4,5,6" = all week.
    autohub_snapshot_days: str = "2"
    autohub_snapshot_db_path: str = "/data/autohub_snapshot.db"
    autohub_snapshot_retention: int = 2  # number of recent snapshots to keep on disk
    autohub_snapshot_timezone: str = "Asia/Seoul"
    autohub_snapshot_max_age_days: int = 8  # snapshots older than this are "stale"
    autohub_snapshot_admin_token: Optional[str] = None  # gate /snapshot/run endpoint
    autohub_snapshot_alert_webhook: Optional[str] = None  # POSTed to on job failure

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Получить настройки приложения (кэшированные)"""
    return Settings()


# Глобальный экземпляр настроек для удобства импорта
settings = get_settings()
