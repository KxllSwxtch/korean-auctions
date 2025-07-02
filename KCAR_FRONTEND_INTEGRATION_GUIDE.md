# KCar Frontend Integration Guide

## 🎯 Цель

Исправить некорректную работу фильтров KCar на Frontend.  
**Backend работает идеально** - проблема в интеграции!

---

## 📋 API Endpoints

### 1. Основной список автомобилей

```
GET /api/v1/kcar/cars
```

**Параметры фильтрации:**

```javascript
{
  manufacturer: "001",           // Код производителя (обязательно строка!)
  model: "001",                 // Код модели (опционально)
  year_from: "2015",           // Год от (строка)
  year_to: "2020",             // Год до (строка)
  price_from: "5000000",       // Цена от в вонах (строка)
  price_to: "10000000",        // Цена до в вонах (строка)
  mileage_from: "50000",       // Пробег от (строка)
  mileage_to: "150000",        // Пробег до (строка)
  fuel_type: "001",            // Тип топлива (строка)
  transmission: "001",         // КПП (строка)
  color: "001",                // Цвет (строка)
  location: "001",             // Локация (строка)
  page_size: 20,               // Размер страницы (число)
  page: 1                      // Номер страницы (число)
}
```

### 2. Каскадные списки

```
GET /api/v1/kcar/manufacturers           // Производители
GET /api/v1/kcar/models/{code}           // Модели для производителя
GET /api/v1/kcar/generations/{code}/{model}  // Поколения для модели
```

### 3. Расширенный поиск

```
POST /api/v1/kcar/search
Content-Type: application/json
```

---

## 💻 TypeScript Interfaces

```typescript
// Модель автомобиля KCar
interface KCarCar {
  CAR_ID: string
  CAR_NM: string
  CNO: string
  THUMBNAIL: string
  THUMBNAIL_MOBILE: string
  AUC_STRT_PRC: string
  AUC_STRT_HOPE: string
  AUC_CD: string
  AUC_STAT: string
  AUC_STAT_NM: string
  AUC_STRT_DT: string
  AUC_STRT_END_DATETIME: string
  AUC_TYPE_DESC: string
  FORM_YR: string
  MILG: string
  FUEL_CD: string
  GBOX_DCD: string
  EXTERIOR_COLOR_NM: string
  COLOR_CD: string
  CAR_POINT: string
  CAR_POINT2: string
  CAR_LOCT: string
  AUC_PLC_NM: string
  lane_type: string
  EXBIT_SEQ: string
}

// Ответ API со списком автомобилей
interface KCarResponse {
  auctionReqVo: any
  CAR_LIST: KCarCar[] // ⚠️ UPPERCASE!
  total_count: number
  current_page: number
  page_size: number
  total_pages: number
  has_next_page: boolean
  has_prev_page: boolean
  success: boolean
  message: string
}

// Производитель
interface KCarManufacturer {
  code: string
  name: string
  name_en: string
}

// Модель
interface KCarModel {
  MNUFTR_CD: string
  MODEL_GRP_CD: string
  MODEL_GRP_NM: string
}

// Поколение
interface KCarGeneration {
  MODEL_CD: string
  MODEL_NM: string
  MODEL_DETAIL_NM: string
}

// Фильтры для поиска
interface KCarFilters {
  manufacturer_code?: string
  model_group_code?: string
  model_code?: string
  year_from?: string
  year_to?: string
  price_from?: string
  price_to?: string
  mileage_from?: string
  mileage_to?: string
  fuel_type?: string
  transmission?: string
  color_code?: string
  auction_type?: string
  page?: number
  page_size?: number
}
```

---

## 🔧 Готовый API Client

```typescript
class KCarApiClient {
  private baseUrl = "/api/v1/kcar"

  // Получить список автомобилей с фильтрами
  async getCars(filters: Record<string, any> = {}): Promise<KCarResponse> {
    const params = new URLSearchParams()

    // Добавляем параметры фильтрации
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== null && value !== undefined && value !== "") {
        params.append(key, String(value))
      }
    })

    const response = await fetch(`${this.baseUrl}/cars?${params}`)

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    return response.json()
  }

  // Получить производителей
  async getManufacturers(): Promise<{ manufacturers: KCarManufacturer[] }> {
    const response = await fetch(`${this.baseUrl}/manufacturers`)
    return response.json()
  }

  // Получить модели для производителя
  async getModels(manufacturerCode: string): Promise<{ modelVo: KCarModel[] }> {
    const response = await fetch(`${this.baseUrl}/models/${manufacturerCode}`)
    return response.json()
  }

  // Получить поколения для модели
  async getGenerations(
    manufacturerCode: string,
    modelGroupCode: string
  ): Promise<{ modelDetailVo: KCarGeneration[] }> {
    const response = await fetch(
      `${this.baseUrl}/generations/${manufacturerCode}/${modelGroupCode}`
    )
    return response.json()
  }

  // Расширенный поиск
  async searchCars(filters: KCarFilters): Promise<KCarResponse> {
    const response = await fetch(`${this.baseUrl}/search`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(filters),
    })

    return response.json()
  }

  // Тестовые данные
  async getTestCars(count: number = 10): Promise<KCarResponse> {
    const response = await fetch(`${this.baseUrl}/cars/test?count=${count}`)
    return response.json()
  }
}

// Экспорт
export const kcarApi = new KCarApiClient()
```

