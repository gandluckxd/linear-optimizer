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
    waste: float  # Отход в мм
    waste_percent: float  # Процент отхода
    remainder: Optional[float] = None  # Остаток (если >= min_remainder)
    
    def get_used_length(self, saw_width: float = 3.0) -> float:
        """Получить использованную длину с учетом пропилов"""
        total = 0
        for cut in self.cuts:
            total += (cut['length'] + saw_width) * cut['quantity']
        return total - saw_width  # Последний пропил не нужен

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
    
    def get_statistics(self) -> Dict:
        """Получить статистику оптимизации"""
        total_stocks = len(self.cut_plans)
        total_cuts = sum(sum(cut['quantity'] for cut in plan.cuts) for plan in self.cut_plans)
        total_length = sum(plan.stock_length for plan in self.cut_plans)
        
        return {
            'total_stocks': total_stocks,
            'total_cuts': total_cuts,
            'total_length': total_length,
            'total_waste': self.total_waste,
            'waste_percent': self.total_waste_percent,
            'avg_waste_per_stock': self.total_waste / total_stocks if total_stocks > 0 else 0
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