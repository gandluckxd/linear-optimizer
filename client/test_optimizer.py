#!/usr/bin/env python3
"""
Тестовый скрипт для проверки исправлений в алгоритме оптимизации
"""

from core.optimizer import SimpleOptimizer, OptimizationSettings
from core.models import Profile, Stock, CutPlan

def test_optimizer():
    """Тестирование оптимизатора с проблемными данными"""
    print("🧪 Тестирование исправленного оптимизатора")
    print("=" * 50)
    
    # Создаем тестовые данные (проблемный случай)
    profiles = [
        Profile(id=1, order_id=1, element_name="Деталь A", profile_code="P001", length=1110, quantity=5),
        Profile(id=2, order_id=1, element_name="Деталь B", profile_code="P002", length=860, quantity=2),
        Profile(id=3, order_id=1, element_name="Деталь C", profile_code="P003", length=610, quantity=8),
    ]
    
    stocks = [
        Stock(id=1, profile_id=1, length=4460, quantity=1),  # Проблемный хлыст
        Stock(id=2, profile_id=1, length=6000, quantity=2),  # Нормальный хлыст
    ]
    
    print(f"📋 Профили для распила:")
    for profile in profiles:
        print(f"   {profile.element_name}: {profile.length}мм x {profile.quantity}шт")
    
    print(f"\n📦 Хлысты:")
    for stock in stocks:
        print(f"   Хлыст {stock.id}: {stock.length}мм x {stock.quantity}шт")
    
    # Создаем оптимизатор
    settings = OptimizationSettings(
        blade_width=5.0,
        min_remainder_length=300.0,
        max_waste_percent=15.0
    )
    
    optimizer = SimpleOptimizer(settings)
    
    print(f"\n🔧 Запуск оптимизации...")
    result = optimizer.optimize(profiles, stocks)
    
    print(f"\n📊 Результаты оптимизации:")
    print(f"   Успех: {result.success}")
    print(f"   Планов распила: {len(result.cut_plans)}")
    print(f"   Общие отходы: {result.total_waste_percent:.1f}%")
    print(f"   Сообщение: {result.message}")
    
    if result.cut_plans:
        print(f"\n📋 Детали планов распила:")
        for i, plan in enumerate(result.cut_plans):
            analysis = optimizer._analyze_cut_plan(plan)
            print(f"\n   Хлыст {plan.stock_id}:")
            print(f"     Длина хлыста: {plan.stock_length:.0f}мм")
            print(f"     Сумма деталей: {analysis['total_pieces_length']:.0f}мм")
            print(f"     Ширина пропилов: {analysis['saw_width_total']:.0f}мм")
            print(f"     Использованная длина: {analysis['used_length']:.0f}мм")
            print(f"     Отходы: {plan.waste:.0f}мм ({plan.waste_percent:.1f}%)")
            print(f"     Корректность: {'✅' if analysis['is_valid'] else '❌'}")
            
            if not analysis['is_valid']:
                print(f"     ПРЕВЫШЕНИЕ: {analysis['used_length'] - analysis['stock_length']:.0f}мм")
            
            print(f"     Распилы: {analysis['cuts_detail']}")

if __name__ == "__main__":
    test_optimizer() 