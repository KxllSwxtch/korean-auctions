# Lotte Auto Auction API

Этот документ описывает новый функционал для работы с аукционом Lotte, добавленный в AutoBaza Parser API.

## Обзор

Система Lotte включает в себя:

1. **Проверку даты аукциона** - определяет, проводится ли аукцион сегодня
2. **Парсинг списка автомобилей** - извлекает данные из таблицы автомобилей
3. **Получение детальной информации** - парсит подробные данные каждого автомобиля
4. **Аутентификацию** - автоматический вход в систему с учетными данными
5. **Кеширование** - оптимизация производительности

## API Endpoints

### 1. Основной endpoint - `/api/v1/lotte/cars`

**Описание**: Главный endpoint для получения автомобилей с проверкой даты аукциона.

**Параметры**:

- `limit` (int, 1-100): Количество автомобилей на странице (по умолчанию: 20)
- `offset` (int, ≥0): Смещение для пагинации (по умолчанию: 0)

**Логика работы**:

1. Проверяет дату аукциона
2. Если аукцион НЕ сегодня - возвращает информацию о ближайшей дате
3. Если аукцион сегодня - возвращает список автомобилей

**Пример запроса**:

```bash
curl "http://localhost:8000/api/v1/lotte/cars?limit=10&offset=0"
```

**Пример ответа (аукцион не сегодня)**:

```json
{
  "success": true,
  "message": "Аукцион не сегодня. Ближайший аукцион: 2025-06-16",
  "auction_date_info": {
    "auction_date": "2025-06-16",
    "year": 2025,
    "month": 6,
    "day": 16,
    "is_today": false,
    "is_future": true,
    "raw_text": "경매예정일2025년 06월 16일"
  },
  "cars": [],
  "total_count": 0,
  "timestamp": "2025-06-10T13:23:56.373343"
}
```

### 2. Дата аукциона - `/api/v1/lotte/auction-date`

**Описание**: Получение информации о дате ближайшего аукциона.

**Пример запроса**:

```bash
curl "http://localhost:8000/api/v1/lotte/auction-date"
```

**Пример ответа**:

```json
{
  "auction_date": "2025-06-16",
  "year": 2025,
  "month": 6,
  "day": 16,
  "is_today": false,
  "is_future": true,
  "raw_text": "경매예정일2025년 06월 16일"
}
```

### 3. Тестовые данные - `/api/v1/lotte/cars/test`

**Описание**: Парсинг данных из локальных HTML файлов для тестирования.

**Требования**: Файлы `lotte-home-example.html`, `lotte-cars-example.html`, `lotte-car-example.html` в корне проекта.

**Пример запроса**:

```bash
curl "http://localhost:8000/api/v1/lotte/cars/test"
```

### 4. Демонстрационные данные - `/api/v1/lotte/cars/demo`

**Описание**: Сгенерированные демонстрационные данные для показа структуры API.

**Параметры**:

- `count` (int, 1-100): Количество демонстрационных автомобилей (по умолчанию: 10)

**Пример запроса**:

```bash
curl "http://localhost:8000/api/v1/lotte/cars/demo?count=5"
```

**Пример ответа**:

