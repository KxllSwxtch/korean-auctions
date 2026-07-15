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

    # Dedicated Korean proxy for DB Auto Glovis. Values remain secret-managed;
    # declaring them lets Pydantic accept the same environment used by the
    # fail-closed Glovis transport.
    glovis_proxy_host: Optional[str] = None
    glovis_proxy_username: Optional[str] = None
    glovis_proxy_password: Optional[str] = None
    glovis_proxy_country: Optional[str] = None
    glovis_proxy_egress_label: Optional[str] = None

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
