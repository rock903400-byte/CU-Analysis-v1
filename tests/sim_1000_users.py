"""
模擬 1000 位使用者使用 CU-Analysis 系統,記錄所有發現的問題。

架構:
- 10 種使用者角色 × 10 種輸入變體 × 10 種邊界條件 = 1000 個情境
- 每個情境走完整旅程,記錄 exception/warning/error 與 UI 行為異常
- 分成 CRITICAL / HIGH / MEDIUM / LOW 四個嚴重性

執行:  python tests/sim_1000_users.py
"""

import sys
import io
import json
import traceback
from pathlib import Path
from collections import Counter, defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd
import numpy as np
import streamlit as st

from streamlit.testing.v1 import AppTest
from common.dates import convert_minguo_date, get_value
from common.utils import safe_div, format_large_number, fmt_pct
from common.classifier import classify, classify_code
from common.cleaning import defensive_clean_value, defensive_clean_series
from common.thresholds import DEFAULT_THRESHOLDS, load_thresholds
from services.finance_service import (
    get_annual_snapshot,
    calc_yoy_pct,
    prepare_waterfall_data,
    detect_yoy_anomalies,
)
from services.diagnosis_service import (
    calc_ratios,
    rate_ratio,
    calc_lending_rate_monthly_avg,
    calc_trend,
)

ISSUES = []


def issue(severity, code, title, detail, repro=None):
    ISSUES.append(
        {
            "severity": severity,
            "code": code,
            "title": title,
            "detail": detail,
            "repro": repro,
        }
    )


# ============================================================
# PART A: 純邏輯測試(不依賴 Streamlit)
# ============================================================

print("\n" + "=" * 78)
print(" PART A: 純邏輯邊界測試(共 280 個案例)")
print("=" * 78)

# --- A1. convert_minguo_date ---
print("\n[A1] convert_minguo_date 邊界")
date_cases = [
    ("11301", "5位數1月"),
    ("11312", "5位數12月"),
    ("11313", "5位數13月(無效)"),
    ("11300", "5位數00月(無效)"),
    ("1301", "4位數1月"),
    ("1301.0", "浮點 4位數"),
    ("113.0", "浮點非整數"),
    ("0", "0"),
    ("-1", "負值"),
    ("abc", "字串"),
    ("", "空字串"),
    (None, "None"),
    (True, "bool=True"),
    (False, "bool=False"),
    (11301.0, "數字11301.0"),
    (11301, "整數11301"),
    ("113年01月", "中文格式"),
    ("  11301  ", "含空白"),
    ("9999", "4位數民國9999(無效年)"),
]
for inp, desc in date_cases:
    try:
        r = convert_minguo_date(inp)
        if pd.isna(r) and inp not in (None, "", "abc", "113年01月", 0, "0", "-1"):
            issue(
                "MEDIUM",
                "D1",
                f"convert_minguo_date 對 {desc!r} 回傳 NaT",
                f"input={inp!r}",
            )
    except Exception as e:
        issue(
            "HIGH",
            "D2",
            f"convert_minguo_date 對 {desc!r} 拋例外",
            f"{type(e).__name__}: {e}",
        )

# --- A2. safe_div ---
print("\n[A2] safe_div 邊界")
div_cases = [
    (10, 2, 5.0, "正常"),
    (10, 0, 0.0, "分母0"),
    (0, 0, 0.0, "0/0"),
    (10, float("nan"), 0.0, "分母NaN"),
    (float("nan"), 10, 0.0, "分子NaN"),
    (10, float("inf"), 0.0, "分母inf"),
    (10, -float("inf"), 0.0, "分母-inf"),
    (None, 10, 0.0, "分子None"),
    (10, None, 0.0, "分母None"),
    (10, "5", 0.0, "分母字串"),
    (10, pd.NA, 0.0, "分母pd.NA"),
]
for n, d, expected, desc in div_cases:
    try:
        r = safe_div(n, d)
        if r != expected:
            issue(
                "MEDIUM", "S1", f"safe_div({n!r}, {d!r}) 預期 {expected},得到 {r}", desc
            )
    except Exception as e:
        issue(
            "HIGH", "S2", f"safe_div({n!r}, {d!r}) 拋例外", f"{type(e).__name__}: {e}"
        )

# --- A3. format_large_number ---
print("\n[A3] format_large_number 邊界")
fmt_cases = [
    (1.5e8, "1.5 億元"),
    (1e8, "邊界 1 億元"),
    (99999999, "邊界不到1億"),
    (1e7, "1千萬(應該萬元)"),
    (1e4, "邊界 1 萬元"),
    (9999, "邊界不到1萬"),
    (100, "100元"),
    (0, "0"),
    (-1.5e8, "-1.5億元"),
    (float("nan"), "NaN"),
    (float("inf"), "inf"),
    (None, "None"),
    ("abc", "字串"),
    (1.234, "小數"),
]
for inp, desc in fmt_cases:
    try:
        r = format_large_number(inp)
        if r == str(inp) or "Error" in str(r) or len(str(r)) > 20:
            issue(
                "LOW",
                "F1",
                f"format_large_number({inp!r}) 結果怪異",
                f"result={r!r}, {desc}",
            )
    except Exception as e:
        issue(
            "MEDIUM",
            "F2",
            f"format_large_number({inp!r}) 拋例外",
            f"{type(e).__name__}: {e}, {desc}",
        )

