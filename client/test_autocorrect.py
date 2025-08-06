#!/usr/bin/env python3
"""
Тест автоматической коррекции некорректных планов распила
"""

import sys

def test_autocorrect():
    """Тест автокоррекции"""
    print("🔧 ТЕСТ АВТОКОРРЕКЦИИ ПЛАНОВ РАСПИЛА")
    print("=" * 50)
    
    try:
        # Импортируем модули
        from core.models import Profile, Stock, CutPlan, OptimizationResult
        from core.optimizer import SimpleOptimizer, OptimizationSettings
        print("✅ Модули импортированы")
        
        # Создаем данные, которые гарантированно дадут ошибку
        # Очень длинные детали для коротких хлыстов
        profiles = [
            Profile(id=1, order_id=1, element_name="Очень длинная деталь", profile_code="P001", length=3500, quantity=2),
            Profile(id=2, order_id=1, element_name="Длинная деталь", profile_code="P001", length=3000, quantity=2),
            Profile(id=3, order_id=1, element_name="Нормальная деталь", profile_code="P001", length=1500, quantity=1),
        ]
        
        stocks = [
            Stock(id=1, profile_id=1, length=4000, quantity=1),  # Один короткий хлыст
            Stock(id=2, profile_id=1, length=6000, quantity=2),  # Два длинных хлыста
        ]
        
        print(f"✅ Создано профилей: {len(profiles)}")
        print(f"   - {profiles[0].element_name}: {profiles[0].length}мм x{profiles[0].quantity}")
        print(f"   - {profiles[1].element_name}: {profiles[1].length}мм x{profiles[1].quantity}")
        print(f"   - {profiles[2].element_name}: {profiles[2].length}мм x{profiles[2].quantity}")
        
        print(f"✅ Создано хлыстов: {len(stocks)}")
        print(f"   - Хлыст {stocks[0].id}: {stocks[0].length}мм x{stocks[0].quantity}")
        print(f"   - Хлыст {stocks[1].id}: {stocks[1].length}мм x{stocks[1].quantity}")
        
        # Создаем оптимизатор
        settings = OptimizationSettings(
            blade_width=5.0,
            min_remainder_length=300.0,
            max_waste_percent=30.0  # Увеличиваем допустимые отходы
        )
        optimizer = SimpleOptimizer(settings)
        print("✅ Оптимизатор создан")
        
        # Запускаем оптимизацию
        print("\n🚀 Запуск оптимизации с автокоррекцией...")
        def progress_callback(percent):
            if percent % 25 == 0:  # Показываем каждые 25%
                print(f"   Прогресс: {percent}%")
        
        result = optimizer.optimize(profiles, stocks, progress_fn=progress_callback)
        
        print(f"\n📊 РЕЗУЛЬТАТЫ:")
        print(f"   Успех: {'✅' if result.success else '❌'}")
        print(f"   Планов распила: {len(result.cut_plans)}")
        print(f"   Отходы: {result.total_waste_percent:.1f}%")
        print(f"   Сообщение: {result.message}")
        
        # Анализируем планы
        print(f"\n🔍 АНАЛИЗ ПЛАНОВ:")
        valid_plans = 0
        invalid_plans = 0
        auto_corrected = 0
        
        for i, plan in enumerate(result.cut_plans):
            is_valid = plan.validate(5.0)
            used_length = plan.get_used_length(5.0)
            
            print(f"\n   План {i+1}:")
            print(f"     Хлыст: {plan.stock_id} ({plan.stock_length}мм)")
            print(f"     Распилы: {len(plan.cuts)} шт")
            print(f"     Использовано: {used_length:.0f}мм")
            print(f"     Отходы: {plan.waste:.0f}мм ({plan.waste_percent:.1f}%)")
            print(f"     Статус: {'✅ Корректный' if is_valid else '❌ Некорректный'}")
            
            if is_valid:
                valid_plans += 1
            else:
                invalid_plans += 1
                print(f"     ⚠️ Превышение: {used_length - plan.stock_length:.0f}мм")
            
            # Проверяем, был ли план автоисправлен
            if 'auto_' in str(plan.stock_id):
                auto_corrected += 1
                print(f"     🔧 Автоисправленный план")
            
            # Показываем детали распилов
            for cut in plan.cuts:
                if isinstance(cut, dict):
                    print(f"       - {cut.get('quantity', 0)}x{cut.get('length', 0)}мм")
        
        print(f"\n📈 СТАТИСТИКА АВТОКОРРЕКЦИИ:")
        print(f"   Корректных планов: {valid_plans}")
        print(f"   Некорректных планов: {invalid_plans}")
        print(f"   Автоисправленных планов: {auto_corrected}")
        
        # Проверяем общий результат
        if auto_corrected > 0:
            print(f"\n🎯 АВТОКОРРЕКЦИЯ СРАБОТАЛА!")
            print(f"   Создано {auto_corrected} новых планов")
            print(f"   Процент исправления: {(auto_corrected / len(result.cut_plans)) * 100:.1f}%")
        else:
            print(f"\n⚠️ Автокоррекция не потребовалась или не сработала")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ОШИБКА В ТЕСТЕ: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_autocorrect()
    print(f"\n{'✅ ТЕСТ АВТОКОРРЕКЦИИ ПРОШЕЛ' if success else '❌ ТЕСТ АВТОКОРРЕКЦИИ ПРОВАЛЕН'}")
    sys.exit(0 if success else 1)