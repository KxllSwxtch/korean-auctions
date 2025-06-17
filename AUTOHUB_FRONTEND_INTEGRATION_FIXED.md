# 🛠 Autohub Frontend Integration - Исправленная версия

## 🔧 Проблема была найдена и решена!

### ❌ **Старые неправильные параметры**:

```json
{
  "auction_number": "1329",
  "auction_date": "2025-06-18",
  "auction_title": "AUTOHUB AUCTION", // ❌ Слишком простое название
  "auction_code": "001", // ❌ Неправильный формат
  "receive_code": "RCV001" // ❌ Неправильный код
}
```

**Результат**: Пустые данные, нет изображений, только заглушки

---

### ✅ **Правильные параметры**:

```json
{
  "auction_number": "1329",
  "auction_date": "2025-06-18",
  "auction_title": "안성 2025/06/18 1329회차 경매", // ✅ Полное корейское название
  "auction_code": "AC202506110001", // ✅ Правильный формат кода
  "receive_code": "RC202506130039", // ✅ Код конкретного автомобиля
  "page_number": 1,
  "page_size": 10,
  "sort_flag": "entry"
}
```

**Результат**: Полные данные, 22 изображения, вся информация ✅

---

## 🚀 Как использовать в Frontend

### 1. **POST запрос для детальной информации**

```javascript
const getCarDetail = async (carParams) => {
  try {
    const response = await fetch(
      "http://localhost:8000/api/v1/autohub/car-detail",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          auction_number: carParams.auction_number,
          auction_date: carParams.auction_date,
          auction_title: carParams.auction_title, // ВАЖНО: полное корейское название
          auction_code: carParams.auction_code, // ВАЖНО: формат "AC202506110001"
          receive_code: carParams.receive_code, // ВАЖНО: код автомобиля "RC202506130039"
          page_number: 1,
          page_size: 10,
          sort_flag: "entry",
        }),
      }
    )

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const data = await response.json()

    if (data.success) {
      return data.data // Возвращает детальную информацию об автомобиле
    } else {
      throw new Error(data.error || "Ошибка получения данных")
    }
  } catch (error) {
    console.error("Ошибка запроса детальной информации:", error)
    throw error
  }
}
```

### 2. **Структура ответа**

```javascript
{
  "success": true,
  "data": {
    "title": "[1001] 기아 더 뉴 니로(19년~현재) 1.6 HEV 트렌디",
    "starting_price": "0",
    "auction_number": "1329",
    "auction_date": "2025-06-18",
    "auction_title": "안성 2025/06/18 1329회차 경매",
    "auction_code": "AC202506110001",

    // Информация об автомобиле
    "car_info": {
      "car_id": "1001",
      "title": "2022 G4LE 하이브리드",
      "year": 2022,
      "mileage": "76,229",
      "transmission": "오토",
      "fuel_type": "하이브리드",
      "main_image_url": "http://www.sellcarauction.co.kr/.../AT174978895311474_M.jpg",
      "vin_number": "KNACA81CGNA500921",
      "parking_number": "B10-6479",
      "entry_number": "1001"
    },

    // Все изображения автомобиля (22 фото)
    "images": [
      {
        "large_url": "http://www.sellcarauction.co.kr/.../AT174978895311474_L.jpg",
        "small_url": "http://www.sellcarauction.co.kr/.../AT174978895311474_S.jpg",
        "sequence": 0
      },
      // ... еще 21 изображение
    ],

    // Оценка производительности
    "performance_info": {
      "rating": "골격 : A   외관 : D",
      "inspector": "이성원",
      "stored_items": ["SD카드"],
      "notes": "-"
    },

    // Опции автомобиля
    "options": {
      "convenience": ["네비", "스마트키"],
      "safety": ["에어백", "ABS"],
      "exterior": ["알로이휠"],
      "interior": ["가죽시트"]
    }
  }
}
```

### 3. **Компонент React для отображения**

```jsx
import React, { useState, useEffect } from "react"

const CarDetailComponent = ({ carParams }) => {
  const [carDetail, setCarDetail] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    const fetchCarDetail = async () => {
      try {
        setLoading(true)
        const detail = await getCarDetail(carParams)
        setCarDetail(detail)
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }

    if (carParams) {
      fetchCarDetail()
    }
  }, [carParams])

  if (loading) return <div>Загрузка...</div>
  if (error) return <div>Ошибка: {error}</div>
  if (!carDetail) return <div>Нет данных</div>

  return (
    <div className="car-detail">
      <h1>{carDetail.title}</h1>

      {/* Основная информация */}
      <div className="car-info">
        <h3>Характеристики</h3>
        <p>Год выпуска: {carDetail.car_info.year}</p>
        <p>Пробег: {carDetail.car_info.mileage}</p>
        <p>Трансмиссия: {carDetail.car_info.transmission}</p>
        <p>Топливо: {carDetail.car_info.fuel_type}</p>
      </div>

      {/* Изображения */}
      <div className="car-images">
        <h3>Изображения ({carDetail.images.length})</h3>
        <div className="image-gallery">
          {carDetail.images.map((image, index) => (
            <img
              key={index}
              src={image.large_url}
              alt={`Автомобиль ${index + 1}`}
              className="car-image"
            />
          ))}
        </div>
      </div>

      {/* Оценка производительности */}
      <div className="performance">
        <h3>Оценка производительности</h3>
        <p>Рейтинг: {carDetail.performance_info.rating}</p>
        <p>Инспектор: {carDetail.performance_info.inspector}</p>
      </div>

      {/* Опции */}
      <div className="options">
        <h3>Опции</h3>
        <div>
          <h4>Удобство:</h4>
          <ul>
            {carDetail.options.convenience.map((option, index) => (
              <li key={index}>{option}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}

export default CarDetailComponent
```

## 📋 Где взять правильные параметры?

### Из списка автомобилей:

```javascript
// GET /api/v1/autohub/cars возвращает:
{
  "data": [
    {
      "car_id": "RC202506130039",           // это receive_code
      "auction_number": "1329",            // auction_number
      "title": "기아 더 뉴 니로...",        // название автомобиля
      // ... другие поля
    }
  ]
}
```

### Формирование правильных параметров:

```javascript
const carParams = {
  auction_number: car.auction_number, // "1329"
  auction_date: "2025-06-18", // дата аукциона
  auction_title: "안성 2025/06/18 1329회차 경매", // полное название
  auction_code: "AC202506110001", // код аукциона
  receive_code: car.car_id, // RC202506130039
}
```

## 🎯 Ключевые моменты:

1. **receive_code** = `car_id` из списка автомобилей
2. **auction_title** должен быть полным корейским названием
3. **auction_code** должен быть в формате "AC + дата + номер"
4. После исправления API возвращает **22 изображения** вместо 0
5. Все поля заполняются корректными данными

## ✅ Результат:

- Полная детальная информация об автомобиле
- 22 высококачественных изображения
- Оценка производительности с инспектором
- Все опции и характеристики автомобиля
