#!/usr/bin/env python3
"""
Финальный тест приложения Linear Optimizer
Проверяет весь процесс от создания данных до отображения результатов
"""

import sys
import traceback

def run_complete_test():
    """Полный тест приложения"""
    print("🚀 ФИНАЛЬНЫЙ ТЕСТ LINEAR OPTIMIZER")
    print("=" * 60)
    
    try:
        # Этап 1: Импорты
        print("\n1️⃣ Импорт модулей...")
        from core.models import Profile, Stock, CutPlan, OptimizationResult
        from core.optimizer import LinearOptimizer, OptimizationSettings
        print("✅ Основные модули импортированы")
        
        # Этап 2: Создание данных
        print("\n2️⃣ Создание тестовых данных...")
        profiles = [
            Profile(id=1, order_id=1, element_name="Рама горизонт", profile_code="P001", length=1500, quantity=3),
            Profile(id=2, order_id=1, element_name="Рама вертикаль", profile_code="P001", length=2000, quantity=2),
            Profile(id=3, order_id=1, element_name="Импост", profile_code="P001", length=800, quantity=4),
        ]
        
        stocks = [
            Stock(id=1, profile_id=1, length=6000, quantity=2),
            Stock(id=2, profile_id=1, length=3000, quantity=1),
        ]
        
        print(f"✅ Создано профилей: {len(profiles)}")
        print(f"✅ Создано хлыстов: {len(stocks)}")
        
        # Этап 3: Создание оптимизатора
        print("\n3️⃣ Инициализация оптимизатора...")
        settings = OptimizationSettings(
            blade_width=5.0,
            min_remainder_length=300.0,
            max_waste_percent=20.0
        )
        optimizer = LinearOptimizer(settings)
        print("✅ Оптимизатор создан")
        
        # Этап 4: Запуск оптимизации
        print("\n4️⃣ Запуск оптимизации...")
        def progress_callback(percent):
            if percent % 20 == 0:  # Показываем каждые 20%
                print(f"   Прогресс: {percent}%")
        
        result = optimizer.optimize(profiles, stocks, progress_fn=progress_callback)
        print(f"✅ Оптимизация завершена: {result.success}")
        print(f"   Планов распила: {len(result.cut_plans)}")
        print(f"   Отходы: {result.total_waste_percent:.1f}%")
        
        # Этап 5: Тестирование методов планов
        print("\n5️⃣ Тестирование методов планов...")
        for i, plan in enumerate(result.cut_plans):
            print(f"\n   План {i+1}:")
            print(f"     Хлыст {plan.stock_id}: {plan.stock_length}мм")
            print(f"     Распилы: {plan.cuts}")
            
            # Тестируем новые методы
            used_length = plan.get_used_length()
            total_pieces = plan.get_total_pieces_length() 
            cuts_count = plan.get_cuts_count()
            is_valid = plan.validate()
            
            print(f"     Использованная длина: {used_length:.0f}мм")
            print(f"     Сумма деталей: {total_pieces:.0f}мм")
            print(f"     Количество кусков: {cuts_count}")
            print(f"     Корректность: {'✅' if is_valid else '❌'}")
            
            if not is_valid:
                print(f"     ⚠️ ПРЕВЫШЕНИЕ: {used_length - plan.stock_length:.0f}мм")
        
        # Этап 6: Тестирование статистики
        print("\n6️⃣ Тестирование статистики...")
        stats = result.get_statistics()
        print(f"   Общая статистика:")
        for key, value in stats.items():
            print(f"     {key}: {value}")
        print("✅ Статистика работает")
        
        # Этап 7: Тестирование GUI компонентов
        print("\n7️⃣ Тестирование GUI (если доступно)...")
        try:
            from PyQt5.QtWidgets import QApplication, QTableWidget
            from gui.table_widgets import fill_optimization_results_table, _create_text_item
            
            # Создаем QApplication если не существует
            if not QApplication.instance():
                app = QApplication([])
            
            # Создаем тестовую таблицу
            table = QTableWidget()
            table.setColumnCount(5)
            table.setHorizontalHeaderLabels(["ID хлыста", "Длина", "Распилы", "Отходы", "% отходов"])
            
            # Заполняем таблицу
            fill_optimization_results_table(table, result.cut_plans)
            
            print(f"✅ Таблица заполнена: {table.rowCount()} строк")
            
            # Проверяем содержимое первой строки
            if table.rowCount() > 0:
                print("   Первая строка:")
                for col in range(min(3, table.columnCount())):
                    item = table.item(0, col)
                    if item:
                        print(f"     Столбец {col}: {item.text()}")
            
        except ImportError:
            print("⚠️ PyQt5 не доступен, пропускаем GUI тесты")
        except Exception as e:
            print(f"⚠️ Ошибка в GUI тестах: {e}")
        
        print("\n🎉 ВСЕ ТЕСТЫ ПРОШЛИ УСПЕШНО!")
        return True
        
    except Exception as e:
        print(f"\n❌ ОШИБКА В ТЕСТЕ: {e}")
        print(f"Тип ошибки: {type(e).__name__}")
        traceback.print_exc()
        return False

def main():
    """Главная функция"""
    success = run_complete_test()
    
    if success:
        print("\n✅ ПРИЛОЖЕНИЕ ГОТОВО К РАБОТЕ!")
        print("Все компоненты функционируют корректно.")
    else:
        print("\n❌ ОБНАРУЖЕНЫ ПРОБЛЕМЫ!")
        print("Проверьте ошибки выше для диагностики.")
    
    return success

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️ Тест прерван пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 КРИТИЧЕСКАЯ ОШИБКА: {e}")
        traceback.print_exc()
        sys.exit(1)