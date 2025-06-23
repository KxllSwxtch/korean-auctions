# AutoBaza Backend API

Модульный API для парсинга автомобильных аукционов Южной Кореи.

## 🚗 Автомобильные Аукционы

Этот API предоставляет доступ к данным различных корейских автомобильных аукционов.

### 🏢 Поддерживаемые аукционы

- **Autohub** (`/api/v1/autohub/`) - Премиальный аукцион
- **Glovis** (`/api/v1/glovis/`) - Крупнейший аукцион Южной Кореи
- **Lotte** (`/api/v1/lotte/`) - Аукцион сети Lotte
- **KCar** (`/api/v1/kcar/`) - Еженедельные аукционы

### 📊 Общие возможности

Все аукционы поддерживают:

- Получение списка автомобилей с фильтрацией
- Детальную информацию об автомобилях
- Статистику и аналитику
- Тестовые данные для разработки

## 🛠 Технологический стек

- **FastAPI** - современный веб-фреймворк
- **BeautifulSoup4** - парсинг HTML
- **Pydantic** - валидация и сериализация данных
- **Loguru** - структурированное логирование
- **Requests** - HTTP клиент с retry механизмом
- **Python 3.8+**

## 📋 Установка и запуск

```bash
# Клонирование репозитория
git clone <repository-url>
cd backend

# Установка зависимостей
pip install -r requirements.txt

# Запуск сервера
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## 📖 API Документация

После запуска сервера документация доступна по адресам:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 🔗 Endpoints

### Autohub API

- `GET /api/v1/autohub/cars` - Список автомобилей (требует авторизации)
- `GET /api/v1/autohub/cars/test` - Тестовые данные
- `GET /api/v1/autohub/cars/demo` - Демо данные
- `GET /api/v1/autohub/cars/stats` - Статистика

### Lotte Auction API

- `GET /api/v1/lotte/cars` - Список автомобилей (требует авторизации)
- `GET /api/v1/lotte/cars/test` - Тестовые данные
- `GET /api/v1/lotte/cars/demo` - Демо данные
- `GET /api/v1/lotte/cars/stats` - Статистика

### KCar API

**Основные endpoints:**

- `GET /api/v1/kcar/cars` - Получение списка автомобилей с weekly аукционов (требует авторизации)
- `GET /api/v1/kcar/cars/test` - Тестовые данные (10 автомобилей)
- `GET /api/v1/kcar/cars/demo` - Расширенные демо данные (до 100 автомобилей)
- `GET /api/v1/kcar/cars/stats` - Статистика по автомобилям

**Формат ответа:**

```json
{
  "auctionReqVo": {...},
  "CAR_LIST": [
    {
      "CAR_ID": "CA20323456",
      "CAR_NM": "현대 소나타 DN8",
      "CNO": "12서1234",
      "THUMBNAIL": "https://www.kcarauction.com/attachment/CAR_IMG/2032/CA20323456/CA203234567hq111xq_370.JPG",
      "THUMBNAIL_MOBILE": "https://www.kcarauction.com/attachment/CAR_IMG/2032/CA20323456/CA203234567hq111xq_640.JPG",
      "AUC_STRT_PRC": "15000000",
      "AUC_STAT_NM": "위클리 대기",
      "FORM_YR": "2020",
      "MILG": "45000",
      "EXTERIOR_COLOR_NM": "흰색",
      "CAR_LOCT": "서울경매장",
      // ... другие поля
    }
  ],
  "total_count": 100,
  "success": true,
  "message": "Успешно получено 100 автомобилей"
}
```

**Пример ответа при отсутствии торгов (нормальное состояние):**

```json
{
  "auctionReqVo": null,
  "CAR_LIST": [],
  "total_count": 0,
  "success": true,
  "message": "В данный момент нет доступных автомобилей в weekly аукционах. Торги могли завершиться или еще не начаться."
}
```

**Пример ответа при ошибке API (fallback на демо данные):**

```json
{
  "auctionReqVo": null,
  "CAR_LIST": [
    /* демо данные */
  ],
  "total_count": 50,
  "success": true,
  "message": "Произошла ошибка API. Показаны демо данные (50 автомобилей)"
}
```

**Новые поля изображений:**

- `THUMBNAIL` - URL основной фотографии автомобиля (370px ширина)
- `THUMBNAIL_MOBILE` - URL мобильной фотографии автомобиля (640px ширина)

**Особенности:**

- Поддержка только **weekly аукционов** (оптимизация)
- Авторизация через логин/пароль из конфигурации
- Автоматическое формирование полных URL для изображений
- Обработка корейских символов в названиях
- Timeout 30 секунд для запросов
- **Корректная обработка пустых списков**: Пустой список автомобилей считается нормальным состоянием (торги завершены/не начались)
- **Fallback на демо данные**: Только при реальных ошибках API, не при пустых списках

**Статус реальных данных:**

- ✅ Авторизация работает
- ✅ Пустой список = торги завершены (нормальное состояние)
- ⚠️ Weekly аукционы зависят от расписания KCar
- ✅ При ошибках API показываются демо данные

### Общие endpoints

- `GET /health` - Проверка состояния сервиса
- `GET /` - Информация о API

## 🔐 Авторизация

Парсеры поддерживают авторизацию на целевых сайтах:

### Autohub (autohub.co.kr)

- Логин: 785701
- Пароль: 782312

### Lotte Auction (lotteauction.co.kr)

- Логин: 119102
- Пароль: for1234@

### KCar Auction (kcarauction.com)

- Логин: autobaza
- Пароль: for1657721@

## 📊 Примеры использования

### Получение тестовых данных

```bash
# Autohub тестовые данные
curl "http://localhost:8000/api/v1/autohub/cars/test?count=5"

