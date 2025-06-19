# 🔧 Восстановление сессии Glovis после выхода из приложения

## 📋 Проблема

После выхода из приложения Glovis на Windows, все сохраненные cookies стали невалидными, и API возвращает ошибку "Не удалось получить данные с сайта".

## 🎯 Решение: Получение новых cookies

### Вариант 1: Автоматическое получение (если работает)

```bash
python fix_glovis_session.py
```

### Вариант 2: Ручное получение cookies (рекомендуется)

#### Шаг 1: Откройте браузер и войдите в Glovis

1. Откройте Chrome/Edge
2. Перейдите на https://auction.autobell.co.kr
3. Войдите в систему:
   - Логин: `7552`
   - Пароль: `for7721@`

#### Шаг 2: Откройте Developer Tools

1. Нажмите F12 или Ctrl+Shift+I
2. Перейдите на вкладку **Network** (Сеть)
3. Включите запись если она выключена

#### Шаг 3: Перейдите на страницу аукциона

1. Перейдите в раздел аукциона: https://auction.autobell.co.kr/auction/exhibitList.do?atn=946&acc=20&flag=Y
2. Дождитесь загрузки списка автомобилей

#### Шаг 4: Найдите запрос с cookies

1. В списке Network найдите запрос типа `exhibitListInclude.do`
2. Кликните правой кнопкой на него
3. Выберите **Copy** → **Copy as cURL**

#### Шаг 5: Обновите файл с cookies

1. Откройте файл `glovis-curl-request.py`
2. Замените содержимое скопированным cURL запросом в формате Python
3. Убедитесь что cookies в формате:

```python
cookies = {
    "SCOUTER": "значение",
    "JSESSIONID": "значение",
    # ... другие cookies
}
```

#### Шаг 6: Обновите cookies в API

```bash
python update_glovis_cookies.py --api-url http://localhost:8000
```

#### Шаг 7: Проверьте работу API

```bash
curl "http://localhost:8000/api/v1/glovis/cars?page=1"
```

## 🚀 Быстрый способ через Browser Export

### Шаг 1: Экспорт cookies из браузера

1. Установите расширение **Export Cookies** или **Cookie Editor**
2. Войдите в Glovis и перейдите на страницу аукциона
3. Экспортируйте cookies для домена `auction.autobell.co.kr`

### Шаг 2: Конвертация cookies

Создайте файл `new_cookies.json` с cookies в формате:

```json
{
  "SCOUTER": "значение",
  "JSESSIONID": "значение_jsessionid",
  "_ga": "значение",
  "_gcl_au": "значение"
}
```

### Шаг 3: Обновление через API

```bash
curl -X POST "http://localhost:8000/api/v1/glovis/update-cookies" \
  -H "Content-Type: application/json" \
  -d @new_cookies.json
```

## 🔍 Проверка результата

### Проверка сессии

```bash
curl "http://localhost:8000/api/v1/glovis/check-session"
```

### Тест получения автомобилей

```bash
curl "http://localhost:8000/api/v1/glovis/cars?page=1" | jq '.success'
```

## ⚠️ Важные моменты

1. **JSESSIONID** - самый важный cookie для аутентификации
2. Cookies действительны только пока вы залогинены в браузере
3. После выхода из Glovis все cookies становятся недействительными
4. Новые cookies нужно получать каждый раз после выхода

## 🔄 Автоматизация (будущее улучшение)

Для автоматического восстановления сессии можно:

1. Настроить автоматический вход через Selenium
2. Использовать headless браузер для получения cookies
3. Настроить мониторинг сессии с автоматическим обновлением

## 📞 Если ничего не помогает

1. Проверьте доступность сайта: https://auction.autobell.co.kr
2. Убедитесь что логин/пароль правильные
3. Проверьте что API сервер запущен: `python main.py`
4. Проверьте логи в папке `logs/`

## 🎯 Краткий алгоритм для срочного восстановления

```bash
# 1. Войдите в Glovis в браузере
# 2. Скопируйте cURL запрос из Developer Tools
# 3. Обновите glovis-curl-request.py
# 4. Выполните:
python update_glovis_cookies.py
python fix_glovis_session.py --force
```
