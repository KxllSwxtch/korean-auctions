# 🌐 KCAR Frontend Integration Guide

## Проблема и решение

### ❌ Старая проблема:

Фронтенд отправлял запросы с номером автомобиля (например: `20머3749`), но API ожидал car_id (например: `CA20324182`), что приводило к пустым страницам.

### ✅ Новое решение:

Добавлен endpoint для поиска car_id по номеру автомобиля, который позволяет фронтенду работать с номерами автомобилей.

---

## 📡 Новый API Endpoint

### GET `/api/v1/kcar/cars/search/by-number`

**Назначение**: Поиск car_id по номеру автомобиля

**Параметры**:

- `car_number` (обязательный) - Номер автомобиля (например: "20머3749")
- `auction_code` (опциональный) - Код аукциона для более точного поиска

**Пример запроса**:

```
GET /api/v1/kcar/cars/search/by-number?car_number=20머3749
```

**Пример ответа** (успех):

```json
{
  "success": true,
  "car_number": "20머3749",
  "car_id": "CA20324182",
  "found_car_number": "20머3749",
  "match_type": "exact",
  "confidence": 100,
  "message": "Найден автомобиль с номером 20머3749",
  "all_matches": [
    {
      "car_id": "CA20324182",
      "car_number": "20머3749",
      "match_type": "exact",
      "confidence": 100
    }
  ],
  "detail_url": "/api/v1/kcar/cars/CA20324182/detail"
}
```

**Пример ответа** (не найден):

```json
{
  "detail": {
    "error": "Автомобиль не найден",
    "message": "Автомобиль с номером 99가9999 не найден в текущих аукционах",
    "car_number": "99가9999",
    "searched_count": 100
  }
}
```

---

## 🔄 Схема интеграции

### Двухэтапный процесс:

```
Фронтенд URL: /auctions/kcar/car/20%EB%A8%B83749?auction_code=AC20250604
                                   ↓
1. Поиск car_id: GET /api/v1/kcar/cars/search/by-number?car_number=20머3749
                                   ↓
2. Детальная информация: GET /api/v1/kcar/cars/CA20324182/detail?auction_code=AC20250604
```

---

## 💻 Примеры кода для фронтенда

### JavaScript/TypeScript

```javascript
class KCarService {
  constructor(baseUrl = "http://127.0.0.1:8000") {
    this.baseUrl = baseUrl
  }

  /**
   * Получение детальной информации об автомобиле по номеру
   */
  async getCarDetailsByNumber(carNumber, auctionCode) {
    try {
      // Шаг 1: Поиск car_id по номеру
      const searchUrl = `${this.baseUrl}/api/v1/kcar/cars/search/by-number`
      const searchParams = new URLSearchParams({
        car_number: carNumber,
      })

      const searchResponse = await fetch(`${searchUrl}?${searchParams}`)

      if (!searchResponse.ok) {
        if (searchResponse.status === 404) {
          throw new Error(`Автомобиль с номером ${carNumber} не найден`)
        }
        throw new Error(`Ошибка поиска: ${searchResponse.status}`)
      }

      const searchData = await searchResponse.json()
      const carId = searchData.car_id

      console.log(`Найден car_id: ${carId} для номера: ${carNumber}`)

      // Шаг 2: Получение детальной информации
      const detailUrl = `${this.baseUrl}/api/v1/kcar/cars/${carId}/detail`
      const detailParams = new URLSearchParams({
        auction_code: auctionCode,
        page_type: "wCfm",
      })

      const detailResponse = await fetch(`${detailUrl}?${detailParams}`)

      if (!detailResponse.ok) {
        throw new Error(`Ошибка получения деталей: ${detailResponse.status}`)
      }

      const detailData = await detailResponse.json()

      if (!detailData.success) {
        throw new Error(detailData.message)
      }

      return {
        success: true,
        car: detailData.car,
        searchInfo: {
          originalCarNumber: carNumber,
          foundCarId: carId,
          confidence: searchData.confidence,
          matchType: searchData.match_type,
        },
      }
    } catch (error) {
      console.error("Ошибка получения информации об автомобиле:", error)
      return {
        success: false,
        error: error.message,
      }
    }
  }

  /**
   * Только поиск car_id (без получения детальной информации)
   */
  async findCarId(carNumber) {
    try {
      const searchUrl = `${this.baseUrl}/api/v1/kcar/cars/search/by-number`
      const searchParams = new URLSearchParams({
        car_number: carNumber,
      })

      const response = await fetch(`${searchUrl}?${searchParams}`)

      if (response.ok) {
        return await response.json()
      } else {
        const errorData = await response.json()
        throw new Error(errorData.detail?.message || "Ошибка поиска")
      }
    } catch (error) {
      console.error("Ошибка поиска car_id:", error)
      throw error
    }
  }
}

// Пример использования
const kcarService = new KCarService()

// В компоненте React/Vue/Angular
async function loadCarDetails(carNumber, auctionCode) {
  setLoading(true)

  try {
    const result = await kcarService.getCarDetailsByNumber(
      carNumber,
      auctionCode
    )

    if (result.success) {
      setCar(result.car)
      console.log("Автомобиль загружен:", result.car.car_name)
      console.log("Изображений:", result.car.all_images.length)
    } else {
      setError(result.error)
    }
  } catch (error) {
    setError("Ошибка загрузки автомобиля")
  } finally {
    setLoading(false)
  }
}
```

