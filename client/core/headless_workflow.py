"""Shared, GUI-independent workflow for MOS optimization.

This module owns the business flow which used to live in the PyQt window:
loading a MOS task, preparing stocks, running both optimizers, saving the
results, creating warehouse documents, and assigning cell numbers.  It has no
Qt or HTTP-client imports, so both the desktop client and batch runner can use
the same rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from .fiberglass_optimizer import optimize as optimize_fiberglass
from .models import Profile, Stock
from .optimizer import LinearOptimizer, OptimizationSettings


ProgressFn = Callable[[str], None]


class WorkflowError(RuntimeError):
    """Controlled workflow failure with a stage for the external orchestrator."""

    def __init__(self, message: str, stage: str = "workflow"):
        super().__init__(message)
        self.stage = stage


@dataclass
class WorkflowSettings:
    """All GUI parameters and post-optimization operations for one MOS run."""

    # Linear optimization: values match LinearOptimizerWindow defaults.
    blade_width: float = 5.0
    min_remainder_length: float = 300.0
    max_waste_percent: float = 15.0
    pair_optimization: bool = True
    use_remainders: bool = True
    time_limit_seconds: int = 60
    begin_indent: float = 10.0
    end_indent: float = 10.0
    min_trash_mm: float = 50.0
    pairing_exact_bonus: float = 3000.0
    pairing_partial_bonus: float = 1000.0
    pairing_partial_threshold: float = 0.7
    pairing_new_simple_bonus: float = 150.0

    # Fiberglass optimization: values match LinearOptimizerWindow defaults.
    planar_min_remainder_width: float = 500.0
    planar_min_remainder_height: float = 500.0
    planar_cut_width: float = 1.0
    sheet_indent: float = 15.0
    remainder_indent: float = 15.0
    planar_max_waste_percent: float = 5.0
    use_warehouse_remnants: bool = True
    allow_rotation: bool = True

    # Operations performed by the GUI after a successful calculation.
    save_result: bool = True
    adjust_materials: bool = True
    distribute_cells: bool = True

    # The runner must not silently issue an incomplete task.  The old GUI
    # calculated this statistic but only displayed it; the production runner
    # makes the explicit requirement configurable.
    require_complete_placement: bool = True
    require_fiberglass_success: bool = True

    def to_linear_settings(self) -> OptimizationSettings:
        return OptimizationSettings(
            blade_width=self.blade_width,
            min_remainder_length=self.min_remainder_length,
            max_waste_percent=self.max_waste_percent,
            pair_optimization=self.pair_optimization,
            use_remainders=self.use_remainders,
            time_limit_seconds=self.time_limit_seconds,
            begin_indent=self.begin_indent,
            end_indent=self.end_indent,
            min_trash_mm=self.min_trash_mm,
            pairing_exact_bonus=self.pairing_exact_bonus,
            pairing_partial_bonus=self.pairing_partial_bonus,
            pairing_partial_threshold=self.pairing_partial_threshold,
            pairing_new_simple_bonus=self.pairing_new_simple_bonus,
        )

    def to_fiberglass_params(self) -> Dict[str, Any]:
        return {
            "planar_min_remainder_width": self.planar_min_remainder_width,
            "planar_min_remainder_height": self.planar_min_remainder_height,
            "planar_cut_width": self.planar_cut_width,
            "sheet_indent": self.sheet_indent,
            "remainder_indent": self.remainder_indent,
            "planar_max_waste_percent": self.planar_max_waste_percent,
            "use_warehouse_remnants": self.use_warehouse_remnants,
            "allow_rotation": self.allow_rotation,
        }


@dataclass
class OptimizationInput:
    grorders_mos_id: int
    grorder_ids: List[int]
    profiles: List[Profile]
    stock_remainders: list
    stock_materials: list
    stocks: List[Stock]
    fabric_details: list
    fabric_remainders: list
    fabric_materials: list
    warnings: List[str] = field(default_factory=list)


@dataclass
class WorkflowRun:
    input_data: OptimizationInput
    linear_result: Any
    fiberglass_result: Optional[Any]
    cell_map: Dict[str, int]
    upload_response: Optional[dict] = None
    materials_response: Optional[dict] = None
    cells_response: Optional[dict] = None
    dry_run: bool = False


def _emit(progress: Optional[ProgressFn], message: str) -> None:
    if progress:
        progress(message)


def build_stocks(stock_remainders: Sequence[Any], stock_materials: Sequence[Any]) -> List[Stock]:
    """Create the same ``Stock`` objects as the former GUI table handler."""
    stocks: List[Stock] = []
    stock_id = 1

    # Every warehouse remainder is a physical bar and must be passed to the
    # optimizer as an individual object.  Full materials remain fungible.
    for remainder in stock_remainders:
        for instance_id in range(int(remainder.quantity_pieces)):
            stock = Stock(
                id=stock_id,
                profile_id=1,
                length=remainder.length,
                quantity=1,
                location="Остатки",
                is_remainder=True,
            )
            stock.profile_code = remainder.profile_code
            stock.warehouseremaindersid = getattr(remainder, "warehouseremaindersid", None)
            stock.groupgoods_thick = getattr(remainder, "groupgoods_thick", 6000)
            stock.instance_id = instance_id + 1
            stocks.append(stock)
            stock_id += 1

    for material in stock_materials:
        stock = Stock(
            id=stock_id,
            profile_id=1,
            length=material.length,
            quantity=material.quantity_pieces,
            location="Материалы",
            is_remainder=False,
        )
        stock.profile_code = material.profile_code
        stock.warehouseremaindersid = None
        stock.groupgoods_thick = getattr(material, "groupgoods_thick", 6000)
        stocks.append(stock)
        stock_id += 1
    return stocks


def load_optimization_input(
    api_client: Any,
    grorders_mos_id: int,
    progress: Optional[ProgressFn] = None,
) -> OptimizationInput:
    """Load exactly the input collections that the GUI loads for a MOS task."""
    try:
        _emit(progress, f"Получение СЗ для GRORDERS_MOS_ID={grorders_mos_id}")
        grorder_ids = list(api_client.get_grorders_by_mos_id(grorders_mos_id))
        if not grorder_ids:
            raise WorkflowError(
                f"Для GRORDERS_MOS_ID={grorders_mos_id} не найдены связанные сменные задания",
                "loading",
            )

        profiles: List[Profile] = []
        for grorder_id in grorder_ids:
            _emit(progress, f"Загрузка профилей СЗ {grorder_id}")
            profiles.extend(api_client.get_profiles(grorder_id))

        profile_codes = list({profile.profile_code for profile in profiles})
        _emit(progress, f"Загрузка складских остатков ({len(profile_codes)} артикулов)")
        stock_remainders = api_client.get_stock_remainders(profile_codes)
        _emit(progress, "Загрузка целых материалов")
        stock_materials = api_client.get_stock_materials(profile_codes)
        stocks = build_stocks(stock_remainders, stock_materials)

        warnings: List[str] = []
        fabric_details: list = []
        fabric_remainders: list = []
        fabric_materials: list = []
        try:
            _emit(progress, "Загрузка деталей фибергласса")
            fabric_details = api_client.get_fiberglass_details(grorders_mos_id)
        except Exception as error:
            # Original GUI continued with linear optimization and showed a
            # warning when this optional data source failed.
            warning = f"Не удалось загрузить детали фибергласса: {error}"
            warnings.append(warning)
            _emit(progress, f"ПРЕДУПРЕЖДЕНИЕ: {warning}")

        if fabric_details:
            goodsids = list({detail.goodsid for detail in fabric_details if detail.goodsid})
            try:
                fabric_remainders = api_client.get_fiberglass_remainders(goodsids)
            except Exception as error:
                warning = f"Не удалось загрузить остатки фибергласса: {error}"
                warnings.append(warning)
                _emit(progress, f"ПРЕДУПРЕЖДЕНИЕ: {warning}")
            try:
                fabric_materials = api_client.get_fiberglass_materials(goodsids)
            except Exception as error:
                warning = f"Не удалось загрузить целый фибергласс: {error}"
                warnings.append(warning)
                _emit(progress, f"ПРЕДУПРЕЖДЕНИЕ: {warning}")

        return OptimizationInput(
            grorders_mos_id=grorders_mos_id,
            grorder_ids=grorder_ids,
            profiles=profiles,
            stock_remainders=stock_remainders,
            stock_materials=stock_materials,
            stocks=stocks,
            fabric_details=fabric_details,
            fabric_remainders=fabric_remainders,
            fabric_materials=fabric_materials,
            warnings=warnings,
        )
    except WorkflowError:
        raise
    except Exception as error:
        raise WorkflowError(f"Не удалось загрузить входные данные: {error}", "loading") from error


def generate_cell_map(profiles: Sequence[Profile], fabric_details: Sequence[Any]) -> Dict[str, int]:
    """Generate the deterministic cell map used by the GUI."""
    unique_items = set()
    for item in [*profiles, *fabric_details]:
        orderitemsid = getattr(item, "orderitemsid", None)
        if orderitemsid is not None:
            unique_items.add((orderitemsid, getattr(item, "izdpart", "") or ""))
    return {
        f"{orderitemsid}_{izdpart}": number
        for number, (orderitemsid, izdpart) in enumerate(
            sorted(unique_items, key=lambda item: (item[0], item[1])), start=1
        )
    }


def optimize_linear(
    profiles: Sequence[Profile],
    stocks: Sequence[Stock],
    settings: OptimizationSettings,
    progress: Optional[Callable[[float], None]] = None,
) -> Any:
    """Run the untouched linear optimizer with the same input as the GUI."""
    return LinearOptimizer().optimize(
        profiles=list(profiles),
        stocks=list(stocks),
        settings=settings,
        progress_fn=progress,
    )


def optimize_fiberglass_for_input(
    input_data: OptimizationInput,
    settings: WorkflowSettings,
    cell_map: Dict[str, int],
    progress: Optional[Callable[[float], None]] = None,
) -> Optional[Any]:
    """Prepare fiberglass data exactly as the GUI did and run its optimizer."""
    if not input_data.fabric_details:
        return None

    return optimize_fiberglass_collections(
        input_data.fabric_details,
        input_data.fabric_remainders,
        input_data.fabric_materials,
        settings.to_fiberglass_params(),
        cell_map,
        progress,
    )


def optimize_fiberglass_collections(
    fabric_details: Sequence[Any],
    fabric_remainders: Sequence[Any],
    fabric_materials: Sequence[Any],
    params: Dict[str, Any],
    cell_map: Dict[str, int],
    progress: Optional[Callable[[float], None]] = None,
) -> Optional[Any]:
    """Adapt GUI/API fiberglass collections for the unchanged optimizer.

    The PyQt client and runner both call this adapter.  Its dictionaries are
    deliberately identical to those formerly assembled in the GUI method.
    """
    if not fabric_details:
        return None

    details = [
        {
            "orderitemsid": str(detail.orderitemsid),
            "width": detail.width,
            "height": detail.height,
            "g_marking": detail.marking,
            "total_qty": detail.quantity,
            "goodsid": detail.goodsid,
            "gp_marking": detail.marking,
            "oi_name": detail.item_name,
            "orderno": detail.orderno,
            "item_name": detail.item_name,
            "izdpart": detail.izdpart,
        }
        for detail in fabric_details
    ]
    materials = [
        {
            "id": str(material.goodsid),
            "width": material.width,
            "height": material.height,
            "g_marking": material.marking,
            "cost": 1500.0,
            "goodsid": material.goodsid,
            "quantity": material.quantity,
        }
        for material in fabric_materials
    ]
    remainders = [
        {
            "id": str(remainder.remainder_id if remainder.remainder_id else remainder.goodsid),
            "width": remainder.width,
            "height": remainder.height,
            "g_marking": remainder.marking,
            "cost": 800.0,
            "goodsid": remainder.goodsid,
            "quantity": remainder.quantity,
        }
        for remainder in fabric_remainders
    ]
    return optimize_fiberglass(
        details=details,
        materials=materials,
        remainders=remainders,
        params=params,
        progress_fn=progress,
        cell_map=cell_map,
    )


def collect_material_adjustments(
    optimization_result: Any,
    profiles: Sequence[Profile],
    fabric_optimization_result: Optional[Any],
) -> tuple[list, list, list, list]:
    """Build the four warehouse payloads formerly assembled by the GUI."""
    materials_by_size: Dict[tuple, Dict[str, Any]] = {}
    for plan in optimization_result.cut_plans:
        cuts = getattr(plan, "cuts", None) or []
        goodsid = cuts[0].get("profile_id") if cuts else None
        if not goodsid:
            continue
        key = (goodsid, getattr(plan, "stock_length", 0), bool(getattr(plan, "is_remainder", False)))
        materials_by_size.setdefault(
            key,
            {
                "goodsid": goodsid,
                "length": getattr(plan, "stock_length", 0),
                "quantity": 0,
                "is_remainder": bool(getattr(plan, "is_remainder", False)),
                "warehouseremaindersid": getattr(plan, "warehouseremaindersid", None),
            },
        )
        materials_by_size[key]["quantity"] += int(getattr(plan, "count", 1) or 1)

    used_materials: List[dict] = []
    for material in materials_by_size.values():
        profile_code = next((p.profile_code for p in profiles if p.id == material["goodsid"]), None)
        material["groupgoods_thick"] = next(
            (getattr(p, "groupgoods_thick", 6000) for p in profiles if p.profile_code == profile_code),
            6000,
        )
        used_materials.append(material)

    remainders_by_size: Dict[tuple, Dict[str, Any]] = {}
    for plan in optimization_result.cut_plans:
        remainder = getattr(plan, "remainder", None)
        cuts = getattr(plan, "cuts", None) or []
        goodsid = cuts[0].get("profile_id") if cuts else None
        if not remainder or remainder <= 0 or not goodsid:
            continue
        key = (goodsid, remainder)
        remainders_by_size.setdefault(key, {"goodsid": goodsid, "length": remainder, "quantity": 0})
        remainders_by_size[key]["quantity"] += int(getattr(plan, "count", 1) or 1)

    used_fiberglass_sheets: List[dict] = []
    new_fiberglass_remainders: List[dict] = []
    layouts = getattr(fabric_optimization_result, "layouts", None) if fabric_optimization_result else None
    for layout in layouts or []:
        sheet = layout.sheet
        used_fiberglass_sheets.append(
            {
                "goodsid": sheet.goodsid,
                "marking": sheet.marking,
                "width": sheet.width,
                "height": sheet.height,
                "is_remainder": sheet.is_remainder,
                "remainder_id": sheet.remainder_id,
                "quantity": 1,
            }
        )
        for item in layout.get_remnants():
            new_fiberglass_remainders.append(
                {
                    "goodsid": sheet.goodsid,
                    "marking": sheet.marking,
                    "width": item.width,
                    "height": item.height,
                    "quantity": 1,
                }
            )
    return used_materials, list(remainders_by_size.values()), used_fiberglass_sheets, new_fiberglass_remainders


class MosOptimizationWorkflow:
    """Run MOS optimization and the same post-processing as the GUI."""

    def __init__(self, api_client: Any, settings: WorkflowSettings):
        self.api_client = api_client
        self.settings = settings

    def run(
        self,
        grorders_mos_id: int,
        *,
        dry_run: bool = False,
        progress: Optional[ProgressFn] = None,
    ) -> WorkflowRun:
        input_data = load_optimization_input(self.api_client, grorders_mos_id, progress)
        for warning in input_data.warnings:
            _emit(progress, f"ПРЕДУПРЕЖДЕНИЕ: {warning}")

        _emit(progress, "Запуск линейной оптимизации")
        linear_settings = self.settings.to_linear_settings()
        stocks = input_data.stocks
        if not input_data.profiles:
            raise WorkflowError("Не найдены профили для оптимизации", "optimization")
        if not linear_settings.use_remainders:
            stocks = [stock for stock in stocks if not bool(getattr(stock, "is_remainder", False))]
        if not stocks:
            raise WorkflowError("После исключения остатков не осталось хлыстов", "optimization")
        try:
            linear_result = optimize_linear(
                input_data.profiles,
                stocks,
                linear_settings,
                progress=lambda percent: _emit(progress, f"Линейная оптимизация: {percent:.0f}%"),
            )
        except Exception as error:
            raise WorkflowError(f"Ошибка линейной оптимизации: {error}", "optimization") from error
        if not linear_result or not linear_result.success:
            raise WorkflowError(
                getattr(linear_result, "message", "Линейная оптимизация не дала результата"),
                "optimization",
            )
        unplaced = int(linear_result.statistics.get("total_pieces_unplaced", 0) or 0)
        if self.settings.require_complete_placement and unplaced:
            raise WorkflowError(
                f"Линейная оптимизация не разместила деталей: {unplaced}",
                "optimization",
            )

        cell_map = generate_cell_map(input_data.profiles, input_data.fabric_details)
        fiberglass_result: Optional[Any] = None
        if input_data.fabric_details:
            _emit(progress, "Запуск оптимизации фибергласса")
            try:
                fiberglass_result = optimize_fiberglass_for_input(
                    input_data,
                    self.settings,
                    cell_map,
                    progress=lambda percent: _emit(progress, f"Фибергласс: {percent:.1f}%"),
                )
            except Exception as error:
                raise WorkflowError(f"Ошибка оптимизации фибергласса: {error}", "optimization") from error
            if not fiberglass_result or not fiberglass_result.success:
                message = getattr(fiberglass_result, "message", "Оптимизация фибергласса не дала результата")
                if self.settings.require_fiberglass_success:
                    raise WorkflowError(message, "optimization")
                input_data.warnings.append(message)

        run = WorkflowRun(
            input_data=input_data,
            linear_result=linear_result,
            fiberglass_result=fiberglass_result,
            cell_map=cell_map,
            dry_run=dry_run,
        )
        if dry_run or not self.settings.save_result:
            _emit(progress, "Расчёт завершён без записи в базу")
            return run

        try:
            _emit(progress, "Запись карт раскроя")
            if not self.api_client.upload_mos_data(
                grorders_mos_id=grorders_mos_id,
                result=linear_result,
                profiles=input_data.profiles,
                blade_width_mm=int(self.settings.blade_width),
                min_remainder_mm=int(self.settings.min_remainder_length),
                begin_indent_mm=int(self.settings.begin_indent),
                end_indent_mm=int(self.settings.end_indent),
                min_trash_mm=int(self.settings.min_trash_mm),
            ):
                raise WorkflowError("API не подтвердил запись карт раскроя", "saving")
            run.upload_response = {"success": True}
        except WorkflowError:
            raise
        except Exception as error:
            raise WorkflowError(f"Не удалось записать карты раскроя: {error}", "saving") from error

        if self.settings.adjust_materials:
            try:
                _emit(progress, "Создание складских документов")
                payloads = collect_material_adjustments(
                    linear_result, input_data.profiles, fiberglass_result
                )
                run.materials_response = self.api_client.adjust_materials_altawin(
                    grorders_mos_id, *payloads
                )
                if not run.materials_response.get("success"):
                    raise WorkflowError(
                        f"Не удалось скорректировать материалы: {run.materials_response}",
                        "warehouse",
                    )
            except WorkflowError:
                raise
            except Exception as error:
                raise WorkflowError(f"Не удалось создать складские документы: {error}", "warehouse") from error

        if self.settings.distribute_cells and cell_map:
            try:
                _emit(progress, "Распределение номеров ячеек")
                run.cells_response = self.api_client.distribute_cell_numbers(
                    grorders_mos_id, cell_map=cell_map
                )
                if not run.cells_response.get("success"):
                    raise WorkflowError(
                        f"Не удалось распределить ячейки: {run.cells_response}",
                        "cells",
                    )
            except WorkflowError:
                raise
            except Exception as error:
                raise WorkflowError(f"Ошибка распределения ячеек: {error}", "cells") from error

        _emit(progress, "Workflow завершён")
        return run


def build_summary(run: WorkflowRun) -> Dict[str, Any]:
    """Return the stable machine-readable result expected by the orchestrator."""
    linear = run.linear_result
    stats = getattr(linear, "statistics", {}) or {}
    fiberglass = run.fiberglass_result
    warehouse = run.materials_response if isinstance(run.materials_response, dict) else {}
    return {
        "success": True,
        "stage": "completed",
        "grorders_mos_id": run.input_data.grorders_mos_id,
        "grorder_ids": run.input_data.grorder_ids,
        "dry_run": run.dry_run,
        "input": {
            "profiles": len(run.input_data.profiles),
            "profile_pieces": sum(profile.quantity for profile in run.input_data.profiles),
            "stocks": len(run.input_data.stocks),
            "stock_remainders": len(run.input_data.stock_remainders),
            "stock_materials": len(run.input_data.stock_materials),
            "fiberglass_details": len(run.input_data.fabric_details),
            "fiberglass_pieces": sum(
                detail.quantity for detail in run.input_data.fabric_details
            ),
        },
        "linear": {
            "plans": len(linear.cut_plans),
            "total_waste": linear.total_waste,
            "total_waste_percent": linear.total_waste_percent,
            "total_pieces_needed": stats.get("total_pieces_needed", 0),
            "total_pieces_placed": stats.get("total_pieces_placed", 0),
            "total_pieces_unplaced": stats.get("total_pieces_unplaced", 0),
            "statistics": stats,
        },
        "fiberglass": {
            "processed": fiberglass is not None,
            "success": getattr(fiberglass, "success", None),
            "layouts": len(getattr(fiberglass, "layouts", []) or []),
            "message": getattr(fiberglass, "message", ""),
        },
        "warnings": run.input_data.warnings,
        "upload": run.upload_response,
        "warehouse": run.materials_response,
        "documents": {
            "outlay_id": warehouse.get("outlay_id"),
            "supply_id": warehouse.get("supply_id"),
        },
        "cell_numbers": run.cells_response,
    }
