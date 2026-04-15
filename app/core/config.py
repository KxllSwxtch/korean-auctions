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
    autohub_username: str = "837301"
    autohub_password: str = "782312"
    autohub_jwt_token: Optional[str] = None

    # Настройки для Glovis
    glovis_base_url: str = "https://auction.autobell.co.kr"
    glovis_list_url: str = (
        "https://auction.autobell.co.kr/auction/exhibitListInclude.do"
    )
    glovis_main_url: str = "https://auction.autobell.co.kr/auction/exhibitList.do"

    # Учётные данные для Glovis
    glovis_username: str = "7552"
    glovis_password: str = "for7721@"

    # Настройки для Lotte
    lotte_base_url: str = "https://www.lotteautoauction.net"
    
    # Учётные данные для Lotte
    lotte_username: str = "119102"
    lotte_password: str = "for1234@"

    # HappyCar credentials
    happycar_username: str = "uztrade"
    happycar_password: str = "u112358@"

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
    cache_ttl_car_list: int = 180        # 3min - car listings
    cache_ttl_car_detail: int = 1800     # 30min - car details
    cache_ttl_filters: int = 3600        # 1h - filter metadata
    cache_ttl_exchange_rate: int = 1800  # 30min - exchange rates

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Получить настройки приложения (кэшированные)"""
    return Settings()


# Глобальный экземпляр настроек для удобства импорта
settings = get_settings()
