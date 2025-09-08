"""
Модели данных для Linear Optimizer Client
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime
from enum import Enum

class RotationMode(Enum):
    """Режимы поворота деталей"""
    NONE = "none"           # Без поворота
    ALLOW_90 = "allow_90"   # Разрешить поворот на 90°
    OPTIMAL = "optimal"     # Автоматический выбор наилучшего поворота

@dataclass
class PlacedFiberglassItem:
    """Размещенный элемент на рулоне"""
    x: float
    y: float
    width: float
    height: float
    item_type: str  # "detail", "remainder", "waste"
    detail: Optional['FiberglassDetail'] = None
    is_rotated: bool = False
    cell_number: Optional[int] = None

    def __post_init__(self):
        self.x2 = self.x + self.width
        self.y2 = self.y + self.height
        self.area = self.width * self.height

@dataclass
class FiberglassRollLayout:
    """Раскладка одного рулона фибергласса"""
    roll: 'FiberglassRoll'
    placed_items: List[PlacedFiberglassItem] = field(default_factory=list)
    waste_percent: float = 0.0
    used_length: float = 0.0

    def get_remnants(self) -> List[PlacedFiberglassItem]:
        """Получить все деловые остатки на рулоне"""
        return [item for item in self.placed_items if item.item_type == "remainder"]

    def get_waste(self) -> List[PlacedFiberglassItem]:
        """Получить все отходы на рулоне"""
        return [item for item in self.placed_items if item.item_type == "waste"]

@dataclass
class FiberglassOptimizationResult:
    """Результат оптимизации фибергласса"""
    success: bool
    layouts: List['FiberglassRollLayout']
    unplaced_details: List['FiberglassDetail']
    total_efficiency: float
    total_waste_percent: float
    total_cost: float
    useful_remnants: List[PlacedFiberglassItem]
    optimization_time: float
    message: str = ""

    def __post_init__(self):
        self.total_rolls = len(self.layouts)
        self.total_placed_details = sum(len(layout.placed_items) for layout in self.layouts
                                       if layout.placed_items and layout.placed_items[0].item_type == "detail")

@dataclass
class Piece:
    """Отдельная деталь для размещения на хлысте"""
    profile_id: int
    profile_code: str
    length: float
    element_name: str
    order_id: int
    piece_id: str  # Уникальный идентификатор детали
    orderitemsid: Optional[int] = None # ID позиции заказа
    izdpart: Optional[str] = None      # Номер части изделия
    itemsdetailid: Optional[int] = None # ID детали конструкции
    quantity: int = 1
    
    # Состояние размещения
    placed: bool = False
    placed_in_stock_id: Optional[str] = None
    placed_in_plan_index: Optional[int] = None
    cell_number: Optional[int] = None
    
    def __post_init__(self):
        if not self.piece_id:
            self.piece_id = f"{self.profile_id}_{self.length}_{self.order_id}_{id(self)}"

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
    orderitemsid: Optional[int] = None # ID позиции заказа
    izdpart: Optional[str] = None      # Номер части изделия
    itemsdetailid: Optional[int] = None # ID детали конструкции
    
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
    warehouseremaindersid: Optional[int] = None  # ID делового остатка в таблице WAREHOUSEREMAINDER
    profile_code: str = ""  # Артикул профиля

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
    warehouseremaindersid: Optional[int] = None  # ID делового остатка в таблице WAREHOUSEREMAINDER
    
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
            
            base_stats = {
                'total_stocks': total_stocks,
                'total_cuts': total_cuts,
                'total_length': total_length,
                'total_waste': self.total_waste,
                'waste_percent': self.total_waste_percent,
                'avg_waste_per_stock': self.total_waste / total_stocks if total_stocks > 0 else 0
            }
            # Добавляем/обновляем дополнительные статистики, если они были сохранены в процессе оптимизации
            try:
                if isinstance(self.statistics, dict) and self.statistics:
                    base_stats.update(self.statistics)
            except Exception as merge_err:
                print(f"⚠️ Ошибка объединения статистики: {merge_err}")
            return base_stats
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

@dataclass
class FiberglassDetail:
    """Деталь фибергласса для раскроя"""
    grorder_mos_id: int
    orderid: int
    orderitemsid: int
    itemsdetailid: int
    item_name: str  # Название изделия (01, 02, 03...)
    width: float    # Ширина детали в мм
    height: float   # Высота детали в мм
    quantity: int   # Количество деталей
    goodsid: int    # ID материала
    marking: str    # Артикул материала
    orderno: str    # Номер заказа
    modelno: Optional[int] = None
    partside: Optional[str] = None
    izdpart: Optional[str] = None

    def __post_init__(self):
        # Вычисляем площадь для сортировки по размеру
        self.area = self.width * self.height

@dataclass
class FiberglassSheet:
    """Лист/рулон фибергласса"""
    goodsid: int
    marking: str    # Артикул материала
    width: float    # Ширина рулона
    height: float   # Длина рулона
    is_remainder: bool = False
    remainder_id: Optional[int] = None  # whremainderid для остатков
    quantity: int = 1
    area_mm2: Optional[float] = None  # Площадь для сортировки остатков

@dataclass
class FiberglassRoll:
    """Рулон фибергласса"""
    id: str
    width: float    # Ширина рулона
    length: float   # Длина рулона (обычно 30000мм = 30м)
    material: str
    cost_per_unit: float = 0.0
    is_remainder: bool = False
    remainder_id: Optional[str] = None

    def __post_init__(self):
        self.area = self.width * self.length

@dataclass
class FiberglassOptimizationParams:
    """Параметры оптимизации фибергласса"""
    min_remainder_width: float = 500.0
    min_remainder_length: float = 1000.0
    target_waste_percent: float = 5.0
    remainder_waste_percent: float = 20.0
    min_waste_side: float = 50.0
    use_warehouse_remnants: bool = True
    rotation_mode: RotationMode = RotationMode.ALLOW_90
    force_adjacent_placement: bool = True
    max_iterations_per_roll: int = 5
    cutting_width: float = 0.0

    # Новые параметры плоскостной оптимизации из интерфейса
    planar_min_remainder_width: float = 500.0    # Минимальная ширина для деловых остатков (мм)
    planar_min_remainder_height: float = 500.0   # Минимальная высота для деловых остатков (мм)
    planar_cut_width: float = 1.0                # Ширина реза для плоскостной оптимизации (мм)
    sheet_indent: float = 15.0                   # Отступы для листа со всех сторон (мм)
    remainder_indent: float = 15.0               # Отступы для делового остатка со всех сторон (мм)
    planar_max_waste_percent: float = 5.0        # Максимальная процент отхода для плоскостной оптимизации (%)

@dataclass
class FiberglassLoadDataResponse:
    """Ответ с загруженными данными фибергласса"""
    details: List[FiberglassDetail]
    materials: List[FiberglassSheet]  # Цельные рулоны
    remainders: List[FiberglassSheet]  # Деловые остатки
    total_details: int
    total_materials: int
    total_remainders: int