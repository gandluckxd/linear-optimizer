#!/usr/bin/env python3
"""
Минимальный тест для диагностики проблемы с падением приложения
"""

def test_step(step_name, test_func):
    """Выполняет тестовый шаг с обработкой ошибок"""
    print(f"🔍 {step_name}...")
    try:
        result = test_func()
        print(f"✅ {step_name} - УСПЕХ")
        return True, result
    except Exception as e:
        print(f"❌ {step_name} - ОШИБКА: {e}")
        import traceback
        print(f"   Трассировка: {traceback.format_exc()}")
        return False, None

def main():
    print("🔧 МИНИМАЛЬНЫЙ ТЕСТ LINEAR OPTIMIZER")
    print("=" * 50)
    
    # Шаг 1: Импорт моделей
    success, _ = test_step("Импорт моделей", lambda: __import__('core.models', fromlist=['Profile', 'Stock', 'CutPlan', 'OptimizationResult']))
    if not success:
        return False
    
    # Шаг 2: Создание объектов моделей
    def create_models():
        from core.models import Profile, Stock
        profile = Profile(id=1, order_id=1, element_name="Тест", profile_code="P001", length=1000, quantity=1)
        stock = Stock(id=1, profile_id=1, length=2000, quantity=1)
        return profile, stock
    
    success, models = test_step("Создание моделей", create_models)
    if not success:
        return False
    
    # Шаг 3: Импорт оптимизатора
    success, _ = test_step("Импорт оптимизатора", lambda: __import__('core.optimizer', fromlist=['SimpleOptimizer']))
    if not success:
        return False
    
    # Шаг 4: Создание оптимизатора
    def create_optimizer():
        from core.optimizer import SimpleOptimizer
        return SimpleOptimizer()
    
    success, optimizer = test_step("Создание SimpleOptimizer", create_optimizer)
    if not success:
        return False
    
    # Шаг 5: Тест оптимизации
    def run_optimization():
        profile, stock = models
        return optimizer.optimize([profile], [stock])
    
    success, result = test_step("Запуск оптимизации", run_optimization)
    if not success:
        return False
    
    # Шаг 6: Проверка результата
    def check_result():
        print(f"   Результат успешен: {result.success}")
        print(f"   Планов распила: {len(result.cut_plans)}")
        if result.cut_plans:
            plan = result.cut_plans[0]
            print(f"   План: длина хлыста={plan.stock_length}, отходы={plan.waste}")
            print(f"   Распилы: {plan.cuts}")
        return True
    
    success, _ = test_step("Проверка результата", check_result)
    if not success:
        return False
    
    # Шаг 7: Тест методов CutPlan
    def test_cutplan_methods():
        if result.cut_plans:
            plan = result.cut_plans[0]
            used_length = plan.get_used_length()
            total_pieces = plan.get_total_pieces_length()
            cuts_count = plan.get_cuts_count()
            is_valid = plan.validate()
            print(f"   Использованная длина: {used_length}")
            print(f"   Общая длина кусков: {total_pieces}")
            print(f"   Количество кусков: {cuts_count}")
            print(f"   Корректность: {is_valid}")
        return True
    
    success, _ = test_step("Тест методов CutPlan", test_cutplan_methods)
    if not success:
        return False
    
    # Шаг 8: Тест статистики
    def test_statistics():
        stats = result.get_statistics()
        print(f"   Статистика: {stats}")
        return True
    
    success, _ = test_step("Тест статистики", test_statistics)
    if not success:
        return False
    
    print("\n🎉 ВСЕ ТЕСТЫ ПРОШЛИ УСПЕШНО!")
    return True

if __name__ == "__main__":
    try:
        if main():
            print("\n✅ Оптимизатор работает корректно. Проблема может быть в GUI.")
        else:
            print("\n❌ Обнаружены проблемы в оптимизаторе.")
    except Exception as e:
        print(f"\n💥 КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()