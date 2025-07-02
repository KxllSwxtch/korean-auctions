# 🚗 Схема деталей автомобиля Autohub - Руководство по интеграции

## 📋 Обзор

Была реализована **схема деталей автомобиля** для аукциона Autohub, которая показывает состояние каждой части автомобиля с цветовой кодировкой повреждений.

## ✅ Backend реализован

Backend полностью готов и возвращает схему деталей автомобиля через endpoint `car-detail`.

### Пример ответа API:

```json
{
  "success": true,
  "data": {
    "title": "기아 셀토스(19년~현재) 가솔린 1600cc 시그니처 2WD",
    "car_info": { ... },
    "car_diagram": {
      "car_type": "sedan",
      "background_image": "/images/front/car_info/bg_car1.png",
      "total_parts": 46,
      "damaged_parts": 12,
      "replacement_needed": 3,
      "repair_needed": 9,
      "parts": [
        {
          "part_id": "A01",
          "part_code": "ax010",
          "condition": "X@@",
          "condition_symbol": "X",
          "zone": "left",
          "position_x": 40,
          "position_y": 60,
          "image_path": "/images/front/car_info/A01X.png"
        }
      ]
    }
  }
}
```

## 🎨 Типы автомобилей

Система поддерживает 3 типа автомобилей:

| Тип      | Описание         | Фоновое изображение                  |
| -------- | ---------------- | ------------------------------------ |
| `sedan`  | Седан            | `/images/front/car_info/bg_car1.png` |
| `pickup` | Пикап            | `/images/front/car_info/bg_car2.png` |
| `truck`  | Грузовик/минивэн | `/images/front/car_info/bg_car3.png` |

## 🔧 Состояния частей

| Код   | Символ | Описание                    | Цвет UI    |
| ----- | ------ | --------------------------- | ---------- |
| `@@@` | -      | Нормальное состояние        | Зелёный    |
| `X@@` | `X`    | Требует замены              | Красный    |
| `@A@` | `A`    | Повреждение от аварии       | Оранжевый  |
| `@U@` | `U`    | Требует ремонта/шпатлевки   | Жёлтый     |
| `@E@` | `E`    | Повреждение от эксплуатации | Синий      |
| `@W@` | `W`    | Требует сварки              | Фиолетовый |

## 🗺 Зоны автомобиля

Части сгруппированы по зонам:

- **`left`** - левая сторона автомобиля
- **`top`** - верх автомобиля
- **`right`** - правая сторона автомобиля
- **`bottom`** - низ автомобиля

## 💻 Frontend реализация

### 1. TypeScript интерфейсы

```typescript
interface CarPartCondition {
  NORMAL: "@@@"
  REPLACEMENT_NEEDED: "X@@"
  ACCIDENT_DAMAGE: "@A@"
  REPAIR_NEEDED: "@U@"
  OPERATIONAL_DAMAGE: "@E@"
  WELDING_NEEDED: "@W@"
}

interface CarPart {
  part_id: string // "A01", "B02", "C03"
  part_code: string // "ax010", "bx015"
  condition: keyof CarPartCondition
  condition_symbol: string // "X", "U", "A", "E", "W", ""
  zone: "left" | "top" | "right" | "bottom"
  position_x?: number // X координата на схеме
  position_y?: number // Y координата на схеме
  image_path: string // Путь к изображению части
}

interface CarDiagram {
  car_type: "sedan" | "pickup" | "truck"
  background_image: string
  total_parts: number
  damaged_parts: number
  replacement_needed: number
  repair_needed: number
  parts: CarPart[]
}

interface AutohubCarDetail {
  title: string
  car_info: any
  car_diagram?: CarDiagram // ← Новое поле
}
```

### 2. React компонент схемы

