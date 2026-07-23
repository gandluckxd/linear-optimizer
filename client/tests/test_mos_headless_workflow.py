"""Contract tests for the unattended MOS runner.

Every API client here is a fake.  The tests neither open a HTTP connection nor
perform a write to Firebird.
"""

from __future__ import annotations

import codecs
import copy
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
from core.headless_workflow import (
    MosOptimizationWorkflow,
    WorkflowError,
    WorkflowSettings,
    build_summary,
)
from core.models import Profile, StockMaterial


class FakeApiClient:
    """Small deterministic API that provides one completely cuttable profile."""

    def __init__(self, _api_url: str = ""):
        self.calls: list[str] = []
        self.state = {
            "grorders_mos_id": 42,
            "optimized_count": 0,
            "detail_count": 0,
            "missing_cell_count": 0,
            "outlays": [],
            "supplies": [],
            "warehouse_content_matches": None,
        }

    def get_mos_job_state(self, _grorders_mos_id: int):
        self.calls.append("get_mos_job_state")
        return copy.deepcopy(self.state)

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
        self.state["optimized_count"] = 1
        self.state["detail_count"] = 1
        self.state["missing_cell_count"] = 1
        return True

    def adjust_materials_altawin(self, *_args):
        self.calls.append("adjust_materials_altawin")
        self.state["outlays"] = [
            {"outlay_id": 81, "deleted": 0, "isapproved": 0}
        ]
        self.state["supplies"] = [
            {"supply_id": 82, "deleted": 0, "isapproved": 0}
        ]
        self.state["warehouse_content_matches"] = True
        return {"success": True, "outlay_id": 81, "supply_id": 82}

    def distribute_cell_numbers(self, *_args, **_kwargs):
        self.calls.append("distribute_cell_numbers")
        self.state["missing_cell_count"] = 0
        return {"success": True, "processed_items": 1}

    def approve_mos_document(
        self,
        _grorders_mos_id: int,
        document_type: str,
        document_id: int,
    ):
        self.calls.append(f"approve_{document_type}_{document_id}")
        collection = self.state["outlays" if document_type == "outlay" else "supplies"]
        matching = [
            item
            for item in collection
            if item[f"{document_type}_id"] == document_id
        ]
        matching[0]["isapproved"] = 1
        return {"success": True, "document_type": document_type, "document_id": document_id}


class ResumeApiClient(FakeApiClient):
    """State left by a crash after warehouse documents were committed."""

    def __init__(self):
        super().__init__()
        self.state = {
            "grorders_mos_id": 42,
            "optimized_count": 1,
            "detail_count": 1,
            "missing_cell_count": 1,
            "outlays": [{"outlay_id": 19024, "deleted": 0, "isapproved": 0}],
            "supplies": [{"supply_id": 12679, "deleted": 0, "isapproved": 0}],
            "warehouse_content_matches": True,
        }

    def distribute_cell_numbers(self, *_args, **_kwargs):
        result = super().distribute_cell_numbers(*_args, **_kwargs)
        self.state["missing_cell_count"] = 0
        return result


class CompletedApiClient(ResumeApiClient):
    def __init__(self):
        super().__init__()
        self.state["missing_cell_count"] = 0
        self.state["outlays"][0]["isapproved"] = 1
        self.state["supplies"][0]["isapproved"] = 1


class OutlayApprovedApiClient(ResumeApiClient):
    def __init__(self):
        super().__init__()
        self.state["missing_cell_count"] = 0
        self.state["outlays"][0]["isapproved"] = 1


class IncompleteCellDistributionApiClient(ResumeApiClient):
    def distribute_cell_numbers(self, *_args, **_kwargs):
        self.calls.append("distribute_cell_numbers")
        return {"success": True, "processed_items": 0}


class TimeoutAfterWarehouseCommitApiClient(FakeApiClient):
    def adjust_materials_altawin(self, *_args):
        super().adjust_materials_altawin(*_args)
        raise TimeoutError("HTTP read timed out after server commit")


class InsufficientMaterialApiClient(FakeApiClient):
    def get_stock_materials(self, _profile_codes):
        self.calls.append("get_stock_materials")
        return [StockMaterial(profile_code="MOS-500", length=900, quantity_pieces=1)]