---

## ⚛️ React Hook для KCar

```typescript
import { useState, useEffect, useCallback } from "react"

interface UseKCarFiltersProps {
  initialFilters?: Record<string, any>
  pageSize?: number
}

export const useKCarFilters = ({
  initialFilters = {},
  pageSize = 20,
}: UseKCarFiltersProps = {}) => {
  const [cars, setCars] = useState<KCarCar[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [filters, setFilters] = useState(initialFilters)
  const [pagination, setPagination] = useState({
    current_page: 1,
    total_pages: 1,
    total_count: 0,
    has_next_page: false,
    has_prev_page: false,
  })

  // Загрузка автомобилей
  const loadCars = useCallback(
    async (newFilters = filters, page = 1) => {
      setLoading(true)
      setError(null)

      try {
        const params = {
          ...newFilters,
          page,
          page_size: pageSize,
        }

        const response = await kcarApi.getCars(params)

        if (response.success) {
          setCars(response.CAR_LIST) // ⚠️ UPPERCASE поле!
          setPagination({
            current_page: response.current_page,
            total_pages: response.total_pages,
            total_count: response.total_count,
            has_next_page: response.has_next_page,
            has_prev_page: response.has_prev_page,
          })
        } else {
          setError(response.message || "Ошибка загрузки данных")
          setCars([])
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Неизвестная ошибка")
        setCars([])
      } finally {
        setLoading(false)
      }
    },
    [filters, pageSize]
  )

  // Обновление фильтров
  const updateFilters = useCallback(
    (newFilters: Record<string, any>) => {
      const updatedFilters = { ...filters, ...newFilters }
      setFilters(updatedFilters)
      loadCars(updatedFilters, 1) // Сброс на первую страницу
    },
    [filters, loadCars]
  )

  // Очистка фильтров
  const clearFilters = useCallback(() => {
    setFilters({})
    loadCars({}, 1)
  }, [loadCars])

  // Изменение страницы
  const goToPage = useCallback(
    (page: number) => {
      loadCars(filters, page)
    },
    [filters, loadCars]
  )

  // Загрузка при монтировании
  useEffect(() => {
    loadCars()
  }, [])

  return {
    cars,
    loading,
    error,
    filters,
    pagination,
    updateFilters,
    clearFilters,
    loadCars,
    goToPage,
  }
}
```

---

## 🎛️ Компонент фильтров

