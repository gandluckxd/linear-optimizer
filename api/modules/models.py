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
    orderitemsid: int # ID элемента заказа
    izdpart: Optional[str] = None # Часть изделия
    itemsdetailid: int # ID детали конструкции
    
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
    warehouseremaindersid: Optional[int] = None  # ID делового остатка в таблице WAREHOUSEREMAINDER

class CutPlan(BaseModel):
    """План распила одного хлыста"""
    stock_id: int  # ID хлыста
    stock_length: float  # Длина хлыста
    cuts: List[dict]  # Список распилов [{profile_id, length, quantity}]
    waste: float  # Отход в мм
    waste_percent: float  # Процент отхода
    remainder: Optional[float] = None  # Остаток (если больше минимального)
    warehouseremaindersid: Optional[int] = None  # ID делового остатка в таблице WAREHOUSEREMAINDER
    
    def get_used_length(self, saw_width: float = 5.0) -> float:
        """Получить использованную длину с учетом пропилов"""
        if not self.cuts:
            return 0.0
        
        total_length = 0.0
        total_cuts = 0
        
        for cut in self.cuts:
            total_length += cut['length'] * cut['quantity']
            total_cuts += cut['quantity']
        
        # Добавляем ширину пропилов (количество пропилов = количество кусков - 1)
        if total_cuts > 1:
            total_length += saw_width * (total_cuts - 1)
        
        return total_length
    
    def get_total_pieces_length(self) -> float:
        """Получить общую длину всех кусков без учета пропилов"""
        return sum(cut['length'] * cut['quantity'] for cut in self.cuts)
    
    def get_cuts_count(self) -> int:
        """Получить общее количество кусков"""
        return sum(cut['quantity'] for cut in self.cuts)
    
    def validate(self, saw_width: float = 5.0) -> bool:
        """Проверить корректность плана распила"""
        used_length = self.get_used_length(saw_width)
        return used_length <= self.stock_length

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


class GrordersByMosIdRequest(BaseModel):
    """Запрос на получение списка grorder_ids по GRORDERS_MOS_ID"""
    grorders_mos_id: int  # Идентификатор сменного задания москитных сеток

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
    izdpart: Optional[str] = None  # Часть изделия
    partside: Optional[str] = None  # Сторона изделия
    
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

# Модели для таблицы GRORDERS_MOS

class GrordersMosCreate(BaseModel):
    """Входная модель для создания записи в GRORDERS_MOS"""
    name: str


class GrordersMos(BaseModel):
    """Модель записи таблицы GRORDERS_MOS"""
    id: int
    name: Optional[str] = None


# Модели для таблицы OPTIMIZED_MOS

class OptimizedMosCreate(BaseModel):
    """Входная модель для создания записи в OPTIMIZED_MOS"""
    grorder_mos_id: int
    goodsid: int
    qty: int
    isbar: int
    longprof: Optional[float] = None
    cutwidth: Optional[int] = None
    border: Optional[int] = None
    minrest: Optional[int] = None
    mintrash: Optional[int] = None
    map: Optional[str] = None
    ostat: Optional[float] = None
    sumprof: Optional[float] = None
    restpercent: Optional[float] = None
    trashpercent: Optional[float] = None
    beginindent: Optional[int] = None
    endindent: Optional[int] = None
    sumtrash: Optional[float] = None


class OptimizedMos(BaseModel):
    """Модель записи таблицы OPTIMIZED_MOS"""
    id: int
    grorder_mos_id: int
    goodsid: int
    qty: int
    isbar: int
    longprof: Optional[float] = None
    cutwidth: Optional[int] = None
    border: Optional[int] = None
    minrest: Optional[int] = None
    mintrash: Optional[int] = None
    map: Optional[str] = None
    ostat: Optional[float] = None
    sumprof: Optional[float] = None
    restpercent: Optional[float] = None
    trashpercent: Optional[float] = None
    beginindent: Optional[int] = None
    endindent: Optional[int] = None
    sumtrash: Optional[float] = None


# Модели для таблицы OPTDETAIL_MOS

