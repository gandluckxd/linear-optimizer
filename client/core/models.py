"""
Модели данных для Linear Optimizer Client
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime

@dataclass
class Profile:
    """Профиль для распила"""
    id: int
    order_id: int
    element_name: str  # Элемент (наименование orderitem)
    profile_code: str  # Артикул профиля
    length: float  # Длина в мм
    quantity: int  # Количество штук
    color: str = ""  # Цвет для визуализации
    
    def __post_init__(self):
        # Копируем количество для отслеживания оставшихся
        self.remaining_quantity = self.quantity

@dataclass
class StockRemainder:
    """Остатки на складе"""
    profile_code: str  # Наименование (артикул профиля)
    length: float  # Длина в мм
    quantity_pieces: int  # Количество палок
    selected_quantity: int = 0  # Выбрано для распила

@dataclass
class StockMaterial:
    """Цельные материалы на складе"""
    profile_code: str  # Наименование (артикул профиля)
    length: float  # Длина в мм
    quantity_pieces: int  # Количество штук
    selected_quantity: int = 0  # Выбрано для распила

# Для обратной совместимости оставляем старую модель Stock
@dataclass
class Stock:
    """Хлыст на складе (для обратной совместимости)"""
    id: int
    profile_id: int
    length: float  # Длина в мм
    quantity: int  # Количество на складе
    location: str = ""  # Место хранения
    is_remainder: bool = False  # Является ли остатком
    selected_quantity: int = 0  # Выбрано для распила

@dataclass
class CutPlan:
    """План распила одного хлыста"""
    stock_id: int
    stock_length: float
    cuts: List[Dict]  # [{profile_id, length, quantity}]
    waste: float  # Отход в мм на один хлыст
    waste_percent: float  # Процент отхода на один хлыст
    remainder: Optional[float] = None  # Остаток (если >= min_remainder)
    count: int = 1  # Количество одинаковых хлыстов с этим планом
    is_remainder: bool = False  # Признак, что исходный хлыст был остатком
    
    def get_used_length(self, saw_width: float = 5.0) -> float:
        """Получить использованную длину с учетом пропилов"""
        if not self.cuts:
            return 0.0
        
        total_length = 0.0
        total_cuts = 0
        
        try:
            for cut in self.cuts:
                # Защитная проверка данных
                if isinstance(cut, dict) and 'length' in cut and 'quantity' in cut:
                    length = float(cut['length'])
                    quantity = int(cut['quantity'])
                    total_length += length * quantity
                    total_cuts += quantity
                else:
                    print(f"⚠️ Некорректные данные в cut: {cut}")
        except (KeyError, ValueError, TypeError) as e:
            print(f"⚠️ Ошибка в get_used_length: {e}")
            return 0.0
        
        # Добавляем ширину пропилов (количество пропилов = количество кусков - 1)
        if total_cuts > 1:
            total_length += saw_width * (total_cuts - 1)
        
        return total_length
    
    def get_total_pieces_length(self) -> float:
        """Получить общую длину всех кусков без учета пропилов"""
        try:
            total = 0.0
            for cut in self.cuts:
                if isinstance(cut, dict) and 'length' in cut and 'quantity' in cut:
                    total += float(cut['length']) * int(cut['quantity'])
            return total
        except (KeyError, ValueError, TypeError) as e:
            print(f"⚠️ Ошибка в get_total_pieces_length: {e}")
            return 0.0
    
    def get_cuts_count(self) -> int:
        """Получить общее количество кусков"""
        try:
            total = 0
            for cut in self.cuts:
                if isinstance(cut, dict) and 'quantity' in cut:
                    total += int(cut['quantity'])
            return total
        except (KeyError, ValueError, TypeError) as e:
            print(f"⚠️ Ошибка в get_cuts_count: {e}")
            return 0
    
    def validate(self, saw_width: float = 5.0) -> bool:
        """Проверить корректность плана распила"""
        try:
            used_length = self.get_used_length(saw_width)
            return used_length <= self.stock_length
        except Exception as e:
            print(f"⚠️ Ошибка в validate: {e}")
            return False

@dataclass
class OptimizationResult:
    """Результат оптимизации"""
    cut_plans: List[CutPlan]
    total_waste: float
    total_waste_percent: float
    settings: 'OptimizationSettings'
    created_at: datetime = field(default_factory=datetime.now)
    success: bool = True
    message: str = ""
    statistics: Dict = field(default_factory=dict)
    
    def get_statistics(self) -> Dict:
        """Получить статистику оптимизации"""
        try:
            total_stocks = sum(getattr(plan, 'count', 1) for plan in self.cut_plans) if self.cut_plans else 0
            total_cuts = 0
            total_length = 0.0
            
            for plan in self.cut_plans:
                total_cuts += plan.get_cuts_count() * getattr(plan, 'count', 1)
                total_length += plan.stock_length * getattr(plan, 'count', 1)
            
            return {
                'total_stocks': total_stocks,
                'total_cuts': total_cuts,
                'total_length': total_length,
                'total_waste': self.total_waste,
                'waste_percent': self.total_waste_percent,
                'avg_waste_per_stock': self.total_waste / total_stocks if total_stocks > 0 else 0
            }
        except Exception as e:
            print(f"⚠️ Ошибка в get_statistics: {e}")
            return {
                'total_stocks': 0,
                'total_cuts': 0,
                'total_length': 0.0,
                'total_waste': 0.0,
                'waste_percent': 0.0,
                'avg_waste_per_stock': 0.0
            }

@dataclass
class Order:
    """Заказ/сменное задание"""
    id: int
    number: str
    customer: str
    date: datetime
    status: str = "new"
    profiles: List[Profile] = field(default_factory=list) 