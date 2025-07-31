"""
Модели данных для Linear Optimizer API
"""

from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

# Модели для получения данных из Altawin

class ProfileRequest(BaseModel):
    """Запрос на получение профилей для распила"""
    order_id: int  # ID заказа или сменного задания
    
class StockRequest(BaseModel):
    """Запрос на получение остатков профиля на складе"""
    profile_id: int  # ID профиля (goodsid)

class StockRemainderRequest(BaseModel):
    """Запрос на получение остатков со склада"""
    profile_codes: List[str]  # Список артикулов профилей

class StockMaterialRequest(BaseModel):
    """Запрос на получение цельных материалов со склада"""
    profile_codes: List[str]  # Список артикулов профилей

# Модели данных

class Profile(BaseModel):
    """Профиль для распила"""
    id: int
    order_id: int
    element_name: str  # Элемент (наименование orderitem)
    profile_code: str  # Артикул профиля
    length: float  # Требуемая длина в мм
    quantity: int  # Количество штук
    
class StockRemainder(BaseModel):
    """Остатки на складе"""
    profile_code: str  # Наименование (артикул профиля)
    length: float  # Длина в мм
    quantity_pieces: int  # Количество палок (важно! не суммарное количество, а именно количество палок)

class StockMaterial(BaseModel):
    """Цельные материалы на складе"""
    profile_code: str  # Наименование (артикул профиля)
    length: float  # Длина в мм
    quantity_pieces: int  # Количество штук

# Для обратной совместимости оставляем старую модель Stock
class Stock(BaseModel):
    """Хлыст на складе (для обратной совместимости)"""
    id: int
    profile_id: int
    length: float  # Длина хлыста в мм
    quantity: int  # Количество на складе
    location: Optional[str] = None  # Место хранения
    is_remainder: bool = False  # Является ли остатком

class CutPlan(BaseModel):
    """План распила одного хлыста"""
    stock_id: int  # ID хлыста
    stock_length: float  # Длина хлыста
    cuts: List[dict]  # Список распилов [{profile_id, length, quantity}]
    waste: float  # Отход в мм
    waste_percent: float  # Процент отхода
    remainder: Optional[float] = None  # Остаток (если больше минимального)

# Модели для загрузки результатов в Altawin

class OptimizationResult(BaseModel):
    """Результат оптимизации для загрузки в Altawin"""
    order_id: int
    cut_plans: List[CutPlan]
    total_waste: float
    total_waste_percent: float
    profiles_cut: int  # Количество распиленных профилей
    stocks_used: int  # Количество использованных хлыстов
    created_at: datetime

class UploadRequest(BaseModel):
    """Запрос на загрузку результатов в Altawin"""
    optimization_result: OptimizationResult
    save_to_order: bool = True  # Сохранить в заказ
    create_cutting_list: bool = True  # Создать задание на распил

# Новые модели для москитных сеток

class MoskitkaRequest(BaseModel):
    """Запрос на получение профилей москитных сеток"""
    grorder_ids: List[int]  # Список ID групп заказов

class MoskitkaProfile(BaseModel):
    """Профиль москитной сетки для раскроя"""
    
    # Конфигурация модели для избежания конфликта с protected namespaces
    model_config = {'protected_namespaces': ()}
    
    grorder_id: int
    order_item_id: int
    order_item_name: str
    grorder_qty: int  # Количество в группе заказов
    order_qty: int  # Количество в заказе
    order_width: Optional[int] = None
    order_height: Optional[int] = None
    
    # Данные детали
    item_detail_id: int
    model_no: int
    part_num: Optional[int] = None
    detail_width: Optional[float] = None
    detail_height: Optional[float] = None
    detail_length: Optional[float] = None  # Длина профиля для раскроя
    detail_qty: Optional[int] = None
    izd_part: Optional[str] = None  # Часть изделия
    part_side: Optional[str] = None  # Сторона изделия
    
    # Данные товара
    goods_group_name: Optional[str] = None
    group_marking: Optional[str] = None
    goods_marking: Optional[str] = None
    
    # Данные профиля
    profil_name: Optional[str] = None
    part_type: Optional[str] = None  # Тип профиля (рама, импост, створка)
    length_prof: Optional[int] = None  # Длина хлыста
    width_prof: Optional[float] = None
    thick_prof: Optional[float] = None
    
    # Расчетные поля
    total_length_needed: Optional[float] = None  # Общая необходимая длина 