from pydantic_settings import BaseSettings
from functools import lru_cache
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
    autohub_list_url: str = (
        "https://www.autohubauction.co.kr/newfront/receive/rc/receive_rc_list.do"
    )
    autohub_login_url: str = (
        "https://www.autohubauction.co.kr/newfront/user/login/user_login_ajax.do"
    )

    # Учётные данные для Autohub
    autohub_username: str = "837301"
    autohub_password: str = "782312"

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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Получить настройки приложения (кэшированные)"""
    return Settings()


# Глобальный экземпляр настроек для удобства импорта
settings = get_settings()
