import csv
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
import yaml

from cross_asset.ingestion.production_csv import ingest_production_csv
from cross_asset.ingestion.wind_canonicalizer import (
    WindCanonicalizerError,
    canonicalize_wind_export,
)


def _mapping(tmp_path, code="000300.SH", rule="CN_EQ_EOD_V1"):
    path = tmp_path / "mapping.yml"
    path.write_text(yaml.safe_dump({"CN_EQ_LARGE": {"source_series_id": code, "available_at_rule": rule, "available_at_basis": "POLICY_DERIVED"}}, sort_keys=False), encoding="utf-8")
    return path


def _xlsx(tmp_path, rows):
    path = tmp_path / "raw.xlsx"
    def cell_ref(row, column):
        letters = ""
        while column:
            column, remainder = divmod(column - 1, 26)
            letters = chr(65 + remainder) + letters
        return f"{letters}{row}"

    cells = []
    for row_number, row in enumerate(rows, 1):
        row_cells = []
        for column_number, value in enumerate(row, 1):
            if value is None:
                continue
            text = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            row_cells.append(f'<c r="{cell_ref(row_number, column_number)}" t="inlineStr"><is><t>{text}</t></is></c>')
        cells.append(f'<row r="{row_number}">{"".join(row_cells)}</row>')
    sheet = '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + "".join(cells) + "</sheetData></worksheet>"
    content_types = '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>'
    workbook = '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>'
    rels = '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return path


def test_pattern_d_uses_labels_supports_multiple_series_and_sorts(tmp_path):
    path = _xlsx(tmp_path, [
        ["频率", "日", "日"], ["来源", "Wind", "Wind"], ["指标名称", "沪深300", "沪深300"],
        ["单位", "点", "点"], ["Wind code", "000300.SH", "000301.SH"],
        ["2026-09-03", 103, 104], ["2026-09-01", 101, 102], ["2026-09-02", 102, 103],
        ["数据来源：Wind", None, None],
    ])
    mapping = _mapping(tmp_path)
    mapping.write_text(yaml.safe_dump({
        "CN_EQ_LARGE": {"source_series_id": "000300.SH", "available_at_rule": "CN_EQ_EOD_V1", "available_at_basis": "POLICY_DERIVED"},
        "CN_EQ_SMALL": {"source_series_id": "000301.SH", "available_at_rule": "CN_EQ_EOD_V1", "available_at_basis": "POLICY_DERIVED"},
    }, sort_keys=False), encoding="utf-8")
    result = canonicalize_wind_export(path, mapping=mapping, dry_run=True)
    assert result["format"] == "WIND_PATTERN_D_XLSX_V1"
    assert {item["status"] for item in result["series"]} == {"READY"}
    assert result["canonical_rows"] == 6
    assert result["series"][0]["date_min"] == "2026-09-01"


