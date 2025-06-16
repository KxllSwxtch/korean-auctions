# 🚗 KCAR Detail API Guide

## Обзор

API для получения детальной информации об автомобиле с аукциона KCAR. Позволяет получить полную информацию о конкретном автомобиле включая технические характеристики, изображения, состояние и аукционную информацию.

## 🔧 Технические детали

### Архитектура

- **Парсер**: `app/parsers/kcar_parser.py` - метод `parse_car_detail_html()`
- **Сервис**: `app/services/kcar_service.py` - метод `get_car_detail()`
- **Модели**: `app/models/kcar.py` - `KCarDetailedCar`, `KCarDetailResponse`
- **API**: `app/routes/kcar.py` - endpoint `/cars/{car_id}/detail`

### Используемые технологии

- **HTTP клиент**: `requests` с сессиями и retry логикой
- **HTML парсер**: `BeautifulSoup4` для извлечения данных
- **Валидация**: `Pydantic` модели для типизации
- **API**: `FastAPI` с автоматической документацией

## 📡 API Endpoint

### GET `/api/v1/kcar/cars/{car_id}/detail`

Получение детальной информации об автомобиле KCAR.

#### Параметры

**Path параметры:**

- `car_id` (string, обязательный) - ID автомобиля (например: `CA20324182`)

**Query параметры:**

- `auction_code` (string, обязательный) - Код аукциона (например: `AC20250604`)
- `page_type` (string, опциональный) - Тип страницы (по умолчанию: `wCfm`)

#### Пример запроса

```bash
curl -X GET "http://127.0.0.1:8000/api/v1/kcar/cars/CA20324182/detail?auction_code=AC20250604&page_type=wCfm"
```

#### Пример ответа

```json
{
  "car": {
    "car_id": "CA20324182",
    "auction_code": "AC20250604",
    "car_number": "20머3749",
    "lot_number": "1001",
    "car_name": "현대 i40 1.7 VGT PYL",
    "manufacturer": "현대",
    "model": "i40 1.7 VGT PYL",
    "year": "2015",
    "registration_date": "2014.10",
    "mileage": "214,143km",
    "fuel_type": "디젤",
    "transmission": "오토",
    "exterior_color": "기타",
    "displacement": "1,685cc",
    "car_type": "중형차",
    "doors": "5",
    "vin": "KMHLB81UBFU097334",
    "engine_type": "D4FD",
    "auction_date": "2025-06-17",
    "start_price": "180 만원",
    "auction_place": "세종경매장",
    "auction_type": "위클리",
    "grade": "D1",
    "seizure_mortgage": "0/0",
    "flood_damage": "보험이력 없음",
    "address": "세종특별자치시 부강면 문곡리 산 249",
    "owner_name": "박광**",
    "owner_id": "******-********",
    "inspection_valid_until": "~ 20251023",
    "main_image": "https://www.kcarauction.com/FILE_UPLOAD/IMAGE_UPLOAD/CAR/2032/CA20324182/CA2032418286u2cd45_832.JPG",
    "all_images": [
      "https://www.kcarauction.com/FILE_UPLOAD/IMAGE_UPLOAD/CAR/2032/CA20324182/CA2032418286u2cd45_1180.JPG",
      "..."
    ],
    "thumbnail_images": [
      "https://www.kcarauction.com/FILE_UPLOAD/IMAGE_UPLOAD/CAR/2032/CA20324182/CA2032418286u2cd45_180.JPG"
    ],
    "usage_type": "상품",
    "created_at": "2025-06-16T15:20:02.379335",
    "updated_at": "2025-06-16T15:20:02.379335"
  },
  "success": true,
  "message": "Успешно извлечена детальная информация для автомобиля CA20324182",
  "source_url": "https://www.kcarauction.com/kcar/auction/weekly_detail/auction_detail_view.do?CAR_ID=CA20324182&AUC_CD=AC20250604&PAGE_TYPE=wCfm"
}
```

## 📋 Структура данных

### KCarDetailedCar

Полная модель автомобиля с детальной информацией:

#### Основные идентификаторы

- `car_id` - ID автомобиля
- `auction_code` - Код аукциона
- `car_number` - Номер автомобиля
- `lot_number` - Номер лота

#### Основная информация

- `car_name` - Полное название автомобиля
- `manufacturer` - Производитель
- `model` - Модель

#### Технические характеристики

- `year` - Год выпуска
- `registration_date` - Дата первой регистрации
- `mileage` - Пробег
- `fuel_type` - Тип топлива
- `transmission` - Коробка передач
- `exterior_color` - Цвет кузова
- `displacement` - Объем двигателя
- `car_type` - Тип кузова
- `doors` - Количество дверей
- `vin` - VIN номер
- `engine_type` - Тип двигателя

#### Аукционная информация