class OptDetailMosCreate(BaseModel):
    """Входная модель для создания записи в OPTDETAIL_MOS"""
    optimized_mos_id: int
    orderid: int
    qty: int
    itemsdetailid: Optional[int] = None
    orderitemsid: Optional[int] = None  # КРИТИЧЕСКИ ВАЖНО: ID изделия для уникальной идентификации
    itemlong: Optional[float] = None
    ug1: Optional[float] = None
    ug2: Optional[float] = None
    num: Optional[int] = None
    subnum: Optional[int] = None
    long_al: Optional[float] = None
    izdpart: Optional[str] = None
    partside: Optional[str] = None
    modelno: Optional[int] = None
    modelheight: Optional[int] = None
    modelwidth: Optional[int] = None
    flugelopentype: Optional[int] = None
    flugelcount: Optional[int] = None
    ishandle: Optional[int] = None
    handlepos: Optional[float] = None
    handleposfalts: Optional[float] = None
    flugelopentag: Optional[str] = None


class OptDetailMos(BaseModel):
    """Модель записи таблицы OPTDETAIL_MOS"""
    id: int
    optimized_mos_id: int
    orderid: int
    qty: int
    itemsdetailid: Optional[int] = None
    orderitemsid: Optional[int] = None  # КРИТИЧЕСКИ ВАЖНО: ID изделия для уникальной идентификации
    itemlong: Optional[float] = None
    ug1: Optional[float] = None
    ug2: Optional[float] = None
    num: Optional[int] = None
    subnum: Optional[int] = None
    long_al: Optional[float] = None
    izdpart: Optional[str] = None
    partside: Optional[str] = None
    modelno: Optional[int] = None
    modelheight: Optional[int] = None
    modelwidth: Optional[int] = None
    flugelopentype: Optional[int] = None
    flugelcount: Optional[int] = None
    ishandle: Optional[int] = None
    handlepos: Optional[float] = None
    handleposfalts: Optional[float] = None
    flugelopentag: Optional[str] = None

# ========================================
# МОДЕЛИ ДЛЯ ФИБЕРГЛАССА
# ========================================

class FiberglassDetailRequest(BaseModel):
    """Запрос на получение деталей фибергласса"""
    grorder_mos_id: int

class FiberglassMaterialsRequest(BaseModel):
    """Запрос на получение материалов фибергласса со склада"""
    goodsids: List[int]

class FiberglassDetail(BaseModel):
    """Деталь фибергласса для раскроя"""
    grorder_mos_id: int
    orderid: int
    orderitemsid: int
    itemsdetailid: int
    item_name: str  # Название изделия (01, 02, 03...)
    width: float    # Ширина детали в мм
    height: float   # Высота детали в мм
    quantity: int   # Количество деталей
    modelno: Optional[int] = None
    partside: Optional[str] = None
    izdpart: Optional[str] = None
    goodsid: int    # ID материала
    marking: str    # Артикул материала
    orderno: str    # Номер заказа

class FiberglassSheet(BaseModel):
    """Лист/рулон фибергласса"""
    goodsid: int
    marking: str    # Артикул материала
    width: float    # Ширина рулона
    height: float   # Длина рулона 
    is_remainder: bool = False
    remainder_id: Optional[int] = None  # whremainderid для остатков
    quantity: int = 1
    area_mm2: Optional[float] = None  # Площадь для сортировки остатков

class FiberglassOptimizationSettings(BaseModel):
    """Настройки оптимизации фибергласса"""
    sheet_margin_top: float = 15.0
    sheet_margin_bottom: float = 15.0
    sheet_margin_left: float = 15.0
    sheet_margin_right: float = 15.0
    remainder_margin_top: float = 15.0
    remainder_margin_bottom: float = 15.0
    remainder_margin_left: float = 15.0
    remainder_margin_right: float = 15.0
    blade_width: float = 1.0
    max_waste_percent: float = 5.0
    min_remainder_width: float = 500.0
    min_remainder_height: float = 500.0
    use_simplified_optimization: bool = True

class FiberglassOptimizeRequest(BaseModel):
    """Запрос на оптимизацию фибергласса"""
    grorder_mos_id: int
    details: List[FiberglassDetail]
    sheets: List[FiberglassSheet]
    settings: FiberglassOptimizationSettings

class FiberglassLoadDataResponse(BaseModel):
    """Ответ с загруженными данными фибергласса"""
    details: List[FiberglassDetail]
    materials: List[FiberglassSheet]  # Цельные рулоны
    remainders: List[FiberglassSheet]  # Деловые остатки
    total_details: int
    total_materials: int
    total_remainders: int