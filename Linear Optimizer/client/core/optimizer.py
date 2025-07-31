"""
Алгоритм линейной оптимизации распила профилей
"""

from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from core.models import Profile, Stock, CutPlan, OptimizationResult

@dataclass
class OptimizationSettings:
    """Настройки оптимизации"""
    blade_width: float = 3.0  # Ширина пропила в мм (совместимость с GUI)
    min_remainder_length: float = 300.0  # Минимальная длина остатка в мм
    max_waste_percent: float = 15.0  # Максимальный процент отходов
    use_remainders: bool = True  # Использовать остатки со склада
    optimize_order: bool = True  # Оптимизировать порядок распила
    
    # Для обратной совместимости
    @property
    def saw_width(self):
        return self.blade_width
    
    @property
    def min_remainder(self):
        return self.min_remainder_length
    
class LinearOptimizer:
    """
    Основной класс для линейной оптимизации распила
    """
    
    def __init__(self, settings: OptimizationSettings = None):
        self.settings = settings or OptimizationSettings()
        
    def optimize(self, profiles: List[Profile], stocks: List[Stock], settings: 'OptimizationSettings' = None, progress_fn=None) -> OptimizationResult:
        """
        Главный метод оптимизации
        
        Args:
            profiles: Список профилей для распила
            stocks: Список доступных хлыстов
            settings: Настройки оптимизации (если не указано, используется self.settings)
            progress_fn: Callback для отчета о прогрессе (0-100)
            
        Returns:
            OptimizationResult: Результат оптимизации
        """
        # Используем переданные настройки или настройки по умолчанию
        if settings:
            current_settings = settings
        else:
            current_settings = self.settings
            
        # Обновляем прогресс
        if progress_fn:
            progress_fn(10)
        
        # TODO: Реализовать алгоритм оптимизации
        # Пока возвращаем заглушку
        
        cut_plans = []
        
        # Простейший алгоритм для демонстрации структуры
        # TODO: Заменить на реальный алгоритм оптимизации
        
        # Сортируем профили по убыванию длины
        sorted_profiles = sorted(profiles, key=lambda p: p.length, reverse=True)
        # Сортируем хлысты по убыванию длины
        sorted_stocks = sorted(stocks, key=lambda s: s.length, reverse=True)
        
        # Временная реализация - просто распределяем профили по хлыстам
        for i, stock in enumerate(sorted_stocks):
            if not sorted_profiles:
                break
                
            plan = self._create_cut_plan_for_stock(stock, sorted_profiles, current_settings)
            if plan.cuts:
                cut_plans.append(plan)
            
            # Обновляем прогресс
            if progress_fn:
                progress = 20 + (i / len(sorted_stocks)) * 70  # 20-90%
                progress_fn(int(progress))
        
        # Обновляем прогресс
        if progress_fn:
            progress_fn(95)
        
        # Создаем результат
        result = OptimizationResult(
            cut_plans=cut_plans,
            total_waste=self._calculate_total_waste(cut_plans),
            total_waste_percent=self._calculate_waste_percent(cut_plans),
            settings=current_settings,
            success=True,
            message="Оптимизация завершена успешно"
        )
        
        # Финальный прогресс
        if progress_fn:
            progress_fn(100)
        
        return result
    
    def _create_cut_plan_for_stock(self, stock: Stock, profiles: List[Profile], settings: OptimizationSettings = None) -> CutPlan:
        """
        Создать план распила для одного хлыста
        
        TODO: Реализовать оптимальный алгоритм
        """
        if settings is None:
            settings = self.settings
            
        cuts = []
        remaining_length = stock.length
        
        # Простейшая жадная стратегия
        for profile in profiles[:]:
            if profile.quantity == 0:
                continue
                
            # Учитываем ширину пропила
            required_length = profile.length + settings.blade_width
            
            # Сколько штук помещается
            count = min(
                int(remaining_length // required_length),
                profile.quantity
            )
            
            if count > 0:
                cuts.append({
                    'profile_id': profile.id,
                    'length': profile.length,
                    'quantity': count
                })
                
                # Обновляем остаток
                remaining_length -= count * required_length
                profile.quantity -= count
                
                # Удаляем профиль если все распилили
                if profile.quantity == 0:
                    profiles.remove(profile)
        
        # Рассчитываем отходы
        waste = remaining_length if remaining_length < settings.min_remainder_length else 0
        remainder = remaining_length if remaining_length >= settings.min_remainder_length else None
        
        return CutPlan(
            stock_id=stock.id,
            stock_length=stock.length,
            cuts=cuts,
            waste=waste,
            waste_percent=(waste / stock.length) * 100 if stock.length > 0 else 0,
            remainder=remainder
        )
    
    def _calculate_total_waste(self, cut_plans: List[CutPlan]) -> float:
        """Рассчитать общие отходы"""
        return sum(plan.waste for plan in cut_plans)
    
    def _calculate_waste_percent(self, cut_plans: List[CutPlan]) -> float:
        """Рассчитать процент отходов"""
        total_length = sum(plan.stock_length for plan in cut_plans)
        total_waste = self._calculate_total_waste(cut_plans)
        
        return (total_waste / total_length) * 100 if total_length > 0 else 0

# Вспомогательные функции для разных стратегий оптимизации

def optimize_first_fit_decreasing(profiles: List[Profile], stocks: List[Stock], 
                                 settings: OptimizationSettings) -> List[CutPlan]:
    """
    Алгоритм First Fit Decreasing
    """
    # TODO: Реализовать
    pass

def optimize_best_fit(profiles: List[Profile], stocks: List[Stock], 
                     settings: OptimizationSettings) -> List[CutPlan]:
    """
    Алгоритм Best Fit
    """
    # TODO: Реализовать
    pass

def optimize_dynamic_programming(profiles: List[Profile], stocks: List[Stock], 
                                settings: OptimizationSettings) -> List[CutPlan]:
    """
    Оптимизация с использованием динамического программирования
    """
    # TODO: Реализовать
    pass 