- `auction_date` - Дата аукциона
- `start_price` - Стартовая цена
- `auction_place` - Место проведения аукциона
- `auction_type` - Тип аукциона

#### Состояние и оценка

- `grade` - Оценка состояния
- `seizure_mortgage` - Арест/залог
- `flood_damage` - Повреждение от наводнения
- `inspection_valid_until` - Техосмотр действителен до

#### Местоположение

- `address` - Подробный адрес

#### Владелец (анонимизированные данные)

- `owner_name` - Имя владельца (зашифрованное)
- `owner_company` - Компания владельца
- `owner_id` - ID владельца (зашифрованное)

#### Изображения

- `main_image` - Основное изображение
- `all_images` - Все изображения автомобиля (высокое разрешение)
- `thumbnail_images` - Миниатюры изображений

#### Дополнительная информация

- `usage_type` - Тип использования
- `created_at` - Время создания записи
- `updated_at` - Время последнего обновления

## 🧪 Тестирование

### Тест парсера

```bash
python test_kcar_detail_parser.py
```

Тестирует парсер на примере HTML файла `KCAR_CAR_PAGE_EXAMPLE.html`.

### Тест API

```bash
python test_kcar_api.py
```

Тестирует API endpoint (требует запущенный сервер).

### Запуск сервера

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

## 🔍 Примеры использования

### Python requests

```python
import requests

# Получение детальной информации
response = requests.get(
    "http://127.0.0.1:8000/api/v1/kcar/cars/CA20324182/detail",
    params={
        "auction_code": "AC20250604",
        "page_type": "wCfm"
    }
)

if response.status_code == 200:
    data = response.json()
    car = data['car']
    print(f"Автомобиль: {car['car_name']}")
    print(f"Год: {car['year']}")
    print(f"Пробег: {car['mileage']}")
    print(f"Цена: {car['start_price']}")
else:
    print(f"Ошибка: {response.status_code}")
```

### JavaScript fetch

```javascript
const carId = "CA20324182"
const auctionCode = "AC20250604"

fetch(
  `http://127.0.0.1:8000/api/v1/kcar/cars/${carId}/detail?auction_code=${auctionCode}`
)
  .then((response) => response.json())
  .then((data) => {
    if (data.success) {
      const car = data.car
      console.log("Автомобиль:", car.car_name)
      console.log("Изображений:", car.all_images.length)
    }
  })
  .catch((error) => console.error("Ошибка:", error))
```

## ⚠️ Ограничения и особенности

### Авторизация

- Требуется авторизация на сайте KCAR
- Учетные данные настраиваются в сервисе
- Автоматическое переподключение при истечении сессии

### Производительность

- Время ответа: 2-5 секунд (зависит от размера страницы)
- Retry логика: до 3 попыток при ошибках
- Таймаут: 30 секунд

### Данные

- Некоторые поля могут быть пустыми (зависит от автомобиля)
- Изображения возвращаются в полном разрешении
- Персональные данные владельца анонимизированы

## 🔧 Настройка и конфигурация

### Переменные окружения

```bash
# В файле .env или переменных окружения
KCAR_USERNAME=your_username
KCAR_PASSWORD=your_password
```

### Настройки сервиса

В `app/services/kcar_service.py`:

```python
# Учетные данные
self.username = "your_username"
self.password = "your_password"

# Таймауты
self.session.timeout = 30

# Retry настройки
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
```

## 🐛 Обработка ошибок

### Коды ошибок

- `400` - Неверные параметры запроса
- `404` - Автомобиль не найден
- `422` - Ошибка валидации параметров
- `500` - Внутренняя ошибка сервера

### Типичные ошибки

1. **Ошибка авторизации**

   ```json
   {
     "success": false,
     "message": "Ошибка авторизации"
   }
   ```

2. **Автомобиль не найден**

   ```json
   {
     "error": "Не удалось получить детальную информацию об автомобиле",
     "car_id": "CA20324182",
     "auction_code": "AC20250604"
   }
   ```

3. **Таймаут**
   ```json
   {
     "success": false,
     "message": "Таймаут получения детальной информации"
   }
   ```

## 📚 Дополнительные ресурсы

- [FastAPI документация](https://fastapi.tiangolo.com/)
- [Pydantic модели](https://pydantic-docs.helpmanual.io/)
- [BeautifulSoup документация](https://www.crummy.com/software/BeautifulSoup/bs4/doc/)
- [Requests документация](https://docs.python-requests.org/)

## 🔄 Обновления и версионирование

### Версия 1.0

- Базовый парсинг детальной информации
- Извлечение технических характеристик
- Получение изображений
- API endpoint

### Планируемые улучшения

- Кэширование результатов
- Асинхронная обработка
- Дополнительные поля данных
- Оптимизация производительности
