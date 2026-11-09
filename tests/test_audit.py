from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from fleetdesk.data.audit import Severity, _probably_same_name, run_audit
from fleetdesk.data.models import Dataset
from fleetdesk.data.repository import DataRepository
from fleetdesk.sample_data import PLANTED_MISTAKES, build_workbook


def _load(path: Path) -> Dataset:
    return DataRepository().load(str(path))


@pytest.fixture
def clean_dataset(tmp_path: Path) -> Dataset:
    return _load(build_workbook(tmp_path / "clean.xlsx", 2026, 9, trips=200))


@pytest.fixture
def faulty_dataset(tmp_path: Path) -> Dataset:
    return _load(build_workbook(tmp_path / "faulty.xlsx", 2026, 9, trips=200, mistakes=True))


def test_clean_sample_has_no_errors_or_warnings(clean_dataset: Dataset) -> None:
    report = run_audit(clean_dataset)
    assert report.attention_count == 0, [f.title for f in report.findings]


def test_every_planted_mistake_is_found(faulty_dataset: Dataset) -> None:
    codes = {f.code for f in run_audit(faulty_dataset).findings if f.severity != Severity.INFO}
    assert codes == set(PLANTED_MISTAKES)


def test_findings_point_to_the_workbook_row(faulty_dataset: Dataset) -> None:
    typo = next(f for f in run_audit(faulty_dataset).findings if f.code == "weight_typo")
    issue = typo.issues[0]
    freight = next(f for f in faulty_dataset.freights if f.ref == issue.ref)

    assert issue.ref is not None
    assert (issue.ref.file, issue.ref.tab) == ("faulty.xlsx", "LANÇAMENTOS")
    assert freight.weight_t < 10
    assert typo.severity == Severity.ERROR
    assert typo.impact and typo.impact > 0


def test_findings_are_ordered_by_severity(faulty_dataset: Dataset) -> None:
    ranks = [f.severity.rank for f in run_audit(faulty_dataset).findings]
    assert ranks == sorted(ranks)


def test_broken_totals_and_dates_are_errors(clean_dataset: Dataset) -> None:
    first, second = clean_dataset.freights[:2]
    clean_dataset.freights[0] = replace(first, gross_revenue=first.gross_revenue + 500)
    clean_dataset.freights[1] = replace(second, period="JAN/2026")

    codes = {f.code for f in run_audit(clean_dataset).findings}
    assert {"freight_math", "date_outside_period"} <= codes


def test_payroll_is_cross_checked_with_freights(clean_dataset: Dataset) -> None:
    summary = clean_dataset.payroll[0]
    clean_dataset.payroll[0] = replace(summary, trips=summary.trips + 3)

    mismatch = next(f for f in run_audit(clean_dataset).findings if f.code == "payroll_mismatch")
    assert summary.driver in mismatch.issues[0].who


def test_period_filter_limits_the_audit(tmp_path: Path) -> None:
    build_workbook(tmp_path / "aug.xlsx", 2026, 8, trips=60, mistakes=True)
    build_workbook(tmp_path / "sep.xlsx", 2026, 9, trips=60)
    dataset = _load(tmp_path)

    assert run_audit(dataset, "SET/2026").attention_count == 0
    assert run_audit(dataset, "AGO/2026").attention_count > 0


@pytest.mark.parametrize(
    ("a", "b", "same"),
    [
        ("VALE NORTE", "VALE NORTE ENGENHARIA", True),
        ("PÓ DE BRITA", "Po de  brita", True),
        ("PEDREIRA SANTA LUZIA", "PEDREIRA SANTA LUSIA", True),
        ("AREIA", "AREIA LAVADA", False),
        ("BRITA 0", "BRITA 1", False),
        ("LOTE 3", "LOTE 5", False),
    ],
)
def test_name_variants(a: str, b: str, same: bool) -> None:
    assert _probably_same_name(a, b) is same
