"""Database-free tests for MOS warehouse idempotency.

All Firebird connections are fakes.  These tests must never read or mutate the
configured Altawin database.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


API_DIR = Path(__file__).resolve().parents[1]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from utils import db_functions


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class ExistingPairCursor:
    def __init__(self, *, include_supply: bool = True):
        self.include_supply = include_supply
        self.rows = []
        self.executed: list[str] = []

    def execute(self, sql, _params=()):
        normalized = " ".join(sql.split()).upper()
        self.executed.append(normalized)
        if "FROM GRORDERS_MOS" in normalized and "WITH LOCK" in normalized:
            self.rows = [("263",)]
        elif "FROM OUTLAY" in normalized and "TRIM(RCOMMENT)" in normalized:
            self.rows = [(19024, 0, 0, "{PAIR-GUID}")]
        elif "FROM SUPPLY" in normalized and "TRIM(RCOMMENT)" in normalized:
            self.rows = (
                [(12679, 0, 0, "{PAIR-GUID}")] if self.include_supply else []
            )
        else:
            raise AssertionError(f"Unexpected SQL before idempotent return: {normalized}")

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


class ApprovalCursor:
    def __init__(self, header_row, *, update_error: Exception | None = None):
        self.header_row = header_row
        self.update_error = update_error
        self.rows = []
        self.executed: list[str] = []

    def execute(self, sql, _params=()):
        normalized = " ".join(sql.split()).upper()
        self.executed.append(normalized)
        if normalized.startswith("SELECT DELETED, ISAPPROVED"):
            self.rows = [self.header_row]
            return
        if normalized.startswith("UPDATE OUTLAY") or normalized.startswith("UPDATE SUPPLY"):
            if self.update_error:
                raise self.update_error
            self.rows = []
            return
        raise AssertionError(f"Unexpected approval SQL: {normalized}")

    def fetchone(self):
        return self.rows[0] if self.rows else None


class PairValidationCursor:
    def __init__(self, *, outlay_detail_qty: int = 6000):
        self.outlay_detail_qty = outlay_detail_qty
        self.rows = []

    def execute(self, sql, _params=()):
        normalized = " ".join(sql.split()).upper()
        if "FROM OPTIMIZED_MOS OM" in normalized:
            self.rows = [
                # goodsid, isbar, longprof, ostat, minrest, qty, group_thick
                (500, 0, 6000, 350, 300, 1, 6000),
                (500, 1, 1200, 20, 300, 1, 6000),
            ]
        elif "FROM OUTLAYDETAIL" in normalized:
            self.rows = [(500, self.outlay_detail_qty)]
        elif "FROM OUTLAYREMAINDER" in normalized:
            self.rows = [(500, 1200, 0, 0, 1)]
        elif "FROM SUPPLYREMAINDER" in normalized:
            self.rows = [(500, 350, 0, 0, 1)]
        else:
            raise AssertionError(f"Unexpected validation SQL: {normalized}")

    def fetchall(self):
        return list(self.rows)


class MosResumeApiTests(unittest.TestCase):
    def test_pair_content_is_validated_against_persisted_maps(self):
        matches, mismatches = db_functions._validate_mos_warehouse_pair(
            PairValidationCursor(),
            263,
            {"outlay_id": 19024, "guid": "{PAIR-GUID}"},
            {"supply_id": 12679, "guid": "{PAIR-GUID}"},
        )

        self.assertTrue(matches)
        self.assertEqual(mismatches, [])

    def test_pair_content_mismatch_reports_the_document_section(self):
        matches, mismatches = db_functions._validate_mos_warehouse_pair(
            PairValidationCursor(outlay_detail_qty=12000),
            263,
            {"outlay_id": 19024, "guid": "{PAIR-GUID}"},
            {"supply_id": 12679, "guid": "{PAIR-GUID}"},
        )

        self.assertFalse(matches)
        self.assertIn("OUTLAYDETAIL", mismatches[0])

    def test_adjust_materials_reuses_valid_pair_without_any_insert(self):
        cursor = ExistingPairCursor()
        connection = FakeConnection(cursor)
        with (
            patch.object(db_functions, "get_db_connection", return_value=connection),
            patch.object(
                db_functions,
                "_validate_mos_warehouse_pair",
                return_value=(True, []),
            ),
        ):
            result = db_functions.adjust_materials_for_moskitka_optimization(
                263,
                used_materials=[{"goodsid": 1, "quantity": 1}],
                business_remainders=[],
            )

        self.assertTrue(result["success"])
        self.assertTrue(result["reused"])
        self.assertEqual(result["outlay_id"], 19024)
        self.assertEqual(result["supply_id"], 12679)
        self.assertTrue(connection.committed)
        self.assertFalse(any("INSERT INTO" in sql for sql in cursor.executed))
        self.assertFalse(any("OUTLAYREMAINDER" in sql for sql in cursor.executed))

    def test_adjust_materials_rejects_half_pair_without_insert(self):
        cursor = ExistingPairCursor(include_supply=False)
        connection = FakeConnection(cursor)
        with patch.object(
            db_functions, "get_db_connection", return_value=connection
        ):
            result = db_functions.adjust_materials_for_moskitka_optimization(263)

        self.assertFalse(result["success"])
        self.assertIn("OUTLAYID=[19024]", result["error"])
        self.assertIn("SUPPLYID=[]", result["error"])
        self.assertFalse(any("INSERT INTO" in sql for sql in cursor.executed))

    def test_approve_already_approved_document_is_a_noop(self):
        cursor = ApprovalCursor((0, 1))
        connection = FakeConnection(cursor)
        with patch.object(
            db_functions, "get_db_connection", return_value=connection
        ):
            result = db_functions.approve_mos_warehouse_document(
                263, "outlay", 19024
            )

        self.assertTrue(result["success"])
        self.assertTrue(result["skipped"])
        self.assertFalse(any(sql.startswith("UPDATE") for sql in cursor.executed))

    def test_approval_error_contains_document_type_id_and_firebird_error(self):
        cursor = ApprovalCursor(
            (0, 0),
            update_error=RuntimeError("WH_CAN_NOT_USE_REMAINDER"),
        )
        connection = FakeConnection(cursor)
        with patch.object(
            db_functions, "get_db_connection", return_value=connection
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                r"outlay ID=19024.*WH_CAN_NOT_USE_REMAINDER",
            ):
                db_functions.approve_mos_warehouse_document(
                    263, "outlay", 19024
                )

        self.assertTrue(connection.rolled_back)


if __name__ == "__main__":
    unittest.main()
