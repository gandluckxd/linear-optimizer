# Исправление ошибки цветов в GUI

## 🐛 Проблема
В таблице результатов оптимизации возникала ошибка:
```
'GlobalColor' object has no attribute 'lighter'
```

## 🔍 Причина
Использование неправильного способа создания цветов в PyQt5:
```python
# НЕПРАВИЛЬНО:
item.setBackground(QtCore.Qt.red.lighter(180))
item.setBackground(QtCore.Qt.yellow.lighter(150))
```

Проблема в том, что `Qt.red` и `Qt.yellow` - это enum значения, а не объекты `QColor`.

## ✅ Решение

### 1. Добавлен импорт QColor:
```python
from PyQt5.QtGui import QColor
```

### 2. Заменены проблемные цвета:
```python
# ПРАВИЛЬНО:
item.setBackground(QColor(255, 200, 200))  # Светло-красный
item.setBackground(QColor(255, 255, 200))  # Светло-желтый
```

### 3. Добавлена дополнительная защита:
```python
try:
    if not is_valid:
        item.setBackground(QColor(255, 200, 200))
    elif used_length > plan.stock_length * 0.95:
        item.setBackground(QColor(255, 255, 200))
except Exception as color_error:
    print(f"⚠️ Ошибка установки цвета: {color_error}")
    # Продолжаем без цвета
```

## 🎯 Результат
- ✅ Устранена ошибка `'GlobalColor' object has no attribute 'lighter'`
- ✅ Цветовая индикация работает корректно
- ✅ Красные строки для невалидных планов
- ✅ Желтые строки для плотно упакованных планов
- ✅ Дополнительная защита от ошибок цветов

## 🔄 Цветовая схема
- **Красный фон (255, 200, 200)**: Ошибочные планы (превышение длины хлыста)
- **Желтый фон (255, 255, 200)**: Плотно упакованные планы (>95% использования)
- **Без цвета**: Нормальные планы

## 📁 Затронутые файлы
- `client/gui/table_widgets.py` - основное исправление
- `client/test_colors.py` - тест исправления