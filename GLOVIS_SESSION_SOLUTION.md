# Решение проблемы с сессиями Glovis

## Проблема

При работе с аукционом Glovis возникает проблема с истечением сессии:

- Сессия работает пока приложение открыто на Windows
- После закрытия приложения через некоторое время сессия истекает
- Требуется ручное обновление cookies из cURL запроса

## Компоненты решения

### 1. Session Manager (`app/core/session_manager.py`)

Централизованный менеджер для управления сессиями:

- Сохранение сессий в файлы (`cache/sessions/`)
- Загрузка сохраненных сессий при старте
- Проверка свежести сессий
- Thread-safe операции

### 2. Glovis Session Monitor

Автоматический монитор сессии:

- Проверяет сессию каждые 5 минут
- Автоматически обновляет из `glovis-curl-request.py` если файл свежий
- Работает в фоновом потоке

### 3. API Endpoints

Новые endpoints для управления сессией:

#### `POST /api/v1/glovis/update-cookies`

Обновляет cookies напрямую через API:

```bash
curl -X POST http://localhost:8000/api/v1/glovis/update-cookies \
  -H "Content-Type: application/json" \
  -d '{"JSESSIONID": "...", "_ga": "...", ...}'
```

#### `GET /api/v1/glovis/check-session`

Проверяет статус текущей сессии:

```bash
curl http://localhost:8000/api/v1/glovis/check-session
```

#### `POST /api/v1/glovis/upload-curl-file`

Загружает файл с curl запросом:

```bash
curl -X POST http://localhost:8000/api/v1/glovis/upload-curl-file \
  -F "file=@glovis-curl-request.py"
```

#### `GET /api/v1/glovis/session-info`

Получает подробную информацию о сессии:

```bash
curl http://localhost:8000/api/v1/glovis/session-info
```

### 4. Windows Session Watcher (`windows_session_watcher.py`)

Автономный сервис для Windows:

- Отслеживает изменения в `glovis-curl-request.py`
- Автоматически извлекает и обновляет cookies
- Работает независимо от основного приложения

## Использование

### Способ 1: Автоматический (рекомендуется)

1. Запустите API сервер:

```bash
python main.py
```

2. В отдельном терминале запустите Windows Watcher:

```bash
python windows_session_watcher.py
```

3. Обновляйте файл `glovis-curl-request.py` когда нужно - cookies обновятся автоматически

### Способ 2: Через утилиту

Используйте существующую утилиту:

```bash
python update_glovis_cookies.py
```

### Способ 3: Через API

Обновите cookies напрямую через API endpoint.

### Способ 4: Загрузка файла

Загрузите файл через веб-интерфейс или API.

## Преимущества решения

1. **Автоматизация**: Не требуется ручное вмешательство
2. **Персистентность**: Сессии сохраняются между перезапусками
3. **Мониторинг**: Автоматическая проверка валидности
4. **Гибкость**: Несколько способов обновления
5. **Независимость**: Windows Watcher работает отдельно

## Настройка

### Конфигурация Session Manager

В `app/core/session_manager.py`:

- `cache_dir`: Директория для хранения сессий (по умолчанию `cache/sessions`)
- `max_age_hours`: Максимальный возраст сессии (по умолчанию 12 часов)
- `check_interval`: Интервал проверки в мониторе (по умолчанию 5 минут)

### Конфигурация Windows Watcher

Параметры запуска:

- `--file`: Файл для отслеживания (по умолчанию `glovis-curl-request.py`)
- `--api-url`: URL API сервера (по умолчанию `http://localhost:8000`)

## Устранение неполадок

### Сессия не обновляется

1. Проверьте статус через API:

```bash
curl http://localhost:8000/api/v1/glovis/check-session
```

2. Проверьте логи Windows Watcher в `glovis_watcher.log`

3. Убедитесь что файл `glovis-curl-request.py` содержит валидные cookies

### Windows Watcher не запускается

1. Установите зависимости:

```bash
pip install watchdog
```

2. Проверьте права доступа к файлам

3. Убедитесь что API сервер доступен

## Дополнительные возможности

### Интеграция с планировщиком Windows

Можно настроить Windows Watcher как службу Windows или задачу в планировщике для автоматического запуска.

### Уведомления

При необходимости можно добавить уведомления о проблемах с сессией через email или другие каналы.

### Расширение на другие аукционы

Архитектура Session Manager позволяет легко добавить поддержку других аукционов (Autohub, Lotte, KCar).
