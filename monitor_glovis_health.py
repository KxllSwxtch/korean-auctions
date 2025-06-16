#!/usr/bin/env python3
"""
Система мониторинга здоровья Glovis с уведомлениями
Непрерывно отслеживает состояние сессии и API
"""

import asyncio
import time
import requests
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
import sys
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


@dataclass
class HealthStatus:
    """Статус здоровья системы"""

    timestamp: str
    session_valid: bool
    api_working: bool
    response_time: float
    cars_count: int
    error_message: Optional[str] = None
    consecutive_failures: int = 0


@dataclass
class AlertConfig:
    """Конфигурация уведомлений"""

    email_enabled: bool = False
    email_smtp_server: str = "smtp.gmail.com"
    email_smtp_port: int = 587
    email_username: str = ""
    email_password: str = ""
    email_to: List[str] = None

    webhook_enabled: bool = False
    webhook_url: str = ""

    console_alerts: bool = True

    failure_threshold: int = 3  # Количество неудач подряд для отправки уведомления
    recovery_notification: bool = True  # Уведомлять о восстановлении


class GlovisHealthMonitor:
    """Монитор здоровья Glovis"""

    def __init__(
        self, api_url: str = "http://localhost:8000", config: AlertConfig = None
    ):
        self.api_url = api_url
        self.config = config or AlertConfig()
        self.session = requests.Session()
        self.health_history: List[HealthStatus] = []
        self.last_alert_time = None
        self.system_down = False
        self.consecutive_failures = 0

    def log(self, message: str, level: str = "INFO"):
        """Логирование с временной меткой"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")

    async def check_health(self) -> HealthStatus:
        """Проверка здоровья системы"""
        timestamp = datetime.now().isoformat()

        try:
            # Проверяем сессию
            session_response = self.session.get(
                f"{self.api_url}/api/v1/glovis/check-session", timeout=30
            )

            session_valid = False
            if session_response.status_code == 200:
                session_data = session_response.json()
                session_valid = session_data.get("data", {}).get("is_valid", False)

            # Проверяем API
            start_time = time.time()
            api_response = self.session.get(
                f"{self.api_url}/api/v1/glovis/cars", timeout=30
            )
            response_time = time.time() - start_time

            api_working = False
            cars_count = 0
            error_message = None

            if api_response.status_code == 200:
                api_data = api_response.json()
                api_working = api_data.get("success", False)
                if api_working:
                    cars_count = len(api_data.get("data", {}).get("cars", []))
                else:
                    error_message = api_data.get(
                        "message", "API returned success=false"
                    )
            else:
                error_message = (
                    f"HTTP {api_response.status_code}: {api_response.text[:100]}"
                )

            # Обновляем счетчик неудач
            if not (session_valid and api_working):
                self.consecutive_failures += 1
            else:
                self.consecutive_failures = 0

            return HealthStatus(
                timestamp=timestamp,
                session_valid=session_valid,
                api_working=api_working,
                response_time=response_time,
                cars_count=cars_count,
                error_message=error_message,
                consecutive_failures=self.consecutive_failures,
            )

        except Exception as e:
            self.consecutive_failures += 1
            return HealthStatus(
                timestamp=timestamp,
                session_valid=False,
                api_working=False,
                response_time=0.0,
                cars_count=0,
                error_message=str(e),
                consecutive_failures=self.consecutive_failures,
            )

    def is_system_healthy(self, status: HealthStatus) -> bool:
        """Проверяет, здорова ли система"""
        return status.session_valid and status.api_working and status.cars_count > 0

    def should_send_alert(self, status: HealthStatus) -> bool:
        """Определяет, нужно ли отправлять уведомление"""
        # Отправляем уведомление если:
        # 1. Система упала и достигнут порог неудач
        # 2. Система восстановилась после падения

        system_healthy = self.is_system_healthy(status)

        if (
            not system_healthy
            and status.consecutive_failures >= self.config.failure_threshold
        ):
            if not self.system_down:  # Первое уведомление о падении
                return True
        elif system_healthy and self.system_down and self.config.recovery_notification:
            return True  # Уведомление о восстановлении

        return False

    async def send_email_alert(self, status: HealthStatus, is_recovery: bool = False):
        """Отправка email уведомления"""
        if not self.config.email_enabled or not self.config.email_to:
            return

        try:
            subject = (
                "🎉 Glovis восстановлен" if is_recovery else "🚨 Проблемы с Glovis"
            )

            # Создаем HTML сообщение
            html_body = self.create_email_body(status, is_recovery)

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.config.email_username
            msg["To"] = ", ".join(self.config.email_to)

            html_part = MIMEText(html_body, "html")
            msg.attach(html_part)

            # Отправляем
            server = smtplib.SMTP(
                self.config.email_smtp_server, self.config.email_smtp_port
            )
            server.starttls()
            server.login(self.config.email_username, self.config.email_password)

            for email in self.config.email_to:
                server.sendmail(self.config.email_username, email, msg.as_string())

            server.quit()
            self.log("📧 Email уведомление отправлено")

        except Exception as e:
            self.log(f"❌ Ошибка отправки email: {str(e)}", "ERROR")

    def create_email_body(self, status: HealthStatus, is_recovery: bool) -> str:
        """Создание HTML тела email"""
        if is_recovery:
            return f"""
            <html>
            <body>
                <h2 style="color: green;">🎉 Glovis восстановлен</h2>
                <p><strong>Время восстановления:</strong> {status.timestamp}</p>
                <p><strong>Статус сессии:</strong> {'✅ Валидна' if status.session_valid else '❌ Невалидна'}</p>
                <p><strong>API работает:</strong> {'✅ Да' if status.api_working else '❌ Нет'}</p>
                <p><strong>Получено автомобилей:</strong> {status.cars_count}</p>
                <p><strong>Время ответа:</strong> {status.response_time:.3f}с</p>
                <hr>
                <p><small>Автоматическое уведомление от системы мониторинга Glovis</small></p>
            </body>
            </html>
            """
        else:
            return f"""
            <html>
            <body>
                <h2 style="color: red;">🚨 Проблемы с Glovis</h2>
                <p><strong>Время обнаружения:</strong> {status.timestamp}</p>
                <p><strong>Статус сессии:</strong> {'✅ Валидна' if status.session_valid else '❌ Невалидна'}</p>
                <p><strong>API работает:</strong> {'✅ Да' if status.api_working else '❌ Нет'}</p>
                <p><strong>Получено автомобилей:</strong> {status.cars_count}</p>
                <p><strong>Время ответа:</strong> {status.response_time:.3f}с</p>
                <p><strong>Неудач подряд:</strong> {status.consecutive_failures}</p>
                {f'<p><strong>Ошибка:</strong> {status.error_message}</p>' if status.error_message else ''}
                <hr>
                <p><small>Автоматическое уведомление от системы мониторинга Glovis</small></p>
            </body>
            </html>
            """

    async def send_webhook_alert(self, status: HealthStatus, is_recovery: bool = False):
        """Отправка webhook уведомления"""
        if not self.config.webhook_enabled or not self.config.webhook_url:
            return

        try:
            payload = {
                "type": "recovery" if is_recovery else "alert",
                "service": "glovis",
                "timestamp": status.timestamp,
                "status": asdict(status),
                "message": (
                    "Система восстановлена" if is_recovery else "Обнаружены проблемы"
                ),
            }

            response = requests.post(self.config.webhook_url, json=payload, timeout=10)

            if response.status_code == 200:
                self.log("🔗 Webhook уведомление отправлено")
            else:
                self.log(f"⚠️ Webhook вернул статус {response.status_code}", "WARNING")

        except Exception as e:
            self.log(f"❌ Ошибка отправки webhook: {str(e)}", "ERROR")

    def print_console_alert(self, status: HealthStatus, is_recovery: bool = False):
        """Вывод уведомления в консоль"""
        if not self.config.console_alerts:
            return

        print("\n" + "=" * 60)
        if is_recovery:
            print("🎉 СИСТЕМА ВОССТАНОВЛЕНА!")
            print(f"⏰ Время восстановления: {status.timestamp}")
        else:
            print("🚨 ОБНАРУЖЕНЫ ПРОБЛЕМЫ!")
            print(f"⏰ Время обнаружения: {status.timestamp}")
            print(f"🔄 Неудач подряд: {status.consecutive_failures}")

        print(f"🔐 Сессия валидна: {'✅' if status.session_valid else '❌'}")
        print(f"🚀 API работает: {'✅' if status.api_working else '❌'}")
        print(f"🚗 Автомобилей получено: {status.cars_count}")
        print(f"⚡ Время ответа: {status.response_time:.3f}с")

        if status.error_message:
            print(f"❌ Ошибка: {status.error_message}")

        print("=" * 60 + "\n")

    async def send_alerts(self, status: HealthStatus):
        """Отправка всех настроенных уведомлений"""
        is_recovery = self.system_down and self.is_system_healthy(status)

        # Консольное уведомление
        self.print_console_alert(status, is_recovery)

        # Email уведомление
        if self.config.email_enabled:
            await self.send_email_alert(status, is_recovery)

        # Webhook уведомление
        if self.config.webhook_enabled:
            await self.send_webhook_alert(status, is_recovery)

        self.last_alert_time = datetime.now()

    def print_status(self, status: HealthStatus):
        """Вывод текущего статуса"""
        health_icon = "🟢" if self.is_system_healthy(status) else "🔴"
        timestamp = datetime.fromisoformat(status.timestamp).strftime("%H:%M:%S")

        print(
            f"{health_icon} [{timestamp}] "
            f"Сессия: {'✅' if status.session_valid else '❌'} | "
            f"API: {'✅' if status.api_working else '❌'} | "
            f"Авто: {status.cars_count} | "
            f"Время: {status.response_time:.3f}с | "
            f"Неудач: {status.consecutive_failures}"
        )

        if status.error_message and not self.is_system_healthy(status):
            print(f"   ⚠️ {status.error_message}")

    def get_statistics(self) -> Dict[str, Any]:
        """Получение статистики мониторинга"""
        if not self.health_history:
            return {}

        total_checks = len(self.health_history)
        healthy_checks = sum(
            1 for s in self.health_history if self.is_system_healthy(s)
        )

        response_times = [
            s.response_time for s in self.health_history if s.response_time > 0
        ]
        avg_response_time = (
            sum(response_times) / len(response_times) if response_times else 0
        )

        return {
            "total_checks": total_checks,
            "healthy_checks": healthy_checks,
            "unhealthy_checks": total_checks - healthy_checks,
            "uptime_percentage": (
                (healthy_checks / total_checks * 100) if total_checks > 0 else 0
            ),
            "average_response_time": avg_response_time,
            "current_consecutive_failures": self.consecutive_failures,
            "monitoring_duration": (
                datetime.fromisoformat(self.health_history[-1].timestamp)
                - datetime.fromisoformat(self.health_history[0].timestamp)
            ).total_seconds()
            / 3600,  # в часах
        }

    def print_statistics(self):
        """Вывод статистики"""
        stats = self.get_statistics()
        if not stats:
            return

        print(f"\n📊 СТАТИСТИКА МОНИТОРИНГА")
        print(f"{'='*40}")
        print(f"⏱️ Время мониторинга: {stats['monitoring_duration']:.1f} часов")
        print(f"🔍 Всего проверок: {stats['total_checks']}")
        print(f"✅ Успешных: {stats['healthy_checks']}")
        print(f"❌ Неуспешных: {stats['unhealthy_checks']}")
        print(f"📈 Uptime: {stats['uptime_percentage']:.1f}%")
        print(f"⚡ Среднее время ответа: {stats['average_response_time']:.3f}с")
        print(f"🔄 Текущих неудач подряд: {stats['current_consecutive_failures']}")
        print(f"{'='*40}\n")

    async def run_monitoring(self, check_interval: int = 60, max_history: int = 1000):
        """Запуск мониторинга"""
        self.log(f"🚀 Запуск мониторинга Glovis (интервал: {check_interval}с)")
        self.log(f"📧 Email уведомления: {'✅' if self.config.email_enabled else '❌'}")
        self.log(
            f"🔗 Webhook уведомления: {'✅' if self.config.webhook_enabled else '❌'}"
        )
        self.log(
            f"🖥️ Консольные уведомления: {'✅' if self.config.console_alerts else '❌'}"
        )
        self.log(f"⚠️ Порог неудач для уведомления: {self.config.failure_threshold}")
        print()

        try:
            while True:
                # Проверяем здоровье
                status = await self.check_health()

                # Сохраняем в историю
                self.health_history.append(status)
                if len(self.health_history) > max_history:
                    self.health_history.pop(0)

                # Выводим статус
                self.print_status(status)

                # Проверяем нужно ли отправлять уведомления
                if self.should_send_alert(status):
                    await self.send_alerts(status)

                # Обновляем состояние системы
                self.system_down = not self.is_system_healthy(status)

                # Каждые 10 проверок выводим статистику
                if len(self.health_history) % 10 == 0:
                    self.print_statistics()

                # Ждем до следующей проверки
                await asyncio.sleep(check_interval)

        except KeyboardInterrupt:
            self.log("\n🛑 Мониторинг остановлен пользователем")
            self.print_statistics()
        except Exception as e:
            self.log(f"❌ Критическая ошибка мониторинга: {str(e)}", "ERROR")


def load_config_from_file(config_file: str) -> AlertConfig:
    """Загрузка конфигурации из файла"""
    try:
        with open(config_file, "r") as f:
            config_data = json.load(f)

        return AlertConfig(
            email_enabled=config_data.get("email_enabled", False),
            email_smtp_server=config_data.get("email_smtp_server", "smtp.gmail.com"),
            email_smtp_port=config_data.get("email_smtp_port", 587),
            email_username=config_data.get("email_username", ""),
            email_password=config_data.get("email_password", ""),
            email_to=config_data.get("email_to", []),
            webhook_enabled=config_data.get("webhook_enabled", False),
            webhook_url=config_data.get("webhook_url", ""),
            console_alerts=config_data.get("console_alerts", True),
            failure_threshold=config_data.get("failure_threshold", 3),
            recovery_notification=config_data.get("recovery_notification", True),
        )
    except Exception as e:
        print(f"⚠️ Ошибка загрузки конфигурации: {e}")
        return AlertConfig()


async def main():
    """Основная функция"""
    import argparse

    parser = argparse.ArgumentParser(description="Мониторинг здоровья Glovis")
    parser.add_argument(
        "--api-url", default="http://localhost:8000", help="URL API сервера"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Интервал проверки в секундах (по умолчанию: 60)",
    )
    parser.add_argument("--config", help="Путь к файлу конфигурации JSON")
    parser.add_argument(
        "--email", help="Email для уведомлений (требует настройки SMTP)"
    )
    parser.add_argument("--webhook", help="URL webhook для уведомлений")
    parser.add_argument(
        "--threshold",
        type=int,
        default=3,
        help="Количество неудач подряд для отправки уведомления",
    )

    args = parser.parse_args()

    # Загружаем конфигурацию
    if args.config:
        config = load_config_from_file(args.config)
    else:
        config = AlertConfig()

    # Переопределяем параметры из командной строки
    if args.email:
        config.email_enabled = True
        config.email_to = [args.email]

    if args.webhook:
        config.webhook_enabled = True
        config.webhook_url = args.webhook

    config.failure_threshold = args.threshold

    # Запускаем мониторинг
    monitor = GlovisHealthMonitor(api_url=args.api_url, config=config)
    await monitor.run_monitoring(check_interval=args.interval)


if __name__ == "__main__":
    asyncio.run(main())