```json
{
  "success": true,
  "message": "Демонстрационные данные Lotte: 5 автомобилей",
  "auction_date_info": {
    "auction_date": "2025-06-16",
    "year": 2025,
    "month": 6,
    "day": 16,
    "is_today": false,
    "is_future": true,
    "raw_text": "경매예정일2025년 06월 16일"
  },
  "cars": [
    {
      "id": "DEMO_0001",
      "auction_number": "0003",
      "lane": "A",
      "license_plate": "41로9525",
      "name": "GRANDEUR HG (H) 2.4 PREMIUM",
      "model": "GRANDEUR",
      "brand": "HYUNDAI",
      "year": 2014,
      "mileage": 160246,
      "fuel_type": "gasoline",
      "transmission": "automatic",
      "color": "기타",
      "grade": "D/D",
      "starting_price": 0,
      "first_registration_date": "2014.02.14",
      "inspection_valid_until": "2026.02.13",
      "usage_type": "자사 - 자가 - 법인",
      "owner_info": "롯데렌탈(주)",
      "vin_number": "KMHFG413BEA001670",
      "engine_model": "G4KK",
      "images": [
        "https://imgmk.lotteautoauction.net/AU_CAR_IMG_ORG_HP/202506/SA20250602000121.JPG",
        "https://imgmk.lotteautoauction.net/AU_CAR_IMG_ORG_HP/202506/SA20250602000122.JPG"
      ],
      "searchMngDivCd": "SA",
      "searchMngNo": "SA202506020001",
      "searchExhiRegiSeq": "1"
    }
  ],
  "total_count": 5,
  "page": 1,
  "per_page": 5,
  "total_pages": 1,
  "timestamp": "2025-06-10T13:23:56.373343",
  "request_duration": 0.1
}
```

### 5. Статистика сервиса - `/api/v1/lotte/cars/stats`

**Описание**: Информация о состоянии сервиса Lotte.

**Пример запроса**:

```bash
curl "http://localhost:8000/api/v1/lotte/cars/stats"
```

**Пример ответа**:

```json
{
  "service_status": "active",
  "authenticated": false,
  "cache_size": 0,
  "cache_keys": [],
  "base_url": "https://www.lotteautoauction.net",
  "available_endpoints": [
    "/api/v1/lotte/auction-date - Дата аукциона",
    "/api/v1/lotte/cars - Основной endpoint с автомобилями",
    "/api/v1/lotte/cars/test - Тестовые данные из HTML файлов",
    "/api/v1/lotte/cars/demo - Демонстрационные данные",
    "/api/v1/lotte/cars/stats - Статистика сервиса"
  ],
  "timestamp": "2025-06-10T13:23:56.373343"
}
```

### 6. Очистка кеша - `/api/v1/lotte/cache/clear` (POST)

**Описание**: Очистка кеша сервиса Lotte.

**Пример запроса**:

```bash
curl -X POST "http://localhost:8000/api/v1/lotte/cache/clear"
```

## Структура данных автомобиля

```json
{
  "id": "SA_SA202506020001_1",
  "auction_number": "0003",
  "lane": "A",
  "license_plate": "41로9525",
  "name": "GRANDEUR HG (H) 2.4 PREMIUM",
  "model": "GRANDEUR",
  "brand": "HYUNDAI",
  "year": 2014,
  "mileage": 160246,
  "fuel_type": "hybrid",
  "transmission": "automatic",
  "engine_capacity": "2.4",
  "color": "기타",
  "grade": "D/D",
  "starting_price": 0,
  "first_registration_date": "2014.02.14",
  "inspection_valid_until": "2026.02.13",
  "usage_type": "자사 - 자가 - 법인",
  "owner_info": "롯데렌탈(주)",
  "vin_number": "KMHFG413BEA001677",
  "engine_model": "G4KK",
  "images": [
    "https://imgmk.lotteautoauction.net/AU_CAR_IMG_ORG_HP/202506/SA20250602000134.JPG"
  ],
  "searchMngDivCd": "SA",
  "searchMngNo": "SA202506020001",
  "searchExhiRegiSeq": "1"
}
```

## Аутентификация

Система автоматически выполняет аутентификацию с учетными данными:

- **Логин**: 119102
- **Пароль**: for1234@

Данные берутся из файла `auctions-auth.txt`.

## Кеширование

- **TTL кеша**: 5 минут (300 секунд)
- **Кешируемые данные**: дата аукциона, списки автомобилей
- **Ключи кеша**: `lotte_auction_date`, `lotte_cars_{limit}_{offset}`

## Обработка ошибок

### Типы ошибок:

