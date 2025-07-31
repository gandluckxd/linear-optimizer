"""
Профессиональный оптимизатор раскроя профилей на базе Google OR-Tools
Единственный файл для всех задач оптимизации распила профилей

Основан на официальной документации OR-Tools и лучших практиках:
- https://developers.google.com/optimization/pack/bin_packing
- https://developers.google.com/optimization/cp/cp_solver

Решает классическую задачу Cutting Stock Problem (CSP) с использованием:
1. CP-SAT (Constraint Programming with Satisfiability) - основной метод
2. Bin Packing - альтернативный подход  
3. Linear Programming - через MPSolver
4. Жадный алгоритм - запасной вариант

Автор: Артем
Версия: 2.0 - Объединенная версия
"""

import time
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import math

try:
    from ortools.sat.python import cp_model
    from ortools.linear_solver import pywraplp
    ORTOOLS_AVAILABLE = True
except ImportError:
    ORTOOLS_AVAILABLE = False
    print("⚠️  OR-Tools не установлен. Будет использоваться только жадный алгоритм.")

from core.models import Profile, Stock, CutPlan, OptimizationResult

class SolverType(Enum):
    """Типы солверов для оптимизации"""
    CP_SAT = "cp_sat"              # Constraint Programming (рекомендуется)
    BIN_PACKING = "bin_packing"    # Классическая упаковка в контейнеры
    LINEAR_PROGRAMMING = "linear_programming"  # Линейное программирование
    GREEDY = "greedy"              # Жадный алгоритм (запасной вариант)

@dataclass
class OptimizationSettings:
    """Настройки оптимизации раскроя"""
    # Основные параметры
    blade_width: float = 5.0              # Ширина пропила в мм
    min_remainder_length: float = 300.0   # Минимальная длина остатка в мм
    time_limit_seconds: int = 300         # Лимит времени решения (5 минут)
    
    # Цели оптимизации (приоритеты от 0.0 до 1.0, сумма должна быть 1.0)
    minimize_waste_weight: float = 0.6    # Приоритет минимизации отходов
    minimize_stocks_weight: float = 0.4   # Приоритет минимизации количества хлыстов
    
    # Продвинутые настройки
    solver_type: SolverType = SolverType.CP_SAT
    max_patterns_per_stock: int = 1000    # Максимум паттернов на хлыст
    enable_preprocessing: bool = True      # Включить предобработку данных
    enable_symmetry_breaking: bool = True # Исключить симметричные решения
    
    # Настройки для больших задач
    use_heuristics: bool = True           # Использовать эвристики для ускорения
    parallel_threads: int = 0             # Количество потоков (0 = auto)

class CuttingPattern:
    """Паттерн раскроя для одного хлыста"""
    
    def __init__(self, stock_length: float, blade_width: float):
        self.stock_length = stock_length
        self.blade_width = blade_width
        self.cuts: Dict[int, int] = {}  # profile_id -> quantity
        self._waste = None
        
    def add_cut(self, profile_id: int, profile_length: float, quantity: int) -> bool:
        """Добавить распил в паттерн. Возвращает True если помещается"""
        if quantity <= 0:
            return False
            
        # Проверяем помещается ли
        current_usage = self.get_used_length()
        needed_length = quantity * (profile_length + self.blade_width)
        if quantity > 0:
            needed_length -= self.blade_width  # Последний пропил не нужен
            
        if current_usage + needed_length <= self.stock_length:
            self.cuts[profile_id] = self.cuts.get(profile_id, 0) + quantity
            self._waste = None  # Сброс кэша
            return True
        return False
    
    def get_used_length(self) -> float:
        """Получить использованную длину с учетом пропилов"""
        if not self.cuts:
            return 0
            
        total_cuts = sum(self.cuts.values())
        if total_cuts == 0:
            return 0
            
        # Общая длина материала + пропилы между кусками
        total_length = 0
        profiles_cache = {}  # Кэш для длин профилей
        
        for profile_id, quantity in self.cuts.items():
            if profile_id not in profiles_cache:
                # В реальной реализации здесь нужен доступ к Profile объектам
                # Пока используем заглушку
                profiles_cache[profile_id] = 1000  # Заглушка
            
            total_length += quantity * profiles_cache[profile_id]
        
        # Добавляем пропилы (на 1 меньше чем количество кусков)
        if total_cuts > 1:
            total_length += (total_cuts - 1) * self.blade_width
            
        return total_length
    
    def get_waste(self) -> float:
        """Получить отходы"""
        if self._waste is None:
            self._waste = self.stock_length - self.get_used_length()
        return self._waste
    
    def is_empty(self) -> bool:
        """Проверить пустой ли паттерн"""
        return not self.cuts or sum(self.cuts.values()) == 0

