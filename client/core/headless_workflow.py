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
    linear_result: Optional[Any]
    fiberglass_result: Optional[Any]
    cell_map: Dict[str, int]
    upload_response: Optional[dict] = None
    materials_response: Optional[dict] = None
    cells_response: Optional[dict] = None
    dry_run: bool = False
    mode: str = "fresh"
    initial_state: Optional[dict] = None
    final_state: Optional[dict] = None
    skipped_steps: List[str] = field(default_factory=list)


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


def load_cell_map_input(
    api_client: Any,
    grorders_mos_id: int,
    progress: Optional[ProgressFn] = None,
) -> OptimizationInput:
    """Load only the immutable order data needed by ``generate_cell_map``."""
    try:
        _emit(progress, f"RESUME: получение СЗ для GRORDERS_MOS_ID={grorders_mos_id}")
        grorder_ids = list(api_client.get_grorders_by_mos_id(grorders_mos_id))
        if not grorder_ids:
            raise WorkflowError(
                f"Для GRORDERS_MOS_ID={grorders_mos_id} не найдены связанные сменные задания",
                "loading",
            )

        profiles: List[Profile] = []
        for grorder_id in grorder_ids:
            profiles.extend(api_client.get_profiles(grorder_id))

        warnings: List[str] = []
        fabric_details: list = []
        try:
            fabric_details = api_client.get_fiberglass_details(grorders_mos_id)
        except Exception as error:
            warning = f"Не удалось загрузить детали фибергласса для карты ячеек: {error}"
            warnings.append(warning)
            _emit(progress, f"ПРЕДУПРЕЖДЕНИЕ: {warning}")

        return OptimizationInput(
            grorders_mos_id=grorders_mos_id,
            grorder_ids=grorder_ids,
            profiles=profiles,
            stock_remainders=[],
            stock_materials=[],
            stocks=[],
            fabric_details=fabric_details,
            fabric_remainders=[],
            fabric_materials=[],
            warnings=warnings,
        )
    except WorkflowError:
        raise
    except Exception as error:
        raise WorkflowError(
            f"Не удалось загрузить входные данные для возобновления: {error}",
            "loading",
        ) from error


def empty_optimization_input(grorders_mos_id: int) -> OptimizationInput:
    """Represent a no-op run without loading optimizer inputs."""
    return OptimizationInput(
        grorders_mos_id=grorders_mos_id,
        grorder_ids=[],
        profiles=[],
        stock_remainders=[],
        stock_materials=[],
        stocks=[],
        fabric_details=[],
        fabric_remainders=[],
        fabric_materials=[],
    )


def active_documents(state: dict, document_type: str) -> List[dict]:
    collection = "outlays" if document_type == "outlay" else "supplies"
    return [
        document
        for document in state.get(collection, [])
        if int(document.get("deleted", 0) or 0) == 0
    ]


def document_id(document: dict, document_type: str) -> Optional[int]:
    value = document.get("outlay_id" if document_type == "outlay" else "supply_id")
    return int(value) if value is not None else None