```typescript
import React, { useState, useEffect } from "react"

interface KCarFiltersProps {
  onFiltersChange: (filters: Record<string, any>) => void
  loading?: boolean
}

export const KCarFilters: React.FC<KCarFiltersProps> = ({
  onFiltersChange,
  loading = false,
}) => {
  const [manufacturers, setManufacturers] = useState<KCarManufacturer[]>([])
  const [models, setModels] = useState<KCarModel[]>([])
  const [generations, setGenerations] = useState<KCarGeneration[]>([])

  const [selectedManufacturer, setSelectedManufacturer] = useState("")
  const [selectedModel, setSelectedModel] = useState("")
  const [selectedGeneration, setSelectedGeneration] = useState("")
  const [yearFrom, setYearFrom] = useState("")
  const [yearTo, setYearTo] = useState("")
  const [priceFrom, setPriceFrom] = useState("")
  const [priceTo, setPriceTo] = useState("")

  // Загрузка производителей при монтировании
  useEffect(() => {
    kcarApi.getManufacturers().then((response) => {
      setManufacturers(response.manufacturers)
    })
  }, [])

  // Загрузка моделей при выборе производителя
  useEffect(() => {
    if (selectedManufacturer) {
      kcarApi.getModels(selectedManufacturer).then((response) => {
        setModels(response.modelVo)
      })
      setSelectedModel("")
      setSelectedGeneration("")
      setGenerations([])
    } else {
      setModels([])
      setGenerations([])
    }
  }, [selectedManufacturer])

  // Загрузка поколений при выборе модели
  useEffect(() => {
    if (selectedManufacturer && selectedModel) {
      kcarApi
        .getGenerations(selectedManufacturer, selectedModel)
        .then((response) => {
          setGenerations(response.modelDetailVo)
        })
      setSelectedGeneration("")
    } else {
      setGenerations([])
    }
  }, [selectedManufacturer, selectedModel])

  // Применение фильтров
  const applyFilters = () => {
    const filters: Record<string, any> = {}

    if (selectedManufacturer) filters.manufacturer = selectedManufacturer
    if (selectedModel) filters.model = selectedModel
    if (yearFrom) filters.year_from = yearFrom
    if (yearTo) filters.year_to = yearTo
    if (priceFrom) filters.price_from = priceFrom
    if (priceTo) filters.price_to = priceTo

    onFiltersChange(filters)
  }

  // Очистка фильтров
  const clearFilters = () => {
    setSelectedManufacturer("")
    setSelectedModel("")
    setSelectedGeneration("")
    setYearFrom("")
    setYearTo("")
    setPriceFrom("")
    setPriceTo("")
    onFiltersChange({})
  }

  return (
    <div className="kcar-filters">
      <div className="filter-row">
        {/* Производитель */}
        <select
          value={selectedManufacturer}
          onChange={(e) => setSelectedManufacturer(e.target.value)}
          disabled={loading}
        >
          <option value="">Выберите производителя</option>
          {manufacturers.map((manufacturer) => (
            <option key={manufacturer.code} value={manufacturer.code}>
              {manufacturer.name} ({manufacturer.name_en})
            </option>
          ))}
        </select>

        {/* Модель */}
        <select
          value={selectedModel}
          onChange={(e) => setSelectedModel(e.target.value)}
          disabled={loading || !selectedManufacturer}
        >
          <option value="">Выберите модель</option>
          {models.map((model) => (
            <option key={model.MODEL_GRP_CD} value={model.MODEL_GRP_CD}>
              {model.MODEL_GRP_NM}
            </option>
          ))}
        </select>

        {/* Поколение */}
        <select
          value={selectedGeneration}
          onChange={(e) => setSelectedGeneration(e.target.value)}
          disabled={loading || !selectedModel}
        >
          <option value="">Выберите поколение</option>
          {generations.map((generation) => (
            <option key={generation.MODEL_CD} value={generation.MODEL_CD}>
              {generation.MODEL_DETAIL_NM}
            </option>
          ))}
        </select>
      </div>

      <div className="filter-row">
        {/* Год */}
        <input
          type="number"
          placeholder="Год от"
          value={yearFrom}
          onChange={(e) => setYearFrom(e.target.value)}
          disabled={loading}
        />
        <input
          type="number"
          placeholder="Год до"
          value={yearTo}
          onChange={(e) => setYearTo(e.target.value)}
          disabled={loading}
        />

        {/* Цена */}
        <input
          type="number"
          placeholder="Цена от (вон)"
          value={priceFrom}
          onChange={(e) => setPriceFrom(e.target.value)}
          disabled={loading}
        />
        <input
          type="number"
          placeholder="Цена до (вон)"
          value={priceTo}
          onChange={(e) => setPriceTo(e.target.value)}
          disabled={loading}
        />
      </div>

      <div className="filter-actions">
        <button onClick={applyFilters} disabled={loading}>
          {loading ? "Загрузка..." : "Применить фильтры"}
        </button>
        <button onClick={clearFilters} disabled={loading}>
          Сбросить
        </button>
      </div>
    </div>
  )
}
```

---

## 🧪 Тестирование

### 1. Простой тест в браузере

```javascript
// Откройте Developer Tools и выполните:
fetch("/api/v1/kcar/cars?manufacturer=001&page_size=5")
  .then((res) => res.json())
  .then((data) => {
    console.log("✅ Результат:", data)
    console.log("🚗 Автомобили:", data.CAR_LIST)
  })
```

### 2. Тест фильтрации

```javascript
// Тест по Kia с ценовым диапазоном
fetch(
  "/api/v1/kcar/cars?manufacturer=002&price_from=5000000&price_to=15000000&page_size=3"
)
  .then((res) => res.json())
  .then((data) => console.log("Kia автомобили:", data.CAR_LIST))
```

### 3. Тест каскадных списков

```javascript
// 1. Производители
fetch("/api/v1/kcar/manufacturers")
  .then((res) => res.json())
  .then((data) => console.log("Производители:", data.manufacturers))

// 2. Модели для Hyundai
fetch("/api/v1/kcar/models/001")
  .then((res) => res.json())
  .then((data) => console.log("Модели Hyundai:", data.modelVo))
```

---

## ❗ Важные моменты

### 1. Поля в UPPERCASE

```javascript
// ❌ НЕ РАБОТАЕТ
data.car_list

// ✅ РАБОТАЕТ
data.CAR_LIST
```

### 2. Строковые параметры

```javascript
// ❌ НЕ РАБОТАЕТ
manufacturer: 1

// ✅ РАБОТАЕТ
manufacturer: "001"
```

### 3. Правильные коды

```javascript
// ✅ Популярные производители
const codes = {
  hyundai: "001",
  kia: "002",
  mercedes: "013",
  bmw: "012",
  audi: "011",
  toyota: "031",
}
```

---

## 🚀 Быстрый старт

1. **Скопируйте API client** и interfaces в проект
2. **Замените существующие вызовы** на новые
3. **Проверьте параметры** - они должны быть строками
4. **Проверьте поля ответа** - они в UPPERCASE
5. **Протестируйте** на простых примерах

---

**Backend готов! Осталось только правильно интегрироваться! 🎯**