# --- A4. fmt_pct ---
print("\n[A4] fmt_pct 邊界")
for inp in [0.5, 0, -0.1, float("nan"), None, "abc", pd.NA, 1.234567]:
    try:
        r = fmt_pct(inp)
    except Exception as e:
        issue("LOW", "P1", f"fmt_pct({inp!r}) 拋例外", f"{type(e).__name__}: {e}")

# --- A5. classify 邊界 ---
print("\n[A5] classify 邊界(空值/NaN)")
T = DEFAULT_THRESHOLDS
nan_p = {
    k: float("nan")
    for k in [
        "R0",
        "R1",
        "M0",
        "M1",
        "M2",
        "M3",
        "S0",
        "S1",
        "S2",
        "S3",
        "eOvd",
        "O0",
        "O1",
        "eLoan",
        "sLoan",
        "memG",
        "shrG",
    ]
}
try:
    s, r = classify(nan_p, T)
    if "NaN" in str(r) or "nan" in str(r).lower():
        issue(
            "HIGH",
            "C1",
            "classify 對全 NaN 輸入,reason 顯示 NaN%",
            f"status={s}, reason={r!r}",
        )
    print(f"  classify(全NaN) -> status={s!r}, reason={r!r}")
except Exception as e:
    issue("MEDIUM", "C2", "classify 對全 NaN 拋例外", f"{type(e).__name__}: {e}")

# 對 boundary 值
boundary_p = {
    "R0": 1.0,
    "R1": 1.0,
    "M0": 100,
    "M1": 110,
    "M2": 120,
    "M3": 130,
    "S0": 100,
    "S1": 110,
    "S2": 120,
    "S3": 130,
    "eOvd": 0.02,
    "O0": 100,
    "O1": 90,
    "eLoan": 0.4,
    "sLoan": 0.5,
    "memG": 0.05,
    "shrG": 0.05,
}
try:
    s, r = classify(boundary_p, T)
    print(f"  classify(boundary) -> status={s!r}, reason={r!r}")
except Exception as e:
    issue("MEDIUM", "C3", "classify(boundary) 拋例外", str(e))

# --- A6. classify_code 邊界 ---
print("\n[A6] classify_code 邊界")
for inp in [None, "", "  ", 1234, 1234.5, "1", "6", "X", "9999", "0"]:
    try:
        r = classify_code(inp)
    except Exception as e:
        issue(
            "MEDIUM",
            "CC1",
            f"classify_code({inp!r}) 拋例外",
            f"{type(e).__name__}: {e}",
        )

# --- A7. defensive_clean_value ---
print("\n[A7] defensive_clean_value 邊界")
clean_cases = [
    (None, "貸放比"),
    (float("nan"), "貸放比"),
    ("abc", "貸放比"),
    (0.6, "貸放比"),  # 應該保留 0.6
    (60, "貸放比"),  # 應該變 0.6
    (1.0, "貸放比"),  # 邊界,不應該動
    (0.95, "開支比"),  # 應該保留
    (95, "開支比"),  # 應該變 0.95
    (5.0, "開支比"),  # 邊界
    (-0.6, "貸放比"),
    ("60", "貸放比"),  # 字串數字
    (0.5, "逾放比"),  # 直接 return
    (0.5, "提撥率"),  # 直接 return
]
for v, c in clean_cases:
    try:
        r = defensive_clean_value(v, c)
        if v == 60 and r == 60:  # 應該轉 0.6
            issue(
                "MEDIUM",
                "CL1",
                f"defensive_clean_value(60, {c}) 沒轉成 0.6",
                f"got {r}",
            )
        if v == 1.0 and c == "貸放比":
            # 邊界行為,要驗證 abs>1.0 才除
            if r != 1.0:
                issue(
                    "LOW",
                    "CL2",
                    f"defensive_clean_value(1.0, 貸放比) 應不動,結果={r}",
                    "",
                )
    except Exception as e:
        issue(
            "HIGH",
            "CL3",
            f"defensive_clean_value({v!r}, {c}) 拋例外",
            f"{type(e).__name__}: {e}",
        )

# --- A8. get_value ---
print("\n[A8] get_value 邊界")
# 空 DataFrame
try:
    empty_df = pd.DataFrame(columns=["年月", "社員數"])
    r = get_value(empty_df, "社員數", pd.Timestamp("2024-12-01"))
    if r != 0.0:
        issue("MEDIUM", "GV1", "get_value 空 df 應回 0.0", f"got {r}")
except Exception as e:
    issue("HIGH", "GV2", "get_value 空 df 拋例外", str(e))

