# 🚨 СРОЧНОЕ ИСПРАВЛЕНИЕ: Autohub receive_code

## 📋 Проблема

Frontend отправляет неправильный `receive_code` (`+receivecd, `) вместо правильного значения из API.

## ✅ Backend Исправлен

Backend теперь возвращает правильные данные:

```json
{
  "car_id": "RC202506250755",
  "receive_code": "RC202506250755", // ← ТЕПЕРЬ ПРАВИЛЬНО
  "auction_number": "1001"
}
```

## 🔧 Frontend Исправления

### 1. **Проверьте получение данных с API**

Убедитесь, что вы используете **свежие данные** с API:

```typescript
// ✅ ПРАВИЛЬНО: Получаем данные с обновлённого API
const response = await fetch("/api/v1/autohub/cars")
const data = await response.json()

console.log("Данные с API:", data.data[0])
// Должно показать:
// {
//   car_id: "RC202506250755",
//   receive_code: "RC202506250755",  // ← Правильное значение
//   auction_number: "1001"
// }
```

### 2. **Исправьте формирование URL**

**❌ НЕПРАВИЛЬНО (текущий код):**

```typescript
// Где-то используются старые/кэшированные данные
const url = `/auctions/autohub/car/${car.auction_number}?receive_code=+receivecd,`
```

**✅ ПРАВИЛЬНО:**

```typescript
// Используйте актуальные данные с API
const url =
  `/auctions/autohub/car/${car.auction_number}?` +
  `auction_date=${encodeURIComponent(car.auction_date)}&` +
  `auction_title=${encodeURIComponent(car.auction_title)}&` +
  `auction_code=${encodeURIComponent(car.auction_code)}&` +
  `receive_code=${encodeURIComponent(car.receive_code)}` // ← Правильное значение
```

### 3. **Обновите TypeScript интерфейсы**

```typescript
interface AutohubCar {
  car_id: string
  auction_number: string
  receive_code: string // ← Убедитесь что используется правильное поле
  auction_date: string
  auction_title: string
  auction_code: string
  title: string
  // ... остальные поля
}
```

### 4. **Очистите кэш**

1. **Очистите browser cache**
2. **Перезапустите frontend dev server**
3. **Проверьте Network tab** в DevTools что запросы идут к правильному API

### 5. **Тестирование**

**Тестовые данные для проверки:**

```
Автомобиль 1:
- auction_number: "1001"
- car_id: "RC202506250755"
- receive_code: "RC202506250755"  // ← Должно быть это значение

Автомобиль 2:
- auction_number: "1002"
- car_id: "RC202506250703"
- receive_code: "RC202506250703"  // ← Должно быть это значение
```

**Правильный URL должен быть:**

```
http://localhost:3000/auctions/autohub/car/1001?
  auction_date=2025-07-02&
  auction_title=%EC%95%88%EC%84%B1+2025%2F07%2F02+1331%ED%9A%8C%EC%B0%A8+%EA%B2%BD%EB%A7%A4&
  auction_code=AC202506250001&
  receive_code=RC202506250755  // ← ПРАВИЛЬНОЕ значение
```

## 🧪 Быстрая проверка

Откройте в браузере:

```
http://localhost:8000/api/v1/autohub/cars?limit=1
```

Проверьте что `receive_code` равен `car_id`:

```json
{
  "data": [
    {
      "car_id": "RC202506250755",
      "receive_code": "RC202506250755" // ← Должны быть одинаковы
    }
  ]
}
```

## ⏰ Время исправления: 5-10 минут

Проблема в том, что frontend использует старые/неправильные данные. Обновите получение данных с API и исправление будет завершено.