class BrokenApiClient(FakeApiClient):
    def get_grorders_by_mos_id(self, _grorders_mos_id):
        raise RuntimeError("API недоступен")


class InconsistentApiClient(FakeApiClient):
    def __init__(self, _api_url: str = ""):
        super().__init__(_api_url)
        self.state = {
            "optimized_count": 1,
            "detail_count": 1,
            "missing_cell_count": 1,
            "outlays": [{"outlay_id": 19024, "deleted": 0, "isapproved": 0}],
            "supplies": [],
            "warehouse_content_matches": None,
        }


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
        write_calls = [
            call
            for call in api.calls
            if call
            in {
                "upload_mos_data",
                "adjust_materials_altawin",
                "distribute_cell_numbers",
                "approve_outlay_81",
                "approve_supply_82",
            }
        ]
        self.assertEqual(
            write_calls,
            [
                "upload_mos_data",
                "adjust_materials_altawin",
                "distribute_cell_numbers",
                "approve_outlay_81",
                "approve_supply_82",
            ],
        )

    def test_partial_commit_resumes_without_reuploading_or_creating_documents(self):
        api = ResumeApiClient()
        log: list[str] = []
        with contextlib.redirect_stdout(io.StringIO()):
            run = MosOptimizationWorkflow(api, WorkflowSettings()).run(
                42, progress=log.append
            )

        self.assertNotIn("get_stock_remainders", api.calls)
        self.assertNotIn("get_stock_materials", api.calls)
        self.assertNotIn("upload_mos_data", api.calls)
        self.assertNotIn("adjust_materials_altawin", api.calls)
        self.assertEqual(run.mode, "resume")
        self.assertIn("distribute_cell_numbers", api.calls)
        self.assertIn("approve_outlay_19024", api.calls)
        self.assertIn("approve_supply_12679", api.calls)
        self.assertEqual(api.state["missing_cell_count"], 0)
        self.assertEqual(api.state["outlays"][0]["isapproved"], 1)
        self.assertEqual(api.state["supplies"][0]["isapproved"], 1)
        self.assertTrue(any("mode=resume" in line for line in log))
        self.assertTrue(any("OUTLAYID=[19024]" in line for line in log))
        self.assertIn(
            "skip=adjust_materials_altawin reason=existing_warehouse_pair",
            log,
        )

    def test_completed_job_is_a_noop(self):
        api = CompletedApiClient()
        log: list[str] = []
        with contextlib.redirect_stdout(io.StringIO()):
            run = MosOptimizationWorkflow(api, WorkflowSettings()).run(
                42, progress=log.append
            )

        self.assertEqual(run.mode, "noop")
        self.assertEqual(api.calls, ["get_mos_job_state"])
        self.assertEqual(run.materials_response["outlay_id"], 19024)
        self.assertEqual(run.materials_response["supply_id"], 12679)
        self.assertTrue(any("mode=noop" in line for line in log))
        self.assertIn("skip=optimization reason=already_completed", log)

    def test_only_draft_supply_is_approved_when_outlay_is_already_approved(self):
        api = OutlayApprovedApiClient()
        with contextlib.redirect_stdout(io.StringIO()):
            run = MosOptimizationWorkflow(api, WorkflowSettings()).run(42)

        self.assertEqual(run.mode, "resume")
        self.assertNotIn("approve_outlay_19024", api.calls)
        self.assertIn("approve_supply_12679", api.calls)
        self.assertNotIn("distribute_cell_numbers", api.calls)

    def test_documents_are_not_approved_while_cells_are_still_missing(self):
        api = IncompleteCellDistributionApiClient()
        with self.assertRaises(WorkflowError) as raised:
            MosOptimizationWorkflow(api, WorkflowSettings()).run(42)

        self.assertEqual(raised.exception.stage, "warehouse/resume")
        self.assertIn("осталось деталей без ячейки: 1", str(raised.exception))
        self.assertNotIn("approve_outlay_19024", api.calls)
        self.assertNotIn("approve_supply_12679", api.calls)

    def test_inconsistent_warehouse_states_never_write(self):
        cases = {
            "duplicate_pair": {
                "optimized_count": 1,
                "detail_count": 1,
                "missing_cell_count": 1,
                "outlays": [
                    {"outlay_id": 19024, "deleted": 0, "isapproved": 0},
                    {"outlay_id": 19025, "deleted": 0, "isapproved": 0},
                ],
                "supplies": [
                    {"supply_id": 12679, "deleted": 0, "isapproved": 0},
                    {"supply_id": 12680, "deleted": 0, "isapproved": 0},
                ],
                "warehouse_content_matches": None,
            },
            "outlay_only": {
                "optimized_count": 1,
                "detail_count": 1,
                "missing_cell_count": 1,
                "outlays": [{"outlay_id": 19024, "deleted": 0, "isapproved": 0}],
                "supplies": [],
                "warehouse_content_matches": None,
            },
            "supply_only": {
                "optimized_count": 1,
                "detail_count": 1,
                "missing_cell_count": 1,
                "outlays": [],
                "supplies": [{"supply_id": 12679, "deleted": 0, "isapproved": 0}],
                "warehouse_content_matches": None,
            },
            "documents_without_maps": {
                "optimized_count": 0,
                "detail_count": 0,
                "missing_cell_count": 0,
                "outlays": [{"outlay_id": 19024, "deleted": 0, "isapproved": 0}],
                "supplies": [{"supply_id": 12679, "deleted": 0, "isapproved": 0}],
                "warehouse_content_matches": False,
            },
            "content_mismatch": {
                "optimized_count": 1,
                "detail_count": 1,
                "missing_cell_count": 1,
                "outlays": [{"outlay_id": 19024, "deleted": 0, "isapproved": 0}],
                "supplies": [{"supply_id": 12679, "deleted": 0, "isapproved": 0}],
                "warehouse_content_matches": False,
                "content_mismatches": ["OUTLAYDETAIL GOODSID=500"],
            },
        }
        for name, state in cases.items():
            with self.subTest(name=name):
                api = FakeApiClient()
                api.state = state
                with self.assertRaises(WorkflowError) as raised:
                    MosOptimizationWorkflow(api, WorkflowSettings()).run(42)
                self.assertEqual(raised.exception.stage, "warehouse/resume")
                self.assertIn("INCONSISTENT", str(raised.exception))
                self.assertNotIn("upload_mos_data", api.calls)
                self.assertNotIn("adjust_materials_altawin", api.calls)
                self.assertNotIn("distribute_cell_numbers", api.calls)

    def test_timeout_after_warehouse_commit_recovers_from_state_without_retry(self):
        api = TimeoutAfterWarehouseCommitApiClient()
        with contextlib.redirect_stdout(io.StringIO()):
            run = MosOptimizationWorkflow(api, WorkflowSettings()).run(42)

        self.assertEqual(run.mode, "fresh")
        self.assertEqual(api.calls.count("adjust_materials_altawin"), 1)
        self.assertEqual(run.materials_response["outlay_id"], 81)
        self.assertEqual(run.materials_response["supply_id"], 82)
        self.assertEqual(run.final_state["missing_cell_count"], 0)

    def test_second_run_does_not_reserve_remainders_again(self):
        api = FakeApiClient()
        workflow = MosOptimizationWorkflow(api, WorkflowSettings())
        with contextlib.redirect_stdout(io.StringIO()):
            first = workflow.run(42)
            second = workflow.run(42)

        self.assertEqual(first.mode, "fresh")
        self.assertEqual(second.mode, "noop")
        self.assertEqual(api.calls.count("upload_mos_data"), 1)
        self.assertEqual(api.calls.count("adjust_materials_altawin"), 1)

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

    def test_inconsistent_state_has_controlled_resume_stage_and_save_exit_code(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = self.write_config(Path(temporary))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = runner.main(
                    ["42", "--config", str(config)],
                    api_client_factory=InconsistentApiClient,
                )

        result = json.loads(output.getvalue())
        self.assertEqual(code, runner.EXIT_SAVE_ERROR)
        self.assertEqual(result["stage"], "warehouse/resume")
        self.assertIn("OUTLAYID=[19024]", result["error"])

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