class CuttingStockOptimizer:
    """
    Профессиональный оптимизатор задачи раскроя профилей
    
    Использует Google OR-Tools для решения классической задачи Cutting Stock Problem (CSP).
    Поддерживает различные методы решения и настройки оптимизации.
    
    Основан на примерах из официальной документации OR-Tools:
    - https://developers.google.com/optimization/pack/bin_packing
    - https://developers.google.com/optimization/cp/cp_solver
    """
    
    def __init__(self, settings: OptimizationSettings = None):
        self.settings = settings or OptimizationSettings()
        self.solve_time = 0.0
        self.solver_status = None
        
        # Проверяем доступность OR-Tools и корректируем настройки
        if not ORTOOLS_AVAILABLE:
            if self.settings.solver_type != SolverType.GREEDY:
                print(f"⚠️  OR-Tools недоступен. Переключение с {self.settings.solver_type.value} на жадный алгоритм.")
                self.settings.solver_type = SolverType.GREEDY
        
        # Валидация настроек
        self._validate_settings()
    
    def _validate_settings(self):
        """Валидация настроек оптимизации"""
        if abs(self.settings.minimize_waste_weight + self.settings.minimize_stocks_weight - 1.0) > 0.001:
            raise ValueError("Сумма весов целей должна быть равна 1.0")
            
        if self.settings.blade_width < 0:
            raise ValueError("Ширина пропила не может быть отрицательной")
            
        if self.settings.min_remainder_length < 0:
            raise ValueError("Минимальная длина остатка не может быть отрицательной")
    
    def optimize(self, profiles: List[Profile], stocks: List[Stock], 
                progress_fn=None) -> OptimizationResult:
        """
        Главный метод оптимизации раскроя профилей
        
        Args:
            profiles: Список профилей для распила
            stocks: Список доступных хлыстов на складе
            progress_fn: Callback функция для отчета о прогрессе (0-100)
            
        Returns:
            OptimizationResult: Результат оптимизации с планами распила
        """
        start_time = time.time()
        
        if progress_fn:
            progress_fn(5)
        
        # Предобработка данных
        if self.settings.enable_preprocessing:
            profiles, stocks = self._preprocess_data(profiles, stocks)
        
        if progress_fn:
            progress_fn(15)
        
        # Выбор метода решения
        if self.settings.solver_type == SolverType.CP_SAT:
            if ORTOOLS_AVAILABLE:
                result = self._solve_with_cp_sat(profiles, stocks, progress_fn)
            else:
                result = self._solve_with_greedy(profiles, stocks, progress_fn)
        elif self.settings.solver_type == SolverType.BIN_PACKING:
            if ORTOOLS_AVAILABLE:
                result = self._solve_with_bin_packing(profiles, stocks, progress_fn)
            else:
                result = self._solve_with_greedy(profiles, stocks, progress_fn)
        elif self.settings.solver_type == SolverType.LINEAR_PROGRAMMING:
            if ORTOOLS_AVAILABLE:
                result = self._solve_with_linear_programming(profiles, stocks, progress_fn)
            else:
                result = self._solve_with_greedy(profiles, stocks, progress_fn)
        elif self.settings.solver_type == SolverType.GREEDY:
            result = self._solve_with_greedy(profiles, stocks, progress_fn)
        else:
            raise ValueError(f"Неподдерживаемый тип солвера: {self.settings.solver_type}")
        
        self.solve_time = time.time() - start_time
        
        # Постобработка результата
        result.message += f" | Время решения: {self.solve_time:.2f}с"
        
        if progress_fn:
            progress_fn(100)
            
        return result
    
    def _preprocess_data(self, profiles: List[Profile], stocks: List[Stock]) -> Tuple[List[Profile], List[Stock]]:
        """
        Предобработка данных для оптимизации
        
        - Удаление профилей с нулевым количеством
        - Сортировка по убыванию длины  
        - Проверка возможности размещения
        """
        # Удаляем профили с нулевым количеством
        valid_profiles = [p for p in profiles if p.quantity > 0]
        
        # Удаляем хлысты с нулевым количеством
        valid_stocks = [s for s in stocks if s.quantity > 0]
        
        # Проверяем что каждый профиль помещается хотя бы в один хлыст
        max_stock_length = max(s.length for s in valid_stocks) if valid_stocks else 0
        impossible_profiles = [
            p for p in valid_profiles 
            if p.length + self.settings.blade_width > max_stock_length
        ]
        
        if impossible_profiles:
            profile_names = [f"{p.element_name} ({p.length}мм)" for p in impossible_profiles]
            raise ValueError(f"Профили не помещаются ни в один хлыст: {', '.join(profile_names)}")
        
        # Сортируем профили по убыванию длины (First Fit Decreasing)
        valid_profiles.sort(key=lambda p: p.length, reverse=True)
        
        # Сортируем хлысты по убыванию длины
        valid_stocks.sort(key=lambda s: s.length, reverse=True)
        
        return valid_profiles, valid_stocks
    
    def _solve_with_cp_sat(self, profiles: List[Profile], stocks: List[Stock], 
                          progress_fn=None) -> OptimizationResult:
        """
        Решение с использованием CP-SAT (Constraint Programming)
        
        Основано на примере из документации OR-Tools для Bin Packing.
        CP-SAT является рекомендуемым солвером для таких задач.
        """
        model = cp_model.CpModel()
        
        if progress_fn:
            progress_fn(20)
        
        # Создаем переменные решения
        # x[i][j] = 1 если профиль i помещается в хлыст j
        x = {}
        for i, profile in enumerate(profiles):
            for j, stock in enumerate(stocks):
                if profile.length + self.settings.blade_width <= stock.length:
                    for copy in range(profile.quantity):
                        var_name = f"x_{i}_{j}_{copy}"
                        x[(i, j, copy)] = model.NewBoolVar(var_name)
        
        # y[j] = 1 если хлыст j используется
        y = {}
        for j, stock in enumerate(stocks):
            for copy in range(stock.quantity):
                var_name = f"y_{j}_{copy}"
                y[(j, copy)] = model.NewBoolVar(var_name)
        
        if progress_fn:
            progress_fn(40)
        
        # Ограничения
        
        # 1. Каждый профиль должен быть размещен ровно в одном хлысте
        for i, profile in enumerate(profiles):
            for copy in range(profile.quantity):
                constraint_terms = []
                for j, stock in enumerate(stocks):
                    for stock_copy in range(stock.quantity):
                        if (i, j, copy) in x:
                            constraint_terms.append(x[(i, j, copy)])
                
                if constraint_terms:
                    model.Add(sum(constraint_terms) == 1)
        
        # 2. Ограничение по длине каждого хлыста
        for j, stock in enumerate(stocks):
            for stock_copy in range(stock.quantity):
                total_length = 0
                item_count = 0
                
                for i, profile in enumerate(profiles):
                    for profile_copy in range(profile.quantity):
                        if (i, j, profile_copy) in x:
                            var = x[(i, j, profile_copy)]
                            total_length += var * profile.length
                            item_count += var
                
                # Добавляем длину пропилов (на 1 меньше чем количество кусков)
                if item_count > 0:
                    total_with_cuts = total_length + (item_count - 1) * self.settings.blade_width
                    model.Add(total_with_cuts <= stock.length * y.get((j, stock_copy), 1))
        
        # 3. Связь переменных использования хлыста с размещением профилей
        for j, stock in enumerate(stocks):
            for stock_copy in range(stock.quantity):
                if (j, stock_copy) in y:
                    items_in_stock = []
                    for i, profile in enumerate(profiles):
                        for profile_copy in range(profile.quantity):
                            if (i, j, profile_copy) in x:
                                items_in_stock.append(x[(i, j, profile_copy)])
                    
                    if items_in_stock:
                        # Если хлыст используется, то в него помещен хотя бы один профиль
                        model.AddMaxEquality(y[(j, stock_copy)], items_in_stock)
        
        if progress_fn:
            progress_fn(60)
        
        # Целевая функция: многоцелевая оптимизация
        objective_terms = []
        
        # Минимизация количества используемых хлыстов
        stocks_used = [y[key] for key in y.keys()]
        if stocks_used:
            stocks_weight = int(self.settings.minimize_stocks_weight * 1000)
            objective_terms.append(stocks_weight * sum(stocks_used))
        
        # Минимизация отходов (упрощенная оценка)
        total_waste = 0
        for j, stock in enumerate(stocks):
            for stock_copy in range(stock.quantity):
                if (j, stock_copy) in y:
                    # Приблизительная оценка отходов
                    used_length = 0
                    for i, profile in enumerate(profiles):
                        for profile_copy in range(profile.quantity):
                            if (i, j, profile_copy) in x:
                                used_length += x[(i, j, profile_copy)] * profile.length
                    
                    waste = (stock.length - used_length) * y[(j, stock_copy)]
                    total_waste += waste
        
        if total_waste > 0:
            waste_weight = int(self.settings.minimize_waste_weight * 10)
            objective_terms.append(waste_weight * total_waste)
        
        # Устанавливаем целевую функцию
        if objective_terms:
            model.Minimize(sum(objective_terms))
        
        if progress_fn:
            progress_fn(80)
        
        # Решаем модель
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.settings.time_limit_seconds
        
        if self.settings.parallel_threads > 0:
            solver.parameters.num_search_workers = self.settings.parallel_threads
        
        status = solver.Solve(model)
        self.solver_status = status
        
        if progress_fn:
            progress_fn(95)
        
        # Обрабатываем результат
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            cut_plans = self._extract_cp_sat_solution(solver, x, y, profiles, stocks)
            
            return OptimizationResult(
                cut_plans=cut_plans,
                total_waste=self._calculate_total_waste(cut_plans),
                total_waste_percent=self._calculate_waste_percent(cut_plans),
                settings=self.settings,
                success=True,
                message=f"CP-SAT: {'Оптимальное' if status == cp_model.OPTIMAL else 'Допустимое'} решение"
            )
        else:
            return OptimizationResult(
                cut_plans=[],
                total_waste=0,
                total_waste_percent=0,
                settings=self.settings,
                success=False,
                message=f"CP-SAT: Решение не найдено. Статус: {solver.StatusName(status)}"
            )
    
    def _solve_with_bin_packing(self, profiles: List[Profile], stocks: List[Stock], 
                               progress_fn=None) -> OptimizationResult:
        """
        Решение с использованием классического Bin Packing подхода
        
        Основано на примере из документации OR-Tools для Bin Packing.
        """
        solver = pywraplp.Solver.CreateSolver('SCIP')
        if not solver:
            return OptimizationResult(
                cut_plans=[], total_waste=0, total_waste_percent=0,
                settings=self.settings, success=False,
                message="Не удалось создать SCIP солвер"
            )
        
        if progress_fn:
            progress_fn(30)
        
        # Создаем список всех элементов для размещения
        items = []
        for i, profile in enumerate(profiles):
            for copy in range(profile.quantity):
                items.append({
                    'profile_index': i,
                    'profile_id': profile.id,
                    'length': profile.length,
                    'element_name': profile.element_name
                })
        
        # Создаем список всех доступных контейнеров (хлыстов)
        bins = []
        for j, stock in enumerate(stocks):
            for copy in range(stock.quantity):
                bins.append({
                    'stock_index': j,
                    'stock_id': stock.id,
                    'length': stock.length
                })
        
        # Переменные: x[i][j] = 1 если элемент i помещается в контейнер j
        x = {}
        for i, item in enumerate(items):
            for j, bin_info in enumerate(bins):
                if item['length'] + self.settings.blade_width <= bin_info['length']:
                    var_name = f"x_{i}_{j}"
                    x[(i, j)] = solver.IntVar(0, 1, var_name)
        
        # Переменные: y[j] = 1 если контейнер j используется
        y = {}
        for j, bin_info in enumerate(bins):
            var_name = f"y_{j}"
            y[j] = solver.IntVar(0, 1, var_name)
        
        if progress_fn:
            progress_fn(50)
        
        # Ограничения
        
        # 1. Каждый элемент должен быть помещен ровно в один контейнер
        for i, item in enumerate(items):
            constraint_terms = []
            for j, bin_info in enumerate(bins):
                if (i, j) in x:
                    constraint_terms.append(x[(i, j)])
            
            if constraint_terms:
                solver.Add(sum(constraint_terms) == 1)
        
        # 2. Ограничение по длине каждого контейнера
        for j, bin_info in enumerate(bins):
            total_length = 0
            item_count = 0
            
            for i, item in enumerate(items):
                if (i, j) in x:
                    var = x[(i, j)]
                    total_length += var * item['length']
                    item_count += var
            
            # Учитываем пропилы
            total_with_cuts = total_length + item_count * self.settings.blade_width
            solver.Add(total_with_cuts <= bin_info['length'] * y[j])
        
        if progress_fn:
            progress_fn(70)
        
        # Целевая функция: минимизировать количество используемых контейнеров
        solver.Minimize(sum(y[j] for j in y.keys()))
        
        # Решаем
        status = solver.Solve()
        
        if progress_fn:
            progress_fn(90)
        
        if status == pywraplp.Solver.OPTIMAL:
            cut_plans = self._extract_bin_packing_solution(solver, x, y, items, bins, stocks)
            
            return OptimizationResult(
                cut_plans=cut_plans,
                total_waste=self._calculate_total_waste(cut_plans),
                total_waste_percent=self._calculate_waste_percent(cut_plans),
                settings=self.settings,
                success=True,
                message="Bin Packing: Оптимальное решение найдено"
            )
        else:
            return OptimizationResult(
                cut_plans=[], total_waste=0, total_waste_percent=0,
                settings=self.settings, success=False,
                message=f"Bin Packing: Решение не найдено. Статус: {status}"
            )
    
    def _solve_with_linear_programming(self, profiles: List[Profile], stocks: List[Stock], 
                                      progress_fn=None) -> OptimizationResult:
        """
        Решение с использованием Linear Programming через MPSolver
        
        Альтернативный подход через стандартный LP солвер.
        """
        solver = pywraplp.Solver.CreateSolver('GLOP')
        if not solver:
            return OptimizationResult(
                cut_plans=[], total_waste=0, total_waste_percent=0,
                settings=self.settings, success=False,
                message="Не удалось создать GLOP солвер для линейного программирования"
            )
        
        if progress_fn:
            progress_fn(30)
        
        # Упрощенная LP модель - используем бинарные переменные
        # x[i][j] = 1 если профиль i помещается в хлыст j
        x = {}
        for i, profile in enumerate(profiles):
            for copy in range(profile.quantity):
                for j, stock in enumerate(stocks):
                    for stock_copy in range(stock.quantity):
                        if profile.length + self.settings.blade_width <= stock.length:
                            var_name = f"x_{i}_{copy}_{j}_{stock_copy}"
                            x[(i, copy, j, stock_copy)] = solver.IntVar(0, 1, var_name)
        
        if progress_fn:
            progress_fn(60)
        
        # Ограничения: каждый профиль должен быть размещен ровно в одном хлысте
        for i, profile in enumerate(profiles):
            for copy in range(profile.quantity):
                constraint_terms = []
                for j, stock in enumerate(stocks):
                    for stock_copy in range(stock.quantity):
                        if (i, copy, j, stock_copy) in x:
                            constraint_terms.append(x[(i, copy, j, stock_copy)])
                
                if constraint_terms:
                    solver.Add(sum(constraint_terms) == 1)
        
        # Ограничения по длине хлыстов
        for j, stock in enumerate(stocks):
            for stock_copy in range(stock.quantity):
                total_length = 0
                for i, profile in enumerate(profiles):
                    for profile_copy in range(profile.quantity):
                        if (i, profile_copy, j, stock_copy) in x:
                            total_length += x[(i, profile_copy, j, stock_copy)] * profile.length
                
                solver.Add(total_length <= stock.length)
        
        if progress_fn:
            progress_fn(80)
        
        # Целевая функция: минимизируем общую длину отходов
        total_waste = 0
        for j, stock in enumerate(stocks):
            for stock_copy in range(stock.quantity):
                used_length = 0
                for i, profile in enumerate(profiles):
                    for profile_copy in range(profile.quantity):
                        if (i, profile_copy, j, stock_copy) in x:
                            used_length += x[(i, profile_copy, j, stock_copy)] * profile.length
                
                waste = stock.length - used_length
                total_waste += waste
        
        solver.Minimize(total_waste)
        
        # Решаем
        status = solver.Solve()
        
        if progress_fn:
            progress_fn(95)
        
        if status == pywraplp.Solver.OPTIMAL:
            cut_plans = self._extract_lp_solution(solver, x, profiles, stocks)
            
            return OptimizationResult(
                cut_plans=cut_plans,
                total_waste=self._calculate_total_waste(cut_plans),
                total_waste_percent=self._calculate_waste_percent(cut_plans),
                settings=self.settings,
                success=True,
                message="Linear Programming: Оптимальное решение найдено"
            )
        else:
            return OptimizationResult(
                cut_plans=[], total_waste=0, total_waste_percent=0,
                settings=self.settings, success=False,
                message=f"Linear Programming: Решение не найдено. Статус: {status}"
            )
    
    def _solve_with_greedy(self, profiles: List[Profile], stocks: List[Stock], 
                          progress_fn=None) -> OptimizationResult:
        """
        Решение с использованием жадного алгоритма (запасной вариант)
        
        Простой и быстрый алгоритм First Fit Decreasing.
        Всегда работает, даже если OR-Tools недоступен.
        """
        if progress_fn:
            progress_fn(20)
        
        cut_plans = []
        
        # Создаем копии для работы
        remaining_profiles = []
        for profile in profiles:
            for _ in range(profile.quantity):
                remaining_profiles.append({
                    'id': profile.id,
                    'length': profile.length,
                    'element_name': profile.element_name
                })
        
        # Сортируем профили по убыванию длины (First Fit Decreasing)
        remaining_profiles.sort(key=lambda p: p['length'], reverse=True)
        
        # Создаем список доступных хлыстов
        available_stocks = []
        for stock in stocks:
            for _ in range(stock.quantity):
                available_stocks.append({
                    'id': stock.id,
                    'length': stock.length,
                    'remaining': stock.length
                })
        
        # Сортируем хлысты по убыванию длины
        available_stocks.sort(key=lambda s: s['length'], reverse=True)
        
        if progress_fn:
            progress_fn(50)
        
        # Жадное размещение
        for i, stock_info in enumerate(available_stocks):
            if not remaining_profiles:
                break
                
            cuts = []
            current_length = 0
            profiles_used = []
            
            # Пытаемся разместить профили в этот хлыст
            for profile in remaining_profiles[:]:
                needed_length = profile['length']
                if cuts:  # Если есть уже распилы, добавляем ширину пропила
                    needed_length += self.settings.blade_width
                
                if current_length + needed_length <= stock_info['length']:
                    # Профиль помещается
                    existing_cut = None
                    for cut in cuts:
                        if cut['profile_id'] == profile['id']:
                            existing_cut = cut
                            break
                    
                    if existing_cut:
                        existing_cut['quantity'] += 1
                    else:
                        cuts.append({
                            'profile_id': profile['id'],
                            'length': profile['length'],
                            'quantity': 1
                        })
                    
                    current_length += needed_length
                    profiles_used.append(profile)
            
            # Удаляем использованные профили
            for profile in profiles_used:
                remaining_profiles.remove(profile)
            
            # Создаем план распила если есть распилы
            if cuts:
                waste = stock_info['length'] - current_length
                remainder = None
                if waste >= self.settings.min_remainder_length:
                    remainder = waste
                    waste = 0
                
                cut_plan = CutPlan(
                    stock_id=stock_info['id'],
                    stock_length=stock_info['length'],
                    cuts=cuts,
                    waste=waste,
                    waste_percent=(waste / stock_info['length']) * 100,
                    remainder=remainder
                )
                cut_plans.append(cut_plan)
            
            if progress_fn:
                progress = 50 + (i / len(available_stocks)) * 40
                progress_fn(int(progress))
        
        if progress_fn:
            progress_fn(95)
        
        # Проверяем все ли профили размещены
        success = len(remaining_profiles) == 0
        message = "Жадный алгоритм: Все профили размещены" if success else f"Жадный алгоритм: {len(remaining_profiles)} профилей не размещены"
        
        return OptimizationResult(
            cut_plans=cut_plans,
            total_waste=self._calculate_total_waste(cut_plans),
            total_waste_percent=self._calculate_waste_percent(cut_plans),
            settings=self.settings,
            success=success,
            message=message
        )
    
    def _extract_lp_solution(self, solver, x, profiles, stocks) -> List[CutPlan]:
        """Извлечение решения из Linear Programming модели"""
        cut_plans = []
        
        # Группируем результат по хлыстам
        stock_assignments = {}
        
        for (i, copy, j, stock_copy), var in x.items():
            if solver.Value(var) > 0.5:  # Пороговое значение для бинарных переменных
                stock_key = (j, stock_copy)
                if stock_key not in stock_assignments:
                    stock_assignments[stock_key] = []
                stock_assignments[stock_key].append(i)
        
        # Создаем планы распила
        for (stock_idx, stock_copy), profile_indices in stock_assignments.items():
            if not profile_indices:
                continue
                
            stock = stocks[stock_idx]
            
            # Группируем по типам профилей
            profile_counts = {}
            total_used_length = 0
            
            for profile_idx in profile_indices:
                profile = profiles[profile_idx]
                if profile.id not in profile_counts:
                    profile_counts[profile.id] = {
                        'length': profile.length,
                        'quantity': 0
                    }
                profile_counts[profile.id]['quantity'] += 1
                total_used_length += profile.length
            
            # Учитываем пропилы
            total_cuts = sum(info['quantity'] for info in profile_counts.values())
            if total_cuts > 1:
                total_used_length += (total_cuts - 1) * self.settings.blade_width
            
            # Создаем список распилов
            cuts = []
            for profile_id, info in profile_counts.items():
                cuts.append({
                    'profile_id': profile_id,
                    'length': info['length'],
                    'quantity': info['quantity']
                })
            
            # Рассчитываем отходы и остаток
            waste = stock.length - total_used_length
            remainder = None
            if waste >= self.settings.min_remainder_length:
                remainder = waste
                waste = 0
            
            cut_plan = CutPlan(
                stock_id=stock.id,
                stock_length=stock.length,
                cuts=cuts,
                waste=waste,
                waste_percent=(waste / stock.length) * 100 if stock.length > 0 else 0,
                remainder=remainder
            )
            cut_plans.append(cut_plan)
        
        return cut_plans
    
    def _extract_cp_sat_solution(self, solver, x, y, profiles, stocks) -> List[CutPlan]:
        """Извлечение решения из CP-SAT модели"""
        cut_plans = []
        
        # Группируем результат по хлыстам
        stock_assignments = {}
        
        for (i, j, copy), var in x.items():
            if solver.Value(var) > 0:
                stock_key = j
                if stock_key not in stock_assignments:
                    stock_assignments[stock_key] = []
                stock_assignments[stock_key].append(i)
        
        # Создаем планы распила
        for stock_idx, profile_indices in stock_assignments.items():
            if not profile_indices:
                continue
                
            stock = stocks[stock_idx]
            
            # Группируем по типам профилей
            profile_counts = {}
            total_used_length = 0
            
            for profile_idx in profile_indices:
                profile = profiles[profile_idx]
                if profile.id not in profile_counts:
                    profile_counts[profile.id] = {
                        'length': profile.length,
                        'quantity': 0
                    }
                profile_counts[profile.id]['quantity'] += 1
                total_used_length += profile.length
            
            # Учитываем пропилы
            total_cuts = sum(info['quantity'] for info in profile_counts.values())
            if total_cuts > 1:
                total_used_length += (total_cuts - 1) * self.settings.blade_width
            
            # Создаем список распилов
            cuts = []
            for profile_id, info in profile_counts.items():
                cuts.append({
                    'profile_id': profile_id,
                    'length': info['length'],
                    'quantity': info['quantity']
                })
            
            # Рассчитываем отходы и остаток
            waste = stock.length - total_used_length
            remainder = None
            if waste >= self.settings.min_remainder_length:
                remainder = waste
                waste = 0
            
            cut_plan = CutPlan(
                stock_id=stock.id,
                stock_length=stock.length,
                cuts=cuts,
                waste=waste,
                waste_percent=(waste / stock.length) * 100 if stock.length > 0 else 0,
                remainder=remainder
            )
            cut_plans.append(cut_plan)
        
        return cut_plans
    
    def _extract_bin_packing_solution(self, solver, x, y, items, bins, stocks) -> List[CutPlan]:
        """Извлечение решения из Bin Packing модели"""
        cut_plans = []
        
        # Группируем элементы по контейнерам
        bin_assignments = {}
        
        for (i, j), var in x.items():
            if solver.Value(var) > 0:
                if j not in bin_assignments:
                    bin_assignments[j] = []
                bin_assignments[j].append(i)
        
        # Создаем планы распила для используемых контейнеров
        for bin_idx, item_indices in bin_assignments.items():
            if not item_indices:
                continue
                
            bin_info = bins[bin_idx]
            stock = stocks[bin_info['stock_index']]
            
            # Группируем элементы по профилям
            profile_counts = {}
            total_used_length = 0
            
            for item_idx in item_indices:
                item = items[item_idx]
                profile_id = item['profile_id']
                
                if profile_id not in profile_counts:
                    profile_counts[profile_id] = {
                        'length': item['length'],
                        'quantity': 0
                    }
                profile_counts[profile_id]['quantity'] += 1
                total_used_length += item['length']
            
            # Учитываем пропилы
            total_cuts = sum(info['quantity'] for info in profile_counts.values())
            if total_cuts > 1:
                total_used_length += (total_cuts - 1) * self.settings.blade_width
            
            # Создаем список распилов
            cuts = []
            for profile_id, info in profile_counts.items():
                cuts.append({
                    'profile_id': profile_id,
                    'length': info['length'],
                    'quantity': info['quantity']
                })
            
            # Рассчитываем отходы и остаток
            waste = stock.length - total_used_length
            remainder = None
            if waste >= self.settings.min_remainder_length:
                remainder = waste
                waste = 0
            
            cut_plan = CutPlan(
                stock_id=stock.id,
                stock_length=stock.length,
                cuts=cuts,
                waste=waste,
                waste_percent=(waste / stock.length) * 100 if stock.length > 0 else 0,
                remainder=remainder
            )
            cut_plans.append(cut_plan)
        
        return cut_plans
    
    def _calculate_total_waste(self, cut_plans: List[CutPlan]) -> float:
        """Рассчитать общие отходы"""
        return sum(plan.waste for plan in cut_plans)
    
    def _calculate_waste_percent(self, cut_plans: List[CutPlan]) -> float:
        """Рассчитать процент отходов"""
        if not cut_plans:
            return 0.0
            
        total_length = sum(plan.stock_length for plan in cut_plans)
        total_waste = self._calculate_total_waste(cut_plans)
        
        return (total_waste / total_length) * 100 if total_length > 0 else 0.0
    
    def get_optimization_stats(self) -> Dict[str, Any]:
        """Получить статистику оптимизации"""
        return {
            'solver_type': self.settings.solver_type.value,
            'solve_time_seconds': self.solve_time,
            'solver_status': str(self.solver_status) if self.solver_status else None,
            'settings': {
                'blade_width': self.settings.blade_width,
                'min_remainder_length': self.settings.min_remainder_length,
                'time_limit_seconds': self.settings.time_limit_seconds,
                'minimize_waste_weight': self.settings.minimize_waste_weight,
                'minimize_stocks_weight': self.settings.minimize_stocks_weight
            }
        }

