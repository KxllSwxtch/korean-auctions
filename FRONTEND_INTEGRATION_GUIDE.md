# Руководство по интеграции HeyDealer API с Frontend

## 🔧 Необходимые изменения на Frontend

### 1. Обновление URL endpoints

Убедитесь, что все запросы используют правильные endpoints с префиксом `/api/v1/`:

```javascript
// ✅ ПРАВИЛЬНО - используйте эти endpoints
const HEYDEALER_API = {
  brands: "/api/v1/heydealer/brands",
  cars: "/api/v1/heydealer/cars",
  carDetail: (carId) => `/api/v1/heydealer/cars/${carId}`,
  brandModels: (brandId) => `/api/v1/heydealer/brands/${brandId}`,
  filters: "/api/v1/heydealer/filters",
}

// ❌ НЕ ИСПОЛЬЗУЙТЕ - старые endpoints без префикса
// '/heydealer/cars'
// '/heydealer/brands'
```

### 2. Правильная работа с брендами

#### Получение списка брендов:

```javascript
async function loadBrands() {
  try {
    const response = await fetch("/api/v1/heydealer/brands")
    const data = await response.json()

    if (data.success) {
      return data.data // Массив брендов с hash_id
    } else {
      throw new Error(data.message)
    }
  } catch (error) {
    console.error("Ошибка загрузки брендов:", error)
    return []
  }
}

// Пример структуры ответа:
// {
//   "success": true,
//   "data": [
//     {
//       "hash_id": "0W5AWm",
//       "name": "BMW",
//       "is_domestic": false,
//       "image_url": "https://...",
//       "count": 740
//     }
//   ]
// }
```

#### Фильтрация автомобилей по бренду:

```javascript
async function loadCarsByBrand(brandHashId, page = 1) {
  try {
    const url = new URL("/api/v1/heydealer/cars", window.location.origin)
    url.searchParams.set("brand", brandHashId)
    url.searchParams.set("page", page)

    const response = await fetch(url)
    const data = await response.json()

    if (data.success) {
      return {
        cars: data.data.cars,
        totalCount: data.data.total_count,
        currentPage: data.current_page,
      }
    } else {
      throw new Error(data.message)
    }
  } catch (error) {
    console.error("Ошибка загрузки автомобилей:", error)
    return { cars: [], totalCount: 0, currentPage: 1 }
  }
}
```

### 3. React/Vue компонент для выбора бренда

#### React пример:

```jsx
import React, { useState, useEffect } from "react"

function BrandSelector({ onBrandSelect }) {
  const [brands, setBrands] = useState([])
  const [selectedBrand, setSelectedBrand] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    loadBrands()
  }, [])

  const loadBrands = async () => {
    setLoading(true)
    try {
      const response = await fetch("/api/v1/heydealer/brands")
      const data = await response.json()

      if (data.success) {
        setBrands(data.data)
      }
    } catch (error) {
      console.error("Ошибка загрузки брендов:", error)
    } finally {
      setLoading(false)
    }
  }

  const handleBrandSelect = (brand) => {
    setSelectedBrand(brand)
    // Передаем hash_id родительскому компоненту
    onBrandSelect(brand?.hash_id || null)
  }

  if (loading) return <div>Загрузка брендов...</div>

  return (
    <select
      value={selectedBrand?.hash_id || ""}
      onChange={(e) => {
        const brand = brands.find((b) => b.hash_id === e.target.value)
        handleBrandSelect(brand)
      }}
    >
      <option value="">Все бренды</option>
      {brands.map((brand) => (
        <option key={brand.hash_id} value={brand.hash_id}>
          {brand.name} ({brand.count})
        </option>
      ))}
    </select>
  )
}

// Использование:
function CarsList() {
  const [cars, setCars] = useState([])
  const [selectedBrandId, setSelectedBrandId] = useState(null)

  const loadCars = async (brandId = null, page = 1) => {
    const url = new URL("/api/v1/heydealer/cars", window.location.origin)
    if (brandId) url.searchParams.set("brand", brandId)
    url.searchParams.set("page", page)

    const response = await fetch(url)
    const data = await response.json()

    if (data.success) {
      setCars(data.data.cars)
    }
  }

  useEffect(() => {
    loadCars(selectedBrandId)
  }, [selectedBrandId])

  return (
    <div>
      <BrandSelector onBrandSelect={setSelectedBrandId} />
      <div>
        {cars.map((car) => (
          <div key={car.hash_id}>{car.detail.full_name}</div>
        ))}
      </div>
    </div>
  )
}
```

#### Vue пример:

```vue
<template>
  <div>
    <select v-model="selectedBrandId" @change="onBrandChange">
      <option value="">Все бренды</option>
      <option
        v-for="brand in brands"
        :key="brand.hash_id"
        :value="brand.hash_id"
      >
        {{ brand.name }} ({{ brand.count }})
      </option>
    </select>

    <div v-if="loading">Загрузка...</div>
    <div v-else>
      <div v-for="car in cars" :key="car.hash_id">
        {{ car.detail.full_name }}
      </div>
    </div>
  </div>
</template>

<script>
export default {
  data() {
    return {
      brands: [],
      cars: [],
      selectedBrandId: "",
      loading: false,
    }
  },

  async mounted() {
    await this.loadBrands()
    await this.loadCars()
  },

  methods: {
    async loadBrands() {
      try {
        const response = await fetch("/api/v1/heydealer/brands")
        const data = await response.json()

        if (data.success) {
          this.brands = data.data
        }
      } catch (error) {
        console.error("Ошибка загрузки брендов:", error)
      }
    },

    async loadCars(brandId = null) {
      this.loading = true
      try {
        const url = new URL("/api/v1/heydealer/cars", window.location.origin)
        if (brandId) url.searchParams.set("brand", brandId)

        const response = await fetch(url)
        const data = await response.json()

        if (data.success) {
          this.cars = data.data.cars
        }
      } catch (error) {
        console.error("Ошибка загрузки автомобилей:", error)
      } finally {
        this.loading = false
      }
    },

    async onBrandChange() {
      await this.loadCars(this.selectedBrandId || null)
    },
  },
}
</script>
```

### 4. Обработка ошибок

```javascript
async function apiRequest(url, options = {}) {
  try {
    const response = await fetch(url, {
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
      ...options,
    })

    const data = await response.json()

    if (!response.ok) {
      throw new Error(
        `HTTP ${response.status}: ${data.message || "Неизвестная ошибка"}`
      )
    }

    if (!data.success) {
      throw new Error(data.message || "Ошибка API")
    }

    return data
  } catch (error) {
    console.error("API Error:", error)
    throw error
  }
}
```

### 5. Пагинация

```javascript
function CarsPagination({
  currentPage,
  totalCount,
  pageSize = 20,
  onPageChange,
}) {
  const totalPages = Math.ceil(totalCount / pageSize)

  return (
    <div className="pagination">
      <button
        disabled={currentPage <= 1}
        onClick={() => onPageChange(currentPage - 1)}
      >
        Предыдущая
      </button>

      <span>
        Страница {currentPage} из {totalPages}
      </span>

      <button
        disabled={currentPage >= totalPages}
        onClick={() => onPageChange(currentPage + 1)}
      >
        Следующая
      </button>
    </div>
  )
}
```

## 🧪 Тестирование интеграции

### Проверочный список:

1. **✅ Загрузка брендов**

   ```bash
   curl "http://localhost:3000/api/v1/heydealer/brands"
   ```

2. **✅ Загрузка всех автомобилей**

   ```bash
   curl "http://localhost:3000/api/v1/heydealer/cars"
   ```

3. **✅ Фильтрация по BMW**

   ```bash
   curl "http://localhost:3000/api/v1/heydealer/cars?brand=0W5AWm"
   ```

4. **✅ Фильтрация по Hyundai**

   ```bash
   curl "http://localhost:3000/api/v1/heydealer/cars?brand=xoKegB"
   ```

5. **✅ Пагинация**
   ```bash
   curl "http://localhost:3000/api/v1/heydealer/cars?page=2"
   ```

### Ожидаемое поведение:

- При выборе бренда список автомобилей должен обновиться
- Все автомобили в списке должны принадлежать выбранному бренду
- Пагинация должна работать корректно
- Счетчик автомобилей должен обновляться

## 🚨 Частые ошибки

1. **Использование неправильных endpoints**

   ```javascript
   // ❌ НЕ РАБОТАЕТ
   fetch("/heydealer/cars?brand=BMW")

   // ✅ РАБОТАЕТ
   fetch("/api/v1/heydealer/cars?brand=0W5AWm")
   ```

2. **Попытка угадать hash_id**

   ```javascript
   // ❌ НЕ ДЕЛАЙТЕ ТАК
   const brandId = brandName.toLowerCase()

   // ✅ ПРАВИЛЬНО
   const brand = brands.find((b) => b.name === brandName)
   const brandId = brand.hash_id
   ```

3. **Неправильная обработка ответов**

   ```javascript
   // ❌ НЕ РАБОТАЕТ
   const cars = response.json()

   // ✅ РАБОТАЕТ
   const data = await response.json()
   const cars = data.success ? data.data.cars : []
   ```

## 📞 Поддержка

Если фильтрация не работает, проверьте:

1. Правильность URL endpoints
2. Использование hash_id вместо названий брендов
3. Обработку success поля в ответах
4. Консоль браузера на наличие ошибок
