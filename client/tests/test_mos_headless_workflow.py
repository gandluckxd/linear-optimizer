"""Contract tests for the unattended MOS runner.

Every API client here is a fake.  The tests neither open a HTTP connection nor
perform a write to Firebird.
"""

from __future__ import annotations

import codecs
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


CLIENT_DIR = Path(__file__).resolve().parents[1]
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

import mos_optimizer_runner as runner
from core.headless_workflow import MosOptimizationWorkflow, WorkflowSettings, build_summary
from core.models import Profile, StockMaterial


class FakeApiClient:
    """Small deterministic API that provides one completely cuttable profile."""

    def __init__(self, _api_url: str = ""):
        self.calls: list[str] = []

    def get_grorders_by_mos_id(self, grorders_mos_id: int):
        self.calls.append("get_grorders_by_mos_id")
        return [1001] if grorders_mos_id == 42 else []

    def get_profiles(self, grorder_id: int):
        self.calls.append("get_profiles")
        return [
            Profile(
                id=500,
                order_id=grorder_id,
                element_name="Рама",
                profile_code="MOS-500",
                length=1000,
                quantity=2,
                orderitemsid=700,
                izdpart="A",
            )
        ]

    def get_stock_remainders(self, _profile_codes):
        self.calls.append("get_stock_remainders")
        return []

    def get_stock_materials(self, _profile_codes):
        self.calls.append("get_stock_materials")
        return [StockMaterial(profile_code="MOS-500", length=6000, quantity_pieces=1)]

    def get_fiberglass_details(self, _grorders_mos_id):
        self.calls.append("get_fiberglass_details")
        return []

    def upload_mos_data(self, **_kwargs):
        self.calls.append("upload_mos_data")
        return True

    def adjust_materials_altawin(self, *_args):
        self.calls.append("adjust_materials_altawin")
        return {"success": True, "outlay_id": 81, "supply_id": 82}

    def distribute_cell_numbers(self, *_args, **_kwargs):
        self.calls.append("distribute_cell_numbers")
        return {"success": True, "processed_items": 1}


class InsufficientMaterialApiClient(FakeApiClient):
    def get_stock_materials(self, _profile_codes):
        self.calls.append("get_stock_materials")
        return [StockMaterial(profile_code="MOS-500", length=900, quantity_pieces=1)]


class BrokenApiClient(FakeApiClient):
    def get_grorders_by_mos_id(self, _grorders_mos_id):
        raise RuntimeError("API недоступен")