# Главная функция для простого использования (заменяет LinearOptimizer)
def optimize_cutting_stock(profiles: List[Profile], stocks: List[Stock], 
                          solver_type: SolverType = SolverType.CP_SAT,
                          blade_width: float = 5.0,
                          min_remainder: float = 300.0,
                          time_limit: int = 300,
                          progress_fn=None) -> OptimizationResult:
    """
    Упрощенная функция для оптимизации раскроя профилей
    
    Args:
        profiles: Список профилей для распила
        stocks: Список доступных хлыстов
        solver_type: Тип солвера (CP_SAT, BIN_PACKING, MIP)
        blade_width: Ширина пропила в мм
        min_remainder: Минимальная длина остатка в мм
        time_limit: Лимит времени в секундах
        progress_fn: Callback для прогресса
        
    Returns:
        OptimizationResult: Результат оптимизации
    """
    settings = OptimizationSettings(
        blade_width=blade_width,
        min_remainder_length=min_remainder,
        time_limit_seconds=time_limit,
        solver_type=solver_type
    )
    
    optimizer = CuttingStockOptimizer(settings)
    return optimizer.optimize(profiles, stocks, progress_fn)


# Классы для обратной совместимости со старым API
class LinearOptimizer:
    """
    Класс для обратной совместимости
    Перенаправляет вызовы к новому CuttingStockOptimizer
    """
    
    def __init__(self, settings=None):
        # Конвертируем старые настройки в новые
        if settings:
            self.cutting_settings = OptimizationSettings(
                blade_width=getattr(settings, 'blade_width', 5.0),
                min_remainder_length=getattr(settings, 'min_remainder_length', 300.0),
                time_limit_seconds=300,
                solver_type=SolverType.CP_SAT
            )
        else:
            self.cutting_settings = OptimizationSettings()
        
        self.optimizer = CuttingStockOptimizer(self.cutting_settings)
    
    def optimize(self, profiles: List[Profile], stocks: List[Stock], 
                settings=None, progress_fn=None, use_professional=True) -> OptimizationResult:
        """
        Главный метод оптимизации (обратная совместимость)
        """
        if not use_professional:
            # Если не хотят профессиональный - используем жадный
            greedy_settings = OptimizationSettings(
                blade_width=self.cutting_settings.blade_width,
                min_remainder_length=self.cutting_settings.min_remainder_length,
                solver_type=SolverType.GREEDY
            )
            greedy_optimizer = CuttingStockOptimizer(greedy_settings)
            return greedy_optimizer.optimize(profiles, stocks, progress_fn)
        
        return self.optimizer.optimize(profiles, stocks, progress_fn)


