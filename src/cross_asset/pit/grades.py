"""Point-in-time evidence grading for data acceptance."""
from __future__ import annotations

from enum import Enum
from typing import Any


class PITGrade(str, Enum):
    A = "A"  # true vintage/revision history
    B = "B"  # actual release timestamp
    C = "C"  # documented conservative lag
    D = "D"  # observation date only


def classify_pit_grade(entry: dict[str, Any]) -> tuple[PITGrade | None, list[str]]:
    """Classify only what the manifest evidence proves; never infer an upgrade."""
    rule = str(entry.get("vintage_rule", "")).strip().lower()
    available = str(entry.get("available_at_rule", "")).strip().lower()
    explicit = str(entry.get("pit_grade", "")).strip().upper()
    if explicit in {grade.value for grade in PITGrade}:
        grade = PITGrade(explicit)
        if grade is PITGrade.A and not any(word in rule for word in ("true", "vintage", "revision")):
            return None, ["pit_grade_a_evidence_missing"]
        if grade is PITGrade.B and not any(word in available for word in ("release", "timestamp", "publish")):
            return None, ["pit_grade_b_evidence_missing"]
        if grade is PITGrade.C and not any(word in available + rule for word in ("lag", "delay", "conservative")):
            return None, ["pit_grade_c_evidence_missing"]
        if grade is PITGrade.D and not any(word in available + rule for word in ("observation", "date-only", "date only")):
            return None, ["pit_grade_d_evidence_missing"]
        return grade, []
    if any(word in rule for word in ("true vintage", "vintage history", "revision history")):
        return PITGrade.A, []
    if any(word in available for word in ("actual release", "release timestamp", "publication timestamp")):
        return PITGrade.B, []
    if any(word in available + rule for word in ("conservative lag", "documented lag", "release lag")):
        return PITGrade.C, ["pit_grade_c_warning"]
    if any(word in available + rule for word in ("observation date only", "observation-date-only", "date only")):
        return PITGrade.D, ["pit_grade_d_research_only"]
    return None, ["pit_grade_unknown"]


def validate_pit_grade(grade: str | PITGrade | None, status: str, gates: dict[str, str]) -> tuple[bool, list[str]]:
    value = str(grade.value if isinstance(grade, PITGrade) else grade or "").upper()
    errors: list[str] = []
    if value not in {g.value for g in PITGrade}:
        errors.append("pit_grade_unknown")
    if status == "PASS":
        if any(gates.get(name) != "PASS" for name in ("TECH", "LEGAL", "PIT", "STABILITY")):
            errors.append("pass_requires_all_gates")
        if value not in {PITGrade.A.value, PITGrade.B.value}:
            errors.append("pass_requires_pit_grade_a_or_b")
    return not errors, errors