class MosHeadlessWorkflowTests(unittest.TestCase):
    def write_config(
        self,
        folder: Path,
        extra: str = "",
        *,
        encoding: str = "utf-8",
        bom: bool = False,
    ) -> Path:
        path = folder / "linear_optimizer_mos.txt"
        content = """# Комментарий для человека — runner его игнорирует.
api_url = http://fake-api:8001
{extra}
""".format(extra=extra)
        if bom:
            path.write_bytes(codecs.BOM_UTF8 + content.encode("utf-8"))
        else:
            path.write_text(content, encoding=encoding)
        return path

    def test_full_workflow_persists_and_reports_document_numbers(self):
        api = FakeApiClient()
        with contextlib.redirect_stdout(io.StringIO()):
            run = MosOptimizationWorkflow(api, WorkflowSettings()).run(42)

        summary = build_summary(run)
        self.assertTrue(summary["success"])
        self.assertFalse(summary["dry_run"])
        self.assertEqual(summary["linear"]["total_pieces_unplaced"], 0)
        self.assertEqual(summary["warehouse"]["outlay_id"], 81)
        self.assertEqual(summary["warehouse"]["supply_id"], 82)
        self.assertEqual(
            api.calls[-3:],
            ["upload_mos_data", "adjust_materials_altawin", "distribute_cell_numbers"],
        )

    def test_dry_run_never_calls_write_methods(self):
        api = FakeApiClient()
        with contextlib.redirect_stdout(io.StringIO()):
            run = MosOptimizationWorkflow(api, WorkflowSettings()).run(42, dry_run=True)

        self.assertTrue(run.dry_run)
        self.assertNotIn("upload_mos_data", api.calls)
        self.assertNotIn("adjust_materials_altawin", api.calls)
        self.assertNotIn("distribute_cell_numbers", api.calls)

    def test_example_txt_is_readable(self):
        api_url, settings, log_file = runner.load_config(
            CLIENT_DIR / "linear_optimizer_mos.example.txt"
        )

        self.assertEqual(api_url, "http://127.0.0.1:8001")
        self.assertEqual(settings.blade_width, 5.0)
        self.assertTrue(settings.pair_optimization)
        self.assertTrue(settings.adjust_materials)
        self.assertEqual(log_file, CLIENT_DIR / "logs/mos-optimizer-runner.log")

    def test_txt_config_accepts_russian_boolean_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_config(
                Path(temporary),
                """pair_optimization = да
use_remainders = нет
allow_rotation = 1
adjust_materials = 0
distribute_cells = false
save_result = true""",
            )
            api_url, settings, _log_file = runner.load_config(path)

        self.assertEqual(api_url, "http://fake-api:8001")
        self.assertTrue(settings.pair_optimization)
        self.assertFalse(settings.use_remainders)
        self.assertTrue(settings.allow_rotation)
        self.assertFalse(settings.adjust_materials)
        self.assertFalse(settings.distribute_cells)
        self.assertTrue(settings.save_result)

    def test_txt_config_accepts_decimal_comma_and_inline_comments(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_config(
                Path(temporary),
                """; Полная строка комментария

blade_width_mm = 4,5 # Комментарий после значения
pairing_partial_threshold = 0,75; Ещё один комментарий""",
            )
            _api_url, settings, _log_file = runner.load_config(path)

        self.assertEqual(settings.blade_width, 4.5)
        self.assertEqual(settings.pairing_partial_threshold, 0.75)

    def test_txt_config_accepts_utf8_bom(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_config(Path(temporary), "use_remainders = да", bom=True)
            _api_url, settings, _log_file = runner.load_config(path)

        self.assertTrue(settings.use_remainders)

    def test_txt_config_accepts_windows_1251(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_config(
                Path(temporary),
                "# Настройка сохранена Блокнотом Windows\nuse_remainders = нет",
                encoding="cp1251",
            )
            _api_url, settings, _log_file = runner.load_config(path)

        self.assertFalse(settings.use_remainders)

    def test_txt_config_rejects_unknown_and_duplicate_parameter_with_line_number(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_config(
                Path(temporary),
                """unknown_parameter = 1
blade_width_mm = 5
blade_width = 6""",
            )
            with self.assertRaisesRegex(runner.WorkflowError, r"Строка 3: неизвестный параметр"):
                runner.load_config(path)

            path = self.write_config(
                Path(temporary),
                """blade_width_mm = 5
blade_width = 6""",
            )
            with self.assertRaisesRegex(runner.WorkflowError, r"Строка 4: параметр blade_width уже задан"):
                runner.load_config(path)

    def test_txt_config_rejects_invalid_line_with_line_number(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_config(Path(temporary), "это не настройка")
            with self.assertRaisesRegex(runner.WorkflowError, r"Строка 3: ожидается запись"):
                runner.load_config(path)

    def test_api_error_has_machine_readable_json_and_nonzero_exit_code(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = self.write_config(Path(temporary))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = runner.main(
                    ["42", "--config", str(config)],
                    api_client_factory=BrokenApiClient,
                )

        result = json.loads(output.getvalue())
        self.assertEqual(code, runner.EXIT_API_ERROR)
        self.assertFalse(result["success"])
        self.assertEqual(result["stage"], "loading")
        self.assertIn("API недоступен", result["error"])

    def test_optimization_error_has_machine_readable_json_and_nonzero_exit_code(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = self.write_config(Path(temporary))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = runner.main(
                    ["42", "--config", str(config)],
                    api_client_factory=InsufficientMaterialApiClient,
                )

        result = json.loads(output.getvalue())
        self.assertEqual(code, runner.EXIT_OPTIMIZATION_ERROR)
        self.assertFalse(result["success"])
        self.assertEqual(result["stage"], "optimization")


if __name__ == "__main__":
    unittest.main()
