import io

import pandas as pd
import pytest

from data.excel_processor import _get_value, process_excel_final


def _make_df(months, values, col="社員數"):
    return pd.DataFrame(
        {
            "年月": [
                pd.Timestamp(f"20{m}-01-01") if isinstance(m, str) else m
                for m in months
            ],
            col: values,
        }
    )


class TestGetValue:
    def test_empty_df_returns_zero(self):
        df = pd.DataFrame(columns=["年月", "社員數"])
        assert _get_value(df, "社員數", pd.Timestamp("2023-01-01")) == 0.0

    def test_returns_last_value_before_date(self):
        df = _make_df(
            [
                pd.Timestamp("2023-01-01"),
                pd.Timestamp("2023-06-01"),
                pd.Timestamp("2023-12-01"),
            ],
            [100, 200, 300],
        )
        result = _get_value(df, "社員數", pd.Timestamp("2023-06-01"))
        assert result == pytest.approx(200.0)

    def test_returns_last_value_strictly_before(self):
        df = _make_df(
            [pd.Timestamp("2023-01-01"), pd.Timestamp("2023-06-01")],
            [100, 200],
        )
        result = _get_value(df, "社員數", pd.Timestamp("2023-03-01"))
        assert result == pytest.approx(100.0)

    def test_no_matching_date_returns_zero(self):
        df = _make_df(
            [pd.Timestamp("2023-06-01"), pd.Timestamp("2023-12-01")],
            [500, 600],
        )
        # 查詢日期早於所有資料 → 回傳 0.0（避免取到未來值）
        result = _get_value(df, "社員數", pd.Timestamp("2023-01-01"))
        assert result == pytest.approx(0.0)

    def test_exact_date_match(self):
        df = _make_df([pd.Timestamp("2023-12-01")], [999])
        assert _get_value(df, "社員數", pd.Timestamp("2023-12-01")) == pytest.approx(
            999.0
        )


SHEETS = {
    "MAIN": "社務及資金運用情形",
    "LOAN": "放款及逾期放款",
    "REGION": "區域分類表",
}

THRESHOLDS = {
    "high_risk_ovd": 0.1,
    "liquidity_loan": 0.9,
    "idle_loan": 0.3,
    "stable_loan_min": 0.4,
    "stable_loan_max": 0.8,
    "ovd_safe_line": 0.02,
    "high_risk_income_ratio": 1.0,
    "high_risk_loan_ratio": 0.1,
    "high_risk_ovd_ratio": 0.5,
}


def _build_excel_bytes(unions: list[dict]) -> bytes:
    """合成 3 分頁的 Excel bytes。
    unions: 每社 dict 含 社號/社名/密碼，並內含 MAIN、LOAN 兩表的月度資料。
    """
    main_rows, loan_rows, region_rows = [], [], []
    for u in unions:
        for month, m in u["months"].items():
            main_rows.append(
                {
                    "年月": month,
                    "社號": u["社號"],
                    "社名": u["社名"],
                    "社員數": m["社員數"],
                    "股金": m["股金"],
                    "貸放比": m["貸放比"],
                    "儲蓄率": m["儲蓄率"],
                }
            )
            loan_rows.append(
                {
                    "年月": month,
                    "社號": u["社號"],
                    "社名": u["社名"],
                    "放款總額": m["放款總額"],
                    "逾期貸款": m["逾期貸款"],
                    "逾放比": m["逾放比"],
                    "提撥率": m["提撥率"],
                    "收支比": m["收支比"],
                }
            )
        region_rows.append(
            {
                "社名": u["社名"],
                "社號": u["社號"],
                "區域": u["區域"],
                "密碼": u["密碼"],
            }
        )

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        pd.DataFrame(main_rows).to_excel(writer, sheet_name=SHEETS["MAIN"], index=False)
        pd.DataFrame(loan_rows).to_excel(writer, sheet_name=SHEETS["LOAN"], index=False)
        pd.DataFrame(region_rows).to_excel(
            writer, sheet_name=SHEETS["REGION"], index=False
        )
    return buf.getvalue()


def _make_union(
    社號: str,
    社名: str,
    *,
    member: int = 1000,
    share: int = 50_000_000,
    savings_rate: float = 0.85,
    latest_savings_rate: float | None = None,
):
    """113 全年 12 個月 + 11401；數值穩健（一般狀態）"""
    latest_savings_rate = (
        savings_rate if latest_savings_rate is None else latest_savings_rate
    )
    months = {}
    for mm in range(1, 13):
        months[f"113{mm:02d}"] = {
            "社員數": member,
            "股金": share,
            "貸放比": 0.6,
            "儲蓄率": savings_rate,
            "放款總額": 30_000_000,
            "逾期貸款": 100_000,
            "逾放比": 0.005,
            "提撥率": 0.02,
            "收支比": 0.95,
        }
    months["11401"] = {
        "社員數": member,
        "股金": share,
        "貸放比": 0.6,
        "儲蓄率": latest_savings_rate,
        "放款總額": 30_000_000,
        "逾期貸款": 100_000,
        "逾放比": 0.005,
        "提撥率": 0.02,
        "收支比": 0.95,
    }
    return {
        "社號": 社號,
        "社名": 社名,
        "區域": "北區",
        "密碼": "1234",
        "months": months,
    }


class TestProcessExcelFinal:
    """端對端覆蓋：確保 process_excel_final 完整路徑無 NameError（過去因 get_v 漏改壞過）"""

    def test_returns_five_tuple_with_correct_shapes(self):
        bytes_ = _build_excel_bytes(
            [
                _make_union("001", "A社"),
                _make_union("002", "B社"),
            ]
        )
        result = process_excel_final(bytes_, THRESHOLDS, SHEETS)
        assert isinstance(result, tuple) and len(result) == 5
        data, df_m, df_l, region_pws, region_map = result

        assert isinstance(data, pd.DataFrame) and len(data) == 2
        assert set(["社號", "社名", "診斷狀態"]).issubset(data.columns)
        assert set(df_m["社號"]) == {"001", "002"}
        assert set(df_l["社號"]) == {"001", "002"}
        assert "1234" in region_pws
        assert region_pws["1234"]["name"] in {"A社", "B社"}
        assert region_map["A社"] == "北區"
        assert region_map["B社"] == "北區"

    def test_diagnosis_status_populated(self):
        bytes_ = _build_excel_bytes([_make_union("001", "A社")])
        data, *_ = process_excel_final(bytes_, THRESHOLDS, SHEETS)
        assert data.iloc[0]["診斷狀態"] in {
            "🚨 特別關懷",
            "⚠️ 流動性緊繃",
            "💤 資金閒置",
            "✅ 穩健模範",
            "📊 一般狀態",
        }

    def test_savings_rate_uses_latest_month_not_dec(self):
        bytes_ = _build_excel_bytes(
            [_make_union("001", "A社", savings_rate=0.7, latest_savings_rate=0.9)]
        )
        data, *_ = process_excel_final(bytes_, THRESHOLDS, SHEETS)
        assert data.iloc[0]["儲蓄率"] == pytest.approx(0.9)

    def test_missing_sheet_raises_value_error(self):
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            pd.DataFrame({"x": [1]}).to_excel(
                writer, sheet_name=SHEETS["MAIN"], index=False
            )
        with pytest.raises(ValueError, match="缺少必要工作表"):
            process_excel_final(buf.getvalue(), THRESHOLDS, SHEETS)
