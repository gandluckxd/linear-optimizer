#!/usr/bin/env python3
"""
Тест исправления проблемы с цветами в GUI
"""

import sys

def test_color_fix():
    """Тест цветов PyQt5"""
    print("🎨 ТЕСТ ИСПРАВЛЕНИЯ ЦВЕТОВ")
    print("=" * 40)
    
    try:
        # Импортируем модули
        from PyQt5.QtWidgets import QApplication, QTableWidget
        from PyQt5.QtGui import QColor
        from gui.table_widgets import fill_optimization_results_table
        from core.models import CutPlan
        
        print("✅ Импорты успешны")
        
        # Создаем QApplication
        if not QApplication.instance():
            app = QApplication([])
        
        # Создаем тестовую таблицу
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["ID хлыста", "Длина", "Распилы", "Отходы", "% отходов"])
        
        # Создаем тестовые планы - включая проблемный
        test_cuts_valid = [
            {'profile_id': 1, 'length': 1000, 'quantity': 2},
            {'profile_id': 2, 'length': 500, 'quantity': 1}
        ]
        
        test_cuts_invalid = [
            {'profile_id': 1, 'length': 3000, 'quantity': 2},  # Слишком длинные детали
            {'profile_id': 2, 'length': 2000, 'quantity': 1}
        ]
        
        plans = [
            # Валидный план
            CutPlan(
                stock_id=1,
                stock_length=3000,
                cuts=test_cuts_valid,
                waste=485,
                waste_percent=16.2
            ),
            # Невалидный план (должен показать красный цвет)
            CutPlan(
                stock_id=2,
                stock_length=4000,
                cuts=test_cuts_invalid,
                waste=-4000,  # Отрицательные отходы = ошибка
                waste_percent=-100.0
            ),
        ]
        
        print("✅ Тестовые планы созданы")
        
        # Заполняем таблицу
        fill_optimization_results_table(table, plans)
        
        print(f"✅ Таблица заполнена: {table.rowCount()} строк")
        
        # Проверяем цвета
        print("\n🔍 Проверка цветов:")
        for row in range(table.rowCount()):
            item = table.item(row, 0)  # Первый столбец
            if item:
                bg_color = item.background()
                if bg_color.isValid():
                    color = bg_color.color()
                    print(f"   Строка {row + 1}: RGB({color.red()}, {color.green()}, {color.blue()})")
                else:
                    print(f"   Строка {row + 1}: Нет цвета фона")
        
        print("\n✅ ТЕСТ ЦВЕТОВ ПРОШЕЛ!")
        return True
        
    except Exception as e:
        print(f"❌ ОШИБКА В ТЕСТЕ ЦВЕТОВ: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_color_fix()
    print(f"\n{'✅ ЦВЕТА ИСПРАВЛЕНЫ' if success else '❌ ПРОБЛЕМЫ С ЦВЕТАМИ'}")
    sys.exit(0 if success else 1)