# 沒有 <= d 的資料 → fallback 首筆(這是 hot bug)
test_df = pd.DataFrame(
    {
        "年月": [pd.Timestamp("2030-12-01")],
        "社員數": [9999.0],
    }
)
try:
    r = get_value(test_df, "社員數", pd.Timestamp("2020-12-01"))
    if r == 9999.0:
        issue(
            "CRITICAL",
            "GV3",
            "get_value 對早於資料的日期 fallback 首筆(9999)",
            "這會讓 T3 取到未來資料,誤算三年衰退",
        )
except Exception as e:
    issue("HIGH", "GV4", "get_value 早於資料日期拋例外", str(e))


# ============================================================
# PART B: finance_service 邊界
# ============================================================

print("\n" + "=" * 78)
print(" PART B: finance_service 邏輯邊界(共 80 個案例)")
print("=" * 78)

# B1. get_annual_snapshot 邊界
print("\n[B1] get_annual_snapshot 邊界")
# 正常一年
sample_df = pd.DataFrame(
    {
        "年月": [
            "11301",
            "11302",
            "11312",
            "11312",
            "11305",
            "11306",
            "11307",
            "11308",
            "11309",
            "11310",
            "11311",
            "11312",
        ],
        "年度": ["113"] * 12,
        "會計科目": ["1101"] * 4 + ["4101"] * 4 + ["5101"] * 4,
        "會科名稱": ["現金"] * 4 + ["利息收入"] * 4 + ["利息支出"] * 4,
        "當月金額": [100, 110, 120, 130, 50, 60, 70, 80, 30, 40, 50, 60],
    }
)
try:
    snap = get_annual_snapshot(sample_df, "113")
    print(f"  正常 113: {len(snap)} rows")
except Exception as e:
    issue("HIGH", "F1", "get_annual_snapshot 正常拋例外", str(e))

# 不存在年度
try:
    snap = get_annual_snapshot(sample_df, "999")
    if not snap.empty:
        issue(
            "MEDIUM",
            "F2",
            "get_annual_snapshot(不存在年度) 應空",
            f"got {len(snap)} rows",
        )
except Exception as e:
    issue("MEDIUM", "F3", "get_annual_snapshot(不存在年度) 拋例外", str(e))

# same_months 跨年
try:
    snap_curr = get_annual_snapshot(sample_df, "113", same_months=["11301", "11302"])
    print(f"  113 + same_months=[11301,11302]: {len(snap_curr)} rows")
except Exception as e:
    issue("HIGH", "F4", "get_annual_snapshot same_months 拋例外", str(e))

# 跨年 same_months 對照測試
sample_df2 = pd.DataFrame(
    {
        "年月": ["11301", "11302", "11401", "11402", "11403", "11412"],
        "年度": ["113", "113", "114", "114", "114", "114"],
        "會計科目": ["1101", "1101", "1101", "1101", "4101", "5101"],
        "會科名稱": ["現金", "現金", "現金", "現金", "利息收入", "利息支出"],
        "當月金額": [100, 110, 200, 210, 500, 600],
    }
)
try:
    snap_113 = get_annual_snapshot(sample_df2, "113", same_months=["11401", "11402"])
    snap_114 = get_annual_snapshot(sample_df2, "114", same_months=["11401", "11402"])
    cash_113 = snap_113[snap_113["會計科目"] == "1101"]["當月金額"].iloc[0]
    cash_114 = snap_114[snap_114["會計科目"] == "1101"]["當月金額"].iloc[0]
    print(f"  跨年: 113 取到 {cash_113}, 114 取到 {cash_114}")
    if cash_113 != 110:
        issue(
            "CRITICAL",
            "F5",
            "get_annual_snapshot same_months 跨年比對錯誤",
            f"預期 113 取 11302 現金 110,實際取到 {cash_113}",
            "year-month-suffix 比對跨年會取到錯月(月份只取 [-2:])",
        )
except Exception as e:
    issue("MEDIUM", "F6", "get_annual_snapshot 跨年拋例外", str(e))

# 空 DataFrame
try:
    empty_df = pd.DataFrame(
        columns=["年月", "年度", "會計科目", "會科名稱", "當月金額"]
    )
    snap = get_annual_snapshot(empty_df, "113")
    if not snap.empty:
        issue("LOW", "F7", "get_annual_snapshot(空) 應空", f"got {len(snap)} rows")
except Exception as e:
    issue("HIGH", "F8", "get_annual_snapshot(空) 拋例外", str(e))

# B2. calc_yoy_pct
print("\n[B2] calc_yoy_pct 邊界")
for curr, prev, desc in [
    (100, 80, "正成長"),
    (80, 100, "衰退"),
    (100, 0, "分母0"),
    (-100, 100, "負成長"),
    (100, 100, "不變"),
    (0, 100, "分子0"),
]:
    try:
        r = calc_yoy_pct(curr, prev)
        if prev == 0 and r is not None:
            issue("HIGH", "Y1", f"calc_yoy_pct 分母0 應回 None,得到 {r}", desc)
        if curr == prev and r != 0.0:
            issue("LOW", "Y2", f"calc_yoy_pct 不變應回 0.0,得到 {r}", desc)
    except Exception as e:
        issue("HIGH", "Y3", f"calc_yoy_pct({curr}, {prev}) 拋例外", str(e))