# Lotte тестовые данные
curl "http://localhost:8000/api/v1/lotte/cars/test?count=5"

# KCar тестовые данные
curl "http://localhost:8000/api/v1/kcar/cars/test?count=5"
```

### Получение реальных данных

```bash
# Autohub автомобили с фильтрацией
curl "http://localhost:8000/api/v1/autohub/cars?manufacturer=현대&page_size=10"

# Lotte автомобили
curl "http://localhost:8000/api/v1/lotte/cars?page_size=20"

# KCar автомобили (только weekly аукционы) - ✅ РАБОТАЕТ
curl "http://localhost:8000/api/v1/kcar/cars?page_size=15"
```

### Статистика

```bash
# Статистика по всем сервисам
curl "http://localhost:8000/api/v1/autohub/cars/stats"
curl "http://localhost:8000/api/v1/lotte/cars/stats"
curl "http://localhost:8000/api/v1/kcar/cars/stats"
```

## 🏗 Архитектура проекта

```
app/
├── core/           # Основные компоненты
│   ├── config.py   # Конфигурация
│   └── logging.py  # Настройка логирования
├── models/         # Pydantic модели
│   ├── autohub.py  # Модели для Autohub
│   ├── lotte.py    # Модели для Lotte
│   └── kcar.py     # Модели для KCar
├── parsers/        # HTML парсеры
│   ├── autohub_parser.py
│   ├── lotte_parser.py
│   └── kcar_parser.py
├── services/       # HTTP клиенты
│   ├── autohub_service.py
│   ├── lotte_service.py
│   └── kcar_service.py
└── routes/         # FastAPI маршруты
    ├── autohub.py
    ├── lotte.py
    └── kcar.py
```

## 🎯 Особенности

### Надежность

- Retry механизм для HTTP запросов
- Обработка SSL/TLS ошибок
- Fallback на тестовые данные при недоступности сервиса
- KCar: работа только с weekly аукционами (Lane A + Lane B)

### Производительность

- Асинхронная обработка запросов
- Эффективный парсинг с BeautifulSoup4
- Минимальные зависимости

### Расширяемость

- Модульная архитектура
- Легко добавлять новые аукционы
- Унифицированные интерфейсы

### Мониторинг

- Подробное логирование операций
- Статистика и метрики
- Health checks

## 🔧 Конфигурация

Создайте файл `.env` для настроек:

```env
LOG_LEVEL=INFO
DEBUG=True
```

## 🐛 Troubleshooting

### Ошибка авторизации

- Проверьте учетные данные в файле конфигурации
- Убедитесь, что сайт доступен
- Проверьте логи на предмет SSL ошибок

### Таймауты соединения

- Увеличьте таймаут в настройках сервиса
- Проверьте интернет-соединение
- Используйте тестовые endpoints для отладки

### Пустые результаты

- Проверьте фильтры запроса
- Убедитесь в корректности параметров
- Используйте демо данные для тестирования

## 📈 Мониторинг

Для мониторинга состояния сервиса используйте:

```bash
# Проверка состояния
curl http://localhost:8000/health

