#!/usr/bin/env python3
"""
Самый простой тест для выявления проблемы
"""

print("🔍 Начинаем простой тест...")

try:
    print("1. Импорт моделей...")
    from core.models import Profile, Stock, CutPlan, OptimizationResult
    print("✅ Модели импортированы")
    
    print("2. Импорт настроек...")
    from core.optimizer import OptimizationSettings
    print("✅ Настройки импортированы")
    
    print("3. Импорт SimpleOptimizer...")
    from core.optimizer import SimpleOptimizer
    print("✅ SimpleOptimizer импортирован")
    
    print("4. Импорт LinearOptimizer...")
    from core.optimizer import LinearOptimizer
    print("✅ LinearOptimizer импортирован")
    
    print("5. Создание простых данных...")
    profiles = [
        Profile(id=1, order_id=1, element_name="Тест", profile_code="P001", length=1000, quantity=1)
    ]
    stocks = [
        Stock(id=1, profile_id=1, length=2000, quantity=1)
    ]
    print("✅ Данные созданы")
    
    print("6. Создание SimpleOptimizer...")
    simple_opt = SimpleOptimizer()
    print("✅ SimpleOptimizer создан")
    
    print("7. Тест SimpleOptimizer.optimize...")
    result1 = simple_opt.optimize(profiles, stocks)
    print(f"✅ SimpleOptimizer работает: {result1.success}")
    
    print("8. Создание LinearOptimizer...")
    linear_opt = LinearOptimizer()
    print("✅ LinearOptimizer создан")
    
    print("9. Тест LinearOptimizer.optimize...")
    result2 = linear_opt.optimize(profiles, stocks)
    print(f"✅ LinearOptimizer работает: {result2.success}")
    
    print("🎉 ВСЕ ТЕСТЫ ПРОШЛИ УСПЕШНО!")
    
except Exception as e:
    print(f"❌ ОШИБКА: {e}")
    import traceback
    traceback.print_exc()