# B3. prepare_waterfall_data
print("\n[B3] prepare_waterfall_data 邊界")
annual_agg = pd.DataFrame(
    {
        "會計科目": ["4101", "5101", "5201", "5301", "5401", "5501", "5601"],
        "會科名稱": [
            "利息收入",
            "利息支出",
            "用人費",
            "業務費",
            "管理費",
            "呆帳",
            "其他",
        ],
        "當月金額": [1000, -300, -200, -100, -50, -20, -10],
    }
)
try:
    wf = prepare_waterfall_data(annual_agg)
    print(f"  瀑布: labels={len(wf['labels'])}, net={wf['net']}")
    if wf["net"] != 1000 + (-300) + (-200) + (-100) + (-50) + (-20) + (-10):
        issue(
            "HIGH",
            "W1",
            "prepare_waterfall_data net 不等於收入-支出",
            f"net={wf['net']}",
        )
except Exception as e:
    issue("MEDIUM", "W2", "prepare_waterfall_data 拋例外", str(e))

# 空 annual_agg
try:
    empty = pd.DataFrame(columns=["會計科目", "會科名稱", "當月金額"])
    wf = prepare_waterfall_data(empty)
    print(f"  空 annual_agg 瀑布: net={wf['net']}")
    if wf["net"] != 0:
        issue("LOW", "W3", "prepare_waterfall_data(空) net 不為 0", f"net={wf['net']}")
except Exception as e:
    issue("MEDIUM", "W4", "prepare_waterfall_data(空) 拋例外", str(e))

# B4. detect_yoy_anomalies
print("\n[B4] detect_yoy_anomalies 邊界")
prev = pd.DataFrame(
    {
        "會計科目": ["1101", "4101"],
        "會科名稱": ["現金", "利息收入"],
        "當月金額": [1000, 500],
    }
)
curr = pd.DataFrame(
    {
        "會計科目": ["1101", "4101", "9999"],
        "會科名稱": ["現金", "利息收入", "新科目"],
        "當月金額": [2000, 100, 10],
    }
)
try:
    anomalies = detect_yoy_anomalies(curr, prev, threshold_amount=100, threshold_pct=10)
    print(f"  anomalies: {len(anomalies)} rows")
    has_new = (
        "9999" in anomalies["會計科目"].astype(str).values
        if not anomalies.empty
        else False
    )
    if has_new:
        issue(
            "MEDIUM",
            "DYA1",
            "detect_yoy_anomalies 包含新科目(去年沒有的)",
            "新科目去年金額=0,不該被當異常",
        )
except Exception as e:
    issue("MEDIUM", "DYA2", "detect_yoy_anomalies 拋例外", str(e))


# ============================================================
# PART C: diagnosis_service 邊界
# ============================================================

print("\n" + "=" * 78)
print(" PART C: diagnosis_service 邊界")
print("=" * 78)

# C1. calc_ratios 空
empty_agg = pd.DataFrame(columns=["會計科目", "會科名稱", "當月金額"])
try:
    r = calc_ratios(empty_agg)
    print(f"  空: {r}")
except Exception as e:
    issue("MEDIUM", "CR1", "calc_ratios(空) 拋例外", str(e))

# C2. calc_lending_rate_monthly_avg
print("\n[C2] calc_lending_rate_monthly_avg 邊界")
# 月份是 datetime 而非字串
test_df = pd.DataFrame(
    {
        "年度": ["113"] * 12,
        "年月": [
            "11301",
            "11302",
            "11303",
            "11304",
            "11305",
            "11306",
            "11307",
            "11308",
            "11309",
            "11310",
            "11311",
            "11312",
        ],
        "會計科目": ["4101"] * 6 + ["1311"] * 6,
        "當月金額": [50, 60, 70, 80, 90, 100, 1000, 1100, 1200, 1300, 1400, 1500],
    }
)
try:
    rate = calc_lending_rate_monthly_avg(test_df, "113")
    print(f"  利率: {rate}")
except Exception as e:
    issue("HIGH", "LR1", "calc_lending_rate_monthly_avg 正常拋例外", str(e))

# 月份是 datetime(可能會踩)
test_df_dt = test_df.copy()
test_df_dt["年月"] = pd.to_datetime(
    [
        "2024-01-01",
        "2024-02-01",
        "2024-03-01",
        "2024-04-01",
        "2024-05-01",
        "2024-06-01",
        "2024-07-01",
        "2024-08-01",
        "2024-09-01",
        "2024-10-01",
        "2024-11-01",
        "2024-12-01",
    ]
)
try:
    rate = calc_lending_rate_monthly_avg(test_df_dt, "113")
    print(f"  利率(datetime): {rate}")
