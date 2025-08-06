#!/usr/bin/env python3
"""
Тест для определения причины падения приложения
"""

import sys
import traceback
import os

def safe_test(name, test_func):
    """Безопасное выполнение теста"""
    print(f"\n🔍 {name}")
    print("-" * 40)
    try:
        result = test_func()
        print(f"✅ {name} - УСПЕХ")
        return True, result
    except Exception as e:
        print(f"❌ {name} - ОШИБКА: {e}")
        print(f"   Тип ошибки: {type(e).__name__}")
        print(f"   Детали: {traceback.format_exc()}")
        return False, None

def test_basic_imports():
    """Тест базовых импортов"""
    from core.models import Profile, Stock, CutPlan, OptimizationResult
    from core.optimizer import SimpleOptimizer, LinearOptimizer, OptimizationSettings
    return "Импорты успешны"

def test_data_creation():
    """Тест создания данных"""
    from core.models import Profile, Stock
    
    profile = Profile(
        id=1, 
        order_id=1, 
        element_name="Тестовая деталь", 
        profile_code="TEST001", 
        length=1500.0, 
        quantity=2
    )
    
    stock = Stock(
        id=1,
        profile_id=1,
        length=3500.0,
        quantity=1
    )
    
    return profile, stock

def test_simple_optimization():
    """Тест простой оптимизации"""
    from core.optimizer import SimpleOptimizer
    from core.models import Profile, Stock
    
    # Создаем простые данные
    profiles = [
        Profile(id=1, order_id=1, element_name="Деталь1", profile_code="P001", length=1000, quantity=1),
        Profile(id=2, order_id=1, element_name="Деталь2", profile_code="P001", length=800, quantity=1)
    ]
    
    stocks = [
        Stock(id=1, profile_id=1, length=2500, quantity=1)
    ]
    
    optimizer = SimpleOptimizer()
    result = optimizer.optimize(profiles, stocks)
    
    print(f"   Успех: {result.success}")
    print(f"   Планов: {len(result.cut_plans)}")
    print(f"   Сообщение: {result.message}")
    
    return result

def test_linear_optimizer():
    """Тест LinearOptimizer"""
    from core.optimizer import LinearOptimizer
    from core.models import Profile, Stock
    
    profiles = [
        Profile(id=1, order_id=1, element_name="Деталь", profile_code="P001", length=1200, quantity=1)
    ]
    
    stocks = [
        Stock(id=1, profile_id=1, length=2000, quantity=1)
    ]
    
    optimizer = LinearOptimizer()
    result = optimizer.optimize(profiles, stocks)
    
    print(f"   Успех: {result.success}")
    print(f"   Планов: {len(result.cut_plans)}")
    
    return result

def test_cutplan_methods():
    """Тест методов CutPlan"""
    from core.models import CutPlan
    
    # Создаем простой план
    cuts = [
        {'profile_id': 1, 'length': 1000, 'quantity': 2},
        {'profile_id': 2, 'length': 500, 'quantity': 1}
    ]
    
    plan = CutPlan(
        stock_id=1,
        stock_length=3000,
        cuts=cuts,
        waste=485,
        waste_percent=16.2
    )
    
    used_length = plan.get_used_length()
    total_pieces = plan.get_total_pieces_length()
    cuts_count = plan.get_cuts_count()
    is_valid = plan.validate()
    
    print(f"   Использовано: {used_length}мм")
    print(f"   Общая длина кусков: {total_pieces}мм")
    print(f"   Количество кусков: {cuts_count}")
    print(f"   Корректность: {is_valid}")
    
    return plan

def test_gui_imports():
    """Тест GUI импортов"""
    try:
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import Qt
        from gui.table_widgets import fill_optimization_results_table
        return "GUI импорты успешны"
    except ImportError as e:
        print(f"   Проблема с GUI: {e}")
        return False

def main():
    """Главная функция диагностики"""
    print("🔧 ДИАГНОСТИКА ПАДЕНИЯ LINEAR OPTIMIZER")
    print("=" * 60)
    
    tests = [
        ("Базовые импорты", test_basic_imports),
        ("Создание данных", test_data_creation),
        ("Простая оптимизация", test_simple_optimization),
        ("LinearOptimizer", test_linear_optimizer),
        ("Методы CutPlan", test_cutplan_methods),
        ("GUI импорты", test_gui_imports),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        success, result = safe_test(test_name, test_func)
        results.append((test_name, success, result))
        
        if not success:
            print(f"\n⚠️ Тест '{test_name}' провален - возможная причина падения!")
    
    print("\n📋 СВОДКА РЕЗУЛЬТАТОВ:")
    print("=" * 60)
    
    failed_tests = []
    for test_name, success, _ in results:
        status = "✅ ПРОШЕЛ" if success else "❌ ПРОВАЛЕН"
        print(f"{status} - {test_name}")
        if not success:
            failed_tests.append(test_name)
    
    if failed_tests:
        print(f"\n⚠️ ПРОБЛЕМНЫЕ ТЕСТЫ: {', '.join(failed_tests)}")
        print("Эти компоненты могут быть причиной падения приложения.")
    else:
        print("\n🎉 ВСЕ ТЕСТЫ ПРОШЛИ! Проблема может быть в GUI или конкретных данных.")
    
    return len(failed_tests) == 0

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n💥 КРИТИЧЕСКАЯ ОШИБКА В ТЕСТЕ: {e}")
        traceback.print_exc()
        sys.exit(1)