import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

import io
import pandas as pd
import streamlit as st

from common.dates import convert_minguo_date, get_value as _get_value
from common.utils import safe_div
from common.classifier import classify
from common.cleaning import defensive_clean_series

_CACHE_VER = "v8"  # spinner 顯示用；真正 bust cache 的是函式內的 _VER，兩者都要 bump


@st.cache_data(ttl=3600, show_spinner=f"🚀 正在執行智慧分析 ({_CACHE_VER})...")
def process_excel_final(file_bytes: bytes, thresholds: dict, sheets: dict):
    _VER = "v8"  # bump when classifier.py logic changes; this string IS in bytecode
    try:
        with pd.ExcelFile(io.BytesIO(file_bytes)) as xls:
            if not all(s in xls.sheet_names for s in sheets.values()):
                raise ValueError("Excel 缺少必要工作表，請檢查分頁名稱。")
            df_m_raw = pd.read_excel(
                xls, sheet_name=sheets["MAIN"], dtype={"社號": str, "年月": str}
            )
            df_l_raw = pd.read_excel(
                xls, sheet_name=sheets["LOAN"], dtype={"社號": str, "年月": str}
            )
            df_r_raw = pd.read_excel(
                xls,
                sheet_name=sheets["REGION"],
                dtype={"社名": str, "區域": str, "密碼": str},
            )
            df_l_raw = df_l_raw.rename(columns={"收支比": "開支比"})
    except Exception as e:
        raise ValueError(f"解析失敗: {e}")

    region_map = dict(zip(df_r_raw["社名"], df_r_raw["區域"]))
    pw_to_info = {
        str(p)
        .strip()
        .replace(".0", ""): {"name": str(n).strip(), "region": str(r).strip()}
        for n, r, p in zip(df_r_raw["社名"], df_r_raw["區域"], df_r_raw["密碼"])
        if pd.notna(n) and pd.notna(r) and pd.notna(p)
    }

    df_m_raw["年月"] = df_m_raw["年月"].apply(convert_minguo_date)
    df_l_raw["年月"] = df_l_raw["年月"].apply(convert_minguo_date)
    for col in ["社員數", "股金", "貸放比"]:
        df_m_raw[col] = pd.to_numeric(df_m_raw[col], errors="coerce").fillna(0)

    df_m_raw["儲蓄率"] = defensive_clean_series(
        pd.to_numeric(df_m_raw["儲蓄率"], errors="coerce").fillna(0), "儲蓄率"
    )
    df_l_raw["逾放比"] = pd.to_numeric(df_l_raw["逾放比"], errors="coerce").fillna(0)
    df_l_raw["逾期貸款"] = pd.to_numeric(df_l_raw["逾期貸款"], errors="coerce").fillna(
        0
    )
    df_l_raw["開支比"] = defensive_clean_series(
        pd.to_numeric(df_l_raw["開支比"], errors="coerce").fillna(0), "開支比"
    )
    if "提撥率" in df_l_raw.columns:
        _no_ovd_mask = df_l_raw["提撥率"].astype(str).str.contains("無逾期", na=False)
        df_l_raw["提撥率"] = pd.to_numeric(df_l_raw["提撥率"], errors="coerce").fillna(
            0
        )
        df_l_raw.loc[_no_ovd_mask, "提撥率"] = -1.0
    else:
        df_l_raw["提撥率"] = 0.0

    df_m = df_m_raw.dropna(subset=["年月"]).sort_values(["社號", "年月"])
    df_l = df_l_raw.dropna(subset=["年月"]).sort_values(["社號", "年月"])

    if df_m.empty:
        return pd.DataFrame(), df_m, df_l, pw_to_info, region_map

    max_d = df_m["年月"].max()
    min_d = df_m["年月"].min()
    dec_dates = df_m[df_m["年月"].dt.month == 12]["年月"]
    T0 = dec_dates.max() if not dec_dates.empty else max_d
    T1 = max(T0 - pd.DateOffset(years=1), min_d)
    T2 = max(T0 - pd.DateOffset(years=2), min_d)
    T3 = max(T0 - pd.DateOffset(years=3), min_d)
    T_12M = max_d - pd.DateOffset(months=12)

    rows = []
    for s_no in df_m["社號"].unique():
        ms = df_m[df_m["社號"] == s_no]
        ls = df_l[df_l["社號"] == s_no]
        if ms.empty:
            continue
        name = ms["社名"].iloc[0]

        M0, M1, M2, M3 = (_get_value(ms, "社員數", t) for t in (T0, T1, T2, T3))
        S0, S1, S2, S3 = (_get_value(ms, "股金", t) for t in (T0, T1, T2, T3))
        R0, R1 = _get_value(ls, "開支比", T0), _get_value(ls, "開支比", T1)
        O0, O1 = _get_value(ls, "逾期貸款", T0), _get_value(ls, "逾期貸款", T1)
        eOvd = _get_value(ls, "逾放比", T0)
        eLoan = _get_value(ms, "貸放比", T0)
        sLoan = _get_value(ms, "貸放比", T1)
        memG = safe_div(M0 - M1, M1)
        shrG = safe_div(S0 - S1, S1)

        p = dict(
            M0=M0,
            M1=M1,
            M2=M2,
            M3=M3,
            S0=S0,
            S1=S1,
            S2=S2,
            S3=S3,
            R0=R0,
            R1=R1,
            O0=O0,
            O1=O1,
            eOvd=eOvd,
            sOvd=_get_value(ls, "逾放比", T1),
            eLoan=eLoan,
            sLoan=sLoan,
            memG=memG,
            shrG=shrG,
        )
        status, reason = classify(p, thresholds)

        curr_M = _get_value(ms, "社員數", max_d)
        curr_S = _get_value(ms, "股金", max_d)
        curr_eLoan = _get_value(ms, "貸放比", max_d)
        curr_eOvd = _get_value(ls, "逾放比", max_d)
        curr_R = _get_value(ls, "開支比", max_d)
        eOvd_12m = _get_value(ls, "逾放比", T_12M)
        M_12m = _get_value(ms, "社員數", T_12M)
        S_12m = _get_value(ms, "股金", T_12M)
        memG_curr = safe_div(curr_M - M_12m, M_12m)
        shrG_curr = safe_div(curr_S - S_12m, S_12m)

        rows.append(
            {
                "社號": s_no,
                "社名": name,
                "區域": region_map.get(name, "未分類"),
                "診斷狀態": status,
                "建議留意事項": reason,
                "現有社員": curr_M,
                "社員成長數(12M)": curr_M - M_12m,
                "社員成長率(12M)": memG_curr,
                "現有股金": curr_S,
                "股金成長率(12M)": shrG_curr,
                "貸放比": curr_eLoan,
                "儲蓄率": _get_value(ms, "儲蓄率", max_d),
                "逾放比(12M)": eOvd_12m,
                "逾放比": curr_eOvd,
                "開支比": curr_R,
                "開支比(年)": R0,
                "提撥率": float(ls.iloc[-1]["提撥率"]) if not ls.empty else 0.0,
                "_sM": M_12m,
                "_sS": S_12m,
            }
        )

    return pd.DataFrame(rows).fillna(0), df_m, df_l, pw_to_info, region_map
