import csv
import zipfile

import pytest

from cross_asset.storage import init_db, stage_wind_csv
from cross_asset.storage.wind_evidence import WIND_CANONICAL


def _csv(path, rows=None):
    rows = rows or [["2026/08/28", "3.1", "50.0"], ["2026/08/29", "3.2", "50.1"]]
    metadata = [
        ["国家", "中国", "中国"],
        ["指标名称", "中国:CPI:当月同比", "中国:制造业PMI"],
        ["频率", "月", "月"],
        ["单位", "%", "%"],
        ["指标ID", "M0000612", "M0017126"],
        ["时间区间", "2020-01:2026-08", "2020-01:2026-08"],
        ["来源", "国家统计局", "国家统计局"],
    ]
    with path.open("w", newline="", encoding="gb18030") as stream:
        writer = csv.writer(stream)
        writer.writerows(metadata + rows)


def test_wind_csv_stages_long_form_and_is_idempotent(tmp_path):
    path = tmp_path / "wind.csv"
    _csv(path)
    store = init_db(":memory:")
    first = stage_wind_csv(store, path)
    second = stage_wind_csv(store, path)
    assert first["new_rows"] == 4
    assert second["new_rows"] == 0
    assert store.conn.execute("select count(*) from wind_evidence_staging").fetchone()[0] == 4
    assert store.conn.execute("select count(*) from observations").fetchone()[0] == 0
    assert store.conn.execute("select count(*) from wind_evidence_staging where available_at is null and vintage_date is null").fetchone()[0] == 4


def test_wind_semantic_candidates_do_not_silently_change_units(tmp_path):
    path = tmp_path / "wind.csv"
    _csv(path)
    store = init_db(":memory:")
    stage_wind_csv(store, path)
    pmi = store.conn.execute("select canonical_candidate,quality_status from wind_evidence_staging where source_series_id='M0017126' limit 1").fetchone()
    assert pmi == ("CN_PMI", "SEMANTIC_UNIT_REVIEW_REQUIRED")


def test_china_ten_year_bond_mapping_uses_export_metadata_id():
    assert WIND_CANONICAL["M1001654"] == "CN_BOND_10Y"
    assert "M1001646" not in WIND_CANONICAL


def test_wind_xlsx_stages_comparable_series_separately(tmp_path):
    path = tmp_path / "index.xlsx"
    shared = """<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>日期</t></si><si><t>300收益['H00300]</t></si><si><t>中证1000全收益(可比)['H00852]</t></si></sst>"""
    sheet = """<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="s"><v>2</v></c></row><row r="2"><c r="A2"><v>40182</v></c><c r="B2"><v>100</v></c><c r="C2"><v>101</v></c></row></sheetData></worksheet>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/sharedStrings.xml", shared)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    from cross_asset.storage import stage_wind_xlsx

    store = init_db(":memory:")
    result = stage_wind_xlsx(store, path)
    assert result["candidate_rows"] == 2
    rows = store.conn.execute("select source_series_id,canonical_candidate from wind_evidence_staging order by source_series_id").fetchall()
    assert rows == [("H00300", "CN_EQ_LARGE"), ("H00852__COMPARABLE", None)]
    assert store.conn.execute("select count(*) from observations").fetchone()[0] == 0


def test_wind_csv_invalid_value_rolls_back(tmp_path):
    path = tmp_path / "wind.csv"
    _csv(path, [["2026/08/28", "not-a-number", "50.0"]])
    store = init_db(":memory:")
    with pytest.raises(ValueError, match="invalid Wind CSV value"):
        stage_wind_csv(store, path)
    assert store.conn.execute("select count(*) from wind_evidence_staging").fetchone()[0] == 0