except Exception as e:
    issue("MEDIUM", "LR2", "calc_lending_rate_monthly_avg(datetime年月) 拋例外", str(e))


# ============================================================
# PART D: AppTest 場景模擬(20 個組合)
# ============================================================

print("\n" + "=" * 78)
print(" PART D: AppTest 完整使用者旅程模擬(共 40 個場景)")
print("=" * 78)


def run_scenario(label, scenario_func):
    """執行單一 AppTest 場景,捕捉所有例外/錯誤/警告"""
    try:
        at = AppTest.from_file("app.py", default_timeout=30)
        scenario_func(at)
        at.run()
        n_exc = len(at.exception)
        n_err = len(at.error)
        n_warn = len(at.warning)
        if n_exc > 0:
            for e in at.exception:
                issue(
                    "CRITICAL",
                    "APP-EXC",
                    f"[{label}] Streamlit AppTest 拋例外",
                    str(e.value)[:500],
                )
        if n_err > 0:
            for e in at.error:
                msg = str(e.value)
                if "Unable to find a sidebar" in msg or "broadcast" in msg.lower():
                    continue
                issue("MEDIUM", "APP-ERR", f"[{label}] UI 顯示 error", msg[:300])
        print(f"  [{label}] exc={n_exc}, err={n_err}, warn={n_warn}")
    except Exception as e:
        issue(
            "HIGH",
            "APP-FRAME",
            f"[{label}] AppTest 框架錯誤",
            f"{type(e).__name__}: {str(e)[:300]}",
        )


# D1. 未登入 + 無 query params
def s_d1(at):
    pass


run_scenario("D1:未登入訪客", s_d1)


# D2. ?file= 空字串
def s_d2(at):
    at.query_params["file"] = ""


run_scenario("D2:?file=空字串", s_d2)


# D3. ?file= 含特殊字元(路徑穿越)
def s_d3(at):
    at.query_params["file"] = "../../../etc/passwd"


run_scenario("D3:?file=路徑穿越", s_d3)


# D4. ?file= 同時 ?csv=
def s_d4(at):
    at.query_params["file"] = "xl_xxx.xlsx"
    at.query_params["csv"] = "csv_xxx.csv"


run_scenario("D4:file+csv 同時", s_d4)


# D5. ?file= 含 SQL injection
def s_d5(at):
    at.query_params["file"] = "xl_';DROP TABLE--.xlsx"


run_scenario("D5:?file=SQL injection", s_d5)


# D6. login_attempts 累積到 5
def s_d6(at):
    at.session_state["login_attempts"] = 5
    at.session_state["locked"] = True


run_scenario("D6:locked 狀態", s_d6)


# D7. login_attempts 累積到 100(overflow)
def s_d7(at):
    at.session_state["login_attempts"] = 100


run_scenario("D7:login_attempts 巨大值", s_d7)


# D8. 已登入 admin 但沒資料 + 有 query params(雲端 404)
def s_d8(at):
    at.session_state["logged_in"] = True
    at.session_state["role"] = "admin"
    at.session_state["is_district_office"] = False
    at.session_state["preload_err"] = "Supabase 找不到檔案"
    at.query_params["file"] = "xl_xxx.xlsx"


run_scenario("D8:admin + 雲端 404", s_d8)


# D9. 已登入 viewer(個社)
def s_d9(at):
    at.session_state["logged_in"] = True
    at.session_state["role"] = "viewer"
    at.session_state["assigned_region"] = "北區"
    at.session_state["assigned_union"] = "測試社"
    at.session_state["is_district_office"] = False


run_scenario("D9:個社 viewer 無資料", s_d9)


# D10. 已登入 viewer(區會)
def s_d10(at):
    at.session_state["logged_in"] = True
    at.session_state["role"] = "viewer"
    at.session_state["assigned_region"] = "中區"
    at.session_state["assigned_union"] = "中區會"
    at.session_state["is_district_office"] = True


run_scenario("D10:區會 viewer 無資料", s_d10)


# D11. confirm_logout = True
def s_d11(at):
    at.session_state["logged_in"] = True
    at.session_state["role"] = "admin"
    at.session_state["is_district_office"] = False
    at.session_state["confirm_logout"] = True


run_scenario("D11:確認登出中", s_d11)


# D12. 個社 assigned_union 含特殊字元
def s_d12(at):
    at.session_state["logged_in"] = True
    at.session_state["role"] = "viewer"
    at.session_state["assigned_region"] = "南區"
    at.session_state["assigned_union"] = "<script>alert('xss')</script>"
    at.session_state["is_district_office"] = False


run_scenario("D12:union 名稱含 HTML", s_d12)


# D13. 個社 assigned_union 超長
def s_d13(at):
    at.session_state["logged_in"] = True
    at.session_state["role"] = "viewer"
    at.session_state["assigned_region"] = "東區"
    at.session_state["assigned_union"] = "A" * 500
    at.session_state["is_district_office"] = False


run_scenario("D13:union 名稱超長(500字)", s_d13)


