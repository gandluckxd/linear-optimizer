#!/usr/bin/env python3
"""
Отладочный скрипт для выявления проблемы с падением приложения
"""

import sys
import traceback

def test_imports():
    """Тестирование импортов"""
    print("🔍 Тестирование импортов...")
    
    try:
        print("  ✅ Импорт datetime...")
        from datetime import datetime
        
        print("  ✅ Импорт typing...")
        from typing import List, Dict, Optional
        
        print("  ✅ Импорт dataclasses...")
        from dataclasses import dataclass, field
        
        print("  ✅ Импорт core.models...")
        from core.models import Profile, Stock, CutPlan, OptimizationResult
        
        print("  ✅ Импорт core.optimizer...")
        from core.optimizer import SimpleOptimizer, OptimizationSettings
        
        print("✅ Все импорты успешны!")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка импорта: {e}")
        traceback.print_exc()
        return False

def test_basic_optimization():
    """Тестирование базовой оптимизации"""
    print("\n🧪 Тестирование базовой оптимизации...")
    
    try:
        from core.models import Profile, Stock
        from core.optimizer import SimpleOptimizer, OptimizationSettings
        
        print("  ✅ Создание тестовых данных...")
        # Простые тестовые данные
        profiles = [
            Profile(id=1, order_id=1, element_name="Тест", profile_code="P001", length=1000, quantity=1)
        ]
        
        stocks = [
            Stock(id=1, profile_id=1, length=2000, quantity=1)
        ]
        
        print("  ✅ Создание оптимизатора...")
        settings = OptimizationSettings(blade_width=5.0, min_remainder_length=300.0)
        optimizer = SimpleOptimizer(settings)
        
        print("  ✅ Запуск оптимизации...")
        result = optimizer.optimize(profiles, stocks)
        
        print(f"  ✅ Результат: успех={result.success}, планов={len(result.cut_plans)}")
        
        if result.cut_plans:
            plan = result.cut_plans[0]
            print(f"  ✅ План: хлыст={plan.stock_length}мм, отходы={plan.waste}мм")
            
            # Тестируем новые методы
            used_length = plan.get_used_length()
            total_pieces = plan.get_total_pieces_length()
            cuts_count = plan.get_cuts_count()
            is_valid = plan.validate()
            
            print(f"  ✅ Валидация: использовано={used_length}мм, кусков={cuts_count}, корректно={is_valid}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка оптимизации: {e}")
        traceback.print_exc()
        return False

def test_gui_imports():
    """Тестирование импортов GUI"""
    print("\n🖥️ Тестирование импортов GUI...")
    
    try:
        print("  ✅ Импорт PyQt5...")
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import Qt
        
        print("  ✅ Импорт gui.table_widgets...")
        from gui.table_widgets import fill_optimization_results_table
        
        print("✅ GUI импорты успешны!")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка GUI импорта: {e}")
        traceback.print_exc()
        return False

def main():
    """Главная функция отладки"""
    print("🔧 ОТЛАДОЧНЫЙ ТЕСТ LINEAR OPTIMIZER")
    print("=" * 50)
    
    # Тест 1: Импорты
    if not test_imports():
        print("\n❌ Тест импортов провален!")
        return False
    
    # Тест 2: Базовая оптимизация
    if not test_basic_optimization():
        print("\n❌ Тест оптимизации провален!")
        return False
    
    # Тест 3: GUI импорты
    if not test_gui_imports():
        print("\n⚠️ Тест GUI импортов провален (возможно, PyQt5 не установлен)")
    
    print("\n🎉 ВСЕ БАЗОВЫЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
    print("Проблема может быть в GUI или в конкретных данных.")
    
    return True

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n💥 КРИТИЧЕСКАЯ ОШИБКА: {e}")
        traceback.print_exc()
        sys.exit(1)