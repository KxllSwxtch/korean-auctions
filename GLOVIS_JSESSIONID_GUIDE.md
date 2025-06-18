# Руководство по работе с JSESSIONID для Glovis аукциона

## 📋 Обзор

Этот документ описывает систему управления сессиями (JSESSIONID) для Glovis аукциона, включая автоматическое обновление cookies из curl запросов.

## 🔧 Что было реализовано

### 1. Обновление cookies в GlovisService

- **Файл**: `app/services/glovis_service.py`
- **Метод**: `_get_fresh_cookies()` обновлен с новыми cookies из `glovis-curl-request.py`
- **JSESSIONID**: `35Giap8x5e0ZG5VZ1Cpo9YMm2atfJuTA2y5kuwiu39qbCS0kAlEEbYh0hTsD9vvQ5.QXV0b0F1Y3Rpb24vQXV0b0F1Y3Rpb24y`

### 2. Обновление параметров запроса

- **Номер аукциона**: изменен с `747` на `748`
- **Временные рамки**: обновлены на `20250617-20250618`
- **Prime аукцион**: включена поддержка VIP/VVIP участников

### 3. Утилита для автоматического обновления

- **Файл**: `app/utils/glovis_cookies_updater.py`
- **Класс**: `GlovisCookiesUpdater`
- **Возможности**:
  - Извлечение cookies из Python curl файлов
  - Валидация JSESSIONID формата
  - Автоматическое обновление сессии

### 4. Admin API endpoints

- **GET** `/api/v1/glovis/admin/session-info` - информация о текущей сессии
- **POST** `/api/v1/glovis/admin/update-cookies` - обновление cookies из curl файла

## 🚀 Использование

### Проверка статуса сессии

```bash
curl -X GET "http://localhost:8000/api/v1/glovis/admin/session-info"
```

**Ответ:**

```json
{
  "success": true,
  "session_info": {
    "session_valid": true,
    "jsessionid": "35Giap8x5e0ZG5VZ1Cpo...",
    "cookies_count": 11,
    "session_created": "2025-06-18T09:05:08.594156",
    "session_expired": false
  }
}
```

### Обновление cookies из curl файла

```bash
curl -X POST "http://localhost:8000/api/v1/glovis/admin/update-cookies?file_path=glovis-curl-request.py"
```

**Ответ:**

```json
{
  "success": true,
  "message": "Cookies успешно обновлены из glovis-curl-request.py",
  "jsessionid": "35Giap8x5e0ZG5VZ1Cpo...",
  "session_valid": true,
  "cookies_count": 11
}
```

### Проверка работы API

```bash
# Получение автомобилей
curl -X GET "http://localhost:8000/api/v1/glovis/cars?page=1"

# Количество полученных автомобилей
curl -X GET "http://localhost:8000/api/v1/glovis/cars?page=1" | jq '.cars | length'
```

## 📁 Структура файлов

```
backend/
├── app/
│   ├── services/
│   │   └── glovis_service.py          # Основной сервис с обновленными cookies
│   ├── utils/
│   │   └── glovis_cookies_updater.py  # Утилита для обновления cookies
│   └── routes/
│       └── glovis.py                  # API endpoints включая admin функции
└── glovis-curl-request.py             # Файл с рабочими cookies
```

## 🔄 Автоматическое обновление cookies

### Из curl файла

1. Поместите новый curl запрос в файл `glovis-curl-request.py`
2. Вызовите endpoint: `POST /api/v1/glovis/admin/update-cookies`
3. Система автоматически извлечет и применит новые cookies

### Программно

```python
from app.services.glovis_service import GlovisService
from app.utils.glovis_cookies_updater import GlovisCookiesUpdater

# Создание экземпляров
service = GlovisService()
updater = GlovisCookiesUpdater()

# Обновление из файла
result = updater.update_cookies_from_curl_file("glovis-curl-request.py")
if result['success']:
    service.update_cookies(result['cookies'])
```

## ⚠️ Важные замечания

1. **Срок жизни сессии**: JSESSIONID имеет ограниченный срок жизни (обычно 30 минут)
2. **Формат JSESSIONID**: должен соответствовать формату `base64_string.server_info`
3. **Безопасность**: cookies содержат конфиденциальную информацию сессии
4. **Мониторинг**: регулярно проверяйте валидность сессии через admin endpoints

## 🧪 Тестирование

Система протестирована и работает корректно:

- ✅ Извлечение cookies из curl файла
- ✅ Обновление сессии в runtime
- ✅ Проверка валидности JSESSIONID
- ✅ Получение данных автомобилей (18 автомобилей на странице)
- ✅ Admin API endpoints

## 📊 Результаты тестирования

```
🧪 Тестирование системы обновления cookies Glovis
==================================================
✅ Данные успешно извлечены из glovis-curl-request.py
🍪 Найдено cookies: 11
🔑 JSESSIONID: 35Giap8x5e0ZG5VZ1Cpo...b24vQXV0b0F1Y3Rpb24y
📊 Сессия валидна: ✅ True
🚗 Получено автомобилей: ✅ 18
🎯 Результат: ✅ Cookies успешно обновлены и работают!
```

## 🔧 Устранение неполадок

### Проблема: Сессия невалидна

**Решение**: Обновите cookies через admin endpoint или получите новый curl запрос

### Проблема: Не удается извлечь cookies

**Решение**: Проверьте формат файла `glovis-curl-request.py`

### Проблема: JSESSIONID имеет неверный формат

**Решение**: Убедитесь, что JSESSIONID содержит точку и две части

---

**Обновлено**: 2025-01-16  
**Статус**: ✅ Рабочий и протестированный