1. **INTERNAL_ERROR** - Внутренняя ошибка сервера
2. **TEST_ERROR** - Ошибка при работе с тестовыми данными
3. **DEMO_ERROR** - Ошибка при генерации демо данных

### Пример ошибки:

```json
{
  "success": false,
  "error_code": "INTERNAL_ERROR",
  "message": "Внутренняя ошибка сервера: Connection timeout",
  "details": null,
  "timestamp": "2025-06-10T13:23:56.373343"
}
```

## Архитектура

### Компоненты:

1. **LotteParser** (`app/parsers/lotte_parser.py`)

   - Парсинг даты аукциона
   - Извлечение списка автомобилей
   - Парсинг детальной информации

2. **LotteService** (`app/services/lotte_service.py`)

   - HTTP клиент с retry стратегией
   - Аутентификация
   - Кеширование
   - Управление сессиями

3. **Модели данных** (`app/models/lotte.py`)

   - LotteCar - модель автомобиля
   - LotteAuctionDate - модель даты аукциона
   - LotteResponse - модель ответа API
   - LotteError - модель ошибки

4. **API маршруты** (`app/routes/lotte.py`)
   - FastAPI endpoints
   - Валидация параметров
   - Обработка ошибок

## Интеграция с Frontend

### Рекомендуемый workflow:

1. **Проверка даты аукциона**:

   ```javascript
   const dateResponse = await fetch("/api/v1/lotte/auction-date")
   const dateInfo = await dateResponse.json()

   if (!dateInfo.is_today) {
     // Показать сообщение о дате следующего аукциона
     showMessage(`Следующий аукцион: ${dateInfo.auction_date}`)
     return
   }
   ```

2. **Получение автомобилей**:

   ```javascript
   const carsResponse = await fetch("/api/v1/lotte/cars?limit=20&offset=0")
   const carsData = await carsResponse.json()

   if (carsData.success && carsData.cars.length > 0) {
     // Отображение автомобилей
     displayCars(carsData.cars)
   } else {
     // Показать сообщение из API
     showMessage(carsData.message)
   }
   ```

3. **Демонстрационные данные** (для разработки):
   ```javascript
   const demoResponse = await fetch("/api/v1/lotte/cars/demo?count=10")
   const demoData = await demoResponse.json()
   displayCars(demoData.cars)
   ```

## Тестирование

### Локальное тестирование:

1. **Запуск сервера**:

   ```bash
   cd /Users/admin/Desktop/Coding/AutoBaza/backend
   python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

2. **Тестирование endpoints**:

   ```bash
   # Демо данные
   curl "http://localhost:8000/api/v1/lotte/cars/demo?count=5"

   # Статистика
   curl "http://localhost:8000/api/v1/lotte/cars/stats"

   # Дата аукциона (требует доступ к сайту)
   curl "http://localhost:8000/api/v1/lotte/auction-date"
   ```

3. **Документация API**:
   Откройте http://localhost:8000/docs в браузере

## Troubleshooting

### Частые проблемы:

1. **ImportError: cannot import name 'settings'**

   - Убедитесь, что в `app/core/config.py` есть `settings = get_settings()`

2. **Ошибки аутентификации**

   - Проверьте учетные данные в `auctions-auth.txt`
   - Убедитесь в доступности сайта Lotte

3. **Timeout ошибки**

   - Проверьте интернет соединение
   - Увеличьте timeout в настройках

4. **Файлы примеров не найдены**
   - Убедитесь, что HTML файлы находятся в корне проекта
   - Используйте демо endpoint вместо тестового

### Логи:

Логи сохраняются в `logs/app.log` и содержат подробную информацию о работе парсера.

## Заключение

Система Lotte полностью интегрирована в AutoBaza Parser API и готова к использованию. Она предоставляет гибкий API для работы с аукционом Lotte, включая проверку дат, парсинг автомобилей и кеширование для оптимальной производительности.