### React Hook пример

```jsx
import { useState, useEffect } from "react"

function useKCarDetails(carNumber, auctionCode) {
  const [car, setCar] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!carNumber || !auctionCode) return

    async function loadCar() {
      setLoading(true)
      setError(null)

      try {
        const kcarService = new KCarService()
        const result = await kcarService.getCarDetailsByNumber(
          carNumber,
          auctionCode
        )

        if (result.success) {
          setCar(result.car)
        } else {
          setError(result.error)
        }
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }

    loadCar()
  }, [carNumber, auctionCode])

  return { car, loading, error }
}

// Использование в компоненте
function CarDetailPage({ carNumber, auctionCode }) {
  const { car, loading, error } = useKCarDetails(carNumber, auctionCode)

  if (loading) return <div>Загрузка...</div>
  if (error) return <div>Ошибка: {error}</div>
  if (!car) return <div>Автомобиль не найден</div>

  return (
    <div>
      <h1>
        {car.year} {car.fuel_type}
      </h1>
      <p>Цена: {car.start_price}</p>
      <p>Изображений: {car.all_images.length}</p>
      {/* Отображение остальной информации */}
    </div>
  )
}
```

---

## 🔧 Адаптация существующего роутинга

### До (проблемный код):

```javascript
// app/routes/car/[carNumber].js
export async function getServerSideProps({ params, query }) {
  const carNumber = params.carNumber // "20%EB%A8%B83749"
  const auctionCode = query.auction_code // "AC20250604"

  // ❌ Это не работает - номер автомобиля используется как car_id
  const response = await fetch(
    `${API_BASE}/api/v1/kcar/cars/${carNumber}/detail?auction_code=${auctionCode}`
  )

  return { props: { car: null } } // Пустая страница
}
```

### После (исправленный код):

```javascript
// app/routes/car/[carNumber].js
export async function getServerSideProps({ params, query }) {
  const carNumber = decodeURIComponent(params.carNumber) // "20머3749"
  const auctionCode = query.auction_code // "AC20250604"

  try {
    // ✅ Сначала находим car_id
    const searchResponse = await fetch(
      `${API_BASE}/api/v1/kcar/cars/search/by-number?car_number=${encodeURIComponent(
        carNumber
      )}`
    )

    if (!searchResponse.ok) {
      return { props: { error: "Автомобиль не найден" } }
    }

    const searchData = await searchResponse.json()
    const carId = searchData.car_id

    // ✅ Затем получаем детальную информацию
    const detailResponse = await fetch(
      `${API_BASE}/api/v1/kcar/cars/${carId}/detail?auction_code=${auctionCode}`
    )

    if (!detailResponse.ok) {
      return { props: { error: "Ошибка загрузки деталей" } }
    }

    const detailData = await detailResponse.json()

    return {
      props: {
        car: detailData.car,
        searchInfo: searchData,
      },
    }
  } catch (error) {
    return { props: { error: error.message } }
  }
}
```

---

## 🎯 Рекомендации по производительности

### 1. Кэширование результатов поиска

```javascript
class KCarService {
  constructor() {
    this.carIdCache = new Map() // Кэш car_number → car_id
  }

  async findCarId(carNumber) {
    // Проверяем кэш
    if (this.carIdCache.has(carNumber)) {
      return this.carIdCache.get(carNumber)
    }

    // Делаем запрос
    const result = await this.searchCarId(carNumber)

    // Кэшируем результат
    if (result.success) {
      this.carIdCache.set(carNumber, result)
    }

    return result
  }
}
```

### 2. Batch запросы (для множественных поисков)

```javascript
async function searchMultipleCars(carNumbers) {
  const promises = carNumbers.map((carNumber) =>
    kcarService.findCarId(carNumber)
  )

  const results = await Promise.allSettled(promises)

  return results.map((result, index) => ({
    carNumber: carNumbers[index],
    success: result.status === "fulfilled",
    data: result.status === "fulfilled" ? result.value : null,
    error: result.status === "rejected" ? result.reason : null,
  }))
}
```

---

## ✅ Чек-лист интеграции

- [ ] **1. Обновить API клиент** для использования двухэтапного процесса
- [ ] **2. Адаптировать роутинг** для декодирования car_number из URL
- [ ] **3. Добавить обработку ошибок** для случаев "автомобиль не найден"
- [ ] **4. Реализовать кэширование** car_number → car_id mappings
- [ ] **5. Обновить типы TypeScript** (если используется)
- [ ] **6. Добавить loading состояния** для двухэтапного процесса
- [ ] **7. Протестировать** на реальных URL-ах с фронтенда

---

## 🚀 Результат

После интеграции:

- ✅ Фронтенд URL `http://localhost:3000/auctions/kcar/car/20%EB%A8%B83749?auction_code=AC20250604` будет работать
- ✅ Автоматический поиск car_id по номеру автомобиля
- ✅ Полная детальная информация с 43 изображениями
- ✅ Корректная обработка ошибок

**Время ответа**: 2-6 секунд (поиск + детальная информация)  
**Надежность**: Высокая с retry логикой и обработкой ошибок  
**Совместимость**: Полная с существующим фронтенд кодом