if __name__ == "__main__":
    # Пример использования
    print("🔧 Тестирование оптимизатора раскроя профилей")
    print("=" * 60)
    
    # Тестовые данные
    test_profiles = [
        Profile(id=1, order_id=1, element_name="Рама", profile_code="P001", length=2400, quantity=4),
        Profile(id=2, order_id=1, element_name="Импост", profile_code="P001", length=1800, quantity=2),
        Profile(id=3, order_id=1, element_name="Створка", profile_code="P001", length=1200, quantity=6),
    ]
    
    test_stocks = [
        Stock(id=1, profile_id=1, length=6000, quantity=5),
        Stock(id=2, profile_id=1, length=4000, quantity=3),
    ]
    
    def progress_callback(percent):
        print(f"  Прогресс: {percent}%")
    
    try:
        # Тестируем разные солверы
        solvers_to_test = [
            (SolverType.GREEDY, "Жадный алгоритм"),
            (SolverType.CP_SAT, "CP-SAT (OR-Tools)"),
            (SolverType.BIN_PACKING, "Bin Packing"),
        ]
        
        for solver_type, solver_name in solvers_to_test:
            print(f"\n🚀 Тестирование {solver_name}...")
            try:
                result = optimize_cutting_stock(
                    test_profiles, test_stocks, 
                    solver_type, 
                    progress_fn=progress_callback
                )
                
                print(f"✅ Результат: {'Успех' if result.success else 'Неудача'}")
                print(f"📊 Отходы: {result.total_waste_percent:.1f}%")
                print(f"📋 Планов распила: {len(result.cut_plans)}")
                print(f"💬 Сообщение: {result.message}")
                
            except Exception as e:
                print(f"❌ Ошибка {solver_name}: {e}")
        
        print(f"\n🎯 Рекомендации:")
        print(f"✅ Для быстрых расчетов: Жадный алгоритм")
        print(f"🚀 Для оптимальных результатов: CP-SAT (требует OR-Tools)")
        print(f"📦 Для минимизации хлыстов: Bin Packing")
        
        print(f"✅ Результат: {result.success}")
        print(f"📊 Отходы: {result.total_waste_percent:.1f}%")
        print(f"📋 Планов распила: {len(result.cut_plans)}")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")