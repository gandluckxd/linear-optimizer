#!/usr/bin/env python3
"""
Диагностика расчета отходов в планах распила
"""

import sys

def test_waste_calculation():
    """Тест расчета отходов"""
    print("🧮 ДИАГНОСТИКА РАСЧЕТА ОТХОДОВ")
    print("=" * 50)
    
    try:
        # Импортируем модули
        from core.models import Profile, Stock, CutPlan
        from core.optimizer import SimpleOptimizer, OptimizationSettings
        print("✅ Модули импортированы")
        
        # Создаем простые тестовые данные
        profiles = [
            Profile(id=1, order_id=1, element_name="Деталь A", profile_code="P001", length=1000, quantity=2),
            Profile(id=2, order_id=1, element_name="Деталь B", profile_code="P001", length=800, quantity=1),
        ]
        
        stocks = [
            Stock(id=1, profile_id=1, length=3000, quantity=1),
        ]
        
        print(f"\n📦 Тестовые данные:")
        print(f"   Профили:")
        for p in profiles:
            print(f"     - {p.element_name}: {p.length}мм x{p.quantity}")
        print(f"   Хлысты:")
        for s in stocks:
            print(f"     - Хлыст {s.id}: {s.length}мм x{s.quantity}")
        
        # Создаем оптимизатор
        settings = OptimizationSettings(
            blade_width=5.0,
            min_remainder_length=300.0,
            max_waste_percent=20.0
        )
        optimizer = SimpleOptimizer(settings)
        print(f"\n✅ Настройки: пропил {settings.blade_width}мм, мин.остаток {settings.min_remainder_length}мм")
        
        # Запускаем оптимизацию
        result = optimizer.optimize(profiles, stocks)
        
        print(f"\n📊 РЕЗУЛЬТАТ ОПТИМИЗАЦИИ:")
        print(f"   Успех: {'✅' if result.success else '❌'}")
        print(f"   Планов: {len(result.cut_plans)}")
        
        # Детальный анализ каждого плана
        for i, plan in enumerate(result.cut_plans):
            print(f"\n🔍 ПЛАН {i+1} (Хлыст {plan.stock_id}):")
            print(f"   Длина хлыста: {plan.stock_length}мм")
            
            # Показываем распилы
            print(f"   Распилы:")
            total_pieces_manual = 0
            total_cuts_manual = 0
            
            for cut in plan.cuts:
                if isinstance(cut, dict):
                    length = cut.get('length', 0)
                    quantity = cut.get('quantity', 0)
                    total_length_cut = length * quantity
                    total_pieces_manual += total_length_cut
                    total_cuts_manual += quantity
                    print(f"     - {quantity}x{length}мм = {total_length_cut}мм")
            
            # Расчеты через методы
            used_length_method = plan.get_used_length(settings.blade_width)
            total_pieces_method = plan.get_total_pieces_length()
            cuts_count_method = plan.get_cuts_count()
            
            # Ручные расчеты
            saw_width_total = settings.blade_width * (total_cuts_manual - 1) if total_cuts_manual > 1 else 0
            used_length_manual = total_pieces_manual + saw_width_total
            waste_manual = plan.stock_length - used_length_manual
            waste_percent_manual = (waste_manual / plan.stock_length * 100) if plan.stock_length > 0 else 0
            
            print(f"\n   📏 РАСЧЕТЫ:")
            print(f"     Сумма деталей (ручной): {total_pieces_manual:.0f}мм")
            print(f"     Сумма деталей (метод):  {total_pieces_method:.0f}мм")
            print(f"     Количество кусков (ручной): {total_cuts_manual}")
            print(f"     Количество кусков (метод):  {cuts_count_method}")
            print(f"     Ширина пропилов: {saw_width_total:.0f}мм ({total_cuts_manual-1} пропилов)")
            print(f"     Использовано (ручной): {used_length_manual:.0f}мм")
            print(f"     Использовано (метод):  {used_length_method:.0f}мм")
            
            print(f"\n   🗑️ ОТХОДЫ:")
            print(f"     Отходы (ручной расчет): {waste_manual:.0f}мм ({waste_percent_manual:.1f}%)")
            print(f"     Отходы (в плане):       {plan.waste:.0f}мм ({plan.waste_percent:.1f}%)")
            
            # Проверяем остаток
            if hasattr(plan, 'remainder') and plan.remainder:
                print(f"     Остаток: {plan.remainder:.0f}мм (>= {settings.min_remainder_length}мм)")
                print(f"     📝 ПРИМЕЧАНИЕ: Остаток >= минимальной длины, поэтому отходы = 0")
            
            # Валидация
            is_valid = plan.validate(settings.blade_width)
            print(f"     Валидность: {'✅' if is_valid else '❌'}")
            
            # Проверяем расхождения
            if abs(used_length_manual - used_length_method) > 0.1:
                print(f"     ⚠️ РАСХОЖДЕНИЕ в использованной длине: {abs(used_length_manual - used_length_method):.1f}мм")
            
            if abs(waste_manual - plan.waste) > 0.1 and not (hasattr(plan, 'remainder') and plan.remainder):
                print(f"     ⚠️ РАСХОЖДЕНИЕ в отходах: {abs(waste_manual - plan.waste):.1f}мм")
        
        # Общая статистика
        stats = result.get_statistics()
        print(f"\n📈 ОБЩАЯ СТАТИСТИКА:")
        for key, value in stats.items():
            print(f"   {key}: {value}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ОШИБКА В ДИАГНОСТИКЕ: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_waste_calculation()
    print(f"\n{'✅ ДИАГНОСТИКА ЗАВЕРШЕНА' if success else '❌ ОШИБКА В ДИАГНОСТИКЕ'}")
    sys.exit(0 if success else 1)