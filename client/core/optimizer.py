"""
Простейший и надежный оптимизатор раскроя профилей
Версия без внешних зависимостей для максимальной стабильности

Автор: Артем
"""

import time
from typing import List, Dict, Any
from dataclasses import dataclass

# Импорт моделей
from .models import Profile, Stock, CutPlan, OptimizationResult, Piece

@dataclass
class OptimizationSettings:
    """Настройки оптимизации раскроя"""
    blade_width: float = 5.0              # Ширина пропила в мм
    min_remainder_length: float = 300.0   # Минимальная длина остатка в мм
    max_waste_percent: float = 15.0       # Максимальный процент отходов
    pair_optimization: bool = True        # Парная оптимизация
    use_remainders: bool = True           # Использовать остатки
    time_limit_seconds: int = 60          # Лимит времени
    begin_indent: float = 10.0            # Отступ от начала (мм)
    end_indent: float = 10.0              # Отступ от конца (мм)
    min_trash_mm: float = 50.0            # Минимальный отход (мм)

    # Параметры плоскостной оптимизации
    min_remainder_width: float = 500.0    # Минимальная ширина для деловых остатков (мм)
    min_remainder_height: float = 500.0   # Минимальная высота для деловых остатков (мм)
    planar_cut_width: float = 1.0         # Ширина реза для плоскостной оптимизации (мм)
    sheet_indent: float = 15.0            # Отступы для листа со всех сторон (мм)
    remainder_indent: float = 15.0        # Отступы для делового остатка со всех сторон (мм)
    planar_max_waste_percent: float = 5.0 # Максимальная процент отхода для плоскостной оптимизации (%)

    # Параметры усиленной парной оптимизации
    pairing_exact_bonus: float = 3000.0           # Бонус за точное совпадение раскроя
    pairing_partial_bonus: float = 1000.0         # Бонус за частичное совпадение (масштабируется по схожести)
    pairing_partial_threshold: float = 0.7        # Порог схожести для частичного совпадения [0..1]
    pairing_new_simple_bonus: float = 150.0       # Бонус за старт простого раскроя на пустом хлысте


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
            
            # КРИТИЧЕСКИ ВАЖНО: Проверяем уникальность деловых остатков
            remainder_validation = self._validate_input_remainders(stocks)
            if remainder_validation["has_duplicates"]:
                error_msg = "Обнаружены дублирующиеся деловые остатки:\n"
                for duplicate in remainder_validation["duplicates"]:
                    error_msg += f"- warehouseremaindersid {duplicate['warehouseremaindersid']}: {duplicate['count']} раз\n"
                return self._create_error_result(error_msg)
            
            # Проверяем достаточность материалов
            if progress_fn:
                progress_fn(15)
            material_check = self._check_material_availability(profiles, stocks)
            if not material_check["sufficient"]:
                # КРИТИЧЕСКАЯ ОШИБКА: Нехватка материалов - останавливаем оптимизацию
                error_msg = "❌ КРИТИЧЕСКАЯ ОШИБКА: НЕХВАТКА МАТЕРИАЛОВ НА СКЛАДЕ\n\n"
                error_msg += "Невозможно выполнить оптимизацию из-за недостатка материалов:\n\n"
                
                for shortage in material_check["shortages"]:
                    error_msg += f"📋 Артикул: {shortage['profile_code']}\n"
                    error_msg += f"   Требуется: {shortage['needed']} деталей общей длиной {shortage['total_length']:.0f}мм\n"
                    error_msg += f"   Доступно: {shortage['available']} хлыстов общей длиной {shortage['available_length']:.0f}мм\n"
                    error_msg += f"   Нехватка: {shortage['shortage']} деталей на {shortage['shortage_length']:.0f}мм\n\n"
                
                error_msg += "🔧 Необходимые действия:\n"
                error_msg += "1. Докупите недостающие материалы на склад\n"
                error_msg += "2. Измените конструкцию для использования доступных материалов\n"
                error_msg += "3. Проверьте остатки на складе\n"
                
                print(f"❌ {error_msg}")
                
                # ОСТАНАВЛИВАЕМ оптимизацию и возвращаем ошибку
                return self._create_error_result(error_msg)
            
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
            
            # Рассчитываем статистику с учетом деловых остатков
            total_waste = sum(plan.waste * getattr(plan, 'count', 1) for plan in cut_plans)
            total_remainder = sum((plan.remainder or 0) * getattr(plan, 'count', 1) for plan in cut_plans)
            total_length = sum(plan.stock_length * getattr(plan, 'count', 1) for plan in cut_plans)
            # ИСПРАВЛЕНО: waste_percent теперь учитывает только отходы, без деловых остатков
            waste_percent = (total_waste / total_length * 100) if total_length > 0 else 0
            remainder_percent = (total_remainder / total_length * 100) if total_length > 0 else 0
            
            self.solve_time = time.time() - start_time
            
            result = OptimizationResult(
                cut_plans=cut_plans,
                total_waste=total_waste,
                total_waste_percent=waste_percent,
                settings=self.settings,
                success=True,
                message=f"Оптимизация завершена за {self.solve_time:.1f}с"
            )
            
            # Добавляем статистику с учетом деловых остатков
            result.statistics = self._calculate_stats(cut_plans)
            # ИСПРАВЛЕНО: Добавляем информацию о деловых остатках в статистику
            result.statistics['total_remainder'] = total_remainder
            result.statistics['remainder_percent'] = remainder_percent
            print(f"📊 СТАТИСТИКА: Отходы={total_waste:.0f}мм ({waste_percent:.1f}%), Деловые остатки={total_remainder:.0f}мм ({remainder_percent:.1f}%)")
            try:
                # Подсчитываем всего деталей нужно (по профилям) и распределено (по планам)
                total_pieces_needed = sum(p.quantity for p in valid_profiles)
                total_pieces_placed = 0
                
                # Правильный подсчет с учетом группировки планов
                for plan in cut_plans:
                    plan_count = getattr(plan, 'count', 1)
                    if hasattr(plan, 'cuts') and plan.cuts:
                        # Считаем детали в одном плане
                        plan_pieces = sum(int(c.get('quantity', 0)) for c in plan.cuts)
                        # Умножаем на количество копий плана
                        total_pieces_placed += plan_pieces * plan_count
                
                # Дополнительная проверка: находим неразмещенные детали
                unplaced_pieces = self._find_unplaced_pieces_in_result(valid_profiles, cut_plans)
                total_pieces_unplaced = len(unplaced_pieces)
                
                # Проверяем корректность подсчета
                if total_pieces_placed != total_pieces_needed:
                    print("⚠️ ВНИМАНИЕ: Несоответствие в подсчете деталей!")
                    print(f"   Нужно: {total_pieces_needed}")
                    print(f"   Размещено: {total_pieces_placed}")
                    print(f"   Разница: {total_pieces_placed - total_pieces_needed}")
                    
                    # Пытаемся исправить подсчет
                    corrected_total = 0
                    for plan in cut_plans:
                        plan_count = getattr(plan, 'count', 1)
                        if hasattr(plan, 'cuts') and plan.cuts:
                            for cut in plan.cuts:
                                if isinstance(cut, dict) and 'quantity' in cut:
                                    corrected_total += int(cut.get('quantity', 0)) * plan_count
                    
                    print(f"   Исправленный подсчет: {corrected_total}")
                    if corrected_total == total_pieces_needed:
                        total_pieces_placed = corrected_total
                        print("   ✅ Подсчет исправлен!")
                    else:
                        print("   ❌ Подсчет все еще некорректен!")
                
                result.statistics['total_pieces_needed'] = int(total_pieces_needed)
                result.statistics['total_pieces_placed'] = int(total_pieces_placed)
                result.statistics['total_pieces_unplaced'] = int(total_pieces_unplaced)
                result.statistics['placement_efficiency'] = round((total_pieces_placed / total_pieces_needed * 100) if total_pieces_needed > 0 else 0, 1)
                
                # Добавляем информацию о неразмещенных деталях
                if total_pieces_unplaced > 0:
                    result.statistics['unplaced_details'] = [
                        {
                            'profile_id': p['profile_id'],
                            'profile_code': p.get('profile_code', ''),
                            'length': p['length'],
                            'element_name': p['element_name']
                        }
                        for p in unplaced_pieces[:10]  # Показываем только первые 10
                    ]
                    
                    print(f"⚠️ ВНИМАНИЕ: {total_pieces_unplaced} деталей не размещены!")
                    print(f"📊 Эффективность размещения: {result.statistics['placement_efficiency']}%")
                else:
                    print(f"✅ ВСЕ детали успешно размещены! ({total_pieces_placed}/{total_pieces_needed})")
                    print("📊 Эффективность размещения: 100%")
                    
            except Exception as stats_err:
                print(f"⚠️ Ошибка расчета статистики деталей: {stats_err}")
                result.statistics['total_pieces_needed'] = 0
                result.statistics['total_pieces_placed'] = 0
                result.statistics['total_pieces_unplaced'] = 0
                result.statistics['placement_efficiency'] = 0
            
            if progress_fn:
                progress_fn(100)
                
            return result
                
        except Exception as e:
            error_msg = f"Ошибка оптимизации: {str(e)}"
            print(f"❌ {error_msg}")
            return self._create_error_result(error_msg)
    
    def _simple_fit_algorithm(self, profiles: List[Profile], stocks: List[Stock], progress_fn=None) -> List[CutPlan]:
        """
        Улучшенный алгоритм размещения с минимизацией отходов
        """
        cut_plans = []
        
        # Создаем список всех кусков для размещения с использованием новой модели Piece
        pieces_to_place = []
        for profile in profiles:
            for i in range(profile.quantity):
                piece = Piece(
                    profile_id=profile.id,
                    profile_code=profile.profile_code,
                    length=profile.length,
                    element_name=profile.element_name,
                    order_id=profile.order_id,
                    piece_id=f"{profile.id}_{profile.length}_{profile.order_id}_{i}",
                    orderitemsid=profile.orderitemsid,
                    izdpart=profile.izdpart,
                    itemsdetailid=profile.itemsdetailid
                )
                pieces_to_place.append(piece)
        
        # Распределяем номера ячеек
        self._distribute_cells_for_profiles(pieces_to_place)
        
        total_pieces = len(pieces_to_place)
        print(f"🔧 Создано {total_pieces} деталей для размещения")
        
        # Создаем список доступных хлыстов
        available_stocks = []
        for stock in stocks:
            if stock.is_remainder:
                # КРИТИЧЕСКИ ВАЖНО: для деловых остатков quantity должно быть ВСЕГДА 1!
                # Если quantity > 1, это ошибка в данных - каждый деловой остаток уникален
                if stock.quantity != 1:
                    print(f"⚠️ ВНИМАНИЕ: Деловой остаток {stock.id} имеет quantity={stock.quantity}, принудительно устанавливаю в 1")
                
                # Создаем ОДИН объект для каждого делового остатка
                available_stocks.append({
                    'id': f"{stock.id}_remainder_unique",  # Уникальный ID для делового остатка
                    'original_id': stock.id,
                    'length': stock.length,
                    'profile_code': getattr(stock, 'profile_code', None),
                    'warehouseremaindersid': getattr(stock, 'warehouseremaindersid', None),
                    'groupgoods_thick': getattr(stock, 'groupgoods_thick', 6000),
                    'is_remainder': True,
                    'used_length': 0,
                    'cuts': [],
                    'cuts_count': 0,
                    'quantity': 1,  # ВСЕГДА 1 для деловых остатков
                    'used_quantity': 0,
                    'max_usage': 1,  # Максимальное количество использований = 1
                    'original_stock': stock,
                    'instance_id': 1,  # Всегда 1, так как остаток уникален
                    'is_used': False  # Флаг использования
                })
                print(f"🔧 Создан уникальный деловой остаток {stock.id} (warehouseremaindersid: {getattr(stock, 'warehouseremaindersid', 'N/A')}) длиной {stock.length}мм")
            else:
                # Для цельных материалов создаем объекты для каждого экземпляра
                for i in range(stock.quantity):
                    available_stocks.append({
                        'id': f"{stock.id}_material_{i+1}",  # Уникальный ID для каждого цельного материала
                        'original_id': stock.id,
                        'length': stock.length,
                        'profile_code': getattr(stock, 'profile_code', None),
                        'warehouseremaindersid': None,
                        'groupgoods_thick': getattr(stock, 'groupgoods_thick', 6000),
                        'is_remainder': False,
                        'used_length': 0,
                        'cuts': [],
                        'cuts_count': 0,
                        'quantity': 1,
                        'used_quantity': 0,
                        'max_usage': 1,  # Каждый экземпляр используется только 1 раз
                        'original_stock': stock,
                        'instance_id': i + 1,
                        'is_used': False
                    })
                print(f"🔧 Создано {stock.quantity} экземпляров цельного материала {stock.id} длиной {stock.length}мм")
        
        # Проверяем, что все хлысты имеют необходимые поля
        for stock in available_stocks:
            if not all(key in stock for key in ['id', 'length', 'used_length', 'cuts', 'cuts_count', 'quantity', 'used_quantity']):
                print(f"⚠️ Хлыст {stock.get('id', 'unknown')} не имеет всех необходимых полей")
                # Добавляем недостающие поля
                stock.setdefault('used_length', 0)
                stock.setdefault('cuts', [])
                stock.setdefault('cuts_count', 0)
                stock.setdefault('quantity', 1)
                stock.setdefault('used_quantity', 0)
        
        # Фильтруем/сортируем хлысты в зависимости от использования деловых остатков
        if not self.settings.use_remainders:
            # Полностью исключаем остатки из рассмотрения
            available_stocks = [s for s in available_stocks if not bool(s.get('is_remainder'))]
            available_stocks.sort(key=lambda x: x['length'])
        else:
            # 🔥 КРИТИЧЕСКИ ВАЖНО: деловые остатки имеют АБСОЛЮТНЫЙ МАКСИМАЛЬНЫЙ приоритет!
            # Сортируем так, чтобы деловые остатки были в самом начале
            remainders = [s for s in available_stocks if s.get('is_remainder')]
            materials = [s for s in available_stocks if not s.get('is_remainder')]
            
            # 🔥 Сортируем деловые остатки: сначала по УБЫВАНИЮ длины (используем длинные в первую очередь)
            # Это помогает использовать большие остатки для крупных деталей
            remainders.sort(key=lambda x: -x['length'])
            
            # Сортируем цельные материалы по возрастанию длины (экономим материал)
            materials.sort(key=lambda x: x['length'])
            
            # 🔥 Объединяем: СНАЧАЛА ВСЕ деловые остатки (приоритет 1), потом цельные материалы (приоритет 2)
            available_stocks = remainders + materials
            
            print(f"🔥 МАКСИМАЛЬНАЯ ПРИОРИТИЗАЦИЯ ОСТАТКОВ: {len(remainders)} деловых остатков впереди, {len(materials)} цельных материалов в конце")
            if remainders:
                print(f"   📊 Диапазон длин остатков: {min(r['length'] for r in remainders):.0f}-{max(r['length'] for r in remainders):.0f}мм")
            if materials:
                print(f"   📊 Диапазон длин цельных материалов: {min(m['length'] for m in materials):.0f}-{max(m['length'] for m in materials):.0f}мм")
        
        # РАЗМЕЩАЕМ ДЕТАЛИ ОДИН РАЗ - убираем множественные проходы!
        print("🚀 ЗАПУСКАЮ ОДИН ПРОХОД ОПТИМИЗАЦИИ!")
        
        # Запускаем один проход оптимизации
        placed_count = self._single_pass_optimization(pieces_to_place, available_stocks, progress_fn)
        
        if progress_fn:
            progress_fn(70)
        
        # Проверяем, сколько деталей размещено
        unplaced_pieces = self._find_unplaced_pieces(pieces_to_place, available_stocks)
        if unplaced_pieces:
            print(f"⚠️ {len(unplaced_pieces)} деталей не размещены после основного прохода")
            
            # Только если есть неразмещенные детали, пытаемся их разместить
            if len(unplaced_pieces) > 0:
                print("🔧 Пытаюсь разместить оставшиеся детали в новые хлысты...")
                additional_placed = self._place_remaining_pieces(unplaced_pieces, available_stocks, stocks)
                placed_count += additional_placed
                
                # Финальная проверка
                final_unplaced = self._find_unplaced_pieces(pieces_to_place, available_stocks)
                if final_unplaced:
                    print(f"⚠️ {len(final_unplaced)} деталей все еще не размещены")
                    print("🔧 Создаю дополнительные хлысты для оставшихся деталей...")
                    
                    # Создаем дополнительные хлысты для оставшихся деталей
                    self._create_final_stocks_for_unplaced(final_unplaced, available_stocks, stocks)
                    
                    # Проверяем еще раз
                    final_check = self._find_unplaced_pieces(pieces_to_place, available_stocks)
                    if final_check:
                        print(f"❌ {len(final_check)} деталей не удалось разместить даже после создания дополнительных хлыстов")
                        for piece in final_check:
                            print(f"   - {piece.element_name}: {piece.length}мм (артикул: {piece.profile_code})")
                    else:
                        print("✅ Все детали успешно размещены после создания дополнительных хлыстов!")
                else:
                    print("✅ Все детали успешно размещены!")
        else:
            print("✅ Все детали успешно размещены в основном проходе!")
        
        # Создаем планы распила ТОЛЬКО для хлыстов с деталями
        # Создаем отдельный план для каждого экземпляра хлыста
        for stock in available_stocks:
            if stock['cuts']:  # Только хлысты с размещенными деталями
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
                        print("❌ Не удалось автоматически исправить план")
                        cut_plans.append(cut_plan)  # Добавляем как есть
                else:
                    cut_plans.append(cut_plan)
                    print(f"🔧 Создан план для экземпляра хлыста {stock['id']} (original_id: {stock['original_id']})")
                    print(f"   Детали: {cut_plan.cuts}")
        
        # Группируем идентичные планы в один с полем count
        return self._group_identical_plans(cut_plans)
    
    def _fill_remainders_with_small_pieces(self, all_pieces: List[Piece], available_stocks: List[Dict], progress_fn=None):
        """
        УСТАРЕВШИЙ МЕТОД - больше не используется
        """
        print("⚠️ Метод _fill_remainders_with_small_pieces устарел и не используется")
        return 0
    
    def _optimize_combinations(self, available_stocks: List[Dict], progress_fn=None):
        """
        УСТАРЕВШИЙ МЕТОД - больше не используется
        """
        print("⚠️ Метод _optimize_combinations устарел и не используется")
        return 0
    
    def _progressive_optimization(self, pieces_to_place: List[Piece], available_stocks: List[Dict], progress_fn=None) -> int:
        """
        УСТАРЕВШИЙ МЕТОД - больше не используется
        """
        print("⚠️ Метод _progressive_optimization устарел и не используется")
        return 0
    
    def _simple_first_fit_placement(self, pieces_to_place: List[Piece], available_stocks: List[Dict]) -> int:
        """
        УСТАРЕВШИЙ МЕТОД - больше не используется
        """
        print("⚠️ Метод _simple_first_fit_placement устарел и не используется")
        return 0
    
    def _improved_best_fit_placement(self, pieces_to_place: List[Piece], available_stocks: List[Dict]) -> int:
        """
        УСТАРЕВШИЙ МЕТОД - больше не используется
        """
        print("⚠️ Метод _improved_best_fit_placement устарел и не используется")
        return 0
    
    def _optimize_remainders(self, pieces_to_place: List[Piece], available_stocks: List[Dict]) -> int:
        """
        УСТАРЕВШИЙ МЕТОД - больше не используется
        """
        print("⚠️ Метод _optimize_remainders устарел и не используется")
        return 0
    
    def _force_place_remaining_pieces(self, pieces_to_place: List[Piece], available_stocks: List[Dict]) -> int:
        """
        УСТАРЕВШИЙ МЕТОД - больше не используется
        """
        print("⚠️ Метод _force_place_remaining_pieces устарел и не используется")
        return 0
    
    def _force_place_unplaced_pieces(self, unplaced_pieces: List[Piece], available_stocks: List[Dict], original_stocks: List[Stock]) -> int:
        """
        УСТАРЕВШИЙ МЕТОД - больше не используется
        """
        print("⚠️ Метод _force_place_unplaced_pieces устарел и не используется")
        return 0
    
    def _create_additional_stocks_for_unplaced(self, unplaced_pieces: List[Piece], available_stocks: List[Dict], original_stocks: List[Stock]):
        """
        УСТАРЕВШИЙ МЕТОД - больше не используется
        """
        print("⚠️ Метод _create_additional_stocks_for_unplaced устарел и не используется")
        return 0
    
    def _create_forced_stock_for_piece(self, piece: Piece, available_stocks: List[Dict], original_stocks: List[Stock]):
        """
        УСТАРЕВШИЙ МЕТОД - больше не используется
        """
        print("⚠️ Метод _create_forced_stock_for_piece устарел и не используется")
        return 0
    
    def _dynamic_placement_forces(self, pieces_to_place: List[Piece], available_stocks: List[Dict]) -> int:
        """
        УСТАРЕВШИЙ МЕТОД - больше не используется
        """
        print("⚠️ Метод _dynamic_placement_forces устарел и не используется")
        return 0
    
    def _calculate_cuts_length(self, cuts: List[Dict]) -> float:
        """Рассчитывает общую длину деталей с учетом пропилов"""
        if not cuts:
            return 0
        
        total_pieces_length = sum(cut['length'] * cut['quantity'] for cut in cuts)
        total_cuts_count = sum(cut['quantity'] for cut in cuts)
        saw_width_total = self.settings.blade_width * (total_cuts_count - 1) if total_cuts_count > 1 else 0
        
        return total_pieces_length + saw_width_total
    
    def _add_piece_to_stock(self, stock: Dict, piece: Piece, force_placement: bool = False) -> bool:
        """Добавляет кусок в хлыст"""
        try:
            # Проверяем, не размещена ли уже эта деталь
            if piece.placed:
                print(f"⚠️ Деталь {piece.length}мм уже размещена в хлысте {piece.placed_in_stock_id}")
                return False
            
            # ЖЕСТКАЯ ПРОВЕРКА: деталь должна поместиться в хлыст
            needed_length = piece.length
            
            # Добавляем ширину пропила если уже есть распилы
            if stock['cuts_count'] > 0:
                needed_length += self.settings.blade_width
            
            # Эффективная длина хлыста с учетом отступов
            effective_length = max(0, stock['length'] - (self.settings.begin_indent + self.settings.end_indent))
            
            # КРИТИЧЕСКИ ВАЖНО: проверяем, что деталь поместится
            if stock['used_length'] + needed_length > effective_length:
                if force_placement:
                    print(f"⚠️ FORCE: Деталь {piece.length}мм не помещается в хлыст {stock['id']} (нужно: {stock['used_length'] + needed_length:.0f}мм, доступно: {effective_length:.0f}мм)")
                    return False
                else:
                    print(f"❌ Деталь {piece.length}мм не помещается в хлыст {stock['id']} (нужно: {stock['used_length'] + needed_length:.0f}мм, доступно: {effective_length:.0f}мм)")
                    return False
            
            # Ищем существующий распил такого же типа (включая orderitemsid для точной группировки по изделиям)
            existing_cut = None
            for cut in stock['cuts']:
                if (cut['profile_id'] == piece.profile_id and 
                    cut['length'] == piece.length and 
                    cut.get('order_id') == piece.order_id and
                    cut.get('cell_number') == piece.cell_number and
                    cut.get('orderitemsid') == piece.orderitemsid and  # КРИТИЧЕСКИ ВАЖНО: проверяем ID изделия
                    cut.get('izdpart') == piece.izdpart): # КРИТИЧЕСКИ ВАЖНО: проверяем часть изделия
                    existing_cut = cut
                    break
            
            if existing_cut:
                # Увеличиваем количество
                old_qty = existing_cut['quantity']
                existing_cut['quantity'] += 1
                print(f"🔧 OPTIMIZER: Увеличено qty существующего cut (orderitemsid={piece.orderitemsid}, length={piece.length}мм): {old_qty} → {existing_cut['quantity']}")
            else:
                # Создаем новый распил
                cut_data = {
                    'profile_id': piece.profile_id,
                    'profile_code': piece.profile_code,  # Добавляем артикул профиля
                    'length': piece.length,
                    'quantity': 1,
                    'order_id': piece.order_id,  # Добавляем order_id для точного маппинга
                    'cell_number': piece.cell_number, # Добавляем номер ячейки
                    'itemsdetailid': piece.itemsdetailid, # Добавляем ID детали
                    'orderitemsid': piece.orderitemsid,  # КРИТИЧЕСКИ ВАЖНО: ID изделия для уникальной идентификации
                    'izdpart': piece.izdpart  # КРИТИЧЕСКИ ВАЖНО: Часть изделия для уникальной идентификации
                }
                stock['cuts'].append(cut_data)
                print(f"🆕 OPTIMIZER: Создан новый cut: length={piece.length}мм, qty=1, orderitemsid={piece.orderitemsid}, izdpart={piece.izdpart}")
            
            # Обновляем использованную длину и счетчик
            # Используем только needed_length, так как он уже включает ширину пропила
            stock['used_length'] += needed_length
            stock['cuts_count'] += 1
            
            # Помечаем деталь как распределенную
            try:
                piece.placed = True
                piece.placed_in_stock_id = stock['id']
                print(f"🔧 DEBUG: Деталь {piece.length}мм помечена как размещенная в хлысте {stock['id']}")
                print(f"   Использовано: {stock['used_length']:.0f}мм из {effective_length:.0f}мм ({stock['used_length']/effective_length*100:.1f}%)")
            except Exception as e:
                print(f"⚠️ Не удалось пометить деталь как размещенную: {e}")
            
            # КРИТИЧЕСКИ ВАЖНО: правильный учет использования хлыста
            effective_length = max(0, stock['length'] - (self.settings.begin_indent + self.settings.end_indent))
            usage_percent = (stock['used_length'] / effective_length) * 100 if effective_length > 0 else 100
            
            # Для деловых остатков: оптимизируем как обычные хлысты!
            if stock['is_remainder']:
                remaining_length = effective_length - stock['used_length']
                # Помечаем как использованный только если места недостаточно для новых деталей
                if remaining_length < self.settings.min_remainder_length:
                    stock['is_used'] = True
                    stock['used_quantity'] = 1
                    print(f"🔧 Деловой остаток {stock['id']} заполнен полностью (остаток {remaining_length:.0f}мм)")
                else:
                    print(f"🔧 Деловой остаток {stock['id']} частично заполнен (остаток {remaining_length:.0f}мм) - можно добавить еще детали")
            else:
                # Для цельных материалов: помечаем как использованный только при очень высоком заполнении
                # ИЛИ если остается слишком мало места для новых деталей
                remaining_length = effective_length - stock['used_length']
                
                # Помечаем как использованный только если:
                # 1. Заполнено более 95% ИЛИ
                # 2. Остается меньше минимальной длины детали (например, 300мм)
                if usage_percent > 95 or remaining_length < self.settings.min_remainder_length:
                    stock['is_used'] = True
                    stock['used_quantity'] = stock.get('max_usage', 1)  # Помечаем как полностью использованный
                    print(f"🔧 Цельный материал {stock['id']} заполнен на {usage_percent:.1f}% (остаток {remaining_length:.0f}мм) и помечен как использованный")
                else:
                    print(f"🔧 Цельный материал {stock['id']} заполнен на {usage_percent:.1f}% (остаток {remaining_length:.0f}мм) - продолжаем использовать")
            
            # Отладочная информация
            if force_placement:
                print(f"🔧 FORCE: Добавлена деталь {piece.length}мм в хлыст {stock['id']} (принудительно)")
            else:
                print(f"🔧 DEBUG: Добавлена деталь {piece.length}мм в хлыст {stock['id']}")
                print(f"   Тип: {'Деловой остаток' if stock['is_remainder'] else 'Цельный хлыст'}")
                print(f"   Использовано хлыстов: {stock['used_quantity']}/{stock['quantity']}")
                print(f"   Использованная длина: {stock['used_length']:.0f}мм")
                if stock['is_remainder']:
                    print(f"   Warehouseremaindersid: {stock.get('warehouseremaindersid', 'N/A')}")
                    print(f"   Instance ID: {stock.get('instance_id', 'N/A')}")
            
            return True  # Успешно размещено
            
        except Exception as e:
            print(f"❌ Ошибка в _add_piece_to_stock: {e}")
            # Возвращаем False вместо ошибки, чтобы оптимизатор мог продолжить работу
            return False
    
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
        # Эффективная длина с учетом отступов
        effective_length = max(0, stock['length'] - (self.settings.begin_indent + self.settings.end_indent))
        waste_or_remainder = max(0, effective_length - used_length)
        waste = waste_or_remainder
        remainder = None
        
        # СПЕЦИАЛЬНАЯ ЛОГИКА для деловых остатков:
        # Если кроим деловой остаток, то обрезок ВСЕГДА проверяем по min_remainder_length
        if stock.get('is_remainder', False):
            # Для деловых остатков: проверяем обрезок по пользовательскому параметру
            if waste_or_remainder >= self.settings.min_remainder_length:
                remainder = waste_or_remainder
                waste = 0
                print(f"🔧 Деловой остаток: обрезок {waste_or_remainder:.0f}мм >= {self.settings.min_remainder_length}мм - становится новым деловым остатком")
            else:
                # Обрезок меньше минимальной длины - в отходы
                waste = waste_or_remainder
                remainder = None
                print(f"🔧 Деловой остаток: обрезок {waste_or_remainder:.0f}мм < {self.settings.min_remainder_length}мм - в отходы")
        else:
            # Для цельных материалов: стандартная логика
            if waste_or_remainder >= self.settings.min_remainder_length:
                remainder = waste_or_remainder
                waste = 0
                print(f"🔧 Цельный материал: остаток {waste_or_remainder:.0f}мм >= {self.settings.min_remainder_length}мм - становится деловым остатком")
            else:
                # Минимальный отход: допускаем, но стараемся избегать в выборе
                waste = waste_or_remainder
                remainder = None
                print(f"🔧 Цельный материал: отход {waste_or_remainder:.0f}мм < {self.settings.min_remainder_length}мм")
        
        waste_percent = (waste / stock['length'] * 100) if stock['length'] > 0 else 0
        
        # Получаем значение is_remainder из исходного хлыста
        is_remainder_value = bool(stock.get('is_remainder', False))
        
        # Получаем warehouseremaindersid из исходного хлыста
        warehouseremaindersid_value = stock.get('warehouseremaindersid', None)
        
        # Отладочная информация
        print(f"🔧 DEBUG: Создаю CutPlan для хлыста {stock['original_id']}")
        print(f"   Длина: {stock['length']}мм")
        print(f"   is_remainder: {is_remainder_value}")
        print(f"   warehouseremaindersid: {warehouseremaindersid_value}")
        print(f"   Количество распилов: {len(stock['cuts'])}")
        print(f"   Детали: {stock['cuts']}")
        
        return CutPlan(
            stock_id=stock['original_id'],  # Используем оригинальный ID хлыста
            stock_length=stock['length'],
            cuts=stock['cuts'].copy(),
            waste=waste,
            waste_percent=waste_percent,
            remainder=remainder,
            count=1,  # Устанавливаем count=1, так как это один план
            is_remainder=is_remainder_value,
            warehouseremaindersid=warehouseremaindersid_value
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
            
            total_stocks = sum(getattr(plan, 'count', 1) for plan in cut_plans)
            total_cuts = sum(plan.get_cuts_count() * getattr(plan, 'count', 1) for plan in cut_plans)
            total_length = sum(plan.stock_length * getattr(plan, 'count', 1) for plan in cut_plans)
            total_waste = sum(plan.waste * getattr(plan, 'count', 1) for plan in cut_plans)
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
    
    def _validate_input_remainders(self, stocks: List[Stock]) -> Dict[str, Any]:
        """
        Валидирует уникальность деловых остатков во входных данных
        
        Returns:
            Dict с результатами валидации
        """
        validation_result = {
            "has_duplicates": False,
            "duplicates": [],
            "total_remainders": 0,
            "unique_remainders": 0
        }
        
        # Отслеживаем warehouseremaindersid
        remainder_counts = {}
        
        for stock in stocks:
            if stock.is_remainder and hasattr(stock, 'warehouseremaindersid') and stock.warehouseremaindersid:
                validation_result["total_remainders"] += stock.quantity
                
                whrid = stock.warehouseremaindersid
                if whrid not in remainder_counts:
                    remainder_counts[whrid] = {
                        "count": 0,
                        "stock_ids": [],
                        "total_quantity": 0
                    }
                
                remainder_counts[whrid]["count"] += 1
                remainder_counts[whrid]["stock_ids"].append(stock.id)
                remainder_counts[whrid]["total_quantity"] += stock.quantity
        
        validation_result["unique_remainders"] = len(remainder_counts)
        
        # Ищем дубли - каждый warehouseremaindersid должен встречаться СТРОГО один раз с quantity=1
        for whrid, info in remainder_counts.items():
            if info["count"] > 1:
                validation_result["has_duplicates"] = True
                validation_result["duplicates"].append({
                    "warehouseremaindersid": whrid,
                    "count": info["count"],
                    "total_quantity": info["total_quantity"],
                    "stock_ids": info["stock_ids"],
                    "issue": f"warehouseremaindersid {whrid} встречается {info['count']} раз (должен быть 1)"
                })
            elif info["total_quantity"] > 1:
                validation_result["has_duplicates"] = True
                validation_result["duplicates"].append({
                    "warehouseremaindersid": whrid,
                    "count": info["count"],
                    "total_quantity": info["total_quantity"],
                    "stock_ids": info["stock_ids"],
                    "issue": f"warehouseremaindersid {whrid} имеет quantity={info['total_quantity']} (должно быть 1)"
                })
        
        if validation_result["has_duplicates"]:
            print("❌ Обнаружены дублирующиеся деловые остатки:")
            for duplicate in validation_result["duplicates"]:
                print(f"   {duplicate['issue']}")
                print(f"   Stock IDs: {duplicate['stock_ids']}")
        else:
            print(f"✅ Валидация деловых остатков пройдена: {validation_result['total_remainders']} остатков, {validation_result['unique_remainders']} уникальных")
        
        return validation_result
    
    def _check_material_availability(self, profiles: List[Profile], stocks: List[Stock]) -> Dict[str, Any]:
        """
        Проверяет достаточность материалов для выполнения заказа
        
        Returns:
            Dict с результатами проверки
        """
        check_result = {
            "sufficient": True,
            "shortages": [],
            "by_profile": {}
        }
        
        # Группируем потребности по артикулам
        needs_by_profile = {}
        for profile in profiles:
            code = profile.profile_code
            if code not in needs_by_profile:
                needs_by_profile[code] = {
                    "pieces": 0,
                    "total_length": 0,
                    "max_length": 0
                }
            
            needs_by_profile[code]["pieces"] += profile.quantity
            needs_by_profile[code]["total_length"] += profile.length * profile.quantity
            needs_by_profile[code]["max_length"] = max(needs_by_profile[code]["max_length"], profile.length)
        
        # Группируем доступные материалы по артикулам
        available_by_profile = {}
        for stock in stocks:
            code = getattr(stock, 'profile_code', '') or ''
            if not code:
                continue
                
            if code not in available_by_profile:
                available_by_profile[code] = {
                    "total_length": 0,
                    "pieces": 0,
                    "stocks": []
                }
            
            # Для деловых остатков каждый остаток считается отдельно
            if stock.is_remainder:
                available_by_profile[code]["total_length"] += stock.length * stock.quantity
                available_by_profile[code]["pieces"] += stock.quantity
            else:
                # Для цельных материалов учитываем типовую длину
                typical_length = getattr(stock, 'groupgoods_thick', 6000) or 6000
                available_by_profile[code]["total_length"] += typical_length * stock.quantity
                available_by_profile[code]["pieces"] += stock.quantity
            
            available_by_profile[code]["stocks"].append(stock)
        
        # Проверяем каждый артикул на достаточность
        for profile_code, needs in needs_by_profile.items():
            available = available_by_profile.get(profile_code, {
                "total_length": 0,
                "pieces": 0,
                "stocks": []
            })
            
            check_result["by_profile"][profile_code] = {
                "needed_pieces": needs["pieces"],
                "needed_length": needs["total_length"],
                "available_pieces": available["pieces"],
                "available_length": available["total_length"],
                "sufficient": available["total_length"] >= needs["total_length"]
            }
            
            # Если материала недостаточно
            if available["total_length"] < needs["total_length"]:
                check_result["sufficient"] = False
                shortage = {
                    "profile_code": profile_code,
                    "needed": needs["pieces"],
                    "total_length": needs["total_length"],
                    "available": available["pieces"],
                    "available_length": available["total_length"],
                    "shortage": needs["pieces"] - available["pieces"],
                    "shortage_length": needs["total_length"] - available["total_length"]
                }
                check_result["shortages"].append(shortage)
        
        print("🔍 Проверка материалов:")
        print(f"   Артикулов требуется: {len(needs_by_profile)}")
        print(f"   Артикулов доступно: {len(available_by_profile)}")
        print(f"   Достаточно материалов: {'Да' if check_result['sufficient'] else 'Нет'}")
        
        if not check_result["sufficient"]:
            print(f"   Нехватка по {len(check_result['shortages'])} артикулам:")
            for shortage in check_result["shortages"]:
                print(f"     {shortage['profile_code']}: нехватка {shortage['shortage_length']:.0f}мм")
        
        return check_result
    
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
                        piece = Piece(
                            profile_id=cut['profile_id'],
                            profile_code=cut.get('profile_code', ''),
                            length=cut['length'],
                            element_name=f"Переразмещаемая деталь {cut['length']}мм",
                            order_id=1  # Временный order_id
                        )
                        pieces_to_redistribute.append(piece)
            
            if not pieces_to_redistribute:
                print("⚠️ Нет деталей для переразмещения")
                return []
            
            print(f"📦 Переразмещаю {len(pieces_to_redistribute)} деталей...")
            
            corrected_plans = []
            unplaced_pieces = pieces_to_redistribute.copy()
            
            # Создаем новые хлысты для неразмещенных деталей
            print(f"📝 Создаю новые хлысты для {len(unplaced_pieces)} деталей...")
            
            # Защита от бесконечного цикла
            max_iterations = 100
            iteration_count = 0
            
            # Группируем детали по оптимальному размещению
            while unplaced_pieces and iteration_count < max_iterations:
                iteration_count += 1
                
                # Находим подходящий хлыст из исходного списка
                best_stock = None
                best_stock_usage = 0
                
                for orig_stock in original_stocks:
                    # Симулируем размещение в этот тип хлыста
                    simulated_length = 0
                    simulated_count = 0
                    temp_pieces = unplaced_pieces.copy()
                    
                    for piece in temp_pieces:
                        needed = piece.length + (self.settings.blade_width if simulated_count > 0 else 0)
                        if simulated_length + needed <= orig_stock.length:
                            simulated_length += needed
                            simulated_count += 1
                    
                    usage_percent = (simulated_length / orig_stock.length) * 100 if orig_stock.length > 0 else 0
                    if simulated_count > 0 and usage_percent > best_stock_usage:
                        best_stock = orig_stock
                        best_stock_usage = usage_percent
                
                if best_stock:
                    # Создаем новый хлыст с ВСЕМИ необходимыми полями
                    new_stock_id = f"auto_{best_stock.id}_{len(corrected_plans) + 1}_{int(time.time())}"
                    new_stock = {
                        'id': new_stock_id,
                        'original_id': best_stock.id,
                        'length': best_stock.length,
                        'profile_code': getattr(best_stock, 'profile_code', None),
                        'warehouseremaindersid': None,
                        'groupgoods_thick': getattr(best_stock, 'groupgoods_thick', 6000),
                        'is_remainder': False,
                        'used_length': 0,
                        'cuts': [],
                        'cuts_count': 0,
                        'quantity': 1,
                        'used_quantity': 0,
                        'original_stock': best_stock
                    }
                    
                    available_stocks.append(new_stock)
                    
                    # Размещаем детали в новый хлыст
                    placed_in_new = []
                    for piece in unplaced_pieces.copy():  # Копируем для безопасной модификации
                        # Пропускаем уже размещенные детали
                        if piece.placed:
                            continue
                            
                        needed = piece.length + (self.settings.blade_width if new_stock['cuts_count'] > 0 else 0)
                        if new_stock['used_length'] + needed <= new_stock['length']:
                            if self._add_piece_to_stock(new_stock, piece):
                                placed_in_new.append(piece)
                                print(f"  ✅ Деталь {piece.length}мм размещена в новый хлыст {new_stock_id}")
                            else:
                                print(f"  ⚠️ Не удалось разместить деталь {piece.length}мм в новый хлыст {new_stock_id}")
                        else:
                            print(f"  ⚠️ Деталь {piece.length}мм не помещается в новый хлыст {new_stock_id} (нужно: {new_stock['used_length'] + needed:.0f}мм, доступно: {new_stock['length']:.0f}мм)")
                    
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
            
            if iteration_count >= max_iterations:
                print(f"⚠️ Достигнут лимит итераций ({max_iterations}), останавливаю автокоррекцию")
            
            if unplaced_pieces:
                print(f"⚠️ Остались неразмещенными {len(unplaced_pieces)} деталей")
                for piece in unplaced_pieces:
                    print(f"   - {piece.element_name}: {piece.length}мм")
            
            print(f"🎯 Автокоррекция завершена. Создано {len(corrected_plans)} планов")
            return corrected_plans
            
        except Exception as e:
            print(f"❌ Ошибка автокоррекции: {e}")
            import traceback
            traceback.print_exc()
            return []

        return []

    def _get_cuts_signature(self, cuts: List[Dict]) -> tuple:
        """Создает уникальную подпись для набора распилов
        
        КРИТИЧЕСКИ ВАЖНО: Подпись должна включать orderitemsid и izdpart,
        чтобы планы для разных изделий НЕ группировались вместе!
        """
        normalized = []
        for c in cuts:
            if isinstance(c, dict):
                # Включаем orderitemsid и izdpart в подпись для уникальной идентификации
                normalized.append((
                    int(c.get('profile_id', 0) or 0), 
                    float(c.get('length', 0) or 0), 
                    int(c.get('quantity', 0) or 0),
                    int(c.get('orderitemsid', 0) or 0),  # КРИТИЧЕСКИ ВАЖНО: ID изделия
                    str(c.get('izdpart', '') or '')      # КРИТИЧЕСКИ ВАЖНО: Часть изделия
                ))
        normalized.sort()
        return tuple(normalized)

    def _calc_signature_similarity(self, sig_a: tuple, sig_b: tuple) -> float:
        """Оценивает схожесть двух сигнатур раскроя [0..1].

        Идея: считаем, какая доля общего количества деталей совпадает по (profile_id, length, orderitemsid, izdpart).
        Кол-во для пары берется как min(qty_a, qty_b) и суммируется по всем совпадающим позициям.
        Делим на максимальную суммарную мощность одной из сигнатур (чтобы избежать деления на 0).
        
        КРИТИЧЕСКИ ВАЖНО: Учитываем orderitemsid и izdpart для точного сравнения!
        """
        if not sig_a and not sig_b:
            return 1.0
        if not sig_a or not sig_b:
            return 0.0

        # Преобразуем в словари: ключ=(profile_id, length, orderitemsid, izdpart), значение=qty
        def to_map(sig: tuple) -> Dict[tuple, int]:
            acc: Dict[tuple, int] = {}
            for item in sig:
                # Обрабатываем кортежи разной длины для обратной совместимости
                if len(item) >= 5:
                    # Новый формат: (profile_id, length, qty, orderitemsid, izdpart)
                    profile_id, length, qty, orderitemsid, izdpart = item[0], item[1], item[2], item[3], item[4]
                    key = (profile_id, length, orderitemsid, izdpart)
                elif len(item) >= 3:
                    # Старый формат: (profile_id, length, qty)
                    profile_id, length, qty = item[0], item[1], item[2]
                    key = (profile_id, length, 0, '')  # Для совместимости
                else:
                    continue
                acc[key] = acc.get(key, 0) + int(qty)
            return acc

        a_map = to_map(sig_a)
        b_map = to_map(sig_b)

        # Общая мощность (сумма qty) по каждой сигнатуре
        sum_a = sum(a_map.values())
        sum_b = sum(b_map.values())
        if max(sum_a, sum_b) == 0:
            return 0.0

        # Совпавшее количество
        common = 0
        for key, qty_a in a_map.items():
            qty_b = b_map.get(key)
            if qty_b:
                common += min(qty_a, qty_b)

        return common / max(sum_a, sum_b)

    def _group_identical_plans(self, cut_plans: List[CutPlan]) -> List[CutPlan]:
        """Группирует идентичные планы (одинаковые длина и набор распилов, и тип хлыста)"""
        
        # Проверяем настройку парной оптимизации
        if not self.settings.pair_optimization:
            print("🔧 Парная оптимизация отключена, группировка планов пропущена.")
            return cut_plans

        groups: Dict[tuple, CutPlan] = {}
        remainder_plans = []  # Отдельный список для планов деловых остатков
        
        for plan in cut_plans:
            # КРИТИЧЕСКИ ВАЖНО: деловые остатки НЕ группируем!
            # Каждый деловой остаток уникален и используется только один раз
            if getattr(plan, 'is_remainder', False):
                remainder_plans.append(plan)
                print(f"🔧 Деловой остаток {plan.stock_id} не группируется (warehouseremaindersid: {getattr(plan, 'warehouseremaindersid', None)})")
                continue
            
            # Группируем только цельные материалы
            cuts_sig = self._get_cuts_signature(plan.cuts)
            key = (
                float(plan.stock_length),
                cuts_sig,
                bool(getattr(plan, 'is_remainder', False)),  # Всегда False для цельных материалов
                getattr(plan, 'warehouseremaindersid', None)  # Всегда None для цельных материалов
            )

            plan_count = getattr(plan, 'count', 1)
            
            # Отладочная информация о cuts в плане
            if plan.cuts:
                print(f"🔧 План {plan.stock_id} содержит {len(plan.cuts)} типов деталей:")
                for i, cut in enumerate(plan.cuts):
                    print(f"   Cut {i+1}: profile_id={cut.get('profile_id')}, length={cut.get('length')}, qty={cut.get('quantity')}, orderitemsid={cut.get('orderitemsid')}, izdpart={cut.get('izdpart')}")
            
            if key in groups:
                # Увеличиваем счетчик группы только для цельных материалов
                old_count = getattr(groups[key], 'count', 1)
                groups[key].count = old_count + plan_count
                print(f"✅ ГРУППИРОВКА: План {plan.stock_id} объединен с существующим (count: {old_count} → {groups[key].count})")
            else:
                # Создаем новую группу для цельных материалов
                new_plan = CutPlan(
                    stock_id=plan.stock_id,  # Используем ID первого плана в группе
                    stock_length=plan.stock_length,
                    cuts=plan.cuts.copy(),
                    waste=plan.waste,
                    waste_percent=plan.waste_percent,
                    remainder=plan.remainder,
                    count=plan_count,
                    is_remainder=False,  # Гарантированно False для цельных материалов
                    warehouseremaindersid=None  # Гарантированно None для цельных материалов
                )
                groups[key] = new_plan
                print(f"🆕 НОВАЯ ГРУППА: Создана для плана {plan.stock_id} (count={plan_count})")

        # Объединяем цельные материалы (сгруппированные) и деловые остатки (несгруппированные)
        result = list(groups.values()) + remainder_plans
        print(f"🔧 Группировка завершена: {len(cut_plans)} планов → {len(result)} финальных планов")
        print(f"   Цельные материалы: {len(groups)} групп")
        print(f"   Деловые остатки: {len(remainder_plans)} планов")
        
        # Проверяем корректность группировки
        total_pieces_before = sum(
            sum(cut.get('quantity', 0) for cut in plan.cuts) * getattr(plan, 'count', 1)
            for plan in cut_plans
        )
        total_pieces_after = sum(
            sum(cut.get('quantity', 0) for cut in plan.cuts) * getattr(plan, 'count', 1)
            for plan in result
        )
        
        if total_pieces_before != total_pieces_after:
            print("⚠️ ВНИМАНИЕ: Группировка изменила количество деталей!")
            print(f"   До группировки: {total_pieces_before}")
            print(f"   После группировки: {total_pieces_after}")
            print(f"   Разница: {total_pieces_after - total_pieces_before}")
        else:
            print("✅ Группировка корректна: количество деталей не изменилось")
        
        # Дополнительная валидация деловых остатков
        remainder_validation_errors = self._validate_remainder_usage(result)
        if remainder_validation_errors:
            print("⚠️ КРИТИЧЕСКИЕ ОШИБКИ с деловыми остатками:")
            for error in remainder_validation_errors:
                print(f"   - {error}")
        else:
            print("✅ Валидация деловых остатков пройдена")
        
        return result

    def _validate_remainder_usage(self, cut_plans: List[CutPlan]) -> List[str]:
        """
        Валидирует корректность использования деловых остатков
        
        Returns:
            Список ошибок (пустой если все корректно)
        """
        errors = []
        
        # Отслеживаем использованные деловые остатки
        used_remainders = {}
        
        for plan in cut_plans:
            is_remainder = getattr(plan, 'is_remainder', False)
            
            if is_remainder:
                plan_count = getattr(plan, 'count', 1)
                warehouseremaindersid = getattr(plan, 'warehouseremaindersid', None)
                
                # Ошибка 1: count > 1 для деловых остатков
                if plan_count > 1:
                    errors.append(f"Деловой остаток {plan.stock_id} используется {plan_count} раз (должен быть 1)")
                
                # Ошибка 2: дублирование warehouseremaindersid
                if warehouseremaindersid:
                    if warehouseremaindersid in used_remainders:
                        errors.append(f"warehouseremaindersid {warehouseremaindersid} используется повторно (хлысты {used_remainders[warehouseremaindersid]} и {plan.stock_id})")
                    else:
                        used_remainders[warehouseremaindersid] = plan.stock_id
                else:
                    errors.append(f"Деловой остаток {plan.stock_id} не имеет warehouseremaindersid")
        
        return errors

    def _find_unplaced_pieces(self, all_pieces: List[Piece], available_stocks: List[Dict]) -> List[Piece]:
        """
        Находит все неразмещенные детали
        ИСПРАВЛЕННАЯ версия: работает с флагом placed
        """
        # Просто возвращаем детали, которые не помечены как размещенные
        unplaced_pieces = []
        for piece in all_pieces:
            if not piece.placed:
                unplaced_pieces.append(piece)
        
        return unplaced_pieces

    def _find_unplaced_pieces_in_result(self, profiles: List[Profile], cut_plans: List[CutPlan]) -> List[Dict]:
        """
        Находит все неразмещенные детали из результата оптимизации
        ПРАВИЛЬНАЯ версия: учитывает количество деталей каждого типа
        """
        # Анализируем размещение профилей в планах
        
        # Создаем счетчик размещенных деталей по (profile_id, length)
        placed_pieces_count = {}
        
        # Собираем все размещенные детали из планов с правильным подсчетом
        for plan in cut_plans:
            plan_count = getattr(plan, 'count', 1)  # Количество одинаковых планов
            print(f"🔧 Анализирую план {plan.stock_id} с count={plan_count}")
            
            for cut in plan.cuts:
                if isinstance(cut, dict) and 'length' in cut and 'quantity' in cut and 'profile_id' in cut:
                    piece_key = (cut['profile_id'], cut['length'])
                    # Учитываем и количество в cut, и количество планов
                    total_quantity = cut['quantity'] * plan_count
                    placed_pieces_count[piece_key] = placed_pieces_count.get(piece_key, 0) + total_quantity
                    print(f"  - Деталь {cut['profile_id']}: {cut['length']}мм × {cut['quantity']}шт × {plan_count} = {total_quantity}шт")
                else:
                    print(f"  ⚠️ Некорректный cut: {cut}")
        
        # Создаем счетчик необходимых деталей
        needed_pieces_count = {}
        for profile in profiles:
            piece_key = (profile.id, profile.length)
            needed_pieces_count[piece_key] = needed_pieces_count.get(piece_key, 0) + profile.quantity
            print(f"🔧 Нужно деталей {profile.id}: {profile.length}мм × {profile.quantity}шт")
        
        # Находим неразмещенные детали
        unplaced_pieces = []
        print("\n🔍 Анализ размещения:")
        
        for profile in profiles:
            piece_key = (profile.id, profile.length)
            needed = needed_pieces_count.get(piece_key, 0)
            placed = placed_pieces_count.get(piece_key, 0)
            
            unplaced_count = max(0, needed - placed)
            
            print(f"  {profile.element_name} ({profile.length}мм): нужно {needed}, размещено {placed}, не размещено {unplaced_count}")
            
            # Добавляем неразмещенные экземпляры
            for i in range(unplaced_count):
                unplaced_pieces.append({
                    'profile_id': profile.id,
                    'profile_code': profile.profile_code,
                    'length': profile.length,
                    'element_name': profile.element_name
                })
        
        print(f"🔧 Всего неразмещенных деталей: {len(unplaced_pieces)}")
        
        # Дополнительная проверка: выводим общую статистику
        total_needed = sum(needed_pieces_count.values())
        total_placed = sum(placed_pieces_count.values())
        print(f"🔧 ИТОГО: нужно {total_needed}, размещено {total_placed}, разница {total_placed - total_needed}")
        
        return unplaced_pieces

    def _single_pass_optimization(self, pieces_to_place: List[Piece], available_stocks: List[Dict], progress_fn=None) -> int:
        """
        Один проход оптимизации - размещаем детали без дублирования
        """
        print("🔧 Запускаю один проход оптимизации...")
        
        if progress_fn:
            progress_fn(10)
        
        placed_count = 0
        
        # Сортируем детали по длине (от больших к меньшим) для лучшего размещения
        pieces_to_place.sort(key=lambda x: x.length, reverse=True)
        
        # 🔥 СПЕЦИАЛЬНАЯ СОРТИРОВКА: деловые остатки ВСЕГДА ПЕРВЫЕ, потом цельные материалы
        # Деловые остатки уже должны быть в начале списка, но убеждаемся в правильном порядке
        remainders = [s for s in available_stocks if s.get('is_remainder', False)]
        materials = [s for s in available_stocks if not s.get('is_remainder', False)]
        
        # 🔥 Сортируем остатки: сначала самые ДЛИННЫЕ (для больших деталей)
        remainders.sort(key=lambda x: -x['length'])
        # Сортируем цельные материалы: сначала самые КОРОТКИЕ (экономим материал)
        materials.sort(key=lambda x: x['length'])
        
        # 🔥 Пересобираем список с МАКСИМАЛЬНЫМ приоритетом остатков
        available_stocks = remainders + materials
        
        print(f"🔥 МАКСИМАЛЬНЫЙ приоритет остатков: {len(remainders)} остатков (ПРИОРИТЕТ 1) → {len(materials)} цельных материалов (ПРИОРИТЕТ 2)")
        if remainders:
            print("   ✅ Остатки будут использованы ПЕРВЫМИ для всех подходящих деталей")
        
        # Группируем хлысты по оригинальному ID, чтобы избежать дублирования
        stock_groups = {}
        for stock in available_stocks:
            original_id = stock['original_id']
            if original_id not in stock_groups:
                stock_groups[original_id] = []
            stock_groups[original_id].append(stock)
        
        print(f"🔧 Сгруппировано {len(stock_groups)} типов хлыстов")
        
        # Размещаем детали в один проход
        for piece in pieces_to_place:
            if piece.placed:  # Пропускаем уже размещенные детали
                continue
                
            # Ищем лучший хлыст для детали среди всех групп
            best_stock = None
            best_score = float('-inf')
            
            for group_id, stock_list in stock_groups.items():
                # Ищем лучший хлыст в группе
                for stock in stock_list:
                    if not self._can_place_piece(stock, piece):
                        continue
                    
                    # Рассчитываем "силу" размещения
                    score = self._calculate_placement_score(stock, piece, available_stocks)
                    if score > best_score:
                        best_score = score
                        best_stock = stock
            
            # Размещаем деталь в лучший найденный хлыст
            if best_stock:
                if self._add_piece_to_stock(best_stock, piece):
                    placed_count += 1
                    stock_type = "ДЕЛОВОЙ ОСТАТОК" if best_stock.get('is_remainder', False) else "цельный хлыст"
                    print(f"🔧 Размещена деталь {piece.length}мм в {stock_type} {best_stock['id']} (score: {best_score:.0f})")
                    
                    # Проверяем, не заполнен ли хлыст полностью (только если явно помечен как использованный)
                    if best_stock.get('is_used', False):
                        # Удаляем использованный хлыст из группы
                        if best_stock in stock_groups[best_stock['original_id']]:
                            stock_groups[best_stock['original_id']].remove(best_stock)
                            print(f"🔧 Удаляю использованный хлыст {best_stock['id']} из группы {best_stock['original_id']}")
                    
                    if progress_fn:
                        progress_fn(10 + (placed_count / len(pieces_to_place)) * 50)
                else:
                    print(f"⚠️ Не удалось разместить деталь {piece.length}мм в хлыст {best_stock['id']}")
            else:
                print(f"⚠️ Не найден подходящий хлыст для детали {piece.length}мм")
        
        print(f"✅ Один проход оптимизации завершен! Размещено: {placed_count}/{len(pieces_to_place)} деталей")
        return placed_count

    def _place_remaining_pieces(self, unplaced_pieces: List[Piece], available_stocks: List[Dict], original_stocks: List[Stock]) -> int:
        """
        Размещает оставшиеся детали, создавая новые хлысты при необходимости
        УЛУЧШЕННАЯ версия: принудительно размещает ВСЕ детали
        """
        print(f"🔧 Размещаю {len(unplaced_pieces)} оставшихся деталей...")
        
        placed_count = 0
        
        # Сортируем детали по длине (от больших к меньшим)
        unplaced_pieces.sort(key=lambda x: x.length, reverse=True)
        
        # Группируем детали по артикулу профиля для оптимального размещения
        pieces_by_profile = {}
        for piece in unplaced_pieces:
            if not piece.placed:
                profile_code = piece.profile_code
                if profile_code not in pieces_by_profile:
                    pieces_by_profile[profile_code] = []
                pieces_by_profile[profile_code].append(piece)
        
        print(f"📦 Группировка по артикулам: {list(pieces_by_profile.keys())}")
        
        # Для каждого артикула создаем подходящие хлысты
        for profile_code, pieces in pieces_by_profile.items():
            if not pieces:
                continue
                
            print(f"🔧 Обрабатываю артикул {profile_code}: {len(pieces)} деталей")
            
            # Находим подходящий исходный хлыст для этого артикула
            suitable_stock = None
            for stock in original_stocks:
                if getattr(stock, 'profile_code', None) == profile_code:
                    suitable_stock = stock
                    break
            
            if not suitable_stock:
                # Берем первый доступный хлыст, если подходящий не найден
                suitable_stock = original_stocks[0] if original_stocks else None
            
            if not suitable_stock:
                print(f"❌ Не найден подходящий хлыст для артикула {profile_code}")
                continue
            
            # Сортируем детали по длине для лучшего размещения
            pieces.sort(key=lambda x: x.length, reverse=True)
            
            # Создаем новые хлысты для размещения деталей
            current_stock = None
            current_stock_length = 0
            
            for piece in pieces:
                if piece.placed:
                    continue
                    
                # Если текущий хлыст заполнен или не создан, создаем новый
                if current_stock is None or current_stock_length + piece.length > suitable_stock.length:
                    # Создаем новый хлыст
                    new_stock_id = f"new_{profile_code}_{len(available_stocks) + 1}_{int(time.time())}"
                    new_stock = {
                        'id': new_stock_id,
                        'original_id': suitable_stock.id,
                        'length': suitable_stock.length,
                        'profile_code': profile_code,
                        'warehouseremaindersid': None,
                        'groupgoods_thick': getattr(suitable_stock, 'groupgoods_thick', 6000),
                        'is_remainder': False,
                        'used_length': 0,
                        'cuts': [],
                        'cuts_count': 0,
                        'quantity': 1,
                        'used_quantity': 0,
                        'original_stock': suitable_stock
                    }
                    
                    available_stocks.append(new_stock)
                    current_stock = new_stock
                    current_stock_length = 0
                    
                    print(f"  ✅ Создан новый хлыст {new_stock_id} для артикула {profile_code}")
                
                # Размещаем деталь в текущий хлыст с ПРИНУДИТЕЛЬНЫМ размещением
                if self._add_piece_to_stock(current_stock, piece, force_placement=True):
                    placed_count += 1
                    current_stock_length += piece.length
                    print(f"    ✅ Размещена деталь {piece.length}мм в хлыст {current_stock['id']}")
                else:
                    print(f"    ⚠️ Не удалось разместить деталь {piece.length}мм в хлыст {current_stock['id']}")
                    
                    # Если деталь не помещается, создаем отдельный хлыст для неё
                    if not piece.placed:
                        single_stock_id = f"single_{profile_code}_{piece.length}_{len(available_stocks) + 1}_{int(time.time())}"
                        single_stock = {
                            'id': single_stock_id,
                            'original_id': suitable_stock.id,
                            'length': piece.length + self.settings.blade_width + 100,  # Минимальная длина + запас
                            'profile_code': profile_code,
                            'warehouseremaindersid': None,
                            'groupgoods_thick': getattr(suitable_stock, 'groupgoods_thick', 6000),
                            'is_remainder': False,
                            'used_length': 0,
                            'cuts': [],
                            'cuts_count': 0,
                            'quantity': 1,
                            'used_quantity': 0,
                            'original_stock': suitable_stock
                        }
                        
                        available_stocks.append(single_stock)
                        
                        if self._add_piece_to_stock(single_stock, piece, force_placement=True):
                            placed_count += 1
                            print(f"    ✅ Размещена деталь {piece.length}мм в отдельный хлыст {single_stock_id}")
                        else:
                            print(f"    ❌ КРИТИЧЕСКАЯ ОШИБКА: Не удалось разместить деталь {piece.length}мм даже в отдельный хлыст")
        
        print(f"✅ Дополнительно размещено {placed_count} деталей в новых хлыстах")
        return placed_count
    
    def _can_place_piece(self, stock: Dict, piece: Piece) -> bool:
        """Проверяет, можно ли разместить деталь в хлыст"""
        # КРИТИЧЕСКАЯ ПРОВЕРКА: хлыст уже использован?
        if stock.get('is_used', False):
            return False
        
        # Для цельных материалов не проверяем used_quantity - позволяем заполнять до конца
        # Для деловых остатков это проверяется через is_used
        
        # Проверяем артикул профиля
        if stock['profile_code'] and piece.profile_code and stock['profile_code'] != piece.profile_code:
            return False
        
        # Проверяем длину
        needed_length = piece.length
        if stock['cuts_count'] > 0:
            needed_length += self.settings.blade_width
        
        effective_length = max(0, stock['length'] - (self.settings.begin_indent + self.settings.end_indent))
        can_fit = stock['used_length'] + needed_length <= effective_length
        
        return can_fit
    
    def _calculate_waste_if_placed(self, stock: Dict, piece: Piece) -> float:
        """Рассчитывает отходы при размещении детали"""
        needed_length = piece.length
        if stock['cuts_count'] > 0:
            needed_length += self.settings.blade_width
        
        effective_length = max(0, stock['length'] - (self.settings.begin_indent + self.settings.end_indent))
        remaining_length = effective_length - (stock['used_length'] + needed_length)
        
        return max(0, remaining_length)

    def _calculate_placement_score(self, stock: Dict, piece: Piece, all_stocks: List[Dict]) -> float:
        """Рассчитывает "силу" размещения детали в хлыст"""
        score = 0.0
        
        # 🔥 МАКСИМАЛЬНЫЙ ПРИОРИТЕТ для деловых остатков - используем их в первую очередь!
        if stock.get('is_remainder', False):
            score += 50000  # КРИТИЧЕСКИ ВЫСОКИЙ приоритет для деловых остатков (увеличено с 10000)
            print(f"🔧 ДЕЛОВОЙ ОСТАТОК: {stock['id']} получает +50000 баллов базового приоритета")
        
        # Базовый балл за размер детали
        score += piece.length * 0.1
        
        effective_length = max(0, stock['length'] - (self.settings.begin_indent + self.settings.end_indent))
        usage_ratio = (stock['used_length'] + piece.length) / effective_length if effective_length > 0 else 1
        remaining_length = effective_length - (stock['used_length'] + piece.length)
        
        # ИСПРАВЛЕНО: Огромный бонус за использование уже частично заполненных хлыстов
        # Это стимулирует заполнение существующих хлыстов вместо создания новых
        if stock['used_length'] > 0:
            if stock.get('is_remainder', False):
                score += 5000  # УВЕЛИЧЕН: Очень высокий бонус для частично заполненных остатков
                print(f"🔧 Частично заполненный ОСТАТОК: {stock['id']} получает +5000 баллов")
            else:
                score += 1500  # Высокий приоритет для частично заполненных цельных хлыстов
            
            # Дополнительный бонус за максимальное заполнение (больше для остатков)
            if usage_ratio > 0.6:
                bonus = 1000 if stock.get('is_remainder', False) else 500
                score += bonus
            if usage_ratio > 0.8:
                bonus = 2000 if stock.get('is_remainder', False) else 800
                score += bonus
            if usage_ratio > 0.9:
                bonus = 3000 if stock.get('is_remainder', False) else 1000
                score += bonus
        else:
            # Для пустых хлыстов
            if stock.get('is_remainder', False):
                score += 3000  # УВЕЛИЧЕН: Очень высокий приоритет для пустых остатков
                print(f"🔧 Пустой ОСТАТОК: {stock['id']} получает +3000 баллов")
            else:
                score -= 5000  # ШТРАФ: Сильно снижаем приоритет для начала использования цельных хлыстов
                print(f"⚠️ Пустой ЦЕЛЬНЫЙ ХЛЫСТ: {stock['id']} получает -5000 баллов (штраф)")
        
        # Бонус за оптимальное использование
        if usage_ratio <= 0.95:  # Хлыст можно заполнить
            score += 100
        else:  # Хлыст переполнен - снижаем приоритет
            score -= 100
        
        # Бонус за полное использование или деловой остаток
        if remaining_length < self.settings.min_remainder_length:
            score += 200  # Полное использование - отлично
        elif remaining_length >= self.settings.min_remainder_length and remaining_length < effective_length * 0.3:
            score += 150  # Деловой остаток разумного размера
        
        # ИСПРАВЛЕНО: Штраф за плохое заполнение хлыста (большой остаток)
        # Это стимулирует максимальное заполнение хлыстов
        if remaining_length > effective_length * 0.4:
            # Если остаток больше 40% длины хлыста - это плохо
            # Используем квадратичный штраф для более сильного эффекта
            waste_ratio = remaining_length / effective_length
            waste_penalty = (waste_ratio ** 2) * 2000  # Квадратичный штраф
            score -= waste_penalty
            # Выводим для отладки
            print(f"⚠️ ШТРАФ за большой остаток: {stock['id']}, остаток={remaining_length:.0f}мм ({waste_ratio*100:.1f}%), штраф=-{waste_penalty:.0f}")
        
        # УБРАЛ штраф за количество деталей - это вредило оптимизации
        
        # Бонус за совпадение артикулов (больше для остатков)
        if stock.get('profile_code') == piece.profile_code:
            if stock.get('is_remainder', False):
                score += 1000  # УВЕЛИЧЕН: Очень большой бонус для остатков того же артикула
                print(f"🔧 Совпадение артикула для ОСТАТКА: {stock['id']} получает +1000 баллов")
            else:
                score += 50   # Обычный бонус для цельных материалов
        
        # --- ENHANCED PAIRING LOGIC ---
        # Усиленная логика поощрения создания одинаковых или похожих раскроев
        # Не применяем для деловых остатков, так как они уникальны
        # ИСПРАВЛЕНО: Парная оптимизация работает только если:
        # 1. Заполнение хлыста хорошее (> 50%)
        # 2. Остаток не слишком большой (< 40% или будет деловым остатком)
        pairing_allowed = (
            not stock.get('is_remainder', False) and 
            self.settings.pair_optimization and 
            usage_ratio > 0.5 and 
            (remaining_length < effective_length * 0.4 or remaining_length >= self.settings.min_remainder_length)
        )
        if pairing_allowed:
            # 1. Создаем временное представление раскроя, как если бы деталь была добавлена
            temp_cuts = [c.copy() for c in stock['cuts']]

            # Имитация инкремента количества для подписи
            existing_cut = None
            for cut in temp_cuts:
                if (cut.get('profile_id') == piece.profile_id and 
                    cut.get('length') == piece.length):
                    existing_cut = cut
                    break

            if existing_cut:
                existing_cut['quantity'] = existing_cut.get('quantity', 0) + 1
            else:
                temp_cuts.append({'profile_id': piece.profile_id, 'length': piece.length, 'quantity': 1})

            # 2. Подпись потенциального нового раскроя
            new_signature = self._get_cuts_signature(temp_cuts)

            # 3. Ищем точные и частичные совпадения
            pairing_bonus_total = 0.0
            best_partial_similarity = 0.0
            for other_stock in all_stocks:
                # Пропускаем сам хлыст, пустые хлысты и деловые остатки
                if (other_stock['id'] == stock['id'] or 
                    not other_stock['cuts'] or 
                    other_stock.get('is_remainder', False)):
                    continue

                other_signature = self._get_cuts_signature(other_stock['cuts'])
                if new_signature == other_signature:
                    pairing_bonus_total += self.settings.pairing_exact_bonus
                    print(f"💎 PAIRING EXACT BONUS: {piece.length}мм в {stock['id']} создаст пару с {other_stock['id']}")
                    # Точное совпадение найдено — можно не искать дальше
                    best_partial_similarity = 1.0
                    break
                else:
                    # Частичное совпадение
                    sim = self._calc_signature_similarity(new_signature, other_signature)
                    if sim > best_partial_similarity:
                        best_partial_similarity = sim

            # Применяем бонус за частичную схожесть, если превышен порог
            if pairing_bonus_total == 0 and best_partial_similarity >= self.settings.pairing_partial_threshold:
                # Масштабируем бонус линейно по величине схожести
                pairing_bonus_total += self.settings.pairing_partial_bonus * best_partial_similarity
                print(f"💠 PAIRING PARTIAL BONUS: sim={best_partial_similarity:.2f} для {stock['id']}")

            # 4. Бонус за старт простого потенциального шаблона на пустом хлысте
            if stock['cuts_count'] == 0 and pairing_bonus_total == 0:
                if len(temp_cuts) == 1:
                    score += self.settings.pairing_new_simple_bonus

            score += pairing_bonus_total
        # --- END OF ENHANCED PAIRING LOGIC ---
        
        return score
    
    def _update_placement_forces(self, stock: Dict):
        """Обновляет "силы" размещения после добавления детали"""
        # Уменьшаем привлекательность хлыста для следующих деталей
        # чтобы детали распределялись более равномерно
        pass  # Пока просто заглушка, можно расширить логику

    def _create_final_stocks_for_unplaced(self, unplaced_pieces: List[Piece], available_stocks: List[Dict], original_stocks: List[Stock]):
        """
        Создает финальные хлысты для оставшихся неразмещенных деталей
        УЛУЧШЕННАЯ версия: гарантированно размещает ВСЕ детали
        """
        print(f"🔧 Создаю финальные хлысты для {len(unplaced_pieces)} неразмещенных деталей...")
        
        # Группируем детали по артикулу профиля
        pieces_by_profile = {}
        for piece in unplaced_pieces:
            if not piece.placed:
                profile_code = piece.profile_code
                if profile_code not in pieces_by_profile:
                    pieces_by_profile[profile_code] = []
                pieces_by_profile[profile_code].append(piece)
        
        # Для каждого артикула создаем отдельный хлыст
        for profile_code, pieces in pieces_by_profile.items():
            if not pieces:
                continue
                
            print(f"🔧 Создаю финальный хлыст для артикула {profile_code}: {len(pieces)} деталей")
            
            # Находим подходящий исходный хлыст
            suitable_stock = None
            for stock in original_stocks:
                if getattr(stock, 'profile_code', None) == profile_code:
                    suitable_stock = stock
                    break
            
            if not suitable_stock:
                suitable_stock = original_stocks[0] if original_stocks else None
            
            if not suitable_stock:
                print(f"❌ Не найден подходящий хлыст для артикула {profile_code}")
                continue
            
            # Сортируем детали по длине для лучшего размещения
            pieces.sort(key=lambda x: x.length, reverse=True)
            
            # Создаем финальный хлыст с достаточной длиной
            max_piece_length = max(p.length for p in pieces)
            total_needed_length = sum(p.length for p in pieces) + (len(pieces) - 1) * self.settings.blade_width
            
            # Используем максимальную из: исходной длины, суммы деталей + пропилы, или максимальной детали + запас
            final_stock_length = max(
                suitable_stock.length,
                total_needed_length + 200,  # Запас 200мм
                max_piece_length + self.settings.blade_width + 300  # Максимальная деталь + запас
            )
            
            final_stock_id = f"final_{profile_code}_{len(available_stocks) + 1}_{int(time.time())}"
            final_stock = {
                'id': final_stock_id,
                'original_id': suitable_stock.id,
                'length': final_stock_length,
                'profile_code': profile_code,
                'warehouseremaindersid': None,
                'groupgoods_thick': getattr(suitable_stock, 'groupgoods_thick', 6000),
                'is_remainder': False,
                'used_length': 0,
                'cuts': [],
                'cuts_count': 0,
                'quantity': 1,
                'used_quantity': 0,
                'original_stock': suitable_stock
            }
            
            available_stocks.append(final_stock)
            
            # Размещаем все детали этого артикула в финальный хлыст
            placed_in_final = 0
            for piece in pieces:
                if not piece.placed:
                    if self._add_piece_to_stock(final_stock, piece, force_placement=True):
                        placed_in_final += 1
                        print(f"  ✅ Размещена деталь {piece.length}мм в финальный хлыст {final_stock_id}")
                    else:
                        print(f"  ⚠️ Не удалось разместить деталь {piece.length}мм в финальный хлыст {final_stock_id}")
                        
                        # Если деталь не помещается даже в финальный хлыст, создаем отдельный хлыст
                        if not piece.placed:
                            single_stock_id = f"single_final_{profile_code}_{piece.length}_{len(available_stocks) + 1}_{int(time.time())}"
                            single_stock = {
                                'id': single_stock_id,
                                'original_id': suitable_stock.id,
                                'length': piece.length + self.settings.blade_width + 200,  # Деталь + пропилы + запас
                                'profile_code': profile_code,
                                'warehouseremaindersid': None,
                                'groupgoods_thick': getattr(suitable_stock, 'groupgoods_thick', 6000),
                                'is_remainder': False,
                                'used_length': 0,
                                'cuts': [],
                                'cuts_count': 0,
                                'quantity': 1,
                                'used_quantity': 0,
                                'original_stock': suitable_stock
                            }
                            
                            available_stocks.append(single_stock)
                            
                            if self._add_piece_to_stock(single_stock, piece, force_placement=True):
                                print(f"  ✅ Размещена деталь {piece.length}мм в отдельный финальный хлыст {single_stock_id}")
                            else:
                                print(f"  ❌ КРИТИЧЕСКАЯ ОШИБКА: Не удалось разместить деталь {piece.length}мм даже в отдельный финальный хлыст")
            
            print(f"  ✅ Создан финальный хлыст {final_stock_id} для артикула {profile_code} (размещено {placed_in_final}/{len(pieces)} деталей)")
        
        print(f"✅ Создано {len(pieces_by_profile)} финальных хлыстов")

    def _distribute_cells_for_profiles(self, pieces: List[Piece]):
        """Распределяет номера ячеек по уникальным проемам для профилей."""
        print("🏠 Распределение номеров ячеек для профилей...")
        
        unique_openings = {}
        
        # Группируем детали по уникальному проему.
        # Проем определяется по 'orderitemsid' и 'izdpart'
        for piece in pieces:
            key = (piece.orderitemsid, piece.izdpart)
            if key not in unique_openings:
                unique_openings[key] = {"pieces": []}
            unique_openings[key]["pieces"].append(piece)
            
        # Сортируем проемы по orderitemsid и izdpart для последовательной нумерации
        sorted_keys = sorted(unique_openings.keys())
        
        print("  --- Начало лога распределения ячеек для профилей ---")
        cell_counter = 1
        for key in sorted_keys:
            opening_data = unique_openings[key]
            print(f"  - Проем (ключ): {key}, Ячейка №{cell_counter}, Кол-во деталей: {len(opening_data['pieces'])}")
            for piece in opening_data["pieces"]:
                piece.cell_number = cell_counter
            cell_counter += 1
        print("  --- Конец лога распределения ячеек для профилей ---")
            
        print(f"✅ Распределение номеров ячеек для профилей завершено. Найдено {len(unique_openings)} уникальных проемов.")

    def _prepare_final_stocks(self, cutting_plans: Dict[str, List[Dict]]) -> List[Dict]:
        """
        Подготавливает финальные хлысты для всех планов распила
        """
        final_stocks = []
        for plan_id, plan_data in cutting_plans.items():
            for stock_data in plan_data:
                stock_id = stock_data['id']
                stock_length = stock_data['length']
                cuts = stock_data['cuts']
                waste = stock_data['waste']
                remainder = stock_data['remainder']
                count = stock_data['count']
                is_remainder = stock_data['is_remainder']
                warehouseremaindersid = stock_data['warehouseremaindersid']
                
                final_stock = {
                    'id': stock_id,
                    'length': stock_length,
                    'cuts': cuts,
                    'waste': waste,
                    'remainder': remainder,
                    'count': count,
                    'is_remainder': is_remainder,
                    'warehouseremaindersid': warehouseremaindersid
                }
                final_stocks.append(final_stock)
        return final_stocks


class LinearOptimizer:
    """
    Класс для совместимости со старым API
    """
    
    def __init__(self, settings=None):
        if settings:
            if isinstance(settings, OptimizationSettings):
                self.settings = settings
            else:
                # Обратная совместимость со "старыми" объектами настроек
                self.settings = OptimizationSettings(
                    blade_width=getattr(settings, 'blade_width', 5.0),
                    min_remainder_length=getattr(settings, 'min_remainder_length', 300.0),
                    max_waste_percent=getattr(settings, 'max_waste_percent', 15.0),
                    pair_optimization=getattr(settings, 'pair_optimization', True),
                    use_remainders=getattr(settings, 'use_remainders', True),
                    time_limit_seconds=getattr(settings, 'time_limit_seconds', 60),
                    begin_indent=getattr(settings, 'begin_indent', 10.0),
                    end_indent=getattr(settings, 'end_indent', 10.0),
                    min_trash_mm=getattr(settings, 'min_trash_mm', 50.0),
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
        
        # Обновляем настройки если переданы (берем напрямую из GUI)
        current_settings = self.settings
        if settings:
            if isinstance(settings, OptimizationSettings):
                current_settings = settings
            else:
                # Обратная совместимость: соберем полный набор полей
                current_settings = OptimizationSettings(
                    blade_width=getattr(settings, 'blade_width', self.settings.blade_width),
                    min_remainder_length=getattr(settings, 'min_remainder_length', self.settings.min_remainder_length),
                    max_waste_percent=getattr(settings, 'max_waste_percent', self.settings.max_waste_percent),
                    pair_optimization=getattr(settings, 'pair_optimization', self.settings.pair_optimization),
                    use_remainders=getattr(settings, 'use_remainders', self.settings.use_remainders),
                    time_limit_seconds=getattr(settings, 'time_limit_seconds', self.settings.time_limit_seconds),
                    begin_indent=getattr(settings, 'begin_indent', self.settings.begin_indent),
                    end_indent=getattr(settings, 'end_indent', self.settings.end_indent),
                    min_trash_mm=getattr(settings, 'min_trash_mm', self.settings.min_trash_mm),
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
            print("\n📋 Детали планов:")
            for i, plan in enumerate(result.cut_plans):
                print(f"  Хлыст {i+1}: {len(plan.cuts)} распилов, отход {plan.waste:.0f}мм")
        
    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")
        import traceback
        traceback.print_exc()
