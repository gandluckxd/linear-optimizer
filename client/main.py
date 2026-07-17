"""Console entry point for the MOS optimizer executable.

Usage:
    linear-optimizer-headless.exe <GRORDERS_MOS_ID> [--config PATH] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from core.headless_workflow import ConfigError, HeadlessOptimizationWorkflow, load_config


def default_config_path() -> Path:
    """Use a configuration file next to the executable, or next to this source."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "optimizer.config.json"
    return Path(__file__).resolve().with_name("optimizer.config.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Headless MOS optimizer: load, optimize and write results to Altawin."
    )
    parser.add_argument(
        "grorders_mos_id",
        type=int,
        help="ID записи GRORDERS_MOS, для которой выполняется оптимизация",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config_path(),
        help="путь к optimizer.config.json (по умолчанию рядом с EXE)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="выполнить загрузку и оптимизацию без любой записи в БД",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    args = parse_args()
    if args.grorders_mos_id <= 0:
        logging.error("GRORDERS_MOS_ID должен быть положительным целым числом")
        return 1

    try:
        config = load_config(args.config)
        report = HeadlessOptimizationWorkflow(config).run(
            args.grorders_mos_id,
            dry_run=args.dry_run,
        )
    except (ConfigError, RuntimeError, ValueError) as error:
        logging.error("Оптимизация не выполнена: %s", error)
        return 1
    except Exception:
        logging.exception("Непредвиденная ошибка headless-оптимизации")
        return 1

    logging.info("Итог: %s", json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
