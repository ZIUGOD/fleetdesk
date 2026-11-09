from __future__ import annotations

import os
import shutil
import time
from collections.abc import Callable
from pathlib import Path

from fleetdesk.data.models import FileStatus
from fleetdesk.data.repository import DataRepository, list_workbooks, period_sort_key
from fleetdesk.data.workbook import read_workbook
from tests.conftest import SAMPLE_TRIPS


def _touch(path: Path) -> None:
    later = time.time() + 10
    os.utime(path, (later, later))


def test_cached_dataset_is_reused_until_the_file_changes(sample_workbook: Path) -> None:
    reads: list[str] = []

    def counting_reader(path: str):  # type: ignore[no-untyped-def]
        reads.append(path)
        return read_workbook(path)

    repo = DataRepository(reader=counting_reader)
    first = repo.load(str(sample_workbook))
    assert repo.load(str(sample_workbook)) is first
    assert len(reads) == 1

    _touch(sample_workbook)
    assert repo.load(str(sample_workbook)) is not first
    assert len(reads) == 2


def test_file_handle_is_released_after_reading(sample_workbook: Path) -> None:
    DataRepository().load(str(sample_workbook))
    sample_workbook.unlink()  # fails on Windows if the workbook were still open


def test_folder_merges_workbooks_and_skips_lock_files(
    tmp_path: Path, make_workbook: Callable[..., Path]
) -> None:
    make_workbook("2026-08/aug.xlsx", month=8)
    make_workbook("2026-09/sep.xlsx", month=9)
    (tmp_path / "~$aug.xlsx").write_text("lock")
    (tmp_path / "notes.txt").write_text("not a workbook")

    dataset = DataRepository().load(str(tmp_path))

    assert [f.name for f in dataset.files] == [
        os.path.join("2026-08", "aug.xlsx"),
        os.path.join("2026-09", "sep.xlsx"),
    ]
    assert len(dataset.freights) == 2 * SAMPLE_TRIPS
    assert dataset.periods == ["SET/2026", "AGO/2026"]
    assert dataset.duplicated_freights == 0


def test_copies_of_a_workbook_are_flagged_as_duplicates(
    tmp_path: Path, sample_workbook: Path
) -> None:
    shutil.copy(sample_workbook, tmp_path / "Cópia de fretes.xlsx")

    dataset = DataRepository().load(str(tmp_path))

    assert sorted(f.duplicated_freights for f in dataset.files) == [0, SAMPLE_TRIPS]


def test_identical_rows_inside_one_workbook_are_not_duplicates(sample_workbook: Path) -> None:
    dataset = DataRepository().load(str(sample_workbook))
    assert dataset.duplicated_freights == 0


def test_unreadable_workbook_is_reported_without_breaking_the_rest(
    tmp_path: Path, sample_workbook: Path
) -> None:
    (tmp_path / "corrupt.xlsx").write_bytes(b"not really a zip file")

    dataset = DataRepository().load(str(tmp_path))
    statuses = {f.name: f.status for f in dataset.files}

    assert statuses["corrupt.xlsx"] is FileStatus.ERROR
    assert statuses[sample_workbook.name] is FileStatus.OK
    assert len(dataset.freights) == SAMPLE_TRIPS


def test_list_workbooks_accepts_a_single_file(sample_workbook: Path) -> None:
    assert list_workbooks(str(sample_workbook)) == [str(sample_workbook)]


def test_periods_sort_chronologically() -> None:
    periods = ["SET/2026", "JAN/2027", "DEZ/2025", "OUT/2026"]
    assert sorted(periods, key=period_sort_key) == ["DEZ/2025", "SET/2026", "OUT/2026", "JAN/2027"]
