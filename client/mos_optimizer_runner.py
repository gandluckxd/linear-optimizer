"""Command-line entry point for unattended MOS optimization.

Example:
    mos-optimizer-runner.exe 123 --config C:\\Altawin\\mos_optimizer.json
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import sys
from dataclasses import fields
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from core.headless_workflow import (
    MosOptimizationWorkflow,
    WorkflowError,
    WorkflowSettings,
    build_summary,
)


EXIT_SUCCESS = 0
EXIT_ARGUMENT_ERROR = 2
EXIT_API_ERROR = 3
EXIT_OPTIMIZATION_ERROR = 4
EXIT_SAVE_ERROR = 5
EXIT_UNEXPECTED_ERROR = 10


class LogWriter:
    """Move legacy ``print`` calls from algorithms/API to the stderr log."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.buffer = ""

    def write(self, value: str) -> int:
        self.buffer += value
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            if line.strip():
                self.logger.info(line.rstrip())
        return len(value)

    def flush(self) -> None:
        if self.buffer.strip():
            self.logger.info(self.buffer.rstrip())
        self.buffer = ""


def default_config_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().with_name("mos_optimizer.json")
    return Path(__file__).resolve().with_name("mos_optimizer.json")


def load_config(path: Path) -> tuple[str, WorkflowSettings, Optional[Path]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise WorkflowError(
            f"Не найден файл конфигурации: {path}. Скопируйте mos_optimizer.example.json в mos_optimizer.json.",
            "configuration",
        ) from error
    except json.JSONDecodeError as error:
        raise WorkflowError(f"Некорректный JSON в {path}: {error}", "configuration") from error

    if not isinstance(raw, dict):
        raise WorkflowError("Корень конфигурации должен быть объектом JSON", "configuration")
    allowed_root_keys = {"api_url", "log_file", "optimization", "operations"}
    unknown_root_keys = sorted(
        key for key in raw if not key.startswith("_") and key not in allowed_root_keys
    )
    if unknown_root_keys:
        raise WorkflowError(
            "Неизвестные разделы конфигурации: " + ", ".join(unknown_root_keys),
            "configuration",
        )
    api_url = raw.get("api_url")
    if not isinstance(api_url, str) or not api_url.strip():
        raise WorkflowError("В конфигурации требуется непустой api_url", "configuration")

    optimization = raw.get("optimization", {})
    operations = raw.get("operations", {})
    if not isinstance(optimization, dict) or not isinstance(operations, dict):
        raise WorkflowError("Разделы optimization и operations должны быть объектами JSON", "configuration")

    aliases = {
        "blade_width_mm": "blade_width",
        "min_remainder_mm": "min_remainder_length",
        "begin_indent_mm": "begin_indent",
        "end_indent_mm": "end_indent",
    }
    values: Dict[str, Any] = {}
    for source in (optimization, operations):
        for key, value in source.items():
            # JSON has no comments. Explanatory keys in the supplied example
            # intentionally begin with an underscore and have no effect.
            if key.startswith("_"):
                continue
            values[aliases.get(key, key)] = value

    allowed = {item.name for item in fields(WorkflowSettings)}
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise WorkflowError(
            "Неизвестные настройки runner: " + ", ".join(unknown),
            "configuration",
        )
    try:
        settings = WorkflowSettings(**values)
    except TypeError as error:
        raise WorkflowError(f"Некорректные настройки runner: {error}", "configuration") from error

    defaults = WorkflowSettings()
    for key, value in values.items():
        default = getattr(defaults, key)
        if isinstance(default, bool):
            valid = isinstance(value, bool)
        elif isinstance(default, int):
            valid = isinstance(value, int) and not isinstance(value, bool)
        else:
            valid = isinstance(value, (int, float)) and not isinstance(value, bool)
        if not valid:
            expected = "true или false" if isinstance(default, bool) else "число"
            raise WorkflowError(
                f"Параметр {key} должен быть {expected}",
                "configuration",
            )

    configured_log = raw.get("log_file")
    log_file = None
    if configured_log:
        log_file = Path(configured_log)
        if not log_file.is_absolute():
            log_file = path.parent / log_file
    return api_url.rstrip("/"), settings, log_file


def configure_logging(log_file: Optional[Path]) -> logging.Logger:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
        force=True,
    )
    return logging.getLogger("mos_optimizer_runner")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Запустить оптимизацию москитных сеток без GUI."
    )
    parser.add_argument("grorders_mos_id", type=int, help="ID из GRORDERS_MOS")
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config_path(),
        help="путь к mos_optimizer.json (по умолчанию рядом с EXE)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="загрузить и рассчитать без записи в Altawin",
    )
    parser.add_argument(
        "--no-adjust-materials",
        action="store_true",
        help="записать карты, но не создавать расход и приход",
    )
    parser.add_argument(
        "--no-distribute-cells",
        action="store_true",
        help="записать результат, но не распределять номера ячеек",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        help="дополнительно сохранить итоговый JSON в указанный файл",
    )
    return parser.parse_args(argv)


