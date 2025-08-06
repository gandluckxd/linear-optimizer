#!/usr/bin/env python3
"""
Тестовый скрипт для проверки исправлений в алгоритме оптимизации
Проверяет проблему с неправильным расчетом использованной длины
"""

from core.optimizer import SimpleOptimizer, OptimizationSettings
from core.models import Profile, Stock

def test_problem_case():
    """Тестирование конкретного проблемного случая"""
    print("🧪 Тестирование исправлений оптимизатора")
    print("=" * 60)
    
    # Создаем проблемный случай: хлыст 4460мм, должно поместиться:
    # 4 детали по 1110мм = 4440мм + 3 пропила по 5мм = 4455мм 
    # Итого: 4455мм < 4460мм ✅
    profiles = [
        Profile(id=1, order_id=1, element_name="Деталь 1110", profile_code="P001", length=1110, quantity=4),
    ]
    
    stocks = [
        Stock(id=1, profile_id=1, length=4460, quantity=1),
    ]
    
    print(f"📋 Тестовые данные:")
    print(f"   Хлыст: {stocks[0].length}мм")
    for profile in profiles:
        print(f"   Профиль: {profile.length}мм x {profile.quantity}шт = {profile.length * profile.quantity}мм")
        print(f"   + Пропилы: {(profile.quantity - 1) * 5}мм (ширина пропила 5мм)")
        print(f"   = Общая длина: {profile.length * profile.quantity + (profile.quantity - 1) * 5}мм")
    
    # Создаем оптимизатор с правильными настройками
    settings = OptimizationSettings(
        blade_width=5.0,
        min_remainder_length=300.0,
        max_waste_percent=15.0
    )
    
    optimizer = SimpleOptimizer(settings)
    
    print(f"\n🔧 Запуск оптимизации...")
    result = optimizer.optimize(profiles, stocks)
    
    print(f"\n📊 Результаты:")
    print(f"   Успех: {result.success}")
    print(f"   Планов распила: {len(result.cut_plans)}")
    print(f"   Общие отходы: {result.total_waste_percent:.1f}%")
    print(f"   Сообщение: {result.message}")
    
    if result.cut_plans:
        print(f"\n📋 Детальный анализ планов:")
        for i, plan in enumerate(result.cut_plans):
            analysis = optimizer._analyze_cut_plan(plan)
            print(f"\n   План {i+1} (Хлыст {plan.stock_id}):")
            print(f"     Длина хлыста: {plan.stock_length:.0f}мм")
            print(f"     Количество деталей: {analysis['cuts_count']}шт")
            print(f"     Сумма длин деталей: {analysis['total_pieces_length']:.0f}мм")
            print(f"     Ширина пропилов: {analysis['saw_width_total']:.0f}мм")
            print(f"     Общая использованная длина: {analysis['used_length']:.0f}мм")
            print(f"     Отходы: {plan.waste:.0f}мм ({plan.waste_percent:.1f}%)")
            print(f"     Корректность: {'✅ ДА' if analysis['is_valid'] else '❌ НЕТ'}")
            
            if not analysis['is_valid']:
                print(f"     ⚠️ ПРЕВЫШЕНИЕ: {analysis['used_length'] - analysis['stock_length']:.0f}мм")
            else:
                print(f"     ✅ Свободно: {analysis['stock_length'] - analysis['used_length']:.0f}мм")
            
            print(f"     Детали: {analysis['cuts_detail']}")
    
    return result

def test_multiple_cases():
    """Тестирование нескольких случаев"""
    print(f"\n\n🔬 Тестирование различных случаев:")
    print("=" * 60)
    
    test_cases = [
        {
            "name": "Простой случай",
            "profiles": [Profile(id=1, order_id=1, element_name="Деталь", profile_code="P001", length=1000, quantity=2)],
            "stocks": [Stock(id=1, profile_id=1, length=2100, quantity=1)]
        },
        {
            "name": "Граничный случай",
            "profiles": [Profile(id=1, order_id=1, element_name="Деталь", profile_code="P001", length=1000, quantity=3)],
            "stocks": [Stock(id=1, profile_id=1, length=3010, quantity=1)]  # 3000 + 10 пропилов = 3010
        },
        {
            "name": "Невозможный случай",
            "profiles": [Profile(id=1, order_id=1, element_name="Деталь", profile_code="P001", length=1000, quantity=3)],
            "stocks": [Stock(id=1, profile_id=1, length=3000, quantity=1)]  # Не хватает места для пропилов
        }
    ]
    
    optimizer = SimpleOptimizer()
    
    for i, case in enumerate(test_cases):
        print(f"\n📋 Тест {i+1}: {case['name']}")
        result = optimizer.optimize(case['profiles'], case['stocks'])
        
        if result.cut_plans:
            plan = result.cut_plans[0]
            analysis = optimizer._analyze_cut_plan(plan)
            print(f"   Корректность: {'✅' if analysis['is_valid'] else '❌'}")
            print(f"   Использовано: {analysis['used_length']:.0f}мм из {analysis['stock_length']:.0f}мм")
        else:
            print(f"   Результат: Нет планов распила")

if __name__ == "__main__":
    # Основной тест проблемного случая
    result = test_problem_case()
    
    # Дополнительные тесты
    test_multiple_cases()
    
    print(f"\n🎯 Заключение:")
    if result.success and result.cut_plans:
        all_valid = all(plan.validate(5.0) for plan in result.cut_plans)
        if all_valid:
            print("✅ Все исправления работают корректно!")
            print("✅ Расчет использованной длины теперь правильный")
            print("✅ Валидация планов работает")
        else:
            print("❌ Обнаружены некорректные планы")
    else:
        print("❌ Оптимизация не удалась")