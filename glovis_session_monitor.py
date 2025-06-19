#!/usr/bin/env python3
"""
Мониторинг сессии Glovis с автоматическим уведомлением о необходимости обновления
Проверяет состояние сессии и уведомляет когда нужно обновить cookies
"""

import time
import requests
import json
import sys
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import argparse
import signal


class GlovisSessionMonitor:
    """Мониторинг сессии Glovis"""
    
    def __init__(self, api_url: str = "http://localhost:8000", check_interval: int = 300):
        self.api_url = api_url
        self.check_interval = check_interval  # секунды между проверками
        self.running = False
        self.last_status = None
        self.consecutive_failures = 0
        self.max_failures = 3
        
    def check_session_status(self) -> Dict[str, Any]:
        """
        Проверяет статус сессии Glovis
        
        Returns:
            Dict с информацией о статусе сессии
        """
        try:
            # Проверяем доступность API
            response = requests.get(f"{self.api_url}/health", timeout=10)
            if response.status_code != 200:
                return {
                    "status": "api_unavailable",
                    "message": f"API недоступно (HTTP {response.status_code})",
                    "timestamp": datetime.now().isoformat(),
                    "healthy": False
                }
            
            # Проверяем сессию Glovis
            response = requests.get(f"{self.api_url}/api/v1/glovis/check-session", timeout=15)
            if response.status_code != 200:
                return {
                    "status": "check_failed",
                    "message": f"Ошибка проверки сессии (HTTP {response.status_code})",
                    "timestamp": datetime.now().isoformat(),
                    "healthy": False
                }
            
            session_data = response.json().get("data", {})
            is_valid = session_data.get("is_valid", False)
            issues = session_data.get("issues", [])
            
            # Тестируем получение автомобилей
            car_test_result = self.test_car_list()
            
            return {
                "status": "valid" if is_valid and car_test_result["success"] else "invalid",
                "session_valid": is_valid,
                "car_list_working": car_test_result["success"],
                "cars_count": car_test_result.get("cars_count", 0),
                "issues": issues,
                "session_info": session_data.get("cookies_info", {}),
                "timestamp": datetime.now().isoformat(),
                "healthy": is_valid and car_test_result["success"],
                "message": (
                    "Сессия работает корректно" 
                    if is_valid and car_test_result["success"]
                    else f"Проблемы: {', '.join(issues) if issues else 'Неизвестная ошибка'}"
                )
            }
            
        except requests.RequestException as e:
            return {
                "status": "connection_error",
                "message": f"Ошибка соединения: {str(e)}",
                "timestamp": datetime.now().isoformat(),
                "healthy": False
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Ошибка мониторинга: {str(e)}",
                "timestamp": datetime.now().isoformat(),
                "healthy": False
            }
    
    def test_car_list(self) -> Dict[str, Any]:
        """
        Тестирует получение списка автомобилей
        
        Returns:
            Dict с результатом теста
        """
        try:
            response = requests.get(f"{self.api_url}/api/v1/glovis/cars?page=1", timeout=20)
            if response.status_code == 200:
                result = response.json()
                return {
                    "success": result.get("success", False),
                    "cars_count": len(result.get("cars", [])) if result.get("success") else 0,
                    "message": result.get("message", "")
                }
            else:
                return {
                    "success": False,
                    "cars_count": 0,
                    "message": f"HTTP {response.status_code}"
                }
        except Exception as e:
            return {
                "success": False,
                "cars_count": 0,
                "message": str(e)
            }
    
    def log_status(self, status: Dict[str, Any], force_log: bool = False):
        """
        Логирует статус сессии
        
        Args:
            status: Статус сессии
            force_log: Принудительное логирование
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Логируем только изменения статуса или по принуждению
        if force_log or not self.last_status or status["status"] != self.last_status.get("status"):
            if status["healthy"]:
                print(f"✅ [{timestamp}] {status['message']}")
                if status.get("cars_count", 0) > 0:
                    print(f"   📊 Получено {status['cars_count']} автомобилей")
            else:
                print(f"❌ [{timestamp}] {status['message']}")
                if status.get("issues"):
                    for issue in status["issues"]:
                        print(f"   - {issue}")
        elif not status["healthy"]:
            # Для проблемных состояний показываем точки каждые N проверок
            if self.consecutive_failures % 5 == 0:
                print(".", end="", flush=True)
    
    def send_notification(self, status: Dict[str, Any]):
        """
        Отправляет уведомление о проблемах с сессией
        
        Args:
            status: Статус сессии с проблемами
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        print(f"\n🚨 [{timestamp}] ТРЕБУЕТСЯ ВНИМАНИЕ!")
        print("=" * 50)
        print(f"Статус: {status['status']}")
        print(f"Проблема: {status['message']}")
        
        if status.get("issues"):
            print("Детали:")
            for issue in status["issues"]:
                print(f"  - {issue}")
        
        print("\n🔧 Рекомендуемые действия:")
        print("1. Зайдите в Glovis через браузер/приложение")
        print("2. Скопируйте cURL запрос из DevTools")
        print("3. Выполните: python glovis_curl_converter.py --from-clipboard")
        print("4. Или выполните: python fix_glovis_session.py")
        print("=" * 50)
    
    def run_once(self) -> Dict[str, Any]:
        """
        Выполняет одну проверку сессии
        
        Returns:
            Dict с результатом проверки
        """
        status = self.check_session_status()
        
        # Отслеживаем последовательные сбои
        if status["healthy"]:
            was_failing = self.consecutive_failures > 0
            self.consecutive_failures = 0
            
            # Если восстановились после сбоев, показываем уведомление
            if was_failing:
                print(f"\n✅ [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Сессия восстановлена!")
        else:
            self.consecutive_failures += 1
        
        # Логируем статус
        self.log_status(status)
        
        # Отправляем уведомление при критических проблемах
        if (not status["healthy"] and 
            self.consecutive_failures >= self.max_failures and
            self.consecutive_failures % self.max_failures == 0):
            self.send_notification(status)
        
        self.last_status = status
        return status
    
    def run_continuous(self):
        """Запускает непрерывный мониторинг"""
        print(f"🔍 Запускаю мониторинг сессии Glovis")
        print(f"🌐 API URL: {self.api_url}")
        print(f"⏰ Интервал проверки: {self.check_interval} секунд")
        print(f"📊 Максимум сбоев до уведомления: {self.max_failures}")
        print("=" * 60)
        
        self.running = True
        
        # Первоначальная проверка
        print("Выполняю первоначальную проверку...")
        self.run_once()
        
        try:
            while self.running:
                time.sleep(self.check_interval)
                if self.running:  # Проверяем снова после sleep
                    self.run_once()
                    
        except KeyboardInterrupt:
            print(f"\n\n⏹️ [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Мониторинг остановлен пользователем")
        except Exception as e:
            print(f"\n❌ Ошибка мониторинга: {e}")
        finally:
            self.running = False
    
    def stop(self):
        """Останавливает мониторинг"""
        self.running = False
    
    def run_daemon(self):
        """Запускает мониторинг в режиме демона"""
        print(f"🔄 Запускаю демон мониторинга Glovis (PID: {os.getpid()})")
        
        # Настраиваем обработку сигналов
        def signal_handler(signum, frame):
            print(f"\n📡 Получен сигнал {signum}, завершаю мониторинг...")
            self.stop()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        self.run_continuous()


