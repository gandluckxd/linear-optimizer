#!/usr/bin/env python3
"""
Тест GUI компонентов Linear Optimizer
"""

import sys
import traceback

def test_step(name, test_func):
    """Безопасное выполнение теста"""
    print(f"\n🔍 {name}")
    print("-" * 50)
    try:
        result = test_func()
        print(f"✅ {name} - УСПЕХ")
        return True, result
    except Exception as e:
        print(f"❌ {name} - ОШИБКА: {e}")
        print(f"   Тип ошибки: {type(e).__name__}")
        print(f"   Детали: {traceback.format_exc()}")
        return False, None

def test_pyqt5_imports():
    """Тест импортов PyQt5"""
    from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QTableWidget
    from PyQt5.QtCore import Qt, QThread, pyqtSignal
    from PyQt5.QtGui import QFont
    return "PyQt5 импорты успешны"

def test_gui_imports():
    """Тест импортов GUI модулей"""
    from gui.table_widgets import (
        fill_optimization_results_table, _create_text_item, _create_numeric_item
    )
    from gui.dialogs import DebugDialog, ProgressDialog
    from gui.config import MAIN_WINDOW_STYLE
    return "GUI модули импортированы"

def test_main_window_import():
    """Тест импорта главного окна"""
    from gui.main_window import LinearOptimizerWindow, OptimizationThread
    return "Главное окно импортировано"

def test_table_widgets():
    """Тест виджетов таблиц"""
    from PyQt5.QtWidgets import QApplication, QTableWidget
    from gui.table_widgets import _create_text_item, _create_numeric_item
    
    # Создаем минимальное QApplication для тестов
    if not QApplication.instance():
        app = QApplication([])
    
    # Тестируем создание элементов таблицы
    text_item = _create_text_item("Тест")
    numeric_item = _create_numeric_item(123.45)
    
    print(f"   Текстовый элемент: {text_item.text()}")
    print(f"   Числовой элемент: {numeric_item.text()}")
    
    return "Виджеты таблиц работают"

def test_optimization_result_display():
    """Тест отображения результатов оптимизации"""
    from PyQt5.QtWidgets import QApplication, QTableWidget
    from gui.table_widgets import fill_optimization_results_table
    from core.models import CutPlan
    
    # Создаем QApplication если не существует
    if not QApplication.instance():
        app = QApplication([])
    
    # Создаем тестовую таблицу
    table = QTableWidget()
    table.setColumnCount(5)
    table.setHorizontalHeaderLabels(["ID хлыста", "Длина хлыста", "Распилы", "Отходы", "% отходов"])
    
    # Создаем тестовый план распила
    test_cuts = [
        {'profile_id': 1, 'length': 1000, 'quantity': 2},
        {'profile_id': 2, 'length': 500, 'quantity': 1}
    ]
    
    test_plan = CutPlan(
        stock_id=1,
        stock_length=3000,
        cuts=test_cuts,
        waste=485,
        waste_percent=16.2
    )
    
    # Тестируем заполнение таблицы
    fill_optimization_results_table(table, [test_plan])
    
    print(f"   Строк в таблице: {table.rowCount()}")
    print(f"   Столбцов в таблице: {table.columnCount()}")
    
    if table.rowCount() > 0:
        for col in range(table.columnCount()):
            item = table.item(0, col)
            if item:
                print(f"   Столбец {col}: {item.text()}")
    
    return "Отображение результатов работает"

def test_main_window_creation():
    """Тест создания главного окна"""
    from PyQt5.QtWidgets import QApplication
    from gui.main_window import LinearOptimizerWindow
    
    # Создаем QApplication если не существует
    if not QApplication.instance():
        app = QApplication([])
    
    # Пытаемся создать главное окно
    try:
        window = LinearOptimizerWindow()
        print(f"   Окно создано: {window.windowTitle()}")
        print(f"   Размер окна: {window.size()}")
        
        # Проверяем основные компоненты
        if hasattr(window, 'optimizer'):
            print(f"   Оптимизатор: {type(window.optimizer).__name__}")
        if hasattr(window, 'profiles'):
            print(f"   Профили инициализированы: {len(window.profiles)}")
        if hasattr(window, 'stocks'):
            print(f"   Хлысты инициализированы: {len(window.stocks)}")
        
        # Не показываем окно, только создаем
        return window
    except Exception as e:
        print(f"   Ошибка создания окна: {e}")
        raise

def test_optimization_thread():
    """Тест потока оптимизации"""
    from PyQt5.QtWidgets import QApplication
    from gui.main_window import OptimizationThread
    from core.optimizer import LinearOptimizer, OptimizationSettings
    from core.models import Profile, Stock
    
    # Создаем QApplication если не существует
    if not QApplication.instance():
        app = QApplication([])
    
    # Создаем тестовые данные
    profiles = [
        Profile(id=1, order_id=1, element_name="Тест", profile_code="P001", length=1000, quantity=1)
    ]
    stocks = [
        Stock(id=1, profile_id=1, length=2000, quantity=1)
    ]
    
    optimizer = LinearOptimizer()
    settings = OptimizationSettings()
    
    # Создаем поток оптимизации
    thread = OptimizationThread(optimizer, profiles, stocks, settings)
    
    print(f"   Поток создан: {type(thread).__name__}")
    print(f"   Профили в потоке: {len(thread.profiles)}")
    print(f"   Хлысты в потоке: {len(thread.stocks)}")
    
    return thread

def main():
    """Главная функция тестирования GUI"""
    print("🖥️ ТЕСТИРОВАНИЕ GUI LINEAR OPTIMIZER")
    print("=" * 60)
    
    tests = [
        ("PyQt5 импорты", test_pyqt5_imports),
        ("GUI модули", test_gui_imports),
        ("Главное окно (импорт)", test_main_window_import),
        ("Виджеты таблиц", test_table_widgets),
        ("Отображение результатов", test_optimization_result_display),
        ("Создание главного окна", test_main_window_creation),
        ("Поток оптимизации", test_optimization_thread),
    ]
    
    results = []
    failed_tests = []
    
    for test_name, test_func in tests:
        success, result = test_step(test_name, test_func)
        results.append((test_name, success, result))
        
        if not success:
            failed_tests.append(test_name)
            print(f"\n⚠️ Тест '{test_name}' провален!")
            break  # Останавливаемся на первой ошибке GUI
    
    print("\n📋 СВОДКА РЕЗУЛЬТАТОВ GUI:")
    print("=" * 60)
    
    for test_name, success, _ in results:
        status = "✅ ПРОШЕЛ" if success else "❌ ПРОВАЛЕН"
        print(f"{status} - {test_name}")
    
    if failed_tests:
        print(f"\n⚠️ ПРОБЛЕМНЫЕ КОМПОНЕНТЫ GUI: {', '.join(failed_tests)}")
        print("Эти компоненты могут быть причиной падения приложения.")
    else:
        print("\n🎉 ВСЕ GUI ТЕСТЫ ПРОШЛИ!")
        print("GUI компоненты работают корректно.")
    
    return len(failed_tests) == 0

if __name__ == "__main__":
    try:
        success = main()
        print(f"\n{'✅ GUI РАБОТАЕТ' if success else '❌ ПРОБЛЕМЫ В GUI'}")
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n💥 КРИТИЧЕСКАЯ ОШИБКА В GUI ТЕСТЕ: {e}")
        traceback.print_exc()
        sys.exit(1)