def classify_job_state(state: dict) -> tuple[str, List[str]]:
    """Classify persisted state before any destructive or reserving operation."""
    optimized_count = int(state.get("optimized_count", 0) or 0)
    detail_count = int(state.get("detail_count", 0) or 0)
    missing_cell_count = int(state.get("missing_cell_count", 0) or 0)
    outlays = active_documents(state, "outlay")
    supplies = active_documents(state, "supply")
    issues: List[str] = []

    if len(outlays) > 1:
        issues.append(
            "найдено несколько активных расходов: "
            + ", ".join(str(document_id(item, "outlay")) for item in outlays)
        )
    if len(supplies) > 1:
        issues.append(
            "найдено несколько активных приходов: "
            + ", ".join(str(document_id(item, "supply")) for item in supplies)
        )
    if bool(outlays) != bool(supplies):
        issues.append(
            "неполная складская пара: "
            f"OUTLAYID={[document_id(item, 'outlay') for item in outlays]}, "
            f"SUPPLYID={[document_id(item, 'supply') for item in supplies]}"
        )

    if outlays or supplies:
        if optimized_count <= 0 or detail_count <= 0:
            issues.append(
                "складские документы существуют, но карты/детали отсутствуют: "
                f"maps={optimized_count}, details={detail_count}"
            )
        if state.get("warehouse_content_matches") is not True:
            mismatches = state.get("content_mismatches") or []
            suffix = f": {'; '.join(map(str, mismatches))}" if mismatches else ""
            issues.append(f"содержимое складских документов не соответствует заданию{suffix}")

    if issues:
        return "inconsistent", issues
    if not outlays and not supplies:
        return "fresh", []

    outlay_approved = int(outlays[0].get("isapproved", 0) or 0) == 1
    supply_approved = int(supplies[0].get("isapproved", 0) or 0) == 1
    if missing_cell_count == 0 and outlay_approved and supply_approved:
        return "noop", []
    return "resume", []


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

    def _get_state(
        self,
        grorders_mos_id: int,
        *,
        stage: str = "warehouse/resume",
    ) -> dict:
        try:
            state = self.api_client.get_mos_job_state(grorders_mos_id)
            if not isinstance(state, dict):
                raise TypeError(f"ожидался объект, получено {type(state).__name__}")
            return state
        except WorkflowError:
            raise
        except Exception as error:
            raise WorkflowError(
                f"Не удалось получить состояние GRORDERS_MOS_ID={grorders_mos_id}: {error}",
                stage,
            ) from error

    def _emit_state(
        self,
        state: dict,
        mode: str,
        progress: Optional[ProgressFn],
    ) -> None:
        outlay_ids = [
            document_id(item, "outlay") for item in active_documents(state, "outlay")
        ]
        supply_ids = [
            document_id(item, "supply") for item in active_documents(state, "supply")
        ]
        _emit(
            progress,
            "mode=%s maps=%s details=%s missing_cells=%s OUTLAYID=%s SUPPLYID=%s"
            % (
                mode,
                int(state.get("optimized_count", 0) or 0),
                int(state.get("detail_count", 0) or 0),
                int(state.get("missing_cell_count", 0) or 0),
                outlay_ids,
                supply_ids,
            ),
        )

    def _warehouse_response_from_state(self, state: dict) -> dict:
        outlays = active_documents(state, "outlay")
        supplies = active_documents(state, "supply")
        return {
            "success": len(outlays) == 1 and len(supplies) == 1,
            "outlay_id": document_id(outlays[0], "outlay") if len(outlays) == 1 else None,
            "supply_id": document_id(supplies[0], "supply") if len(supplies) == 1 else None,
            "reused": True,
        }

    def _require_consistent_state(
        self,
        state: dict,
        progress: Optional[ProgressFn],
    ) -> str:
        mode, issues = classify_job_state(state)
        self._emit_state(state, mode, progress)
        if mode == "inconsistent":
            outlay_ids = [
                document_id(item, "outlay") for item in active_documents(state, "outlay")
            ]
            supply_ids = [
                document_id(item, "supply") for item in active_documents(state, "supply")
            ]
            raise WorkflowError(
                "INCONSISTENT: "
                + "; ".join(issues)
                + f"; проблемные OUTLAYID={outlay_ids}, SUPPLYID={supply_ids}",
                "warehouse/resume",
            )
        return mode

    def _approve_document(
        self,
        grorders_mos_id: int,
        document_type: str,
        document: dict,
        progress: Optional[ProgressFn],
    ) -> None:
        document_id_value = document_id(document, document_type)
        if int(document.get("isapproved", 0) or 0) == 1:
            _emit(
                progress,
                f"skip=approve_{document_type} id={document_id_value} reason=already_approved",
            )
            return
        try:
            _emit(progress, f"Проводка {document_type} ID={document_id_value}")
            result = self.api_client.approve_mos_document(
                grorders_mos_id,
                document_type,
                document_id_value,
            )
            if not isinstance(result, dict) or not result.get("success"):
                raise RuntimeError(result)
        except Exception as error:
            # The update may have committed even when the HTTP response was
            # lost. Re-read the header before deciding whether it failed.
            recovered = self._get_state(grorders_mos_id)
            documents = active_documents(recovered, document_type)
            matching = [
                item
                for item in documents
                if document_id(item, document_type) == document_id_value
            ]
            if matching and int(matching[0].get("isapproved", 0) or 0) == 1:
                _emit(
                    progress,
                    f"recovered=approve_{document_type} id={document_id_value} after_error={error}",
                )
                return
            raise WorkflowError(
                f"Ошибка проводки {document_type} ID={document_id_value}: {error}",
                "warehouse/resume",
            ) from error

    def _complete_existing_pair(
        self,
        grorders_mos_id: int,
        state: dict,
        progress: Optional[ProgressFn],
        *,
        mode: str,
        input_data: Optional[OptimizationInput] = None,
        cell_map: Optional[Dict[str, int]] = None,
        linear_result: Optional[Any] = None,
        fiberglass_result: Optional[Any] = None,
        upload_response: Optional[dict] = None,
        materials_response: Optional[dict] = None,
        initial_state: Optional[dict] = None,
    ) -> WorkflowRun:
        """Finish cells and approvals without recalculation or warehouse INSERT."""
        current_state = state
        current_input = input_data
        current_cell_map = cell_map or {}
        skipped_steps: List[str] = []
        if mode == "resume":
            skipped_steps.extend(["upload_mos_data", "adjust_materials_altawin"])
            _emit(progress, "skip=upload_mos_data reason=existing_warehouse_pair")
            _emit(
                progress,
                "skip=adjust_materials_altawin reason=existing_warehouse_pair",
            )

        if int(current_state.get("missing_cell_count", 0) or 0) > 0:
            if not self.settings.distribute_cells:
                raise WorkflowError(
                    "Нельзя завершить RESUME: CELL_NUMBER не заполнены, "
                    "а distribute_cells отключён",
                    "warehouse/resume",
                )
            if current_input is None:
                current_input = load_cell_map_input(
                    self.api_client, grorders_mos_id, progress
                )
            if not current_cell_map:
                current_cell_map = generate_cell_map(
                    current_input.profiles,
                    current_input.fabric_details,
                )
            if not current_cell_map:
                raise WorkflowError(
                    "Не удалось построить детерминированную карту CELL_NUMBER",
                    "warehouse/resume",
                )
            try:
                _emit(progress, "RESUME: распределение отсутствующих CELL_NUMBER")
                cells_response = self.api_client.distribute_cell_numbers(
                    grorders_mos_id,
                    cell_map=current_cell_map,
                )
                if not cells_response.get("success"):
                    raise RuntimeError(cells_response)
            except Exception as error:
                recovered = self._get_state(grorders_mos_id)
                if int(recovered.get("missing_cell_count", 0) or 0) != 0:
                    raise WorkflowError(
                        f"Ошибка распределения CELL_NUMBER при RESUME: {error}",
                        "warehouse/resume",
                    ) from error
                _emit(progress, f"recovered=distribute_cell_numbers after_error={error}")
                cells_response = {
                    "success": True,
                    "recovered_after_transport_error": True,
                }
            current_state = self._get_state(grorders_mos_id)
        else:
            skipped_steps.append("distribute_cell_numbers")
            _emit(
                progress,
                "skip=distribute_cell_numbers reason=all_cells_already_assigned",
            )
            cells_response = {"success": True, "skipped": True}

        consistent_mode = self._require_consistent_state(current_state, progress)
        if consistent_mode not in {"resume", "noop"}:
            raise WorkflowError(
                f"Складская пара исчезла во время RESUME: mode={consistent_mode}",
                "warehouse/resume",
            )
        remaining_cells = int(current_state.get("missing_cell_count", 0) or 0)
        if remaining_cells:
            raise WorkflowError(
                "RESUME не заполнил все CELL_NUMBER; "
                f"осталось деталей без ячейки: {remaining_cells}",
                "warehouse/resume",
            )
        outlay = active_documents(current_state, "outlay")[0]
        supply = active_documents(current_state, "supply")[0]
        self._approve_document(grorders_mos_id, "outlay", outlay, progress)
        current_state = self._get_state(grorders_mos_id)
        supply_matches = [
            item
            for item in active_documents(current_state, "supply")
            if document_id(item, "supply") == document_id(supply, "supply")
        ]
        if not supply_matches:
            raise WorkflowError(
                f"SUPPLYID={document_id(supply, 'supply')} исчез во время RESUME",
                "warehouse/resume",
            )
        self._approve_document(
            grorders_mos_id,
            "supply",
            supply_matches[0],
            progress,
        )

        final_state = self._get_state(grorders_mos_id)
        final_mode = self._require_consistent_state(final_state, progress)
        if final_mode != "noop":
            raise WorkflowError(
                "Итоговая проверка не подтверждает COMPLETED: "
                f"mode={final_mode}, missing_cells={final_state.get('missing_cell_count')}",
                "warehouse/resume",
            )
        if current_input is None:
            current_input = empty_optimization_input(grorders_mos_id)
        response = materials_response or self._warehouse_response_from_state(final_state)
        response.setdefault("reused", mode == "resume")
        return WorkflowRun(
            input_data=current_input,
            linear_result=linear_result,
            fiberglass_result=fiberglass_result,
            cell_map=current_cell_map,
            upload_response=upload_response
            or {"success": True, "skipped": mode == "resume"},
            materials_response=response,
            cells_response=cells_response,
            mode=mode,
            initial_state=initial_state or state,
            final_state=final_state,
            skipped_steps=skipped_steps,
        )

    def run(
        self,
        grorders_mos_id: int,
        *,
        dry_run: bool = False,
        progress: Optional[ProgressFn] = None,
    ) -> WorkflowRun:
        initial_state = self._get_state(
            grorders_mos_id,
            stage="loading",
        )
        initial_mode = self._require_consistent_state(initial_state, progress)
        if not dry_run and self.settings.save_result:
            if initial_mode == "noop":
                _emit(progress, "mode=noop: задание уже полностью завершено")
                warehouse = self._warehouse_response_from_state(initial_state)
                noop_skips = [
                    "optimization",
                    "upload_mos_data",
                    "adjust_materials_altawin",
                    "distribute_cell_numbers",
                    "approve_outlay",
                    "approve_supply",
                ]
                for step in noop_skips:
                    _emit(progress, f"skip={step} reason=already_completed")
                return WorkflowRun(
                    input_data=empty_optimization_input(grorders_mos_id),
                    linear_result=None,
                    fiberglass_result=None,
                    cell_map={},
                    upload_response={"success": True, "skipped": True},
                    materials_response=warehouse,
                    cells_response={"success": True, "skipped": True},
                    mode="noop",
                    initial_state=initial_state,
                    final_state=initial_state,
                    skipped_steps=noop_skips,
                )
            if initial_mode == "resume":
                return self._complete_existing_pair(
                    grorders_mos_id,
                    initial_state,
                    progress,
                    mode="resume",
                    initial_state=initial_state,
                )

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
            mode="fresh",
            initial_state=initial_state,
        )
        if dry_run or not self.settings.save_result:
            _emit(progress, "Расчёт завершён без записи в базу")
            return run

        try:
            _emit(progress, "step=upload_mos_data action=write_cut_maps")
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
            recovered = self._get_state(grorders_mos_id)
            expected_maps = sum(
                1 for plan in linear_result.cut_plans if getattr(plan, "cuts", None)
            )
            expected_details = sum(
                1
                for plan in linear_result.cut_plans
                for cut in (getattr(plan, "cuts", None) or [])
                if int(cut.get("quantity", 0) or 0) > 0
                and float(cut.get("length", 0) or 0) > 0
            )
            if (
                int(recovered.get("optimized_count", 0) or 0) == expected_maps
                and int(recovered.get("detail_count", 0) or 0) == expected_details
            ):
                _emit(progress, f"recovered=upload_mos_data after_error={error}")
                run.upload_response = {
                    "success": True,
                    "recovered_after_transport_error": True,
                }
            else:
                raise WorkflowError(
                    "Неопределённый результат upload_mos_data; повторная запись запрещена: "
                    f"expected_maps={expected_maps}, actual_maps={recovered.get('optimized_count')}, "
                    f"expected_details={expected_details}, actual_details={recovered.get('detail_count')}, "
                    f"error={error}",
                    "saving",
                ) from error

        persisted_state = self._get_state(grorders_mos_id)
        expected_maps = sum(
            1 for plan in linear_result.cut_plans if getattr(plan, "cuts", None)
        )
        expected_details = sum(
            1
            for plan in linear_result.cut_plans
            for cut in (getattr(plan, "cuts", None) or [])
            if int(cut.get("quantity", 0) or 0) > 0
            and float(cut.get("length", 0) or 0) > 0
        )
        if (
            int(persisted_state.get("optimized_count", 0) or 0) != expected_maps
            or int(persisted_state.get("detail_count", 0) or 0) != expected_details
        ):
            raise WorkflowError(
                "Проверка записи карт не пройдена: "
                f"expected_maps={expected_maps}, actual_maps={persisted_state.get('optimized_count')}, "
                f"expected_details={expected_details}, actual_details={persisted_state.get('detail_count')}",
                "saving",
            )

        if self.settings.adjust_materials:
            try:
                _emit(
                    progress,
                    "step=adjust_materials_altawin action=create_or_reuse_pair",
                )
                payloads = collect_material_adjustments(
                    linear_result, input_data.profiles, fiberglass_result
                )
                run.materials_response = self.api_client.adjust_materials_altawin(
                    grorders_mos_id, *payloads
                )
                if not run.materials_response.get("success"):
                    raise WorkflowError(
                        f"Не удалось скорректировать материалы: {run.materials_response}",
                        "warehouse/resume",
                    )
            except WorkflowError:
                raise
            except Exception as error:
                recovered = self._get_state(grorders_mos_id)
                recovered_mode = self._require_consistent_state(recovered, progress)
                if recovered_mode not in {"resume", "noop"}:
                    raise WorkflowError(
                        "Неопределённый результат adjust_materials_altawin; "
                        "повторный INSERT запрещён: "
                        f"mode={recovered_mode}, error={error}",
                        "warehouse/resume",
                    ) from error
                _emit(
                    progress,
                    f"recovered=adjust_materials_altawin mode={recovered_mode} after_error={error}",
                )
                run.materials_response = self._warehouse_response_from_state(recovered)

            warehouse_state = self._get_state(grorders_mos_id)
            warehouse_mode = self._require_consistent_state(warehouse_state, progress)
            if warehouse_mode not in {"resume", "noop"}:
                raise WorkflowError(
                    "API не создал распознаваемую складскую пару: "
                    f"mode={warehouse_mode}, response={run.materials_response}",
                    "warehouse/resume",
                )
            return self._complete_existing_pair(
                grorders_mos_id,
                warehouse_state,
                progress,
                mode="fresh",
                input_data=input_data,
                cell_map=cell_map,
                linear_result=linear_result,
                fiberglass_result=fiberglass_result,
                upload_response=run.upload_response,
                materials_response=run.materials_response,
                initial_state=initial_state,
            )

        # This legacy opt-out deliberately does not create or approve documents.
        if self.settings.distribute_cells and cell_map:
            _emit(progress, "Распределение номеров ячеек")
            run.cells_response = self.api_client.distribute_cell_numbers(
                grorders_mos_id, cell_map=cell_map
            )
            if not run.cells_response.get("success"):
                raise WorkflowError(
                    f"Не удалось распределить ячейки: {run.cells_response}",
                    "cells",
                )
        run.final_state = self._get_state(grorders_mos_id)
        _emit(progress, "Workflow завершён без складских документов по настройке")
        return run


def build_summary(run: WorkflowRun) -> Dict[str, Any]:
    """Return the stable machine-readable result expected by the orchestrator."""
    linear = run.linear_result
    stats = getattr(linear, "statistics", {}) or {}
    fiberglass = run.fiberglass_result
    warehouse = run.materials_response if isinstance(run.materials_response, dict) else {}
    final_state = run.final_state or run.initial_state or {}
    return {
        "success": True,
        "stage": "completed",
        "mode": run.mode,
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
            "plans": len(getattr(linear, "cut_plans", []) or [])
            if linear is not None
            else int(final_state.get("optimized_count", 0) or 0),
            "total_waste": getattr(linear, "total_waste", None),
            "total_waste_percent": getattr(linear, "total_waste_percent", None),
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
        "state": {
            "initial": run.initial_state,
            "final": run.final_state,
        },
        "skipped_steps": run.skipped_steps,
    }
