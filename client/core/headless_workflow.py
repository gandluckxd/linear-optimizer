"""Headless orchestration for the MOS optimization workflow.

The module deliberately reuses the existing API client and optimizers.  It
contains only the non-visual part of ``LinearOptimizerWindow``: loading input
data, preparing stocks, invoking the optimizers, and persisting their result.
"""

from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .api_client import APIClient
from .fiberglass_optimizer import optimize as optimize_fiberglass
from .models import Profile, Stock
from .optimizer import LinearOptimizer, OptimizationSettings


logger = logging.getLogger(__name__)


DEFAULT_CONFIG: Dict[str, Any] = {
    "api": {
        "base_url": "http://localhost:8001",
    },
    "operations": {
        "adjust_materials": True,
        "distribute_cells": True,
    },
    # These values are identical to the parameters initialized in the GUI.
    "linear_optimization": {
        "blade_width": 5.0,
        "min_remainder_length": 300.0,
        "max_waste_percent": 15.0,
        "pair_optimization": True,
        "use_remainders": True,
        "time_limit_seconds": 60,
        "begin_indent": 10.0,
        "end_indent": 10.0,
        "min_trash_mm": 50.0,
        "min_remainder_width": 500.0,
        "min_remainder_height": 500.0,
        "planar_cut_width": 1.0,
        "sheet_indent": 15.0,
        "remainder_indent": 15.0,
        "planar_max_waste_percent": 5.0,
        "pairing_exact_bonus": 3000.0,
        "pairing_partial_bonus": 1000.0,
        "pairing_partial_threshold": 0.7,
        "pairing_new_simple_bonus": 150.0,
    },
    "fiberglass_optimization": {
        "planar_min_remainder_width": 500.0,
        "planar_min_remainder_height": 500.0,
        "planar_cut_width": 1.0,
        "sheet_indent": 15.0,
        "remainder_indent": 15.0,
        "planar_max_waste_percent": 5.0,
        "use_warehouse_remnants": True,
        "allow_rotation": True,
    },
}


class ConfigError(ValueError):
    """A configuration file cannot be used safely."""


@dataclass
class LoadedData:
    profiles: List[Profile]
    stocks: List[Stock]
    fabric_details: list
    fabric_remainders: list
    fabric_materials: list
    grorder_ids: List[int]


def _merge_config(default: Dict[str, Any], supplied: Dict[str, Any], path: str = "") -> Dict[str, Any]:
    """Merge a JSON config into defaults and reject misspelled settings."""
    result = copy.deepcopy(default)
    for key, value in supplied.items():
        setting_path = f"{path}.{key}" if path else key
        if key not in default:
            raise ConfigError(f"Неизвестный параметр конфигурации: {setting_path}")
        if isinstance(default[key], dict):
            if not isinstance(value, dict):
                raise ConfigError(f"Параметр {setting_path} должен быть объектом JSON")
            result[key] = _merge_config(default[key], value, setting_path)
        else:
            result[key] = value
    return result


