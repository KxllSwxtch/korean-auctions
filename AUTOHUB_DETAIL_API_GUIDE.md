# Autohub Car Detail API Guide

## 🚗 Обзор

API для получения детальной информации об автомобиле с аукциона Autohub. Поддерживает два способа запроса: POST с телом запроса и GET с параметрами.

## 📡 Endpoints

### 1. POST /api/v1/autohub/car-detail

Получение детальной информации через POST запрос с JSON телом.

**Request Body:**

```json
{
  "auction_number": "1329",
  "auction_date": "2025-06-18",
  "auction_title": "안성 2025/06/18 1329회차 경매",
  "auction_code": "AC202506110001",
  "receive_code": "RC202506130039",
  "page_number": 1,
  "page_size": 10,
  "sort_flag": "entry"
}
```

### 2. GET /api/v1/autohub/car-detail/{auction_number}

Альтернативный способ через GET с параметрами запроса.

**URL:** `/api/v1/autohub/car-detail/1329?auction_date=2025-06-18&auction_title=안성%202025/06/18%201329회차%20경매&auction_code=AC202506110001&receive_code=RC202506130039`

## 🔧 Параметры запроса

| Параметр         | Тип     | Обязательный | Описание                                |
| ---------------- | ------- | ------------ | --------------------------------------- |
| `auction_number` | string  | ✅           | Номер аукциона                          |
| `auction_date`   | string  | ✅           | Дата аукциона (YYYY-MM-DD)              |
| `auction_title`  | string  | ✅           | Название аукциона                       |
| `auction_code`   | string  | ✅           | Код аукциона                            |
| `receive_code`   | string  | ✅           | Код получения                           |
| `page_number`    | integer | ❌           | Номер страницы (по умолчанию: 1)        |
| `page_size`      | integer | ❌           | Размер страницы (по умолчанию: 10)      |
| `sort_flag`      | string  | ❌           | Флаг сортировки (по умолчанию: "entry") |

## 📊 Структура ответа

```json
{
  "success": true,
  "data": {
    "title": "[1001] 기아 더 뉴 니로(19년~현재) 1.6 HEV 트렌디",
    "starting_price": "0",
    "auction_number": "",
    "auction_date": "",
    "auction_title": "",
    "auction_code": "",
    "car_info": {
      "car_id": "1001",
      "auction_number": "1001",
      "car_number": "126호9942",
      "parking_number": "B10-6479",
      "title": "2022 G4LE 하이브리드",
      "year": 2022,
      "mileage": "76,229",
      "transmission": "오토",
      "fuel_type": "하이브리드",
      "status": "출품등록",
      "entry_number": "1001",
      "vin_number": "KNACA81CGNA500921",
      "engine_type": "G4LE",
      "displacement": "1,580cc",
      "history": "렌터카",
      "color": "기타",
      "vehicle_type": "승용",
      "tax_type": "면세사업자",
      "accident_history": "사고이력상세"
    },
    "performance_info": {
      "rating": "골격 : A   외관 : D",
      "inspector": "이성원",
      "stored_items": [],
      "stored_items_present": "N",
      "notes": "-"
    },
    "options": {
      "convenience": [],
      "safety": [],
      "exterior": [],
      "interior": []
    },
    "images": [
      {
        "large_url": "http://www.sellcarauction.co.kr/AJSCIMG/upload/upload_file/INSPECT/2025/202506/IP202506130039/AT174978895311474_L.jpg",
        "small_url": "http://www.sellcarauction.co.kr/AJSCIMG/upload/upload_file/INSPECT/2025/202506/IP202506130039/AT174978895311474_S.jpg",
        "sequence": 0
      }
    ],
    "parsed_at": "2025-01-21T10:30:00",
    "source_url": "https://www.autohubauction.co.kr"
  },
  "error": null,
  "request_params": {
    "auction_number": "1329",
    "auction_date": "2025-06-18",
    "auction_title": "안성 2025/06/18 1329회차 경매",
    "auction_code": "AC202506110001",
    "receive_code": "RC202506130039",
    "page_number": 1,
    "page_size": 10,
    "sort_flag": "entry"
  }
}
```

## 🛠️ Дополнительные endpoints

### Установка cookies для аутентификации

**POST /api/v1/autohub/auth/set-cookies**

```json
{
  "WMONID": "your_wmonid",
  "gubun": "on",
  "userid": "your_userid",
  "JSESSIONID": "your_jsessionid"
}
```

### Проверка здоровья сервиса

**GET /api/v1/autohub/health**

```json
{
  "status": "healthy",
  "service": "autohub",
  "version": "1.0.0"
}
```

## 🔍 Пример использования

### Python (requests)

```python
import requests

# POST запрос
url = "http://localhost:8000/api/v1/autohub/car-detail"
data = {
    "auction_number": "1329",
    "auction_date": "2025-06-18",
    "auction_title": "안성 2025/06/18 1329회차 경매",
    "auction_code": "AC202506110001",
    "receive_code": "RC202506130039"
}

response = requests.post(url, json=data)
result = response.json()

if result['success']:
    car_detail = result['data']
    print(f"Автомобиль: {car_detail['title']}")
    print(f"Год: {car_detail['car_info']['year']}")
    print(f"Пробег: {car_detail['car_info']['mileage']}")
else:
    print(f"Ошибка: {result['error']}")
```

### cURL

```bash
# POST запрос
curl -X POST "http://localhost:8000/api/v1/autohub/car-detail" \
  -H "Content-Type: application/json" \
  -d '{
    "auction_number": "1329",
    "auction_date": "2025-06-18",
    "auction_title": "안성 2025/06/18 1329회차 경매",
    "auction_code": "AC202506110001",
    "receive_code": "RC202506130039"
  }'

# GET запрос
curl "http://localhost:8000/api/v1/autohub/car-detail/1329?auction_date=2025-06-18&auction_title=안성%202025/06/18%201329회차%20경매&auction_code=AC202506110001&receive_code=RC202506130039"
```

## ⚠️ Важные замечания

1. **Аутентификация**: Для доступа к данным может потребоваться установка cookies аутентификации через `/auth/set-cookies`

2. **Rate Limiting**: Не делайте слишком частые запросы, чтобы избежать блокировки со стороны Autohub

3. **Кодировка**: При передаче корейских символов в GET параметрах используйте URL-encoding

4. **Ошибки**: Всегда проверяйте поле `success` в ответе перед обработкой данных

## 🐛 Коды ошибок

- `404 Not Found` - Автомобиль не найден
- `503 Service Unavailable` - Сервис Autohub временно недоступен
- `500 Internal Server Error` - Внутренняя ошибка сервера

## 🚀 Запуск для тестирования

```bash
# Запуск сервера
python main.py

# Swagger UI доступен по адресу:
# http://localhost:8000/docs

# Тестирование парсера
python test_autohub_detail_parser.py
```
