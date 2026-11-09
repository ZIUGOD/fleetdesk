"""Load the data source (a workbook or a folder of workbooks) with change-aware caching."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path

from fleetdesk.data.models import Dataset, FileStatus, Freight, SourceFile, WorkbookData
from fleetdesk.data.workbook import read_workbook

WORKBOOK_EXTENSIONS = (".xlsx", ".xlsm")
_MONTHS = ("JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ")

FileVersion = tuple[int, int]  # (mtime_ns, size)


def list_workbooks(source: str) -> list[str]:
    """Workbooks of a source: the file itself, or every workbook under the folder."""
    if os.path.isfile(source):
        return [source]
    found: list[str] = []
    for root, dirs, names in os.walk(source):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in sorted(names):
            # "~$" files are lock files Excel creates while a workbook is open.
            if name.lower().endswith(WORKBOOK_EXTENSIONS) and not name.startswith("~$"):
                found.append(os.path.join(root, name))
    return found


def period_sort_key(period: str) -> tuple[int, int]:
    """Chronological key for labels like ``SET/2026``; unknown labels sort first."""
    try:
        month, year = period.split("/")
        return int(year), _MONTHS.index(month.strip().upper()[:3])
    except ValueError:
        return 0, 0


class DataRepository:
    """Thread-safe cache: each workbook is re-read only when its size or mtime changes."""

    def __init__(self, reader: Callable[[str], WorkbookData] = read_workbook) -> None:
        self._reader = reader
        self._lock = threading.Lock()
        self._files: dict[str, tuple[FileVersion, WorkbookData]] = {}
        self._dataset_key: tuple[object, ...] | None = None
        self._dataset: Dataset | None = None

    def load(self, source: str) -> Dataset:
        versions: list[tuple[str, FileVersion]] = []
        for path in list_workbooks(source):
            try:
                stat = os.stat(path)
            except OSError:
                continue
            versions.append((path, (stat.st_mtime_ns, stat.st_size)))
        key = (source, tuple(versions))

        with self._lock:
            if self._dataset is None or self._dataset_key != key:
                workbooks = [self._read_cached(path, version) for path, version in versions]
                self._dataset = merge(source, workbooks)
                self._dataset_key = key
            return self._dataset

    def invalidate(self) -> None:
        with self._lock:
            self._files.clear()
            self._dataset_key = None

    def _read_cached(self, path: str, version: FileVersion) -> WorkbookData:
        cached = self._files.get(path)
        if cached and cached[0] == version:
            return cached[1]
        try:
            data = self._reader(path)
        except Exception as exc:  # any unreadable file is reported in the UI, never fatal
            if cached and cached[1].status is FileStatus.OK:
                # Most likely caught mid-save by Excel or Drive: keep the last good read.
                return cached[1]
            data = WorkbookData(
                path=path, status=FileStatus.ERROR, reason=f"Não foi possível ler: {exc}"
            )
        self._files[path] = (version, data)
        return data


def _freight_key(f: Freight) -> tuple[object, ...]:
    return f.date, f.invoice, f.driver, f.plate, f.weight_t, f.gross_revenue


def merge(source: str, workbooks: Iterable[WorkbookData]) -> Dataset:
    is_folder = os.path.isdir(source)
    files: list[SourceFile] = []
    dataset = Dataset(
        freights=[],
        fuel=[],
        tolls=[],
        adjustments=[],
        payroll=[],
        vehicles=[],
        files=files,
        periods=[],
        drivers=[],
        customers=[],
        materials=[],
        loaded_at=datetime.now(),
        last_modified=None,
    )
    seen: set[tuple[object, ...]] = set()

    for wb in workbooks:
        # Identical rows inside one workbook are legitimate (several trips on one invoice),
        # so only rows already seen in a *previous* workbook count as duplicates.
        keys = [_freight_key(f) for f in wb.freights]
        duplicated = sum(1 for k in keys if k in seen)
        seen.update(keys)

        dataset.freights.extend(wb.freights)
        dataset.fuel.extend(wb.fuel)
        dataset.tolls.extend(wb.tolls)
        dataset.adjustments.extend(wb.adjustments)
        dataset.payroll.extend(wb.payroll)
        dataset.vehicles.extend(wb.vehicles)
        files.append(
            SourceFile(
                name=os.path.relpath(wb.path, source) if is_folder else Path(wb.path).name,
                status=wb.status,
                reason=wb.reason,
                freights=len(wb.freights),
                duplicated_freights=duplicated,
                modified_at=wb.modified_at,
            )
        )
        if (
            wb.status is FileStatus.OK
            and wb.modified_at
            and (dataset.last_modified is None or wb.modified_at > dataset.last_modified)
        ):
            dataset.last_modified = wb.modified_at

    period_sources: list[Iterable[str]] = [
        (r.period for r in dataset.freights),
        (r.period for r in dataset.fuel),
        (r.period for r in dataset.tolls),
        (r.period for r in dataset.adjustments),
    ]
    dataset.periods = sorted(
        {p for source_periods in period_sources for p in source_periods if p},
        key=period_sort_key,
        reverse=True,
    )
    dataset.drivers = _distinct(f.driver for f in dataset.freights)
    dataset.customers = _distinct(f.customer for f in dataset.freights)
    dataset.materials = _distinct(f.material for f in dataset.freights)
    return dataset


def _distinct(values: Iterable[str]) -> list[str]:
    return sorted({v for v in values if v})
