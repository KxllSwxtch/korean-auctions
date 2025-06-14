# AutoBaza Backend API

Модульный API для парсинга автомобильных аукционов Южной Кореи.

## 🚗 Поддерживаемые аукционы

- **Autohub** (autohub.co.kr) - Ведущий автомобильный аукцион
- **Lotte Auction** (lotteauction.co.kr) - Аукцион Lotte Group
- **KCar Auction** (kcarauction.com) - Специализированный K-Car аукцион

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