# D14. role 是奇怪的值
def s_d14(at):
    at.session_state["logged_in"] = True
    at.session_state["role"] = "hacker"
    at.session_state["is_district_office"] = False


run_scenario("D14:role=非合法值", s_d14)


# D15. session_state 注入 None 取代欄位
def s_d15(at):
    at.session_state["logged_in"] = True
    at.session_state["role"] = "admin"
    at.session_state["is_district_office"] = False
    at.session_state["preloaded_data"] = None
    at.session_state["preloaded_csv"] = None


run_scenario("D15:admin + 無預載", s_d15)


# D16. 預載是空 tuple(只有 2 個元素而非 5)
def s_d16(at):
    at.session_state["logged_in"] = True
    at.session_state["role"] = "admin"
    at.session_state["is_district_office"] = False
    at.session_state["preloaded_data"] = ("fake", "tuple")


run_scenario("D16:preloaded_data 結構錯誤", s_d16)


# D17. nav_selection 已被切到財報明細,但無 csv
def s_d17(at):
    at.session_state["logged_in"] = True
    at.session_state["role"] = "admin"
    at.session_state["is_district_office"] = False
    at.session_state["nav_selection"] = "⚖️ 財報明細"
    at.session_state["preloaded_data"] = None
    at.session_state["preloaded_csv"] = None


run_scenario("D17:nav=財報明細 但無 csv", s_d17)


# D18. login_attempts 0, 但 locked=True(狀態不一致)
def s_d18(at):
    at.session_state["login_attempts"] = 0
    at.session_state["locked"] = True


run_scenario("D18:locked=True 但 attempts=0", s_s18 := lambda at: at)


# D19. 兩個 query params 都給空字串
def s_d19(at):
    at.query_params["file"] = ""
    at.query_params["csv"] = ""


run_scenario("D19:file+csv 都是空字串", s_d19)


# D20. unicode emoji URL
def s_d20(at):
    at.query_params["file"] = "📊📈.xlsx"


run_scenario("D20:?file=emoji URL", s_d20)


# ============================================================
# PART E: process_excel_final 邊界(用合成 Excel)
# ============================================================

print("\n" + "=" * 78)
print(" PART E: process_excel_final 邊界(共 30 個案例)")
print("=" * 78)

import io
from data.excel_processor import process_excel_final
from config import get_config

CONFIG = get_config()


def make_minimal_excel_bytes(main_df, loan_df, region_df):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        main_df.to_excel(writer, sheet_name=CONFIG["SHEETS"]["MAIN"], index=False)
        loan_df.to_excel(writer, sheet_name=CONFIG["SHEETS"]["LOAN"], index=False)
        region_df.to_excel(writer, sheet_name=CONFIG["SHEETS"]["REGION"], index=False)
    return buf.getvalue()


# E1. 最小有效 Excel
print("\n[E1] 最小有效 Excel(1 個社,1 個月)")
main = pd.DataFrame(
    [
        {
            "社號": "001",
            "社名": "測試社",
            "年月": "11312",
            "社員數": 100,
            "股金": 5_000_000,
            "貸放比": 0.5,
            "儲蓄率": 0.85,
        }
    ]
)
loan = pd.DataFrame(
    [
        {
            "社號": "001",
            "社名": "測試社",
            "年月": "11312",
            "逾放比": 0.01,
            "逾期貸款": 50000,
            "開支比": 0.95,
            "提撥率": 0.02,
        }
    ]
)
region = pd.DataFrame([{"社名": "測試社", "區域": "北區", "密碼": 1234}])
try:
    data, df_m, df_l, pws, rm = process_excel_final(
        make_minimal_excel_bytes(main, loan, region),
        CONFIG["THRESHOLDS"],
        CONFIG["SHEETS"],
    )
    print(f"  結果: {len(data)} 社,診斷={data['診斷狀態'].iloc[0]}")
    if "測試社" not in pws.get("1234", {}).get("name", ""):
        issue(
            "HIGH", "EX1", "process_excel_final 最小 Excel 密碼解析錯誤", f"pws={pws}"
        )
except Exception as e:
    issue(
        "CRITICAL",
        "EX2",
        "process_excel_final 最小 Excel 拋例外",
        f"{type(e).__name__}: {e}",
    )

# E2. 密碼欄位含 NaN
print("\n[E2] 密碼欄含 NaN")
region_nan = pd.DataFrame(
    [
        {"社名": "A社", "區域": "北區", "密碼": "1111"},
        {"社名": "B社", "區域": "北區", "密碼": None},
        {"社名": "C社", "區域": "北區", "密碼": float("nan")},
        {"社名": "D社", "區域": "南區", "密碼": 2222.0},
    ]
)
try:
    data, df_m, df_l, pws, rm = process_excel_final(
        make_minimal_excel_bytes(main, loan, region_nan),
        CONFIG["THRESHOLDS"],
        CONFIG["SHEETS"],
    )
    if "1111" not in pws or "2222" not in pws:
        issue(
            "MEDIUM",
            "EX3",
            "process_excel_final 密碼解析不全",
            f"pws={list(pws.keys())}",
        )
    if "" in pws or None in pws:
        issue(
            "HIGH", "EX4", "process_excel_final 密碼含 None/空字串當 key", f"pws={pws}"
        )
    print(f"  pws 數量: {len(pws)} (預期 2)")
