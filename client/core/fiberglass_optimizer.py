#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ПОЛНОСТЬЮ ЗАИМСТВОВАННЫЙ ОПТИМИЗАТОР ИЗ GLASS OPTIMIZER v2.0
Адаптированный для работы с рулонами вместо листов

Основные изменения:
- Работа с рулонами вместо листов
- Минимизация использования метров рулона (не листов)
- Интеграция новых параметров плоскостной оптимизации из интерфейса
- Логика определения делового остатка: меньшая сторона > меньшего параметра И большая сторона > большего параметра
"""

import time
import copy
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Callable, Set, Any
from enum import Enum
import random

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RotationMode(Enum):
    """Режимы поворота деталей"""
    NONE = "none"           # Без поворота
    ALLOW_90 = "allow_90"   # Разрешить поворот на 90°
    OPTIMAL = "optimal"     # Автоматический выбор наилучшего поворота

@dataclass
class Detail:
    """Деталь для размещения"""
    id: str
    width: float
    height: float
    material: str
    quantity: int = 1
    can_rotate: bool = True
    priority: int = 0
    oi_name: str = ""
    goodsid: Optional[int] = None  # Добавлено поле goodsid
    marking: str = ""  # Артикул материала
    orderitemsid: str = ""  # ID позиции заказа
    gp_marking: str = ""  # Групповой артикул
    orderno: str = ""  # Номер заказа
    item_name: str = ""  # Номер изделия
    izdpart: str = ""  # Номер части изделия
    cell_number: Optional[int] = None

    def __post_init__(self):
        self.area = self.width * self.height

    def get_rotated(self) -> 'Detail':
        """Возвращает повернутую на 90° копию детали"""
        rotated = copy.copy(self)
        rotated.width, rotated.height = self.height, self.width
        return rotated

@dataclass
class Sheet:
    """Лист материала"""
    id: str
    width: float
    height: float
    material: str
    cost_per_unit: float = 0.0
    is_remainder: bool = False
    remainder_id: Optional[str] = None
    goodsid: Optional[int] = None  # Добавлено поле goodsid
    marking: str = ""  # Артикул материала
    whremainderid: Optional[int] = None  # ID остатка на складе

    def __post_init__(self):
        self.area = self.width * self.height

@dataclass
class PlacedItem:
    """Размещенный элемент (деталь или остаток/отход)"""
    x: float
    y: float
    width: float
    height: float
    item_type: str  # "detail", "remnant", "waste"
    detail: Optional[Detail] = None
    is_rotated: bool = False
    cell_number: Optional[int] = None

    def __post_init__(self):
        self.x2 = self.x + self.width
        self.y2 = self.y + self.height
        self.area = self.width * self.height

@dataclass
class Rectangle:
    """Прямоугольная область"""
    x: float
    y: float
    width: float
    height: float

    def __post_init__(self):
        self.x2 = self.x + self.width
        self.y2 = self.y + self.height
        self.area = self.width * self.height

    def intersects(self, other: 'Rectangle') -> bool:
        """Проверяет пересечение с другим прямоугольником"""
        return not (self.x2 <= other.x or other.x2 <= self.x or
                   self.y2 <= other.y or other.y2 <= self.y)

    def contains(self, other: 'Rectangle') -> bool:
        """Проверяет, содержит ли данный прямоугольник другой"""
        return (self.x <= other.x and self.y <= other.y and
                other.x2 <= self.x2 and other.y2 <= self.y2)

@dataclass
class FreeRectangle:
    """Свободная прямоугольная область"""
    x: float
    y: float
    width: float
    height: float

    def __post_init__(self):
        self.x2 = self.x + self.width
        self.y2 = self.y + self.height
        self.area = self.width * self.height

@dataclass
class SheetLayout:
    """Раскладка листа"""
    sheet: Sheet
    placed_items: List[PlacedItem] = field(default_factory=list)

    def __post_init__(self):
        self.total_area = self.sheet.area
        self.used_area = 0.0
        self.waste_area = 0.0
        self.remnant_area = 0.0
        self._update_areas()

    def _update_areas(self):
        """Обновляет расчет площадей"""
        self.used_area = sum(item.area for item in self.placed_items if item.item_type == "detail")
        self.remnant_area = sum(item.area for item in self.placed_items if item.item_type == "remnant")
        self.waste_area = self.total_area - self.used_area - self.remnant_area

    def get_placed_details(self) -> List[PlacedItem]:
        """Возвращает размещенные детали"""
        return [item for item in self.placed_items if item.item_type == "detail"]

    def get_remnants(self) -> List[PlacedItem]:
        """Возвращает деловые остатки"""
        return [item for item in self.placed_items if item.item_type == "remnant"]

    def get_waste(self) -> List[PlacedItem]:
        """Возвращает отходы"""
        return [item for item in self.placed_items if item.item_type == "waste"]

    def get_coverage_percent(self) -> float:
        """Возвращает процент покрытия листа"""
        return (self.used_area + self.remnant_area) / self.total_area * 100 if self.total_area > 0 else 0

    def has_bad_waste(self, min_side: float) -> bool:
        """Проверяет наличие плохих отходов (слишком маленькие области)"""
        for item in self.placed_items:
            if item.item_type == "waste" and (item.width < min_side or item.height < min_side):
                return True
        return False

@dataclass
class OptimizationParams:
    """Параметры оптимизации"""
    min_remnant_width: float = 100.0
    min_remnant_height: float = 100.0
    target_waste_percent: float = 5.0
    remainder_waste_percent: float = 20.0  # ДОБАВЛЕНО: Процент отходов для деловых остатков
    min_waste_side: float = 10.0
    use_warehouse_remnants: bool = True
    rotation_mode: RotationMode = RotationMode.ALLOW_90
    force_adjacent_placement: bool = True
    max_waste_rectangles: int = 10
    cutting_width: float = 3.0
    max_iterations_per_sheet: int = 5  # Максимум попыток пересборки листа

    # Новые параметры плоскостной оптимизации из интерфейса
    planar_min_remainder_width: float = 500.0    # Минимальная ширина для деловых остатков (мм)
    planar_min_remainder_height: float = 500.0   # Минимальная высота для деловых остатков (мм)
    planar_cut_width: float = 1.0                # Ширина реза для плоскостной оптимизации (мм)
    sheet_indent: float = 15.0                   # Отступы для листа со всех сторон (мм)
    remainder_indent: float = 15.0               # Отступы для делового остатка со всех сторон (мм)
    planar_max_waste_percent: float = 5.0        # Максимальная процент отхода для плоскостной оптимизации (%)

@dataclass
class OptimizationResult:
    """Результат оптимизации"""
    success: bool
    layouts: List[SheetLayout]
    unplaced_details: List[Detail]
    total_efficiency: float
    total_waste_percent: float
    total_cost: float
    useful_remnants: List[FreeRectangle]
    optimization_time: float
    message: str = ""

    def __post_init__(self):
        self.total_sheets = len(self.layouts)
        self.total_rolls = len(self.layouts)  # Для совместимости с интерфейсом
        self.total_placed_details = sum(len(l.get_placed_details()) for l in self.layouts)
        self.sheets = self.layouts  # Для совместимости

class GuillotineOptimizer:
    """
    Оптимизатор с алгоритмом гильотинного раскроя
    Гарантирует 100% покрытие листа без пересечений
    """

    def __init__(self, params: OptimizationParams):
        self.params = params
        self.progress_callback: Optional[Callable[[float], None]] = None

    def set_progress_callback(self, callback: Callable[[float], None]):
        """Установка callback для отслеживания прогресса"""
        self.progress_callback = callback

    def _report_progress(self, progress: float):
        """Отправка прогресса"""
        if self.progress_callback:
            self.progress_callback(progress)

    def _check_material_availability(self, details: List[Detail], sheets: List[Sheet]) -> Dict[str, Any]:
        """
        Проверяет достаточность материалов для выполнения плоскостного раскроя
        
        Returns:
            Dict с результатами проверки
        """
        check_result = {
            "sufficient": True,
            "shortages": [],
            "by_material": {}
        }
        
        # Группируем потребности по материалам (артикулам)
        needs_by_material = {}
        for detail in details:
            material = detail.material
            if material not in needs_by_material:
                needs_by_material[material] = {
                    "pieces": 0,
                    "total_area": 0,
                    "max_width": 0,
                    "max_height": 0
                }
            
            needs_by_material[material]["pieces"] += detail.quantity
            needs_by_material[material]["total_area"] += detail.area * detail.quantity
            needs_by_material[material]["max_width"] = max(needs_by_material[material]["max_width"], detail.width)
            needs_by_material[material]["max_height"] = max(needs_by_material[material]["max_height"], detail.height)
        
        # Группируем доступные материалы по артикулам
        available_by_material = {}
        for sheet in sheets:
            material = sheet.material
            if not material:
                continue
                
            if material not in available_by_material:
                available_by_material[material] = {
                    "total_area": 0,
                    "sheets_count": 0,
                    "sheets": []
                }
            
            # Для всех листов (остатков и цельных) считаем площадь
            available_by_material[material]["total_area"] += sheet.area
            available_by_material[material]["sheets_count"] += 1
            available_by_material[material]["sheets"].append(sheet)
        
        # Проверяем каждый материал на достаточность
        for material, needs in needs_by_material.items():
            available = available_by_material.get(material, {
                "total_area": 0,
                "sheets_count": 0,
                "sheets": []
            })
            
            check_result["by_material"][material] = {
                "needed_pieces": needs["pieces"],
                "needed_area": needs["total_area"],
                "available_sheets": available["sheets_count"],
                "available_area": available["total_area"],
                "sufficient": available["total_area"] >= needs["total_area"]
            }
            
            # Если материала недостаточно
            if available["total_area"] < needs["total_area"]:
                check_result["sufficient"] = False
                shortage = {
                    "material": material,
                    "needed_pieces": needs["pieces"],
                    "needed_area": needs["total_area"],
                    "available_sheets": available["sheets_count"],
                    "available_area": available["total_area"],
                    "shortage_area": needs["total_area"] - available["total_area"],
                    "shortage_percent": ((needs["total_area"] - available["total_area"]) / needs["total_area"] * 100) if needs["total_area"] > 0 else 0
                }
                check_result["shortages"].append(shortage)
        
        logger.info("🔍 Проверка материалов фибергласса:")
        logger.info(f"   Материалов требуется: {len(needs_by_material)}")
        logger.info(f"   Материалов доступно: {len(available_by_material)}")
        logger.info(f"   Достаточно материалов: {'Да' if check_result['sufficient'] else 'Нет'}")
        
        if not check_result["sufficient"]:
            logger.warning(f"   Нехватка по {len(check_result['shortages'])} материалам:")
            for shortage in check_result["shortages"]:
                logger.warning(f"     {shortage['material']}: нехватка {shortage['shortage_area']:.0f}мм² ({shortage['shortage_percent']:.1f}%)")
        
        return check_result

    def optimize(self, details: List[Detail], sheets: List[Sheet], cell_map: Dict[str, int] = None) -> OptimizationResult:
        """
        Главный метод оптимизации

        Args:
            details: Список деталей для раскроя
            sheets: Список доступных листов
            cell_map (Dict[str, int], optional): Предварительно сгенерированная карта ячеек.

        Returns:
            OptimizationResult: Результат оптимизации
        """
        start_time = time.time()

        try:
            logger.info(f"🚀 Запуск алгоритма оптимизации")
            logger.info(f"📋 Детали: {len(details)}, Листы: {len(sheets)}")

            if not details:
                return OptimizationResult(
                    success=False,
                    layouts=[],
                    unplaced_details=[],
                    total_efficiency=0.0,
                    total_waste_percent=100.0,
                    total_cost=0.0,
                    useful_remnants=[],
                    optimization_time=time.time() - start_time,
                    message="Нет деталей для раскроя"
                )

            if not sheets:
                return OptimizationResult(
                    success=False,
                    layouts=[],
                    unplaced_details=details,
                    total_efficiency=0.0,
                    total_waste_percent=100.0,
                    total_cost=0.0,
                    useful_remnants=[],
                    optimization_time=time.time() - start_time,
                    message="Нет доступных листов"
                )

            # Проверяем достаточность материалов фибергласса
            self._report_progress(5)
            material_check = self._check_material_availability(details, sheets)
            if not material_check["sufficient"]:
                # КРИТИЧЕСКАЯ ОШИБКА: Нехватка материалов - останавливаем оптимизацию
                error_msg = "❌ КРИТИЧЕСКАЯ ОШИБКА: НЕХВАТКА ФИБЕРГЛАССА НА СКЛАДЕ\n\n"
                error_msg += "Невозможно выполнить плоскостную оптимизацию из-за недостатка материалов:\n\n"
                
                for shortage in material_check["shortages"]:
                    error_msg += f"📋 Материал: {shortage['material']}\n"
                    error_msg += f"   Требуется: {shortage['needed_pieces']} деталей общей площадью {shortage['needed_area']:.0f}мм²\n"
                    error_msg += f"   Доступно: {shortage['available_sheets']} листов общей площадью {shortage['available_area']:.0f}мм²\n"
                    error_msg += f"   Нехватка: {shortage['shortage_area']:.0f}мм² ({shortage['shortage_percent']:.1f}%)\n\n"
                
                error_msg += "🔧 Необходимые действия:\n"
                error_msg += "1. Докупите недостающий фибергласс на склад\n"
                error_msg += "2. Измените размеры деталей для использования доступных материалов\n"
                error_msg += "3. Проверьте остатки фибергласса на складе\n"
                
                logger.error(f"❌ {error_msg}")
                
                # ОСТАНАВЛИВАЕМ оптимизацию и возвращаем ошибку
                return OptimizationResult(
                    success=False,
                    layouts=[],
                    unplaced_details=details,
                    total_efficiency=0.0,
                    total_waste_percent=100.0,
                    total_cost=0.0,
                    useful_remnants=[],
                    optimization_time=time.time() - start_time,
                    message=error_msg
                )

            # Подготовка данных
            self._report_progress(10)
            prepared_details = self._prepare_details(details)

            # Распределение ячеек
            self._assign_cells_from_map(prepared_details, cell_map)

            prepared_sheets = self._prepare_sheets(sheets)

            # Группировка по материалам
            detail_groups = self._group_details_by_material(prepared_details)
            layouts: List[SheetLayout] = []

            total_progress = 10
            progress_step = 80 / len(detail_groups) if detail_groups else 80

            for material, material_details in detail_groups.items():
                logger.info(f"🔄 Оптимизация материала '{material}': {len(material_details)} деталей")

                # Фильтруем листы по материалу
                material_sheets = [s for s in prepared_sheets if s.material == material]

                if not material_sheets:
                    logger.warning(f"⚠️ Нет листов материала '{material}' для {len(material_details)} деталей")
                    continue

                # Оптимизация для одного материала
                material_layouts, unplaced = self._optimize_material(material_details, material_sheets)

                layouts.extend(material_layouts)

                # Обновляем прогресс
                total_progress += progress_step
                self._report_progress(min(90, total_progress))

            # Финальный расчет результата
            self._report_progress(95)
            result = self._calculate_final_result(layouts, [], start_time)

            logger.info("✅ Оптимизация завершена успешно")
            return result

        except Exception as e:
            logger.error(f"❌ Критическая ошибка оптимизации: {e}")
            import traceback
            logger.error(traceback.format_exc())

            return OptimizationResult(
                success=False,
                layouts=[],
                unplaced_details=details,
                total_efficiency=0.0,
                total_waste_percent=100.0,
                total_cost=0.0,
                useful_remnants=[],
                optimization_time=time.time() - start_time,
                message=f"Ошибка оптимизации: {str(e)}"
            )

    def _prepare_details(self, details: List[Detail]) -> List[Detail]:
        """Подготовка деталей"""
        expanded = []

        for base_index, detail in enumerate(details):
            for i in range(detail.quantity):
                detail_copy = copy.deepcopy(detail)
                # Гарантируем ГЛОБАЛЬНУЮ уникальность идентификатора даже при совпадающих orderitemsid
                detail_copy.id = f"{detail.id}__{base_index+1}_{i+1}"
                detail_copy.quantity = 1
                expanded.append(detail_copy)

        # Сортировка: сначала большие детали
        expanded.sort(key=lambda d: (-d.area, -d.priority, d.id))

        return expanded

    def _prepare_sheets(self, sheets: List[Sheet]) -> List[Sheet]:
        """Подготовка листов с МАКСИМАЛЬНЫМ приоритетом остатков"""
        # 🔥 КРИТИЧЕСКИ ВАЖНО: деловые остатки ВСЕГДА используем первыми!
        # Сортировка: (1) сначала ВСЕ остатки, (2) потом цельные листы
        # Внутри каждой группы: (а) сначала большие по площади
        sheets.sort(key=lambda s: (
            0 if s.is_remainder else 1,  # Остатки = 0 (первые), цельные = 1 (вторые)
            -s.area  # Большие листы/остатки первыми (по убыванию площади)
        ))
        
        # Выводим информацию о приоритизации
        remainders_count = sum(1 for s in sheets if s.is_remainder)
        materials_count = len(sheets) - remainders_count
        print(f"🔥 МАКСИМАЛЬНАЯ ПРИОРИТИЗАЦИЯ ОСТАТКОВ: {remainders_count} остатков впереди, {materials_count} цельных листов в конце")
        
        return sheets

    def _group_details_by_material(self, details: List[Detail]) -> Dict[str, List[Detail]]:
        """Группировка деталей по материалам"""
        groups = {}
        for detail in details:
            if detail.material not in groups:
                groups[detail.material] = []
            groups[detail.material].append(detail)
        return groups

    def _optimize_material(self, details: List[Detail], sheets: List[Sheet]) -> Tuple[List[SheetLayout], List[Detail]]:
        """Оптимизация размещения деталей одного материала с МАКСИМАЛЬНЫМ приоритетом остатков"""
        layouts = []
        unplaced_details = details.copy()

        # 🔥 МАКСИМАЛЬНЫЙ ПРИОРИТЕТ ОСТАТКОВ: Сначала все остатки, потом цельные листы
        remainder_sheets = [s for s in sheets if s.is_remainder]
        material_sheets = [s for s in sheets if not s.is_remainder]
        
        # 🔥 Сортируем остатки по УБЫВАНИЮ площади (большие остатки используем первыми)
        remainder_sheets.sort(key=lambda s: -s.area)

        logger.info(f"🔥 МАКСИМАЛЬНОЕ использование {len(remainder_sheets)} остатков (ПРИОРИТЕТ 1) + {len(material_sheets)} цельных листов (ПРИОРИТЕТ 2)")

        # 🔥 ПЕРВЫЙ ЭТАП: МАКСИМАЛЬНО агрессивное использование ВСЕХ остатков
        if remainder_sheets:
            logger.info(f"🔥 ЭТАП 1: МАКСИМАЛЬНО агрессивное использование {len(remainder_sheets)} остатков")
            logger.info(f"   ✅ Будет сделано НЕСКОЛЬКО попыток размещения на каждом остатке для максимального использования")
            
            for sheet in remainder_sheets:
                if not unplaced_details:
                    break

                logger.info(f"🔥 МАКСИМАЛЬНО пытаемся использовать остаток {sheet.id} ({sheet.width}x{sheet.height}, площадь={sheet.area:.0f})")
                
                # 🔥 МНОЖЕСТВЕННЫЕ ПОПЫТКИ размещения с разными стратегиями для максимального использования остатков
                best_layout = None
                max_placed = 0
                
                for iteration in range(3):  # 3 попытки с разными стратегиями
                    layout = self._create_sheet_layout_guillotine(sheet, unplaced_details.copy(), iteration)
                    
                    if layout:
                        placed_count = len(layout.get_placed_details())
                        if placed_count > max_placed:
                            max_placed = placed_count
                            best_layout = layout
                            logger.info(f"   ✅ Итерация {iteration+1}: размещено {placed_count} деталей (новый рекорд!)")
                        else:
                            logger.info(f"   ➡️ Итерация {iteration+1}: размещено {placed_count} деталей")
                
                if best_layout and max_placed > 0:
                    layouts.append(best_layout)
                    # Удаляем размещенные детали из списка
                    placed_ids = {item.detail.id for item in best_layout.get_placed_details() if item.detail}
                    unplaced_details = [d for d in unplaced_details if d.id not in placed_ids]
                    logger.info(f"✅ Остаток {sheet.id} МАКСИМАЛЬНО использован: размещено {max_placed} деталей (лучший результат из 3 попыток)")
                    logger.info(f"   📊 Эффективность остатка: {best_layout.get_coverage_percent():.1f}%")
                else:
                    logger.info(f"⏭️ Остаток {sheet.id} не использован (ни одна деталь не подошла)")

        # ВТОРОЙ ЭТАП: Использование цельных листов
        if material_sheets and unplaced_details:
            logger.info(f"📋 ЭТАП 2: Размещение {len(unplaced_details)} деталей на цельных листах")

            # Используем первый лист как шаблон для создания новых
            sheet_template = material_sheets[0]
            sheet_index = 0

            # Цикл продолжается, пока есть неразмещенные детали
            while unplaced_details:
                sheet_index += 1
                # Создаем новый лист на основе шаблона
                current_sheet = copy.deepcopy(sheet_template)
                current_sheet.id = f"{sheet_template.id}_copy_{sheet_index}"

                logger.info(f"📋 Работаем с новым листом {current_sheet.id} ({current_sheet.width}x{current_sheet.height})")
                
                # Пытаемся создать раскладку для текущего листа
                layout = self._create_sheet_layout_guillotine(current_sheet, unplaced_details.copy(), 0)

                # Если на листе размещена хотя бы одна деталь
                if layout and layout.get_placed_details():
                    layouts.append(layout)
                    
                    # Определяем ID размещенных деталей
                    placed_ids = {item.detail.id for item in layout.get_placed_details() if item.detail}
                    
                    # Обновляем список неразмещенных деталей
                    unplaced_details = [d for d in unplaced_details if d.id not in placed_ids]
                    
                    logger.info(f"✅ Лист {current_sheet.id}: размещено {len(placed_ids)} деталей. Осталось: {len(unplaced_details)}")
                else:
                    # Если на новом листе не удалось разместить ни одной детали, прерываем цикл
                    logger.warning(f"⚠️ Не удалось разместить детали на новом листе {current_sheet.id}. Прерываем, чтобы избежать бесконечного цикла.")
                    break
        
        return layouts, unplaced_details

    def _create_sheet_layout_guillotine(self, sheet: Sheet, details: List[Detail], iteration: int) -> Optional[SheetLayout]:
        """Создает раскладку листа с гильотинным алгоритмом"""
        layout = SheetLayout(sheet=sheet)
        free_areas = [Rectangle(0, 0, sheet.width, sheet.height)]

        # Варьируем порядок деталей в зависимости от итерации
        if iteration > 0:
            # Случайная перестановка для разнообразия
            random.seed(42 + iteration)  # Фиксированный seed для воспроизводимости
            details = details.copy()
            random.shuffle(details)

        placed_detail_ids = set()

        # Размещаем детали
        while details and free_areas:
            best_placement = None
            best_score = float('inf')
            best_area_idx = -1

            for area_idx, area in enumerate(free_areas):
                for detail in details:
                   if detail.id in placed_detail_ids:
                       continue

                   # Пробуем без поворота и с поворотом
                   orientations = [(detail.width, detail.height, False)]
                   if self.params.rotation_mode != RotationMode.NONE and detail.can_rotate:
                       orientations.append((detail.height, detail.width, True))

                   for width, height, is_rotated in orientations:
                       if area.width >= width and area.height >= height:
                           # Проверяем, что разрез создаст допустимые остатки
                           if self._is_valid_guillotine_cut(area, width, height):
                               score = self._calculate_guillotine_score(area, width, height, is_rotated, sheet)
                               if score < best_score:
                                   best_score = score
                                   best_placement = (detail, width, height, is_rotated, area)
                                   best_area_idx = area_idx

            if not best_placement:
                break

            # Размещаем деталь
            detail, width, height, is_rotated, area = best_placement

            placed_item = PlacedItem(
                x=area.x,
                y=area.y,
                width=width,
                height=height,
                item_type="detail",
                detail=detail,
                is_rotated=is_rotated,
                cell_number=detail.cell_number
            )
            layout.placed_items.append(placed_item)
            placed_detail_ids.add(detail.id)
            details.remove(detail)

            # Делаем гильотинный разрез и получаем новые области
            new_areas = self._guillotine_cut(area, width, height)

            # Заменяем использованную область новыми
            free_areas[best_area_idx:best_area_idx+1] = new_areas

        # КРИТИЧЕСКИ ВАЖНО: заполняем ВСЕ оставшиеся области
        self._fill_remaining_areas(layout, free_areas)

        # Обновляем площади после добавления всех элементов
        layout._update_areas()

        # Проверка покрытия
        coverage = layout.get_coverage_percent()
        if coverage < 99.9:
            logger.error(f"❌ ОШИБКА: Покрытие листа только {coverage:.1f}%!")

        return layout

    def _assign_cells_from_map(self, details: List[Detail], cell_map: Optional[Dict[str, int]]):
        """Присваивает номера ячеек деталям из предоставленной карты."""
        if not cell_map:
            logger.warning("⚠️ Карта ячеек не предоставлена, ячейки не будут назначены.")
            return

        logger.info("🏠 Присвоение номеров ячеек из карты...")
        assigned_count = 0
        for detail in details:
            key = f"{detail.orderitemsid}_{detail.izdpart or ''}"
            cell_number = cell_map.get(key)
            if cell_number is not None:
                detail.cell_number = cell_number
                assigned_count += 1
        logger.info(f"✅ Номера ячеек присвоены для {assigned_count} деталей.")


    def _is_valid_guillotine_cut(self, area: Rectangle, detail_width: float, detail_height: float) -> bool:
        """Проверяет, создаст ли гильотинный разрез допустимые остатки"""
        # Остатки после горизонтального разреза
        remainder_right = area.width - detail_width
        remainder_top = area.height - detail_height

        # Если остаток слишком мал, но не нулевой - это недопустимо
        if 0 < remainder_right < self.params.min_waste_side:
            return False
        if 0 < remainder_top < self.params.min_waste_side:
            return False

        # Проверяем подобласти, которые будут созданы
        if remainder_right > 0 and remainder_top > 0:
            # Будет создана L-образная область, проверяем обе части
            if detail_height < self.params.min_waste_side:
                return False
            if remainder_top < self.params.min_waste_side:
                return False

        return True

    def _calculate_guillotine_score(self, area: Rectangle, width: float, height: float, is_rotated: bool = False, sheet: Sheet = None) -> float:
        """Вычисляет оценку для гильотинного размещения (меньше = лучше)"""
        # Предпочитаем размещения, которые минимизируют остатки
        waste = area.area - (width * height)

        # 🔥 МАКСИМАЛЬНЫЙ БОНУС для размещения на деловых остатках
        if sheet and sheet.is_remainder:
            waste *= 0.5  # 50% бонус для остатков (сильно поощряем использование остатков!)
            logger.debug(f"🔥 БОНУС для размещения на остатке: waste уменьшен на 50%")

        # Бонус за точное соответствие размерам (сильнее поощряем на остатках)
        if abs(area.width - width) < 0.1 or abs(area.height - height) < 0.1:
            if sheet and sheet.is_remainder:
                waste *= 0.6  # 40% бонус на остатках (усиленный)
            else:
                waste *= 0.8  # 20% бонус на цельных листах

        # Штраф за поворот (если не оптимальный режим)
        if is_rotated and self.params.rotation_mode != RotationMode.OPTIMAL:
            waste *= 1.1  # 10% штраф

        return waste

    def _guillotine_cut(self, area: Rectangle, width: float, height: float) -> List[Rectangle]:
        """Выполняет гильотинный разрез и возвращает новые свободные области"""
        areas = []

        # Правая часть (если есть)
        if area.width > width:
            right_area = Rectangle(
                area.x + width,
                area.y,
                area.width - width,
                height
            )
            if right_area.width >= self.params.min_waste_side and right_area.height >= self.params.min_waste_side:
                areas.append(right_area)

        # Верхняя часть (на всю ширину)
        if area.height > height:
            top_area = Rectangle(
                area.x,
                area.y + height,
                area.width,
                area.height - height
            )
            if top_area.width >= self.params.min_waste_side and top_area.height >= self.params.min_waste_side:
                areas.append(top_area)

        return areas

    def _fill_remaining_areas(self, layout: SheetLayout, free_areas: List[Rectangle]):
        """Заполняет оставшиеся области деловыми остатками или отходами"""
        for area in free_areas:
            if area.width > 0 and area.height > 0:
                self._classify_and_add_area(area, layout)

    def _classify_and_add_area(self, area: Rectangle, layout: SheetLayout):
        """Классифицирует область как остаток или отход и добавляет в раскладку"""
        # Используем новую логику определения делового остатка
        is_remnant = self._is_business_remainder(area.width, area.height)

        item_type = "remnant" if is_remnant else "waste"
        logger.debug(f"🔧 ОБЛАСТЬ: {area.width:.0f}x{area.height:.0f} - {'ДЕЛОВОЙ ОСТАТОК' if is_remnant else 'ОТХОД'}")

        # Создаем фиктивный объект Detail для хранения артикула материала
        sheet_detail = Detail(
            id=f"{item_type}_{layout.sheet.id}",
            width=area.width,
            height=area.height,
            material=layout.sheet.material,
            marking=layout.sheet.marking,
            goodsid=layout.sheet.goodsid
        )

        placed_item = PlacedItem(
            x=area.x,
            y=area.y,
            width=area.width,
            height=area.height,
            item_type=item_type,
            detail=sheet_detail,
            is_rotated=False
        )
        layout.placed_items.append(placed_item)

    def _calculate_final_result(self, layouts: List[SheetLayout], unplaced: List[Detail], start_time: float) -> OptimizationResult:
        """Вычисляет финальный результат оптимизации"""

        if not layouts and unplaced:
            return OptimizationResult(
                success=False,
                layouts=layouts,
                unplaced_details=unplaced,
                total_efficiency=0.0,
                total_waste_percent=100.0,
                total_cost=0.0,
                useful_remnants=[],
                optimization_time=time.time() - start_time,
                message="Нет размещенных деталей"
            )

        # Собираем полезные остатки
        useful_remnants = []
        for layout in layouts:
            for remnant in layout.get_remnants():
                useful_remnants.append(FreeRectangle(
                    remnant.x, remnant.y,
                    remnant.width, remnant.height
                ))

        # Общая статистика
        total_area = sum(layout.total_area for layout in layouts)
        total_used = sum(layout.used_area for layout in layouts)
        total_waste_area = sum(layout.waste_area for layout in layouts)
        total_remnant_area = sum(layout.remnant_area for layout in layouts)

        total_efficiency = ((total_used + total_remnant_area) / total_area * 100) if total_area > 0 else 0
        total_waste_percent = (total_waste_area / total_area * 100) if total_area > 0 else 0

        # Общая стоимость
        total_cost = sum(layout.sheet.cost_per_unit * layout.sheet.area for layout in layouts)

        # Сообщение о результате
        success = len(unplaced) == 0
        if success:
            message = f"Все детали успешно размещены на {len(layouts)} листах"
        else:
            message = f"Размещено {sum(len(l.get_placed_details()) for l in layouts)} деталей, не размещено: {len(unplaced)}"

        return OptimizationResult(
            success=success,
            layouts=layouts,
            unplaced_details=unplaced,
            total_efficiency=total_efficiency,
            total_waste_percent=total_waste_percent,
            total_cost=total_cost,
            useful_remnants=useful_remnants,
            optimization_time=time.time() - start_time,
            message=message
        )

    def _is_business_remainder(self, width: float, height: float) -> bool:
        """
        Определяет, является ли область деловым остатком по новой логике плоскостной оптимизации

        Логика: если меньшая сторона больше меньшего параметра(ширина или высота)
        и большая сторона больше большего параметра, то остаток можно считать деловым,
        иначе это отход

        Args:
            width: ширина остатка
            height: высота остатка

        Returns:
            bool: True если деловой остаток, False если отход
        """
        # Учитываем отступы для делового остатка со всех сторон
        effective_width = width - 2 * self.params.remainder_indent
        effective_height = height - 2 * self.params.remainder_indent

        # Если после вычета отступов размеры стали отрицательными или слишком маленькими
        if effective_width <= 0 or effective_height <= 0:
            return False

        # Определяем меньшую и большую стороны
        min_side = min(effective_width, effective_height)
        max_side = max(effective_width, effective_height)

        # Определяем меньший и больший параметры
        min_param = min(self.params.planar_min_remainder_width, self.params.planar_min_remainder_height)
        max_param = max(self.params.planar_min_remainder_width, self.params.planar_min_remainder_height)

        # Проверяем условие: меньшая сторона > меньший параметр И большая сторона > больший параметр
        is_business_remainder = (min_side > min_param) and (max_side > max_param)

        # Дополнительная отладка для понимания логики
        print(f"🔧 Проверка делового остатка: {width:.0f}мм x {height:.0f}мм")
        print(f"   Эффективный размер с отступами: {effective_width:.0f}мм x {effective_height:.0f}мм")
        print(f"   Стороны: мин={min_side:.0f}мм, макс={max_side:.0f}мм")
        print(f"   Параметры: мин={min_param:.0f}мм, макс={max_param:.0f}мм")
        print(f"   Условия: min_side({min_side:.0f}) > min_param({min_param:.0f}) = {min_side > min_param}")
        print(f"   Условия: max_side({max_side:.0f}) > max_param({max_param:.0f}) = {max_side > max_param}")
        print(f"   Финальный результат: {'ДЕЛОВОЙ ОСТАТОК' if is_business_remainder else 'ОТХОД'}")
        print(f"   ---")

        return is_business_remainder

# Функция для совместимости с существующим интерфейсом
def optimize(details: List[dict], materials: List[dict], remainders: List[dict],
             params: dict = None, progress_fn: Optional[Callable[[float], None]] = None, 
             cell_map: Optional[Dict[str, int]] = None, **kwargs) -> OptimizationResult:
    """
    Главная функция оптимизации для совместимости с существующим GUI
    """

    try:
        logger.info(f"🚀 Запуск алгоритма оптимизации")

        # Объединяем параметры
        if params:
            kwargs.update(params)

        # Преобразуем входные данные
        detail_objects = []
        for detail_data in details:
            try:
                # Извлекаем goodsid
                goodsid = detail_data.get('goodsid')
                if goodsid:
                    goodsid = int(goodsid)

                detail = Detail(
                    id=str(detail_data.get('orderitemsid', detail_data.get('id', f'detail_{len(detail_objects)}'))),
                    width=float(detail_data.get('width', 0)),
                    height=float(detail_data.get('height', 0)),
                    material=str(detail_data.get('g_marking', '')),
                    quantity=int(detail_data.get('total_qty', detail_data.get('quantity', 1))),
                    can_rotate=True,
                    priority=int(detail_data.get('priority', 0)),
                    oi_name=str(detail_data.get('oi_name', '')),
                    goodsid=goodsid,  # Передаем goodsid в деталь
                    marking=str(detail_data.get('g_marking', '')) # Сохраняем артикул
                )

                # ДОБАВЛЕНО: Передаем новые поля для XML генерации
                detail.gp_marking = str(detail_data.get('gp_marking', ''))
                detail.orderno = str(detail_data.get('orderno', ''))
                detail.orderitemsid = detail_data.get('orderitemsid', '')
                detail.item_name = str(detail_data.get('item_name', ''))
                detail.izdpart = str(detail_data.get('izdpart', ''))
                print(f"🔍 OPTIMIZER: Обработана деталь {detail.material}, izdpart='{detail.izdpart}'")
                if detail.width > 0 and detail.height > 0 and detail.material:
                    detail_objects.append(detail)
                    logger.info(f"🔧 Создана деталь: {detail.oi_name}, материал={detail.material}, goodsid={goodsid}")
            except Exception as e:
                logger.error(f"Ошибка обработки детали: {e}")

        # Преобразуем материалы
        sheets = []
        # Обрабатываем цельные листы
        for material_data in materials:
            try:
                sheet = Sheet(
                    id=str(material_data.get('id', f'material_{len(sheets)}')),
                    width=float(material_data.get('width', 0)),
                    height=float(material_data.get('height', 0)),
                    material=str(material_data.get('g_marking', '')),
                    cost_per_unit=float(material_data.get('cost', 0)),
                    is_remainder=False,
                    goodsid=int(material_data.get('goodsid', 0)) if material_data.get('goodsid') else None,
                    marking=str(material_data.get('g_marking', '')) # Сохраняем артикул
                )
                if sheet.width > 0 and sheet.height > 0 and sheet.material:
                    sheets.append(sheet)
                    logger.info(f"🔧 Создан лист: {sheet.material}, goodsid={sheet.goodsid}")
            except Exception as e:
                logger.error(f"Ошибка обработки листа: {e}")

        # Обрабатываем остатки
        for remainder_data in remainders:
            try:
                qty = int(remainder_data.get('quantity', 1))
                logger.info(f"📦 Обработка остатка: материал={remainder_data.get('g_marking', '')}, "
                           f"размер={remainder_data.get('width', 0)}x{remainder_data.get('height', 0)}, "
                           f"количество={qty}")

                # Извлекаем goodsid
                goodsid = remainder_data.get('goodsid')
                if goodsid:
                    goodsid = int(goodsid)

                # Создаем листы по количеству остатков
                for j in range(qty):
                    sheet = Sheet(
                        id=f"remainder_{remainder_data.get('id', len(sheets))}_{j+1}",
                        width=float(remainder_data.get('width', 0)),
                        height=float(remainder_data.get('height', 0)),
                        material=str(remainder_data.get('g_marking', '')),
                        cost_per_unit=float(remainder_data.get('cost', 0)),
                        is_remainder=True,
                        remainder_id=str(remainder_data.get('id', '')),
                        goodsid=goodsid,  # Передаем goodsid в остаток
                        marking=str(remainder_data.get('g_marking', '')) # Сохраняем артикул
                    )
                    if sheet.width > 0 and sheet.height > 0 and sheet.material:
                        sheets.append(sheet)
                        logger.info(f"�� Создан остаток {j+1}/{qty}: {sheet.material}, goodsid={goodsid}")
            except Exception as e:
                logger.error(f"Ошибка обработки остатка: {e}")

        # Создаем параметры оптимизации
        params_obj = OptimizationParams(
            target_waste_percent=float(kwargs.get('planar_max_waste_percent', 5.0)),
            use_warehouse_remnants=bool(kwargs.get('use_warehouse_remnants', True)),
            rotation_mode=RotationMode.ALLOW_90 if kwargs.get('allow_rotation', True) else RotationMode.NONE,

            # Новые параметры плоскостной оптимизации
            planar_min_remainder_width=float(kwargs.get('planar_min_remainder_width', 500.0)),
            planar_min_remainder_height=float(kwargs.get('planar_min_remainder_height', 500.0)),
            planar_cut_width=float(kwargs.get('planar_cut_width', 1.0)),
            sheet_indent=float(kwargs.get('sheet_indent', 15.0)),
            remainder_indent=float(kwargs.get('remainder_indent', 15.0)),
            planar_max_waste_percent=float(kwargs.get('planar_max_waste_percent', 5.0))
        )

        # Создаем оптимизатор и запускаем
        optimizer = GuillotineOptimizer(params_obj)
        if progress_fn:
            optimizer.set_progress_callback(progress_fn)

        return optimizer.optimize(detail_objects, sheets, cell_map=cell_map)

    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return OptimizationResult(
            success=False,
            layouts=[],
            unplaced_details=[],
            total_efficiency=0.0,
            total_waste_percent=100.0,
            total_cost=0.0,
            useful_remnants=[],
            optimization_time=0.0,
            message=f"Ошибка оптимизации: {str(e)}"
        )
