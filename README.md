# AutoBaza Parser API

Модульный API для парсинга автомобильных аукционов (Autohub, Glovis, Lotte, KCar) с использованием Python, FastAPI и BeautifulSoup4.

## 🚀 Особенности

- **Модульная архитектура**: Четкое разделение на компоненты (routes, services, parsers, models)
- **Надёжность**: Retry механизмы, обработка ошибок, таймауты
- **Масштабируемость**: Легко добавлять новые аукционы
- **Документация**: Автоматическая OpenAPI документация
- **Логирование**: Полное логирование всех операций
- **Типизация**: Полная типизация с Pydantic моделями

## 📁 Структура проекта

```
backend/
├── app/
│   ├── core/           # Конфигурация и логирование
│   ├── models/         # Pydantic модели
│   ├── parsers/        # Парсеры для разных аукционов
│   ├── routes/         # FastAPI маршруты
│   ├── services/       # Бизнес логика и HTTP клиенты
│   └── utils/          # Утилиты
├── logs/               # Логи приложения
├── main.py            # Точка входа приложения
└── requirements.txt   # Зависимости
```

## 🛠 Установка и запуск

### 1. Клонирование и настройка окружения

```bash
# Создание виртуального окружения
python -m venv venv

# Активация (Windows)
venv\Scripts\activate

# Активация (macOS/Linux)
source venv/bin/activate

# Установка зависимостей
pip install -r requirements.txt
```

### 2. Запуск сервера

```bash
# Режим разработки (рекомендуется)
fastapi dev main.py

# Или через uvicorn
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Или через Python
python main.py
```

### ✅ Авторизация настроена!

API автоматически выполняет авторизацию на сайте Autohub с учётными данными:

- **Логин:** 785701
- **Пароль:** 782312

Проверить статус авторизации: `GET /api/v1/autohub/auth/status`

### 3. Запуск в продакшене

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

## 📚 API Endpoints

### 🚗 Autohub Endpoints

| Метод | Endpoint                          | Описание                                        |
| ----- | --------------------------------- | ----------------------------------------------- |
| GET   | `/api/v1/autohub/cars`            | Получить список автомобилей (с авторизацией) ✅ |
| GET   | `/api/v1/autohub/cars/test`       | Получить тестовые данные (10 автомобилей)       |
| GET   | `/api/v1/autohub/cars/demo`       | Демо данные (до 100 автомобилей)                |
| GET   | `/api/v1/autohub/cars/stats`      | Статистика по автомобилям                       |
| GET   | `/api/v1/autohub/auth/status`     | Проверить статус авторизации ✅                 |
| GET   | `/api/v1/autohub/pagination/demo` | Демонстрация пагинации ✅                       |

### 📋 Основные Endpoints

| Метод | Endpoint  | Описание                   |
| ----- | --------- | -------------------------- |
| GET   | `/`       | Информация о API           |
| GET   | `/health` | Проверка состояния сервиса |
| GET   | `/docs`   | Интерактивная документация |
| GET   | `/redoc`  | ReDoc документация         |

## 🔧 Использование API

### Проверка авторизации

```bash
# Проверить статус авторизации
curl "http://localhost:8000/api/v1/autohub/auth/status"
```

### Получение списка автомобилей

```bash
# Базовый запрос (с автоматической авторизацией)
curl "http://localhost:8000/api/v1/autohub/cars"

# С пагинацией
curl "http://localhost:8000/api/v1/autohub/cars?page=2&limit=20"

# С параметрами фильтрации
curl "http://localhost:8000/api/v1/autohub/cars?page=1&limit=10&min_price=1000&max_price=5000"

# Поиск по названию
curl "http://localhost:8000/api/v1/autohub/cars?search=현대"
```

### 🔄 Пагинация

API поддерживает полную пагинацию с автоматическим извлечением общего количества записей:

```bash
# Демонстрация пагинации (первые автомобили с 3 страниц)
curl "http://localhost:8000/api/v1/autohub/pagination/demo?max_pages=3"

# Получение конкретной страницы
curl "http://localhost:8000/api/v1/autohub/cars?page=2"

# Информация о пагинации в ответе:
# - total_count: 1761 (общее количество автомобилей)
# - total_pages: 177 (общее количество страниц)
# - current_page: 2 (текущая страница)
# - page_size: 10 (автомобилей на странице)
# - has_next_page: true/false
# - has_prev_page: true/false

# Пагинация работает на стороне сервера Autohub
# Параметр page преобразуется в i_iNowPageNo для сайта
```

### Параметры запроса