def main():
    """Основная функция"""
    parser = argparse.ArgumentParser(
        description="Мониторинг сессии Glovis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:

1. Одноразовая проверка:
   python glovis_session_monitor.py --check-once

2. Непрерывный мониторинг (каждые 5 минут):
   python glovis_session_monitor.py --interval 300

3. Быстрый мониторинг (каждую минуту):
   python glovis_session_monitor.py --interval 60

4. Демон режим:
   python glovis_session_monitor.py --daemon
        """
    )
    
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="URL API сервера (по умолчанию: http://localhost:8000)"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Интервал проверки в секундах (по умолчанию: 300)"
    )
    parser.add_argument(
        "--check-once",
        action="store_true",
        help="Выполнить только одну проверку"
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Запустить в режиме демона"
    )
    parser.add_argument(
        "--max-failures",
        type=int,
        default=3,
        help="Максимум сбоев до уведомления (по умолчанию: 3)"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Тихий режим - показывать только проблемы"
    )
    
    args = parser.parse_args()
    
    # Создаем монитор
    monitor = GlovisSessionMonitor(
        api_url=args.api_url,
        check_interval=args.interval
    )
    monitor.max_failures = args.max_failures
    
    if args.check_once:
        # Одноразовая проверка
        print("🔍 Выполняю проверку сессии Glovis...")
        status = monitor.run_once()
        
        if status["healthy"]:
            print(f"\n✅ Сессия работает корректно")
            if status.get("cars_count", 0) > 0:
                print(f"📊 Получено {status['cars_count']} автомобилей")
            return 0
        else:
            print(f"\n❌ Проблемы с сессией:")
            print(f"   {status['message']}")
            if status.get("issues"):
                for issue in status["issues"]:
                    print(f"   - {issue}")
            
            print(f"\n🔧 Для восстановления выполните:")
            print("   python glovis_curl_converter.py --from-clipboard")
            return 1
    
    elif args.daemon:
        # Демон режим
        monitor.run_daemon()
        return 0
    
    else:
        # Непрерывный мониторинг
        try:
            monitor.run_continuous()
            return 0
        except Exception as e:
            print(f"❌ Ошибка мониторинга: {e}")
            return 1


if __name__ == "__main__":
    import os
    exit(main())