# Информация о версии
curl http://localhost:8000/

# Специфичная информация по сервисам
curl http://localhost:8000/api/v1/kcar/info
```

## 🚀 Развертывание

### Docker (рекомендуется)

```bash
# Создание Docker образа
docker build -t autobaza-api .

# Запуск контейнера
docker run -p 8000:8000 autobaza-api
```

### Production

```bash
# Установка production сервера
pip install gunicorn

# Запуск с Gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

## 🤝 Вклад в проект

1. Fork проекта
2. Создайте feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit изменения (`git commit -m 'Add some AmazingFeature'`)
4. Push в branch (`git push origin feature/AmazingFeature`)
5. Создайте Pull Request

## 📄 Лицензия

Этот проект лицензирован под MIT License.

## 📞 Поддержка

Для получения поддержки:

- Создайте Issue в GitHub
- Проверьте документацию в `/docs`
- Используйте тестовые endpoints для отладки

## 🔥 Новая система фильтрации KCar

### 📋 Обзор

Система фильтрации KCar предоставляет мощные инструменты для поиска автомобилей:

1. **Производители** - Статический список поддерживаемых марок
2. **Модели** - Динамическое получение моделей по производителю
3. **Поколения** - Получение поколений по модели
4. **Расширенный поиск** - Поиск с множественными фильтрами

### 🛡️ Эндпоинты системы фильтрации

#### 1. Получение производителей

```http
GET /api/v1/kcar/manufacturers
```

Возвращает статический список всех поддерживаемых производителей автомобилей.

**Пример ответа:**

```json
{
  "manufacturers": [
    {"code": "001", "name": "현대", "name_en": "Hyundai"},
    {"code": "002", "name": "기아", "name_en": "Kia"},
    ...
  ],
  "total_count": 8,
  "success": true
}
```

#### 2. Получение моделей

```http
GET /api/v1/kcar/models/{manufacturer_code}?input_car_code=001
```

**Параметры:**

- `manufacturer_code` (обязательный) - Код производителя (например, "002" для Kia)
- `input_car_code` (опциональный) - Код типа автомобиля (по умолчанию "001")

**Пример запроса:**

```bash
curl -X GET "http://localhost:8000/api/v1/kcar/models/002"
```

**Пример ответа:**

```json
{
  "models": [
    {"manufacturer_code": "002", "model_group_code": "001", "model_group_name": "K5"},
    {"manufacturer_code": "002", "model_group_code": "060", "model_group_name": "K3"},
    ...
  ],
  "success": true,
  "message": "Успешно получено 30 моделей"
}
```

#### 3. Получение поколений

```http
GET /api/v1/kcar/generations/{manufacturer_code}/{model_group_code}?input_car_code=001
```

**Параметры:**

- `manufacturer_code` - Код производителя
- `model_group_code` - Код группы модели
- `input_car_code` (опциональный) - Код типа автомобиля

**Пример запроса:**

```bash
curl -X GET "http://localhost:8000/api/v1/kcar/generations/002/001"
```

**Пример ответа:**

```json
{
  "generations": [
    {
      "model_code": "188",
      "model_name": "더 뉴 K5 3세대",
      "model_detail_name": "더 뉴 K5 3세대(23년~현재)"
    },
    ...
  ],
  "success": true,
  "message": "Успешно получено 11 поколений"
}
```

#### 4. Расширенный поиск

```http
POST /api/v1/kcar/search
```

**Тело запроса (JSON):**

