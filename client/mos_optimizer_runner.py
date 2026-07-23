"""Command-line entry point for unattended MOS optimization.

Example:
    mos-optimizer-runner.exe 123 --config C:\\Altawin\\linear_optimizer_mos.txt
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import re
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
        return Path(sys.executable).resolve().with_name("linear_optimizer_mos.txt")
    return Path(__file__).resolve().with_name("linear_optimizer_mos.txt")


def _read_config_text(path: Path) -> str:
    """Read a technology config saved by Notepad in a supported encoding."""
    try:
        raw = path.read_bytes()
    except FileNotFoundError as error:
        raise WorkflowError(
            "Не найден файл конфигурации: "
            f"{path}. Скопируйте linear_optimizer_mos.example.txt "
            "в linear_optimizer_mos.txt.",
            "configuration",
        ) from error
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise WorkflowError(
        f"Не удалось прочитать {path}: используйте UTF-8, UTF-8 BOM или Windows-1251 (ANSI).",
        "configuration",
    )


def _strip_inline_comment(value: str) -> str:
    """Remove an optional ``#`` or ``;`` comment after a value."""
    positions = [position for marker in ("#", ";") if (position := value.find(marker)) >= 0]
    return value[: min(positions)].strip() if positions else value.strip()


def _configuration_error(line_number: int, message: str) -> WorkflowError:
    return WorkflowError(f"Строка {line_number}: {message}", "configuration")


def _parse_bool(value: str, line_number: int, parameter: str) -> bool:
    normalized = value.strip().casefold()
    if normalized in {"да", "true", "1"}:
        return True
    if normalized in {"нет", "false", "0"}:
        return False
    raise _configuration_error(
        line_number,
        f"параметр {parameter} должен быть «да»/«нет», true/false или 1/0",
    )


def _parse_int(value: str, line_number: int, parameter: str) -> int:
    if not re.fullmatch(r"[+-]?\d+", value.strip()):
        raise _configuration_error(line_number, f"параметр {parameter} должен быть целым числом")
    return int(value)


def _parse_float(value: str, line_number: int, parameter: str) -> float:
    try:
        return float(value.strip().replace(",", "."))
    except ValueError as error:
        raise _configuration_error(line_number, f"параметр {parameter} должен быть числом") from error


def load_config(path: Path) -> tuple[str, WorkflowSettings, Optional[Path]]:
    """Read flat ``parameter = value`` settings for the unattended runner."""
    text = _read_config_text(path)

    aliases = {
        "blade_width_mm": "blade_width",
        "min_remainder_mm": "min_remainder_length",
        "begin_indent_mm": "begin_indent",
        "end_indent_mm": "end_indent",
    }
    allowed = {item.name for item in fields(WorkflowSettings)}
    defaults = WorkflowSettings()
    values: Dict[str, Any] = {}
    seen_lines: Dict[str, int] = {}
    connection_values: Dict[str, str] = {}

    for line_number, source_line in enumerate(text.splitlines(), start=1):
        line = source_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if "=" not in line:
            raise _configuration_error(line_number, "ожидается запись «параметр = значение»")
        raw_key, raw_value = line.split("=", 1)
        key = raw_key.strip().casefold()
        value = _strip_inline_comment(raw_value)
        if not key:
            raise _configuration_error(line_number, "не указано имя параметра")
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", key):
            raise _configuration_error(line_number, f"некорректное имя параметра «{raw_key.strip()}»")
        if not value:
            raise _configuration_error(line_number, f"не задано значение параметра {key}")

        setting = aliases.get(key, key)
        if setting in seen_lines:
            raise _configuration_error(
                line_number,
                f"параметр {key} уже задан в строке {seen_lines[setting]}",
            )
        if key in {"api_url", "log_file"}:
            connection_values[key] = value
            seen_lines[setting] = line_number
            continue
        if setting not in allowed:
            raise _configuration_error(line_number, f"неизвестный параметр {key}")

        default = getattr(defaults, setting)
        if isinstance(default, bool):
            parsed_value = _parse_bool(value, line_number, key)
        elif isinstance(default, int):
            parsed_value = _parse_int(value, line_number, key)
        else:
            parsed_value = _parse_float(value, line_number, key)
        values[setting] = parsed_value
        seen_lines[setting] = line_number

    api_url = connection_values.get("api_url", "").strip()
    if not api_url:
        raise WorkflowError("Не задан обязательный параметр api_url", "configuration")
    try:
        settings = WorkflowSettings(**values)
    except TypeError as error:
        raise WorkflowError(f"Некорректные настройки runner: {error}", "configuration") from error

    configured_log = connection_values.get("log_file", "").strip()
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
        help="путь к linear_optimizer_mos.txt (по умолчанию рядом с EXE)",
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
    if error.stage in {"saving", "warehouse", "warehouse/resume", "cells"}:
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