- `page` - Номер страницы (по умолчанию: 1)
- `limit` - Количество на странице (по умолчанию: 20, максимум: 100)
- `search` - Поиск по названию
- `min_price` / `max_price` - Диапазон цен (в манвонах)
- `fuel_type` - Тип топлива (`휘발유`, `경유`, `전기`, `하이브리드`)
- `year_from` / `year_to` - Диапазон годов выпуска

### Тестовые данные

```bash
# Получение тестовых данных для демонстрации (10 автомобилей)
curl "http://localhost:8000/api/v1/autohub/cars/test"

# Демо данные с настраиваемым количеством автомобилей
curl "http://localhost:8000/api/v1/autohub/cars/demo?count=50"
```

### Статистика

```bash
# Получение статистики по автомобилям
curl "http://localhost:8000/api/v1/autohub/cars/stats"
```

## 📊 Пример ответа API

```json
{
  "success": true,
  "message": "Страница 2 из 177: загружено 10 автомобилей",
  "total_count": 1761,
  "current_page": 2,
  "page_size": 10,
  "total_pages": 177,
  "has_next_page": true,
  "has_prev_page": true,
  "cars": [
    {
      "car_id": "RC202506040490",
      "auction_number": "1005",
      "car_number": "90고4479",
      "parking_number": "A10-0395",
      "title": "현대 올 뉴 투싼 (15년~20년) 디젤 1.7 2WD 스타일",
      "year": 2019,
      "mileage": "120,441km",
      "transmission": "오토",
      "fuel_type": "경유",
      "first_registration_date": "2019-09-22",
      "condition_grade": "AC",
      "history": "자가용",
      "starting_price": 1370,
      "status": "출품등록",
      "main_image_url": "http://www.sellcarauction.co.kr/...",
      "parsed_at": "2025-06-09T14:43:23.611369"
    }
  ],
  "parsed_at": "2025-06-09T14:43:23.615431"
}
```

## 🔧 Конфигурация

Создайте файл `.env` для настройки параметров:

```env
# Основные настройки
DEBUG=false
LOG_LEVEL=INFO

# Настройки парсинга
REQUEST_TIMEOUT=30
MAX_RETRIES=3
RETRY_DELAY=1.0

# Настройки Autohub
AUTOHUB_BASE_URL=https://www.autohubauction.co.kr
AUTOHUB_LIST_URL=https://www.autohubauction.co.kr/newfront/receive/rc/receive_rc_list.do
```

## 🧪 Тестирование

```bash
# Тест парсера
python -c "from app.services.autohub_service import AutohubService; service = AutohubService(); result = service.get_test_data(); print(f'Найдено: {len(result.cars)} автомобилей')"

# Тест API
curl "http://localhost:8000/api/v1/autohub/cars/test"
```

## 📝 Логи

Логи сохраняются в папку `logs/`:

- `logs/app.log` - Основные логи приложения
- Ротация логов каждые 10MB
- Хранение логов 7 дней

## 🚀 Расширение функциональности

### Добавление нового аукциона

1. Создайте модели в `app/models/`
2. Создайте парсер в `app/parsers/`
3. Создайте сервис в `app/services/`
4. Создайте маршруты в `app/routes/`
5. Подключите в `main.py`

### Пример добавления Glovis

```python
# app/models/glovis.py
class GlovisCar(BaseModel):
    # модели для Glovis

# app/parsers/glovis_parser.py
class GlovisParser:
    # парсер для Glovis

# app/services/glovis_service.py
class GlovisService:
    # сервис для Glovis

# app/routes/glovis.py
router = APIRouter()
# маршруты для Glovis
```

## 🛡 Антиблокировочные меры

- Случайные User-Agent'ы
- Задержки между запросами
- Retry стратегия с backoff
- Ротация headers
- Обработка ошибок соединения

## 📖 Документация

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 🐛 Решение проблем

### ⚠️ Проблема с авторизацией Autohub

**Проблема**: Endpoint `/api/v1/autohub/cars` возвращает ошибку о необходимости авторизации.

**Причина**: Сайт Autohub требует авторизации для доступа к списку автомобилей.

**Решение**:

- Используйте `/api/v1/autohub/cars/test` для тестовых данных (10 автомобилей)
- Используйте `/api/v1/autohub/cars/demo?count=N` для демо данных (до 100 автомобилей)
- Для полного доступа потребуется реализация авторизации с учётными данными

### Проблема с кодировкой

```python
# В случае проблем с корейским текстом
response.encoding = 'utf-8'
```

### Тестирование соединения

```bash
curl "http://localhost:8000/health"
```

### Проверка логов

```bash
tail -f logs/app.log
```

## 📄 Лицензия

MIT License

## 🤝 Вклад в проект

1. Fork проекта
2. Создайте feature branch
3. Commit изменения
4. Push в branch
5. Создайте Pull Request

## 📞 Поддержка

Для вопросов и предложений создайте issue в репозитории.