def test_legacy_wide_header_selects_h00300_total_return_and_hsi_price(tmp_path):
    path = _xlsx(
        tmp_path,
        [
            ["日期", "300收益['H00300]", "恒生指数(可比)['HSI]", "恒生指数['HSI]"],
            [43835, 100.0, 200.0, 300.0],
            [43836, 101.0, 201.0, 301.0],
            ["数据来源：Wind", None, None, None],
        ],
    )
    mapping = tmp_path / "mapping.yml"
    mapping.write_text(
        yaml.safe_dump(
            {
                "CN_EQ_LARGE": {
                    "source_series_id": "H00300",
                    "available_at_rule": "CN_EQ_EOD_V1",
                    "available_at_basis": "POLICY_DERIVED",
                },
                "HK_EQ": {
                    "source_series_id": "HSI",
                    "available_at_rule": "HK_EQ_EOD_V1",
                    "available_at_basis": "POLICY_DERIVED",
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    result = canonicalize_wind_export(path, mapping=mapping, dry_run=True)

    assert result["format"] == "WIND_PATTERN_A_HEADER_XLSX_V1"
    assert result["canonical_rows"] == 4
    ready = {
        item["wind_code"]: item
        for item in result["series"]
        if item["status"] == "READY"
    }
    assert set(ready) == {"H00300", "HSI"}
    assert ready["H00300"]["return_type"] == "total_return"
    assert ready["HSI"]["return_type"] == "price"
    assert any(
        item["wind_code"] == "HSI__COMPARABLE"
        and item["status"] == "UNRESOLVED_MAPPING"
        for item in result["series"]
    )


def test_wide_csv_reads_gb18030_metadata_and_skips_non_date_rows(tmp_path):
    path = tmp_path / "wind-wide.csv"
    rows = [
        ["国家", "中国", "中国"],
        ["指标名称", "沪深300", "中国国债收益率:10年"],
        ["频率", "日", "日"],
        ["单位", "点", "%"],
        ["指标ID", "H00300", "M1001654"],
        ["时间区间", "2010-01-04:2026-08-31", "2007-12-14:2026-08-31"],
        ["来源", "中证指数公司", "中国货币网"],
        ["更新时间", "2026-09-04", "2026-09-04"],
        ["2026-08-31", "4000", "2.1"],
        ["数据来源：Wind", "", ""],
    ]
    with path.open("w", encoding="gb18030", newline="") as handle:
        csv.writer(handle).writerows(rows)

    mapping = tmp_path / "mapping.yml"
    mapping.write_text(
        yaml.safe_dump(
            {
                "CN_EQ_LARGE": {
                    "source_series_id": "H00300",
                    "available_at_rule": "CN_EQ_EOD_V1",
                    "available_at_basis": "POLICY_DERIVED",
                },
                "CN_BOND_10Y": {
                    "source_series_id": "M1001654",
                    "available_at_rule": "CN_BOND_10Y_EOD_V1",
                    "available_at_basis": "POLICY_DERIVED",
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    result = canonicalize_wind_export(path, mapping=mapping, dry_run=True)

    assert result["format"] == "WIND_PATTERN_D_WIDE_CSV_V1"
    assert result["status"] == "READY"
    assert result["canonical_rows"] == 2
    assert {item["wind_code"] for item in result["series"]} == {
        "H00300",
        "M1001654",
    }


def test_legacy_xls_is_explicitly_non_blocking_for_supported_inputs(tmp_path):
    path = tmp_path / "legacy.xls"
    path.write_bytes(b"legacy workbook is intentionally not parsed")

    with pytest.raises(WindCanonicalizerError, match="UNSUPPORTED_LEGACY") as exc_info:
        canonicalize_wind_export(path, mapping=_mapping(tmp_path), dry_run=True)

    assert exc_info.value.code == "UNSUPPORTED_LEGACY"


def test_blank_is_omitted_without_forward_fill_and_csv_is_importer_valid(tmp_path):
    path = _xlsx(tmp_path, [["指标名称", "沪深300"], ["频率", "日"], ["单位", "点"], ["Wind code", "000300.SH"],
                           ["2026-09-01", 100], ["2026-09-02", None], ["2026-09-03", 102]])
    output = tmp_path / "canonical.csv"
    result = canonicalize_wind_export(path, mapping=_mapping(tmp_path), output=output)
    assert result["canonical_rows"] == 2
    assert result["series"][0]["omitted_missing_rows"] == 1
    rows = list(csv.DictReader(output.open(encoding="utf-8", newline="")))
    assert [row["value"] for row in rows] == ["100.0", "102.0"]
    assert ingest_production_csv(output, dry_run=True)["status"] == "VALID"


def test_invalid_value_duplicate_and_unresolved_mapping_fail_closed(tmp_path):
    invalid = _xlsx(tmp_path, [["Wind code", "UNKNOWN"], ["2026-09-01", "abc"]])
    result = canonicalize_wind_export(invalid, mapping=_mapping(tmp_path), dry_run=True)
    assert result["status"] == "PARTIAL"
    assert result["series"][0]["status"] == "UNRESOLVED_MAPPING"

    duplicate = _xlsx(tmp_path, [["Wind code", "000300.SH"], ["2026-09-01", 1], ["2026-09-01", 2]])
    result = canonicalize_wind_export(duplicate, mapping=_mapping(tmp_path), dry_run=True)
    assert result["series"][0]["status"] == "DUPLICATE_OBSERVATION"

    invalid = _xlsx(tmp_path, [["Wind code", "000300.SH"], ["2026-09-01", "abc"]])
    result = canonicalize_wind_export(invalid, mapping=_mapping(tmp_path), dry_run=True)
    assert result["series"][0]["status"] == "INVALID_VALUE"


def test_pit_policy_is_derived_and_report_preserves_metadata(tmp_path):
    path = _xlsx(tmp_path, [["instrument name", "CSI"], ["frequency", "daily"], ["unit", "points"],
                           ["Wind code", "000300.SH"], ["2026-09-02", 1]])
    result = canonicalize_wind_export(path, mapping=_mapping(tmp_path), dry_run=True)
    series = result["series"][0]
    assert series["instrument_name"] == "CSI"
    assert series["available_at_basis"] == "POLICY_DERIVED"
    assert result["dry_run"] is True


def test_mapping_cannot_override_policy_derived_basis(tmp_path):
    path = _xlsx(tmp_path, [["Wind code", "000300.SH"], ["2026-09-02", 1]])
    mapping = _mapping(tmp_path)
    mapping.write_text(
        yaml.safe_dump(
            {
                "CN_EQ_LARGE": {
                    "source_series_id": "000300.SH",
                    "available_at_rule": "CN_EQ_EOD_V1",
                    "available_at_basis": "VENDOR_TIMESTAMP",
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(WindCanonicalizerError, match="POLICY_DERIVED"):
        canonicalize_wind_export(path, mapping=mapping, dry_run=True)


@pytest.mark.parametrize("rule, expected", [
    ("CN_EQ_EOD_V1", "2026-09-02T16:00:00+08:00"),
    ("HK_EQ_EOD_V1", "2026-09-02T16:30:00+08:00"),
    ("US_EQ_EOD_V1", "2026-09-03T06:00:00+08:00"),
    ("CN_BOND_10Y_EOD_V1", "2026-09-02T18:00:00+08:00"),
    ("COMEX_EOD_V1", "2026-09-03T06:00:00+08:00"),
])
def test_all_v1_pit_policies_are_deterministic(tmp_path, rule, expected):
    path = _xlsx(tmp_path, [["Wind code", "000300.SH"], ["2026-09-02", 1]])
    output = tmp_path / f"{rule}.csv"
    result = canonicalize_wind_export(path, mapping=_mapping(tmp_path, rule=rule), output=output)
    assert result["series"][0]["available_at_rule"] == rule
    assert result["series"][0]["available_at_basis"] == "POLICY_DERIVED"
    assert next(csv.DictReader(output.open(encoding="utf-8")))["available_at"] == expected