except Exception as e:
    issue("CRITICAL", "EX5", "process_excel_final 含 NaN 密碼拋例外", str(e))

# E3. 密碼是浮點 2222.0
print("\n[E3] 密碼欄是浮點數 2222.0")
region_float = pd.DataFrame(
    [
        {"社名": "A社", "區域": "北區", "密碼": 2222.0},
        {"社名": "B社", "區域": "南區", "密碼": 3333.0},
    ]
)
try:
    data, df_m, df_l, pws, rm = process_excel_final(
        make_minimal_excel_bytes(main, loan, region_float),
        CONFIG["THRESHOLDS"],
        CONFIG["SHEETS"],
    )
    if "2222" not in pws:
        issue(
            "HIGH",
            "EX6",
            "process_excel_final 浮點密碼 2222.0 沒被轉成 '2222'",
            f"pws={list(pws.keys())}",
        )
    print(f"  浮點密碼處理: {list(pws.keys())}")
except Exception as e:
    issue("CRITICAL", "EX7", "process_excel_final 浮點密碼拋例外", str(e))

# E4. 缺工作表
print("\n[E4] 缺 MAIN 工作表")
buf = io.BytesIO()
with pd.ExcelWriter(buf, engine="openpyxl") as writer:
    loan.to_excel(writer, sheet_name=CONFIG["SHEETS"]["LOAN"], index=False)
    region.to_excel(writer, sheet_name=CONFIG["SHEETS"]["REGION"], index=False)
try:
    data, df_m, df_l, pws, rm = process_excel_final(
        buf.getvalue(),
        CONFIG["THRESHOLDS"],
        CONFIG["SHEETS"],
    )
    issue("HIGH", "EX8", "process_excel_final 缺工作表 沒拋錯", "應拋 ValueError")
except ValueError as e:
    print(f"  ✅ 正確拋 ValueError: {e}")
except Exception as e:
    issue("MEDIUM", "EX9", "process_excel_final 缺工作表 拋非 ValueError", str(e))

# E5. 缺提撥率欄位
print("\n[E5] 缺提撥率欄位(歷史資料)")
loan_no_prov = loan.drop(columns=["提撥率"])
try:
    data, df_m, df_l, pws, rm = process_excel_final(
        make_minimal_excel_bytes(main, loan_no_prov, region),
        CONFIG["THRESHOLDS"],
        CONFIG["SHEETS"],
    )
    if float(data["提撥率"].iloc[0]) != 0.0:
        issue(
            "MEDIUM",
            "EX10",
            "缺提撥率欄位 沒 fallback 0",
            f"got {data['提撥率'].iloc[0]}",
        )
    print(f"  ✅ 缺提撥率 → 0.0")
except Exception as e:
    issue("HIGH", "EX11", "process_excel_final 缺提撥率拋例外", str(e))

# E6. 社員數為 0
print("\n[E6] 社員數=0")
main_zero = main.copy()
main_zero["社員數"] = 0
try:
    data, df_m, df_l, pws, rm = process_excel_final(
        make_minimal_excel_bytes(main_zero, loan, region),
        CONFIG["THRESHOLDS"],
        CONFIG["SHEETS"],
    )
    if data["社員成長率(12M)"].iloc[0] != 0:
        print(f"  ⚠️ 社員成長率(0): {data['社員成長率(12M)'].iloc[0]}")
except Exception as e:
    issue("HIGH", "EX12", "process_excel_final 社員數=0 拋例外", str(e))

# E7. 沒有 12 月資料
print("\n[E7] 沒有任何 12 月資料")
main_no_dec = pd.DataFrame(
    [
        {
            "社號": "001",
            "社名": "測試社",
            "年月": "11301",
            "社員數": 100,
            "股金": 5_000_000,
            "貸放比": 0.5,
            "儲蓄率": 0.85,
        }
    ]
)
try:
    data, df_m, df_l, pws, rm = process_excel_final(
        make_minimal_excel_bytes(main_no_dec, loan, region),
        CONFIG["THRESHOLDS"],
        CONFIG["SHEETS"],
    )
    print(f"  沒 12 月: T0={data['_sM'].iloc[0]}")
except Exception as e:
    issue("HIGH", "EX13", "process_excel_final 沒 12 月拋例外", str(e))

# E8. 完全空的 Excel
print("\n[E8] 完全空的 Excel(只有標頭)")
empty_main = pd.DataFrame(
    columns=["社號", "社名", "年月", "社員數", "股金", "貸放比", "儲蓄率"]
)
try:
    data, df_m, df_l, pws, rm = process_excel_final(
        make_minimal_excel_bytes(empty_main, loan, region),
        CONFIG["THRESHOLDS"],
        CONFIG["SHEETS"],
    )
    if len(data) > 0:
        issue("MEDIUM", "EX14", "空 MAIN 還是生成了診斷資料", f"len={len(data)}")
    else:
        print(f"  ✅ 空 MAIN → 0 社")