```tsx
import React from "react"

interface CarDiagramProps {
  diagram: CarDiagram
}

const CarDiagram: React.FC<CarDiagramProps> = ({ diagram }) => {
  const getConditionColor = (condition: string): string => {
    switch (condition) {
      case "@@@":
        return "#10B981" // Зелёный
      case "X@@":
        return "#EF4444" // Красный
      case "@A@":
        return "#F59E0B" // Оранжевый
      case "@U@":
        return "#EAB308" // Жёлтый
      case "@E@":
        return "#3B82F6" // Синий
      case "@W@":
        return "#8B5CF6" // Фиолетовый
      default:
        return "#6B7280" // Серый
    }
  }

  const getConditionIcon = (symbol: string): string => {
    return symbol || "○"
  }

  return (
    <div className="car-diagram-container">
      <div className="diagram-header">
        <h3>Схема деталей автомобиля</h3>
        <div className="stats">
          <span>Всего частей: {diagram.total_parts}</span>
          <span>Повреждённых: {diagram.damaged_parts}</span>
          <span>Требует замены: {diagram.replacement_needed}</span>
          <span>Требует ремонта: {diagram.repair_needed}</span>
        </div>
      </div>

      <div className="diagram-view" style={{ position: "relative" }}>
        {/* Фоновое изображение схемы */}
        <img
          src={diagram.background_image}
          alt={`Схема ${diagram.car_type}`}
          style={{ width: "736px", height: "561px" }}
        />

        {/* Части автомобиля */}
        {diagram.parts.map((part) =>
          part.position_x && part.position_y ? (
            <div
              key={part.part_id}
              className="car-part"
              style={{
                position: "absolute",
                left: `${part.position_x}px`,
                top: `${part.position_y}px`,
                backgroundColor: getConditionColor(part.condition),
                color: "white",
                borderRadius: "50%",
                width: "20px",
                height: "20px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "12px",
                fontWeight: "bold",
                cursor: "pointer",
                zIndex: 10,
              }}
              title={`${part.part_id}: ${part.condition}`}
            >
              {getConditionIcon(part.condition_symbol)}
            </div>
          ) : null
        )}
      </div>

      {/* Легенда */}
      <div className="diagram-legend">
        <div className="legend-item">
          <span style={{ color: "#10B981" }}>○</span> Нормальное состояние
        </div>
        <div className="legend-item">
          <span style={{ color: "#EF4444" }}>X</span> Требует замены
        </div>
        <div className="legend-item">
          <span style={{ color: "#F59E0B" }}>A</span> Авария
        </div>
        <div className="legend-item">
          <span style={{ color: "#EAB308" }}>U</span> Ремонт
        </div>
        <div className="legend-item">
          <span style={{ color: "#3B82F6" }}>E</span> Эксплуатация
        </div>
        <div className="legend-item">
          <span style={{ color: "#8B5CF6" }}>W</span> Сварка
        </div>
      </div>
    </div>
  )
}

export default CarDiagram
```

### 3. Использование в компоненте автомобиля

```tsx
import { CarDiagram } from "./CarDiagram"

const CarDetailPage: React.FC<{ carData: AutohubCarDetail }> = ({
  carData,
}) => {
  return (
    <div className="car-detail">
      <h1>{carData.title}</h1>

      {/* Основная информация об автомобиле */}
      <CarInfo info={carData.car_info} />

      {/* Схема деталей */}
      {carData.car_diagram && (
        <section className="car-diagram-section">
          <CarDiagram diagram={carData.car_diagram} />
        </section>
      )}

      {/* Остальные секции */}
    </div>
  )
}
```

### 4. CSS стили

```css
.car-diagram-container {
  background: white;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  margin: 20px 0;
}

.diagram-header {
  margin-bottom: 20px;
}

.diagram-header h3 {
  margin: 0 0 10px 0;
  font-size: 18px;
  font-weight: 600;
}

.stats {
  display: flex;
  gap: 15px;
  font-size: 14px;
  color: #6b7280;
}

.stats span {
  background: #f3f4f6;
  padding: 4px 8px;
  border-radius: 4px;
}

.diagram-view {
  display: flex;
  justify-content: center;
  margin: 20px 0;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}

.car-part {
  transition: transform 0.2s ease;
}

.car-part:hover {
  transform: scale(1.2);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

.diagram-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 15px;
  margin-top: 15px;
  padding-top: 15px;
  border-top: 1px solid #e5e7eb;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 14px;
}

.legend-item span {
  font-weight: bold;
  font-size: 16px;
}
```

## 🧪 Тестирование

### Endpoint для тестирования:

```
GET /api/v1/autohub/car-detail/1001?auction_date=2025-07-02&auction_title=안성%202025/07/02%201331회차%20경매&auction_code=AC202506250001&receive_code=RC202506250755
```

### Пример тестового ответа:

- ✅ **46 частей** в схеме
- ✅ **12 поврежденных** частей
- ✅ **3 требуют замены** (красные X)
- ✅ **9 требуют ремонта** (жёлтые U, оранжевые A, синие E)

## 📱 Мобильная адаптация

```css
@media (max-width: 768px) {
  .diagram-view img {
    width: 100%;
    height: auto;
    max-width: 500px;
  }

  .car-part {
    width: 16px;
    height: 16px;
    font-size: 10px;
  }

  .stats {
    flex-direction: column;
    gap: 8px;
  }

  .diagram-legend {
    justify-content: center;
  }
}
```

## 🎯 Результат

После реализации пользователи смогут:

1. **Видеть схему автомобиля** с точным расположением частей
2. **Различать состояния частей** по цветам и символам
3. **Получать статистику** по повреждениям
4. **Понимать объём ремонта** перед покупкой
5. **Принимать обоснованные решения** о покупке

## ⚡ Быстрый старт

1. Обновите TypeScript интерфейсы
2. Добавьте компонент `CarDiagram`
3. Интегрируйте в страницу автомобиля
4. Добавьте CSS стили
5. Протестируйте на тестовом автомобиле

**Готово! 🚗✨**