def failure_summary(grorders_mos_id: Optional[int], stage: str, error: Exception) -> dict:
    return {
        "success": False,
        "stage": stage,
        "grorders_mos_id": grorders_mos_id,
        "error": str(error),
    }


def write_summary(summary: dict, output_json: Optional[Path] = None) -> None:
    rendered = json.dumps(summary, ensure_ascii=False, indent=2, default=str)
    print(rendered)
    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(rendered + "\n", encoding="utf-8")


def exit_code_for(error: WorkflowError) -> int:
    if error.stage == "configuration":
        return EXIT_ARGUMENT_ERROR
    if error.stage == "loading":
        return EXIT_API_ERROR
    if error.stage in {"saving", "warehouse", "cells"}:
        return EXIT_SAVE_ERROR
    return EXIT_OPTIMIZATION_ERROR


def main(
    argv: Optional[list[str]] = None,
    api_client_factory: Optional[Callable[[str], Any]] = None,
) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.grorders_mos_id <= 0:
        error = WorkflowError("GRORDERS_MOS_ID должен быть положительным числом", "configuration")
        write_summary(failure_summary(args.grorders_mos_id, error.stage, error), args.output_json)
        return EXIT_ARGUMENT_ERROR

    logger = configure_logging(None)
    try:
        api_url, settings, log_file = load_config(args.config)
        logger = configure_logging(log_file)
        if args.no_adjust_materials:
            settings.adjust_materials = False
        if args.no_distribute_cells:
            settings.distribute_cells = False

        if api_client_factory is None:
            from core.api_client import APIClient

            api_client_factory = APIClient
        workflow = MosOptimizationWorkflow(api_client_factory(api_url), settings)
        logger.info(
            "Старт GRORDERS_MOS_ID=%s (dry_run=%s, save_result=%s, adjust_materials=%s)",
            args.grorders_mos_id,
            args.dry_run,
            settings.save_result,
            settings.adjust_materials,
        )
        # Legacy modules use print extensively. Keep stdout machine-readable by
        # redirecting those messages to the log and print only final JSON below.
        with contextlib.redirect_stdout(LogWriter(logger)):
            run = workflow.run(args.grorders_mos_id, dry_run=args.dry_run, progress=logger.info)
        summary = build_summary(run)
        write_summary(summary, args.output_json)
        logger.info("GRORDERS_MOS_ID=%s успешно обработан", args.grorders_mos_id)
        return EXIT_SUCCESS
    except WorkflowError as error:
        logger.error("Ошибка workflow на этапе %s: %s", error.stage, error)
        write_summary(failure_summary(args.grorders_mos_id, error.stage, error), args.output_json)
        return exit_code_for(error)
    except Exception as error:
        logger.exception("Непредвиденная ошибка runner")
        write_summary(failure_summary(args.grorders_mos_id, "unexpected", error), args.output_json)
        return EXIT_UNEXPECTED_ERROR


if __name__ == "__main__":
    sys.exit(main())