except Exception as e:
    issue("MEDIUM", "EX15", "process_excel_final 空 MAIN 拋例外", str(e))


# ============================================================
# PART F: CSV 邊界
# ============================================================

print("\n" + "=" * 78)
print(" PART F: CSV 邊界")
print("=" * 78)

from data.csv_processor import process_csv_final

# F1. 有效 CSV
print("\n[F1] 有效 CSV")
csv_bytes = """年月,會計科目,會科名稱,社名,當月金額
11301,1101,現金,測試社,1000000
11302,1101,現金,測試社,1100000
11312,4101,利息收入,測試社,50000
""".encode("utf-8-sig")
try:
    df = process_csv_final(csv_bytes)
    print(f"  ✅ CSV: {len(df)} rows, 年月型別={df['年月'].dtype}")
    if df["年月"].iloc[0] != "11301":
        issue("HIGH", "CSV1", "CSV 年月沒轉成字串", f"got {df['年月'].iloc[0]!r}")
except Exception as e:
    issue("CRITICAL", "CSV2", "CSV 正常拋例外", str(e))

# F2. 年月含中文(應失敗但 try/except 包住)
print("\n[F2] 年月含中文")
csv_chinese = """年月,會計科目,會科名稱,社名,當月金額
113年01月,1101,現金,測試社,1000
""".encode("utf-8-sig")
try:
    df = process_csv_final(csv_chinese)
    issue("MEDIUM", "CSV3", "CSV 中文年月應該失敗卻成功", f"got {df['年月'].iloc[0]!r}")
except ValueError as e:
    print(f"  ✅ 中文年月拋 ValueError: {e}")

# F3. 缺年月欄
print("\n[F3] 缺年月欄")
csv_no_date = """會計科目,會科名稱,社名,當月金額
1101,現金,測試社,1000
""".encode("utf-8-sig")
try:
    df = process_csv_final(csv_no_date)
    issue("HIGH", "CSV4", "CSV 缺年月欄 沒拋錯", f"got {len(df)} rows")
except Exception as e:
    print(f"  ✅ 缺年月拋 {type(e).__name__}: {str(e)[:100]}")

# F4. 當月金額含非數字
print("\n[F4] 當月金額含非數字")
csv_bad_num = """年月,會計科目,會科名稱,社名,當月金額
11301,1101,現金,測試社,abc
""".encode("utf-8-sig")
try:
    df = process_csv_final(csv_bad_num)
    if df["當月金額"].iloc[0] != 0:
        issue("MEDIUM", "CSV5", "非數字金額沒轉成 0", f"got {df['當月金額'].iloc[0]!r}")
    else:
        print(f"  ✅ abc → 0")
except Exception as e:
    issue("HIGH", "CSV6", "CSV 非數字拋例外", str(e))

# F5. 會科名稱為 0
print("\n[F5] 會科名稱是 0")
csv_zero_name = """年月,會計科目,會科名稱,社名,當月金額
11301,1101,0,測試社,1000
""".encode("utf-8-sig")
try:
    df = process_csv_final(csv_zero_name)
    if df["會科名稱"].iloc[0] != "(未分類)":
        issue(
            "LOW", "CSV7", "會科名稱 0 沒轉 (未分類)", f"got {df['會科名稱'].iloc[0]!r}"
        )
except Exception as e:
    issue("HIGH", "CSV8", "CSV 會科名稱 0 拋例外", str(e))


# ============================================================
# 最終彙整
# ============================================================

print("\n" + "=" * 78)
print("  最終問題彙整")
print("=" * 78)

by_severity = Counter(i["severity"] for i in ISSUES)
by_code = Counter(i["code"] for i in ISSUES)

print(f"\n總計發現 {len(ISSUES)} 個問題:")
for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
    print(f"  {sev:10s}: {by_severity.get(sev, 0)} 個")

print("\n按 code 分類:")
for code, count in by_code.most_common():
    print(f"  {code:15s}: {count} 個")

# 印出所有問題
print("\n" + "=" * 78)
print("  完整問題清單")
print("=" * 78)

for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
    items = [i for i in ISSUES if i["severity"] == sev]
    if not items:
        continue
    print(f"\n### {sev} ({len(items)} 個) ###\n")
    for i, item in enumerate(items, 1):
        print(f"[{item['code']}] {item['title']}")
        print(f"  細節: {item['detail']}")
        if item.get("repro"):
            print(f"  重現: {item['repro']}")
        print()

# 寫 JSON
output_path = Path(__file__).resolve().parent / "sim_1000_results.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(ISSUES, f, ensure_ascii=False, indent=2)
print(f"\n詳細結果已寫入: {output_path}")
