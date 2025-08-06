"""
Простейший и надежный оптимизатор раскроя профилей
Версия без внешних зависимостей для максимальной стабильности

Автор: Артем
"""

import time
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

# Импорт моделей
from .models import Profile, Stock, CutPlan, OptimizationResult

@dataclass
class OptimizationSettings:
    """Настройки оптимизации раскроя"""
    blade_width: float = 5.0              # Ширина пропила в мм
    min_remainder_length: float = 300.0   # Минимальная длина остатка в мм
    max_waste_percent: float = 15.0       # Максимальный процент отходов
    pair_optimization: bool = True        # Парная оптимизация
    use_remainders: bool = True          # Использовать остатки
    time_limit_seconds: int = 60         # Лимит времени


class SimpleOptimizer:
    """
    Простейший оптимизатор раскроя - гарантированно работающий алгоритм
    """
    
    def __init__(self, settings: OptimizationSettings = None):
        self.settings = settings or OptimizationSettings()
        self.solve_time = 0.0
    
    def optimize(self, profiles: List[Profile], stocks: List[Stock], 
                settings: OptimizationSettings = None, progress_fn=None) -> OptimizationResult:
        """
        Главный метод оптимизации
        
        Args:
            profiles: Список профилей для распила
            stocks: Список доступных хлыстов 
            settings: Настройки оптимизации
            progress_fn: Функция прогресса
            
        Returns:
            OptimizationResult: Результат оптимизации
        """
        start_time = time.time()
        
        try:
            # Используем переданные настройки
            if settings:
                self.settings = settings
                
            if progress_fn:
                progress_fn(10)
            
            # Валидация входных данных
            if not profiles:
                return self._create_error_result("Нет профилей для распила")
                
            if not stocks:
                return self._create_error_result("Нет доступных хлыстов")
            
            # Фильтруем данные
            valid_profiles = [p for p in profiles if p.quantity > 0 and p.length > 0]
            valid_stocks = [s for s in stocks if s.quantity > 0 and s.length > 0]
            
            if not valid_profiles:
                return self._create_error_result("Нет действительных профилей")
                
            if not valid_stocks:
                return self._create_error_result("Нет действительных хлыстов")
        
            if progress_fn:
                progress_fn(25)
                    
            # Проверяем возможность размещения
            max_stock_length = max(s.length for s in valid_stocks)
            impossible = [p for p in valid_profiles if p.length > max_stock_length - self.settings.blade_width]
            
            if impossible:
                names = [p.element_name for p in impossible[:3]]
                return self._create_error_result(f"Профили не помещаются: {', '.join(names)}")
        
            if progress_fn:
                progress_fn(40)
                
            # Сортируем профили по убыванию длины
            valid_profiles.sort(key=lambda p: p.length, reverse=True)
            
            # Запускаем простейший алгоритм
            cut_plans = self._simple_fit_algorithm(valid_profiles, valid_stocks, progress_fn)
        
            if progress_fn:
                progress_fn(90)
            
            # Рассчитываем статистику
            total_waste = sum(plan.waste for plan in cut_plans)
            total_length = sum(plan.stock_length for plan in cut_plans)
            waste_percent = (total_waste / total_length * 100) if total_length > 0 else 0
            
            self.solve_time = time.time() - start_time
            
            result = OptimizationResult(
                cut_plans=cut_plans,
                total_waste=total_waste,
                total_waste_percent=waste_percent,
                settings=self.settings,
                success=True,
                message=f"Оптимизация завершена за {self.solve_time:.1f}с"
            )
            
            # Добавляем статистику
            result.statistics = self._calculate_stats(cut_plans)
            
            if progress_fn:
                progress_fn(100)
                
            return result
                
        except Exception as e:
            error_msg = f"Ошибка оптимизации: {str(e)}"
            print(f"❌ {error_msg}")
            return self._create_error_result(error_msg)
    
    def _simple_fit_algorithm(self, profiles: List[Profile], stocks: List[Stock], progress_fn=None) -> List[CutPlan]:
        """
        Простейший алгоритм размещения - First Fit
        """
        cut_plans = []
        
        # Создаем список всех кусков для размещения
        pieces_to_place = []
        for profile in profiles:
            for i in range(profile.quantity):
                pieces_to_place.append({
                    'profile_id': profile.id,
                    'length': profile.length,
                    'element_name': profile.element_name
                })
        
        total_pieces = len(pieces_to_place)
        
        # Создаем список доступных хлыстов
        available_stocks = []
        for stock in stocks:
            for i in range(stock.quantity):
                available_stocks.append({
                    'id': f"{stock.id}_{i+1}",
                    'original_id': stock.id,
                    'length': stock.length,
                    'used_length': 0,
                    'cuts': [],
                    'cuts_count': 0
                })
        
        # Размещаем куски
        placed_count = 0
        
        for piece in pieces_to_place:
            placed = False
            
            # Ищем первый подходящий хлыст
            for stock in available_stocks:
                needed_length = piece['length']
                
                # Добавляем ширину пропила если уже есть распилы
                if stock['cuts_count'] > 0:
                    needed_length += self.settings.blade_width
                
                # Проверяем помещается ли
                if stock['used_length'] + needed_length <= stock['length']:
                    # Дополнительная проверка: создаем временный план для валидации
                    temp_cuts = stock['cuts'].copy()
                    temp_cuts.append({
                        'profile_id': piece['profile_id'],
                        'length': piece['length'],
                        'quantity': 1
                    })
                    
                    temp_plan = CutPlan(
                        stock_id=stock['original_id'],
                        stock_length=stock['length'],
                        cuts=temp_cuts,
                        waste=0,
                        waste_percent=0
                    )
                    
                    # Проверяем, что план корректен
                    if temp_plan.validate(self.settings.blade_width):
                        # Размещаем кусок
                        self._add_piece_to_stock(stock, piece)
                        placed = True
                        placed_count += 1
                        break
                    else:
                        # Пропускаем этот хлыст, пробуем следующий
                        continue
            
            if not placed:
                print(f"⚠️ Не удалось разместить: {piece['element_name']} ({piece['length']}мм)")
            
            # Обновляем прогресс реже (каждые 10% кусков)
            if progress_fn and total_pieces > 0 and placed_count % max(1, total_pieces // 10) == 0:
                progress = 40 + (placed_count / total_pieces) * 45
                progress_fn(int(progress))
        
        # Создаем планы распила
        for stock in available_stocks:
            if stock['cuts']:
                cut_plan = self._create_cut_plan_from_stock(stock)
                
                # Валидируем план
                if not cut_plan.validate(self.settings.blade_width):
                    analysis = self._analyze_cut_plan(cut_plan)
                    print(f"⚠️ ВНИМАНИЕ: План распила хлыста {cut_plan.stock_id} некорректен!")
                    print(f"   Длина хлыста: {analysis['stock_length']:.0f}мм")
                    print(f"   Сумма деталей: {analysis['total_pieces_length']:.0f}мм")
                    print(f"   Ширина пропилов: {analysis['saw_width_total']:.0f}мм")
                    print(f"   Общая использованная длина: {analysis['used_length']:.0f}мм")
                    print(f"   Превышение: {analysis['used_length'] - analysis['stock_length']:.0f}мм")
                    print(f"   Детали распила: {analysis['cuts_detail']}")
                    
                    # Пытаемся исправить план автоматически
                    corrected_plans = self._auto_correct_invalid_plan(cut_plan, available_stocks, stocks)
                    if corrected_plans:
                        print(f"✅ План автоматически исправлен! Создано планов: {len(corrected_plans)}")
                        cut_plans.extend(corrected_plans)
                    else:
                        print(f"❌ Не удалось автоматически исправить план")
                        cut_plans.append(cut_plan)  # Добавляем как есть
                else:
                    cut_plans.append(cut_plan)
        
        return cut_plans
    
    def _add_piece_to_stock(self, stock: Dict, piece: Dict):
        """Добавляет кусок в хлыст"""
        # Добавляем длину куска
        needed_length = piece['length']
        
        # Добавляем ширину пропила если уже есть распилы
        if stock['cuts_count'] > 0:
            needed_length += self.settings.blade_width
        
        # Ищем существующий распил такого же типа
        existing_cut = None
        for cut in stock['cuts']:
            if cut['profile_id'] == piece['profile_id']:
                existing_cut = cut
                break
        
        if existing_cut:
            # Увеличиваем количество
            existing_cut['quantity'] += 1
        else:
            # Создаем новый распил
            stock['cuts'].append({
                'profile_id': piece['profile_id'],
                'length': piece['length'],
                'quantity': 1
            })
        
        # Обновляем использованную длину и счетчик
        # Используем только needed_length, так как он уже включает ширину пропила
        stock['used_length'] += needed_length
        stock['cuts_count'] += 1
    
    def _create_cut_plan_from_stock(self, stock: Dict) -> CutPlan:
        """Создает план распила из заполненного хлыста"""
        # Создаем временный CutPlan для правильного расчета
        temp_cuts = stock['cuts'].copy()
        temp_plan = CutPlan(
            stock_id=stock['original_id'],
            stock_length=stock['length'],
            cuts=temp_cuts,
            waste=0,
            waste_percent=0
        )
        
        # Рассчитываем правильную использованную длину
        used_length = temp_plan.get_used_length(self.settings.blade_width)
        waste = stock['length'] - used_length
        remainder = None
        
        # Проверяем остаток
        if waste >= self.settings.min_remainder_length:
            remainder = waste
            waste = 0
        
        waste_percent = (waste / stock['length'] * 100) if stock['length'] > 0 else 0
        
        return CutPlan(
            stock_id=stock['original_id'],
            stock_length=stock['length'],
            cuts=stock['cuts'].copy(),
            waste=waste,
            waste_percent=waste_percent,
            remainder=remainder
        )
    
    def _calculate_stats(self, cut_plans: List[CutPlan]) -> Dict[str, Any]:
        """Рассчитывает статистику"""
        try:
            if not cut_plans:
                return {
                    'total_stocks': 0,
                    'total_cuts': 0,
                    'total_length': 0,
                    'total_waste': 0,
                    'waste_percent': 0,
                    'avg_waste_per_stock': 0
                }
            
            total_stocks = len(cut_plans)
            total_cuts = sum(plan.get_cuts_count() for plan in cut_plans)
            total_length = sum(plan.stock_length for plan in cut_plans)
            total_waste = sum(plan.waste for plan in cut_plans)
            waste_percent = (total_waste / total_length * 100) if total_length > 0 else 0
            
            return {
                'total_stocks': total_stocks,
                'total_cuts': total_cuts,
                'total_length': total_length,
                'total_waste': total_waste,
                'waste_percent': waste_percent,
                'avg_waste_per_stock': total_waste / total_stocks if total_stocks > 0 else 0
            }
        except Exception as e:
            print(f"⚠️ Ошибка в _calculate_stats: {e}")
            return {
                'total_stocks': 0,
                'total_cuts': 0,
                'total_length': 0,
                'total_waste': 0,
                'waste_percent': 0,
                'avg_waste_per_stock': 0
            }
    
    def _analyze_cut_plan(self, cut_plan: CutPlan) -> Dict[str, Any]:
        """Анализирует план распила и возвращает детальную информацию"""
        total_pieces_length = cut_plan.get_total_pieces_length()
        used_length = cut_plan.get_used_length(self.settings.blade_width)
        cuts_count = cut_plan.get_cuts_count()
        saw_width_total = self.settings.blade_width * (cuts_count - 1) if cuts_count > 1 else 0
        
        return {
            'stock_id': cut_plan.stock_id,
            'stock_length': cut_plan.stock_length,
            'total_pieces_length': total_pieces_length,
            'used_length': used_length,
            'cuts_count': cuts_count,
            'saw_width_total': saw_width_total,
            'waste': cut_plan.waste,
            'waste_percent': cut_plan.waste_percent,
            'is_valid': cut_plan.validate(self.settings.blade_width),
            'cuts_detail': cut_plan.cuts
        }
    
    def _create_error_result(self, message: str) -> OptimizationResult:
        """Создает результат с ошибкой"""
        return OptimizationResult(
            cut_plans=[],
            total_waste=0,
            total_waste_percent=0,
            settings=self.settings,
            success=False,
            message=message
        )
    
    def _auto_correct_invalid_plan(self, invalid_plan: 'CutPlan', available_stocks: List[Dict], original_stocks: List['Stock']) -> List['CutPlan']:
        """
        Автоматическая коррекция некорректного плана распила
        
        Args:
            invalid_plan: Некорректный план распила
            available_stocks: Доступные хлысты  
            original_stocks: Исходные хлысты для создания новых
            
        Returns:
            Список исправленных планов распила
        """
        try:
            print(f"🔧 Начинаю автокоррекцию плана хлыста {invalid_plan.stock_id}...")
            
            # Получаем детали из некорректного плана
            pieces_to_redistribute = []
            for cut in invalid_plan.cuts:
                if isinstance(cut, dict) and 'length' in cut and 'quantity' in cut and 'profile_id' in cut:
                    for i in range(cut['quantity']):
                        pieces_to_redistribute.append({
                            'profile_id': cut['profile_id'],
                            'length': cut['length'],
                            'element_name': f"Переразмещаемая деталь {cut['length']}мм"
                        })
            
            if not pieces_to_redistribute:
                print("⚠️ Нет деталей для переразмещения")
                return []
            
            print(f"📦 Переразмещаю {len(pieces_to_redistribute)} деталей...")
            
            corrected_plans = []
            unplaced_pieces = pieces_to_redistribute.copy()
            
            # Создаем новые хлысты для неразмещенных деталей
            print(f"📝 Создаю новые хлысты для {len(unplaced_pieces)} деталей...")
            
            # Группируем детали по оптимальному размещению
            while unplaced_pieces:
                # Находим подходящий хлыст из исходного списка
                best_stock = None
                best_stock_usage = 0
                
                for orig_stock in original_stocks:
                    # Симулируем размещение в этот тип хлыста
                    simulated_length = 0
                    simulated_count = 0
                    temp_pieces = unplaced_pieces.copy()
                    
                    for piece in temp_pieces:
                        needed = piece['length'] + (self.settings.blade_width if simulated_count > 0 else 0)
                        if simulated_length + needed <= orig_stock.length:
                            simulated_length += needed
                            simulated_count += 1
                    
                    usage_percent = (simulated_length / orig_stock.length) * 100 if orig_stock.length > 0 else 0
                    if simulated_count > 0 and usage_percent > best_stock_usage:
                        best_stock = orig_stock
                        best_stock_usage = usage_percent
                
                if best_stock:
                    # Создаем новый хлыст
                    new_stock_id = f"auto_{best_stock.id}_{len(corrected_plans) + 1}"
                    new_stock = {
                        'id': new_stock_id,
                        'original_id': best_stock.id,
                        'length': best_stock.length,
                        'used_length': 0,
                        'cuts': [],
                        'cuts_count': 0
                    }
                    
                    # Размещаем детали в новый хлыст
                    placed_in_new = []
                    for piece in unplaced_pieces.copy():  # Копируем для безопасной модификации
                        needed = piece['length'] + (self.settings.blade_width if new_stock['cuts_count'] > 0 else 0)
                        if new_stock['used_length'] + needed <= new_stock['length']:
                            self._add_piece_to_stock(new_stock, piece)
                            placed_in_new.append(piece)
                            print(f"  ✅ Деталь {piece['length']}мм размещена в новый хлыст {new_stock_id}")
                    
                    # Удаляем размещенные детали из списка неразмещенных
                    for piece in placed_in_new:
                        if piece in unplaced_pieces:
                            unplaced_pieces.remove(piece)
                    
                    # Создаем план для нового хлыста
                    if new_stock['cuts']:
                        new_plan = self._create_cut_plan_from_stock(new_stock)
                        if new_plan.validate(self.settings.blade_width):
                            corrected_plans.append(new_plan)
                            print(f"  ✅ Создан новый корректный план: хлыст {new_plan.stock_id}")
                        else:
                            print(f"  ⚠️ Новый план тоже некорректен: хлыст {new_plan.stock_id}")
                            corrected_plans.append(new_plan)  # Добавляем даже некорректный
                else:
                    print("❌ Не удалось найти подходящий хлыст для оставшихся деталей")
                    break
            
            if unplaced_pieces:
                print(f"⚠️ Остались неразмещенными {len(unplaced_pieces)} деталей")
                for piece in unplaced_pieces:
                    print(f"   - {piece['element_name']}: {piece['length']}мм")
            
            print(f"🎯 Автокоррекция завершена. Создано {len(corrected_plans)} планов")
            return corrected_plans
            
        except Exception as e:
            print(f"❌ Ошибка автокоррекции: {e}")
            import traceback
            traceback.print_exc()
            return []


class LinearOptimizer:
    """
    Класс для совместимости со старым API
    """
    
    def __init__(self, settings=None):
        if settings:
            self.settings = OptimizationSettings(
                blade_width=getattr(settings, 'blade_width', 5.0),
                min_remainder_length=getattr(settings, 'min_remainder_length', 300.0),
                max_waste_percent=getattr(settings, 'max_waste_percent', 15.0),
                pair_optimization=getattr(settings, 'pair_optimization', True),
                use_remainders=getattr(settings, 'use_remainders', True)
            )
        else:
            self.settings = OptimizationSettings()
        
        self.optimizer = SimpleOptimizer(self.settings)
    
    def optimize(self, profiles: List[Profile], stocks: List[Stock], 
                settings=None, progress_fn=None, use_professional=True) -> OptimizationResult:
        """
        Главный метод оптимизации (обратная совместимость)
        """
        print(f"🔧 LinearOptimizer.optimize вызван с {len(profiles)} профилями и {len(stocks)} хлыстами")
        
        # Обновляем настройки если переданы
        current_settings = self.settings
        if settings:
            current_settings = OptimizationSettings(
                blade_width=getattr(settings, 'blade_width', self.settings.blade_width),
                min_remainder_length=getattr(settings, 'min_remainder_length', self.settings.min_remainder_length),
                max_waste_percent=getattr(settings, 'max_waste_percent', self.settings.max_waste_percent),
                pair_optimization=getattr(settings, 'pair_optimization', self.settings.pair_optimization),
                use_remainders=getattr(settings, 'use_remainders', self.settings.use_remainders)
            )
        
        return self.optimizer.optimize(profiles, stocks, current_settings, progress_fn)


# Дополнительные классы для совместимости
class CuttingStockOptimizer:
    """Класс для совместимости с новым API"""
    
    def __init__(self, settings: OptimizationSettings = None):
        self.settings = settings or OptimizationSettings()
        self.optimizer = SimpleOptimizer(self.settings)
    
    def optimize(self, profiles: List[Profile], stocks: List[Stock], 
                progress_fn=None) -> OptimizationResult:
        """Главный метод оптимизации"""
        return self.optimizer.optimize(profiles, stocks, self.settings, progress_fn)


# Перечисления для совместимости
class SolverType:
    """Типы солверов (заглушка для совместимости)"""
    GREEDY = "greedy"
    CP_SAT = "cp_sat" 
    BIN_PACKING = "bin_packing"
    LINEAR_PROGRAMMING = "linear_programming"


# Функция для прямого вызова
def optimize_cutting_stock(profiles: List[Profile], stocks: List[Stock], 
                          solver_type=None, blade_width: float = 5.0,
                          min_remainder: float = 300.0, time_limit: int = 300,
                          progress_fn=None) -> OptimizationResult:
    """
    Простая функция для оптимизации раскроя
    """
    settings = OptimizationSettings(
        blade_width=blade_width,
        min_remainder_length=min_remainder,
        time_limit_seconds=time_limit
    )
    
    optimizer = SimpleOptimizer(settings)
    return optimizer.optimize(profiles, stocks, settings, progress_fn)


if __name__ == "__main__":
    print("🔧 Тестирование простейшего оптимизатора")
    print("=" * 40)
    
    # Создаем тестовые данные
    test_profiles = [
        Profile(id=1, order_id=1, element_name="Рама", profile_code="P001", length=2400, quantity=2),
        Profile(id=2, order_id=1, element_name="Импост", profile_code="P001", length=1800, quantity=2),
        Profile(id=3, order_id=1, element_name="Створка", profile_code="P001", length=1200, quantity=2),
    ]
    
    test_stocks = [
        Stock(id=1, profile_id=1, length=6000, quantity=2),
        Stock(id=2, profile_id=1, length=4000, quantity=1),
    ]
    
    print(f"Профили: {len(test_profiles)}")
    print(f"Хлысты: {len(test_stocks)}")
    
    def test_progress(percent):
        print(f"  Прогресс: {percent}%")
    
    try:
        optimizer = SimpleOptimizer()
        result = optimizer.optimize(test_profiles, test_stocks, progress_fn=test_progress)
        
        print(f"\n✅ Результат: {'Успех' if result.success else 'Ошибка'}")
        print(f"📊 Планов распила: {len(result.cut_plans)}")
        print(f"📈 Отходы: {result.total_waste_percent:.1f}%")
        print(f"💬 Сообщение: {result.message}")
        
        if result.cut_plans:
            print(f"\n📋 Детали планов:")
            for i, plan in enumerate(result.cut_plans):
                print(f"  Хлыст {i+1}: {len(plan.cuts)} распилов, отход {plan.waste:.0f}мм")
        
    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")
        import traceback
        traceback.print_exc()