def load_config(path: Path) -> Dict[str, Any]:
    """Load and minimally validate the external JSON configuration."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ConfigError(f"Файл конфигурации не найден: {path}") from error
    except json.JSONDecodeError as error:
        raise ConfigError(f"Некорректный JSON в {path}: {error}") from error

    if not isinstance(raw, dict):
        raise ConfigError("Корень конфигурации должен быть объектом JSON")

    config = _merge_config(DEFAULT_CONFIG, raw)
    base_url = config["api"]["base_url"]
    if not isinstance(base_url, str) or not base_url.strip():
        raise ConfigError("api.base_url должен быть непустой строкой")

    for section in ("linear_optimization", "fiberglass_optimization"):
        for key, value in config[section].items():
            default = DEFAULT_CONFIG[section][key]
            if isinstance(default, bool):
                if not isinstance(value, bool):
                    raise ConfigError(f"{section}.{key} должен быть true или false")
            elif not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ConfigError(f"{section}.{key} должен быть числом")

    for key, value in config["operations"].items():
        if not isinstance(value, bool):
            raise ConfigError(f"operations.{key} должен быть true или false")

    return config


def build_stocks(stock_remainders: list, stock_materials: list) -> List[Stock]:
    """Build exactly the stock objects previously built by the GUI table handler."""
    stocks: List[Stock] = []
    stock_id = 1

    # A business remainder must be represented by a separate Stock object for
    # each physical bar.  The linear optimizer relies on this behaviour.
    for remainder in stock_remainders:
        for instance_id in range(remainder.quantity_pieces):
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


def generate_cell_map(profiles: List[Profile], fabric_details: list) -> Dict[str, int]:
    """Create the same deterministic cell map as the former GUI workflow."""
    unique_items = set()
    for item in [*profiles, *fabric_details]:
        orderitemsid = getattr(item, "orderitemsid", None)
        if orderitemsid is not None:
            unique_items.add((orderitemsid, getattr(item, "izdpart", "") or ""))

    ordered_items = sorted(unique_items, key=lambda item: (item[0], item[1]))
    return {
        f"{orderitemsid}_{izdpart}": number
        for number, (orderitemsid, izdpart) in enumerate(ordered_items, start=1)
    }


def collect_material_adjustments(
    optimization_result: Any,
    profiles: List[Profile],
    fabric_optimization_result: Optional[Any],
) -> tuple[list, list, list, list]:
    """Create the four payloads sent to ``adjust-materials-altawin``.

    This is the non-visual equivalent of ``on_upload_mos_clicked``.  It keeps
    its grouping rules, including ``CutPlan.count`` for grouped identical bars.
    """
    materials_by_size: Dict[tuple, Dict[str, Any]] = {}
    for plan in optimization_result.cut_plans:
        cuts = getattr(plan, "cuts", None) or []
        goodsid = cuts[0].get("profile_id") if cuts else None
        if not goodsid:
            continue

        stock_length = getattr(plan, "stock_length", 0)
        is_remainder = bool(getattr(plan, "is_remainder", False))
        material_key = (goodsid, stock_length, is_remainder)
        if material_key not in materials_by_size:
            materials_by_size[material_key] = {
                "goodsid": goodsid,
                "length": stock_length,
                "quantity": 0,
                "is_remainder": is_remainder,
                "warehouseremaindersid": getattr(plan, "warehouseremaindersid", None),
            }
        materials_by_size[material_key]["quantity"] += int(getattr(plan, "count", 1) or 1)

    used_materials = []
    for material in materials_by_size.values():
        profile_code = next((p.profile_code for p in profiles if p.id == material["goodsid"]), None)
        groupgoods_thick = 6000
        if profile_code:
            groupgoods_thick = next(
                (getattr(p, "groupgoods_thick", 6000) for p in profiles if p.profile_code == profile_code),
                6000,
            )
        material["groupgoods_thick"] = groupgoods_thick
        used_materials.append(material)

    remainders_by_size: Dict[tuple, Dict[str, Any]] = {}
    for plan in optimization_result.cut_plans:
        remainder = getattr(plan, "remainder", None)
        cuts = getattr(plan, "cuts", None) or []
        goodsid = cuts[0].get("profile_id") if cuts else None
        if not remainder or remainder <= 0 or not goodsid:
            continue

        remainder_key = (goodsid, remainder)
        if remainder_key not in remainders_by_size:
            remainders_by_size[remainder_key] = {
                "goodsid": goodsid,
                "length": remainder,
                "quantity": 0,
            }
        remainders_by_size[remainder_key]["quantity"] += int(getattr(plan, "count", 1) or 1)

    used_fiberglass_sheets: list = []
    new_fiberglass_remainders: list = []
    layouts = getattr(fabric_optimization_result, "layouts", None) if fabric_optimization_result else None
    if layouts:
        for layout in layouts:
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


class HeadlessOptimizationWorkflow:
    """Run the existing MOS workflow without importing PyQt or creating windows."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.api_client = APIClient(config["api"]["base_url"].rstrip("/"))

    def load_data(self, grorders_mos_id: int) -> LoadedData:
        grorder_ids = self.api_client.get_grorders_by_mos_id(grorders_mos_id)
        if not grorder_ids:
            raise RuntimeError(
                f"Для GRORDERS_MOS_ID={grorders_mos_id} не найдены связанные сменные задания"
            )

        profiles: List[Profile] = []
        for grorder_id in grorder_ids:
            loaded_profiles = self.api_client.get_profiles(grorder_id)
            logger.info("СЗ %s: загружено профилей: %s", grorder_id, len(loaded_profiles))
            profiles.extend(loaded_profiles)
        if not profiles:
            raise RuntimeError("Не найдены профили для оптимизации")

        profile_codes = list({profile.profile_code for profile in profiles})
        stock_remainders = self.api_client.get_stock_remainders(profile_codes)
        stock_materials = self.api_client.get_stock_materials(profile_codes)
        stocks = build_stocks(stock_remainders, stock_materials)
        if not stocks:
            raise RuntimeError("Не найдены доступные хлысты или деловые остатки")

        fabric_remainders: list = []
        fabric_materials: list = []
        fabric_details: list = []
        try:
            fabric_details = self.api_client.get_fiberglass_details(grorders_mos_id)
        except Exception as error:
            # The former GUI reported this as a warning and continued with the
            # profile optimization, so retain that operational behaviour.
            logger.warning("Не удалось загрузить данные фибергласса: %s", error)

        if fabric_details:
            goodsids = list({detail.goodsid for detail in fabric_details if detail.goodsid})
            try:
                fabric_remainders = self.api_client.get_fiberglass_remainders(goodsids)
            except Exception as error:  # The GUI treats this source as optional.
                logger.warning("Не удалось загрузить остатки фибергласса: %s", error)
            try:
                fabric_materials = self.api_client.get_fiberglass_materials(goodsids)
            except Exception as error:  # The GUI treats this source as optional.
                logger.warning("Не удалось загрузить цельный фибергласс: %s", error)

        logger.info(
            "Входные данные: профилей=%s, хлыстов=%s, деталей фибергласса=%s",
            len(profiles), len(stocks), len(fabric_details),
        )
        return LoadedData(
            profiles=profiles,
            stocks=stocks,
            fabric_details=fabric_details,
            fabric_remainders=fabric_remainders,
            fabric_materials=fabric_materials,
            grorder_ids=list(grorder_ids),
        )

    def optimize_linear(self, data: LoadedData) -> Any:
        settings = OptimizationSettings(**self.config["linear_optimization"])
        stocks = data.stocks
        if not settings.use_remainders:
            stocks = [stock for stock in stocks if not bool(getattr(stock, "is_remainder", False))]
        if not stocks:
            raise RuntimeError("После исключения остатков не осталось доступных хлыстов")

        result = LinearOptimizer().optimize(
            profiles=data.profiles,
            stocks=stocks,
            settings=settings,
            progress_fn=lambda percent: logger.info("Линейная оптимизация: %.0f%%", percent),
        )
        if not result or not result.success:
            raise RuntimeError(getattr(result, "message", "Линейная оптимизация не дала результата"))
        logger.info("Линейная оптимизация завершена: планов=%s", len(result.cut_plans))
        return result

    def optimize_fiberglass(self, data: LoadedData, cell_map: Dict[str, int]) -> Optional[Any]:
        if not data.fabric_details:
            logger.info("Деталей фибергласса нет; плоскостная оптимизация пропущена")
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
            for detail in data.fabric_details
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
            for material in data.fabric_materials
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
            for remainder in data.fabric_remainders
        ]

        result = optimize_fiberglass(
            details=details,
            materials=materials,
            remainders=remainders,
            params=self.config["fiberglass_optimization"],
            progress_fn=lambda percent: logger.info("Фибергласс: %.1f%%", percent),
            cell_map=cell_map,
        )
        if result and result.success:
            logger.info("Оптимизация фибергласса завершена: раскладок=%s", len(result.layouts))
        else:
            # This deliberately matches the former GUI: a failed fiberglass run
            # does not discard a successful linear optimization result.
            logger.warning(
                "Оптимизация фибергласса не дала результата: %s",
                getattr(result, "message", "неизвестная ошибка"),
            )
        return result

    def run(self, grorders_mos_id: int, dry_run: bool = False) -> Dict[str, Any]:
        logger.info("Запуск headless-оптимизации для GRORDERS_MOS_ID=%s", grorders_mos_id)
        data = self.load_data(grorders_mos_id)
        cell_map = generate_cell_map(data.profiles, data.fabric_details)
        linear_result = self.optimize_linear(data)
        fiberglass_result = self.optimize_fiberglass(data, cell_map)

        report = {
            "grorders_mos_id": grorders_mos_id,
            "grorder_ids": data.grorder_ids,
            "linear_cut_plans": len(linear_result.cut_plans),
            "fiberglass_layouts": len(getattr(fiberglass_result, "layouts", []) or []),
            "cell_map_items": len(cell_map),
            "dry_run": dry_run,
        }
        if dry_run:
            logger.warning("Dry-run: результаты оптимизации и материалы в БД не записывались")
            return report

        linear = self.config["linear_optimization"]
        if not self.api_client.upload_mos_data(
            grorders_mos_id=grorders_mos_id,
            result=linear_result,
            profiles=data.profiles,
            blade_width_mm=int(linear["blade_width"]),
            min_remainder_mm=int(linear["min_remainder_length"]),
            begin_indent_mm=int(linear["begin_indent"]),
            end_indent_mm=int(linear["end_indent"]),
            min_trash_mm=int(linear["min_trash_mm"]),
        ):
            raise RuntimeError("Не удалось записать результаты линейной оптимизации")
        report["optimization_uploaded"] = True

        if self.config["operations"]["adjust_materials"]:
            payloads = collect_material_adjustments(linear_result, data.profiles, fiberglass_result)
            adjustment = self.api_client.adjust_materials_altawin(grorders_mos_id, *payloads)
            if not adjustment.get("success"):
                raise RuntimeError(f"Не удалось скорректировать материалы: {adjustment.get('error', adjustment)}")
            report["materials_adjusted"] = True
            report["outlay_id"] = adjustment.get("outlay_id")
            report["supply_id"] = adjustment.get("supply_id")

        if self.config["operations"]["distribute_cells"] and cell_map:
            distribution = self.api_client.distribute_cell_numbers(grorders_mos_id, cell_map=cell_map)
            if not distribution.get("success"):
                raise RuntimeError(
                    f"Не удалось распределить ячейки: {distribution.get('error', distribution.get('message', distribution))}"
                )
            report["cells_distributed"] = distribution.get("processed_items", 0)

        logger.info("Headless-оптимизация завершена успешно")
        return report