```json
{
  "manufacturer_code": "002", // Код производителя (опционально)
  "model_group_code": "001", // Код группы модели (опционально)
  "model_code": "188", // Код поколения (опционально)
  "year_from": "2020", // Год выпуска от (опционально)
  "year_to": "2023", // Год выпуска до (опционально)
  "price_from": "1000000", // Стартовая цена от (опционально)
  "price_to": "5000000", // Стартовая цена до (опционально)
  "mileage_from": "0", // Пробег от (опционально)
  "mileage_to": "100000", // Пробег до (опционально)
  "fuel_type": "가솔린", // Тип топлива (опционально)
  "transmission": "오토", // Коробка передач (опционально)
  "color_code": "007", // Код цвета (опционально)
  "auction_type": "weekly", // Тип аукциона (по умолчанию "weekly")
  "lane_type": "A", // Тип лейна (по умолчанию "A")
  "auction_location": "172", // Код места аукциона (опционально)
  "car_number": "10다0625", // Номер автомобиля (опционально)
  "page": 1, // Номер страницы (по умолчанию 1)
  "page_size": 18, // Размер страницы (по умолчанию 18)
  "sort_order": "" // Порядок сортировки (опционально)
}
```

**Пример запроса:**

```bash
curl -X POST "http://localhost:8000/api/v1/kcar/search" \
  -H "Content-Type: application/json" \
  -d '{
    "manufacturer_code": "002",
    "model_group_code": "001",
    "page": 1,
    "page_size": 5
  }'
```

#### 5. Информация о фильтрах

```http
GET /api/v1/kcar/search/filters/info
```

Возвращает подробную информацию о всех доступных фильтрах, их типах и возможных значениях.

### 🔄 Типичный workflow использования

```python
import requests

base_url = "http://localhost:8000/api/v1/kcar"

# 1. Получаем список производителей
manufacturers = requests.get(f"{base_url}/manufacturers").json()
print("Производители:", [m["name_en"] for m in manufacturers["manufacturers"]])

# 2. Выбираем Kia (код "002") и получаем модели
models = requests.get(f"{base_url}/models/002").json()
print("Модели Kia:", [m["model_group_name"] for m in models["models"]])

# 3. Выбираем K5 (код "001") и получаем поколения
generations = requests.get(f"{base_url}/generations/002/001").json()
print("Поколения K5:", [g["model_detail_name"] for g in generations["generations"]])

# 4. Ищем конкретные автомобили
search_filters = {
    "manufacturer_code": "002",
    "model_group_code": "001",
    "year_from": "2020",
    "page_size": 10
}

cars = requests.post(f"{base_url}/search", json=search_filters).json()
print(f"Найдено автомобилей: {len(cars.get('cars', []))}")
```

### 📝 Коды производителей

**Корейские производители (001_XXX):**
| Код | Название | English |
| ------- | --------------------- | -------------------------- |
| 001_001 | 현대 | Hyundai |
| 001_007 | 제네시스 | Genesis |
| 001_002 | 기아 | Kia |
| 001_003 | 쉐보레(GM대우) | Chevrolet (GM Daewoo) |
| 001_005 | 르노코리아(삼성) | Renault Korea (Samsung) |
| 001_004 | KG모빌리티(쌍용) | KG Mobility (SsangYong) |
| 001_088 | 대우버스 | Daewoo Bus |
| 001_006 | 기타 제조사 | Other Domestic |

**Импортные производители - Европа (002_XXX):**
| Код | Название | English |
| ------- | ----------- | ------------- |
| 002_013 | 벤츠 | Mercedes-Benz |
| 002_012 | BMW | BMW |
| 002_011 | 아우디 | Audi |
| 002_014 | 폭스바겐 | Volkswagen |
| 002_054 | 미니 | MINI |
| 002_017 | 볼보 | Volvo |
| 002_091 | 폴스타 | Polestar |
| 002_015 | 포르쉐 | Porsche |
| 002_081 | 스마트 | Smart |
| 002_053 | 마세라티 | Maserati |
| 002_019 | 재규어 | Jaguar |
| 002_020 | 랜드로버 | Land Rover |
| 002_021 | 푸조 | Peugeot |
| 002_022 | 시트로엥 | Citroën |
| 002_018 | 피아트 | Fiat |
| 002_041 | 페라리 | Ferrari |
| 002_049 | 람보르기니 | Lamborghini |
| 002_084 | 맥라렌 | McLaren |
| 002_080 | 마이바흐 | Maybach |
| 002_050 | 벤틀리 | Bentley |
| 002_047 | 롤스로이스 | Rolls-Royce |
| 002_016 | 사브 | Saab |
| 002_070 | 애스턴마틴 | Aston Martin |

