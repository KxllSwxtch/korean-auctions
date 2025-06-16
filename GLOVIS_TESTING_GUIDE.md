# 🧪 Руководство по тестированию и мониторингу Glovis

## 📋 Содержание

- [Быстрый старт](#быстрый-старт)
- [Инструменты тестирования](#инструменты-тестирования)
- [Мониторинг в реальном времени](#мониторинг-в-реальном-времени)
- [Автоматизация](#автоматизация)
- [Устранение проблем](#устранение-проблем)

## 🚀 Быстрый старт

### 1. Проверка системы (30 секунд)

```bash
# Быстрая проверка всех компонентов
python run_all_tests.py --quick
```

### 2. Обновление cookies при проблемах

```bash
# Автоматическое обновление из glovis-curl-request.py
python update_glovis_cookies.py --test
```

### 3. Полное тестирование (2-3 минуты)

```bash
# Комплексное тестирование всех функций
python run_all_tests.py
```

## 🛠️ Инструменты тестирования

### 1. **test_glovis_session.py** - Базовые тесты сессии

**Что тестирует:**

- ✅ Создание новой сессии
- ✅ Проверка валидности сессии
- ✅ Выполнение API запросов
- ✅ TTL (время жизни) сессии
- ✅ Обновление cookies
- ✅ Восстановление при ошибках
- ✅ Параллельные запросы

**Использование:**

```bash
# Запуск всех базовых тестов
python test_glovis_session.py

# Вывод в JSON формате
python test_glovis_session.py --json-output
```

**Пример вывода:**

```
🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ! Система управления сессией работает надежно.
📈 Всего тестов: 7
✅ Пройдено: 7
❌ Провалено: 0
📊 Успешность: 100.0%
```

### 2. **stress_test_glovis.py** - Стресс-тестирование

**Что тестирует:**

- 🔥 Параллельные запросы (5-10 одновременно)
- 🔥 Последовательные запросы (15-20 подряд)
- 🔥 HTTP API нагрузка
- 🔥 Инвалидация сессии под нагрузкой

**Использование:**

```bash
# Полный стресс-тест
python stress_test_glovis.py

# Легкий режим (меньше запросов)
python stress_test_glovis.py --light
```

**Пример вывода:**

```
📊 Общая успешность: 95.2%
🎉 Отличная стабильность! Система готова к продакшену.
```

### 3. **update_glovis_cookies.py** - Управление cookies

**Функции:**

- 🍪 Автоматическое извлечение cookies из файла
- 🔄 Обновление через API
- ✅ Проверка валидности сессии
- 🧪 Тестирование API

**Использование:**

```bash
# Полное обновление с тестом
python update_glovis_cookies.py --test

# Только проверка статуса
python update_glovis_cookies.py --check-only

# Из другого файла
python update_glovis_cookies.py --file my-cookies.py
```

### 4. **run_all_tests.py** - Комплексное тестирование

**Функции:**

- 🎯 Запуск всех тестов последовательно
- 📊 Итоговый отчет
- ⚡ Быстрый режим
- 🔍 Проверка предварительных условий

**Использование:**

```bash
# Полное тестирование
python run_all_tests.py

# Быстрый режим (только основные тесты)
python run_all_tests.py --quick

# Пропустить проверки
python run_all_tests.py --skip-checks
```

## 📊 Мониторинг в реальном времени

### 1. **monitor_glovis_health.py** - Непрерывный мониторинг

**Функции:**

- 🔍 Проверка здоровья каждые N секунд
- 📧 Email уведомления при проблемах
- 🔗 Webhook уведомления (Slack, Discord)
- 📈 Статистика uptime
- 🚨 Автоматические алерты

**Базовое использование:**

```bash
# Мониторинг каждую минуту
python monitor_glovis_health.py

# Проверка каждые 30 секунд
python monitor_glovis_health.py --interval 30

# С email уведомлениями
python monitor_glovis_health.py --email admin@company.com

# С webhook уведомлениями
python monitor_glovis_health.py --webhook https://hooks.slack.com/...
```

**Настройка уведомлений:**

1. **Создайте файл конфигурации:**

```json
{
  "email_enabled": true,
  "email_username": "monitoring@company.com",
  "email_password": "app-password",
  "email_to": ["admin@company.com", "dev@company.com"],
  "webhook_enabled": true,
  "webhook_url": "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK",
  "failure_threshold": 3
}
```

2. **Запустите с конфигурацией:**

```bash
python monitor_glovis_health.py --config monitor_config.json
```

**Пример вывода мониторинга:**

```
🟢 [14:30:15] Сессия: ✅ | API: ✅ | Авто: 18 | Время: 0.450с | Неудач: 0
🟢 [14:31:15] Сессия: ✅ | API: ✅ | Авто: 18 | Время: 0.523с | Неудач: 0
🔴 [14:32:15] Сессия: ❌ | API: ❌ | Авто: 0 | Время: 5.000с | Неудач: 1
   ⚠️ HTTP 401: Unauthorized

🚨 ОБНАРУЖЕНЫ ПРОБЛЕМЫ!
⏰ Время обнаружения: 2025-06-16T14:32:15
🔄 Неудач подряд: 3
```

### 2. **monitor_glovis_session.py** - Простой мониторинг

**Функции:**

- 🔍 Проверка сессии и API
- 🔄 Автоматическое восстановление
- 📊 Статистика в реальном времени

**Использование:**

```bash
# Мониторинг каждую минуту
python monitor_glovis_session.py

# Частые проверки
python monitor_glovis_session.py --interval 10
```

## 🤖 Автоматизация

### 1. Cron задачи для Linux/macOS

```bash
# Проверка каждые 5 минут
*/5 * * * * cd /path/to/project && python update_glovis_cookies.py --check-only

# Полное тестирование каждый час
0 * * * * cd /path/to/project && python run_all_tests.py --quick

# Непрерывный мониторинг (запуск при загрузке)
@reboot cd /path/to/project && python monitor_glovis_health.py --config monitor_config.json
```

### 2. Systemd сервис (Linux)

**Создайте файл `/etc/systemd/system/glovis-monitor.service`:**

```ini
[Unit]
Description=Glovis Health Monitor
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/project
ExecStart=/path/to/venv/bin/python monitor_glovis_health.py --config monitor_config.json
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Запуск:**

```bash
sudo systemctl enable glovis-monitor
sudo systemctl start glovis-monitor
sudo systemctl status glovis-monitor
```

### 3. Docker контейнер

**Dockerfile:**

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "monitor_glovis_health.py", "--config", "monitor_config.json"]
```

**Запуск:**

```bash
docker build -t glovis-monitor .
docker run -d --name glovis-monitor --restart unless-stopped glovis-monitor
```

## 🚨 Устранение проблем

### Проблема: Сессия постоянно истекает

**Симптомы:**

- Частые ошибки "JavaScript редирект на логин"
- HTTP 401 ошибки
- Пустые ответы от API

**Решение:**

1. Обновите cookies из браузера:

```bash
# Скопируйте новые cookies в glovis-curl-request.py
python update_glovis_cookies.py --test
```

2. Проверьте параметры аукциона:

```bash
# Убедитесь что atn (номер аукциона) актуален
curl "http://localhost:8000/api/v1/glovis/check-session"
```

### Проблема: API возвращает 0 автомобилей

**Возможные причины:**

- Аукцион еще не начался
- Аукцион уже закончился
- Неверные параметры поиска
- Проблемы с сессией

**Диагностика:**

```bash
# Проверьте статус сессии
python update_glovis_cookies.py --check-only

# Проверьте прямой запрос
curl "http://localhost:8000/api/v1/glovis/cars" | jq '.success'
```

### Проблема: Медленные ответы

**Симптомы:**

- Время ответа > 5 секунд
- Таймауты запросов

**Решение:**

1. Проверьте сетевое подключение
2. Увеличьте таймауты в коде
3. Используйте прокси если нужно

### Проблема: Тесты падают

**Диагностика:**

```bash
# Проверьте что API сервер запущен
curl "http://localhost:8000/docs"

# Проверьте логи
python test_glovis_session.py --json-output | jq '.results[] | select(.success == false)'
```

## 📈 Интерпретация результатов

### Успешность тестов

- **100%** - 🎉 Отлично! Система полностью готова
- **90-99%** - ✅ Хорошо, незначительные проблемы
- **80-89%** - ⚠️ Требует внимания
- **< 80%** - 🚨 Критические проблемы

### Время ответа

- **< 1с** - 🚀 Отлично
- **1-3с** - ✅ Хорошо
- **3-5с** - ⚠️ Медленно
- **> 5с** - 🚨 Очень медленно

### Uptime

- **> 99%** - 🎯 Продакшн готов
- **95-99%** - ✅ Стабильно
- **90-95%** - ⚠️ Нестабильно
- **< 90%** - 🚨 Неприемлемо

## 🎯 Рекомендации для продакшена

### 1. Настройте мониторинг

```bash
# Запустите непрерывный мониторинг
python monitor_glovis_health.py --config monitor_config.json
```

### 2. Автоматизируйте обновление cookies

```bash
# Добавьте в cron
*/30 * * * * cd /path/to/project && python update_glovis_cookies.py --check-only
```

### 3. Настройте уведомления

- Email для критических ошибок
- Slack/Discord для команды разработки
- SMS для экстренных случаев

### 4. Логирование

- Настройте централизованное логирование
- Мониторьте метрики производительности
- Сохраняйте историю проблем

### 5. Резервные планы

- Подготовьте запасные cookies
- Настройте автоматический failover
- Документируйте процедуры восстановления

---

## 📞 Поддержка

При возникновении проблем:

1. **Запустите диагностику:**

```bash
python run_all_tests.py --quick
```

2. **Проверьте логи:**

```bash
tail -f app.log
```

3. **Обновите cookies:**

```bash
python update_glovis_cookies.py --test
```

4. **Создайте issue** с результатами тестов и логами

---

**Система тестирования Glovis обеспечивает:**

- 🔒 Надежность сессий
- ⚡ Высокую производительность
- 📊 Полную наблюдаемость
- 🚀 Готовность к продакшену