**Импортные производители - Япония (002_XXX):**
| Код | Название | English |
| ------- | ----------- | ----------- |
| 002_035 | 렉서스 | Lexus |
| 002_031 | 도요타 | Toyota |
| 002_058 | 인피니티 | Infiniti |
| 002_027 | 혼다 | Honda |
| 002_033 | 닛산 | Nissan |
| 002_030 | 미쯔비시 | Mitsubishi |
| 002_037 | 스즈키 | Suzuki |
| 002_029 | 마쯔다 | Mazda |
| 002_028 | 이스즈 | Isuzu |
| 002_052 | 스바루 | Subaru |
| 002_051 | 다이하쯔 | Daihatsu |
| 002_057 | 어큐라 | Acura |

**Импортные производители - США (002_XXX):**
| Код | Название | English |
| ------- | ----------- | ---------- |
| 002_087 | 테슬라 | Tesla |
| 002_024 | 포드 | Ford |
| 002_083 | 지프 | Jeep |
| 002_043 | 캐딜락 | Cadillac |
| 002_023 | 크라이슬러 | Chrysler |
| 002_044 | 링컨 | Lincoln |
| 002_056 | GMC | GMC |
| 002_034 | 닷지 | Dodge |
| 002_038 | 쉐보레 | Chevrolet |
| 002_048 | 험머 | Hummer |

**Импортные производители - Китай (002_XXX):**
| Код | Название | English |
| ------- | ----------- | ----------------- |
| 002_090 | 동풍소콘 | Dongfeng Sokon |
| 002_086 | 북기은상 | BAIC |
| 002_085 | 포톤 | Foton |
| 002_093 | BYD | BYD |
| 002_092 | 선롱 버스 | Sunlong Bus |

**Коммерческие автомобили (003_XXX):**
| Код | Название | English |
| ------- | --------------------- | --------------------------------- |
| 003_005 | 카고(화물)트럭 | Cargo Truck |
| 003_003 | 윙바디/탑 | Wing Body/Top |
| 003_002 | 버스 | Bus |
| 003_007 | 크레인 형태 | Crane Type |
| 003_004 | 차량견인/운송 | Vehicle Towing/Transport |
| 003_011 | 폐기/음식물수송 | Waste/Food Transport |
| 003_012 | 활어차 | Live Fish Transport |
| 003_008 | 탱크로리 | Tank Lorry |
| 003_010 | 트렉터 | Tractor |
| 003_009 | 트레일러 | Trailer |
| 003_001 | 덤프/건설/중기 | Dump/Construction/Heavy Equipment |
| 003_006 | 캠핑카/캠핑 트레일러 | Camping Car/Trailer |
| 003_999 | 기타 | Others |

### 🎯 Полезные советы

**Система кодов производителей:**

- **UI коды** (001_001, 002_013, etc.) - используются для отображения в интерфейсе
- **API коды** (001, 002, 007, etc.) - используются для работы с API
- Система автоматически преобразует UI коды в API коды
- Все импортные производители (002_XXX) преобразуются в код "007" (Import)
- Коммерческие автомобили (003_XXX) преобразуются в код "008" (Others)

**Аутентификация:**

- Для получения моделей и поколений требуется авторизация
- Для расширенного поиска требуется авторизация
- Список производителей доступен без авторизации

**Лимиты и пагинация:**

- Максимум 100 результатов на страницу
- По умолчанию 18 результатов на страницу
- Используйте параметры `page` и `page_size` для навигации

**Отладка:**

- Используйте endpoint `/api/v1/kcar/search/filters/info` для получения схемы фильтров
- Логи содержат информацию о преобразовании кодов производителей
- При ошибках проверьте корректность кодов производителя и модели
