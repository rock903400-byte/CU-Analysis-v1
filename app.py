"""
儲互社分析系統 — 主入口
"""

import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

import html
import logging
import uuid

import streamlit as st

from services.auth import render_login_page, handle_login
from services.cloud import init_supabase, download_file_from_storage
from config import APP_CSS, get_config
from data.csv_processor import process_csv_final
from data.excel_processor import process_excel_final
from views.overview import render_overview_page
from views.war_room import render_war_room_page
from components.onboarding import render_welcome_page

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

CONFIG = get_config()

# ── 頁面設定 ──────────────────────────────────────────────
st.set_page_config(
    page_title="儲互社分析系統",
    layout="wide",
    page_icon="🏦",
    initial_sidebar_state="collapsed",
)
st.markdown(APP_CSS.format(theme_bg=CONFIG["THEME_BG"]), unsafe_allow_html=True)

# ── Session State 初始化 ──────────────────────────────────
_DEFAULTS = {
    "logged_in": False,
    "role": None,
    "assigned_region": None,
    "assigned_union": None,
    "login_attempts": 0,
    "locked": False,
    "preloaded_data": None,  # (data, df_m, df_l, raw_bytes, region_map)
    "preloaded_csv": None,  # (df, raw_bytes)
    "preloaded_passwords": {},
    "nav_selection": "📊 社務診斷",
    "is_district_office": False,
    "confirm_logout": False,
    "xl_msg": None,
    "csv_msg": None,
    "preload_err": None,
    "preload_csv_err": None,
    "share_generating": False,
    "latest_share_url": None,
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ── 雲端服務 ──────────────────────────────────────────────
supabase = init_supabase()

# ── 共享連結預載 ──────────────────────────────────────────
_MAX_PARAM_LEN = 256

shared_file = st.query_params.get("file")
shared_csv = st.query_params.get("csv")

if shared_file and len(shared_file) > _MAX_PARAM_LEN:
    st.error("❌ 分享連結參數過長（可能為攻擊或損壞），已忽略。")
    shared_file = None
if shared_csv and len(shared_csv) > _MAX_PARAM_LEN:
    st.error("❌ 分享連結參數過長（可能為攻擊或損壞），已忽略。")
    shared_csv = None

_CLOUD_ERR = (
    "Name or service not known", "getaddrinfo", "Connection refused",
    "Temporary failure in name resolution", "remote end closed",
    "ConnectionError",
)

if shared_file and st.session_state["preloaded_data"] is None:
    # 嘗試載入雲端檔案前，先清除前一次的錯誤訊息，避免舊錯誤殘留
    st.session_state["preload_err"] = None
    st.session_state["preload_csv_err"] = None
    try:
        raw_bytes = download_file_from_storage(
            supabase, CONFIG["BUCKET_NAME"], shared_file
        )
        data, df_m, df_l, region_pws, region_map = process_excel_final(
            raw_bytes, CONFIG["THRESHOLDS"], CONFIG["SHEETS"]
        )
        st.session_state.update(
            preloaded_passwords=region_pws,
            preloaded_data=(data, df_m, df_l, raw_bytes, region_map),
        )
    except Exception as e:
        _m = str(e)
        if any(k in _m for k in _CLOUD_ERR):
            st.session_state["preload_err"] = "☁️ 雲端服務暫停中，請通知管理員恢復後再試。"
        else:
            st.session_state["preload_err"] = _m

if shared_csv and st.session_state["preloaded_csv"] is None:
    try:
        raw_csv = download_file_from_storage(
            supabase, CONFIG["BUCKET_NAME"], shared_csv
        )
        st.session_state["preloaded_csv"] = (process_csv_final(raw_csv), raw_csv)
    except Exception as e:
        _m = str(e)
        if any(k in _m for k in _CLOUD_ERR):
            logger.error(f"CSV 載入失敗（雲端連線問題）: {e}")
            st.session_state["preload_csv_err"] = "☁️ 雲端服務暫停中，請通知管理員恢復後再試。"
        else:
            logger.error(f"CSV 載入失敗: {e}")
            st.session_state["preload_csv_err"] = f"CSV 載入失敗：{_m}"

# ── 預載錯誤反饋 ──────────────────────────────────────────
if "preload_err" in st.session_state and st.session_state["preload_err"]:
    st.error(f"❌ Excel 資料載入失敗：{st.session_state['preload_err']}")
    st.session_state["preload_err"] = None
if "preload_csv_err" in st.session_state and st.session_state["preload_csv_err"]:
    st.error(f"❌ CSV 資料載入失敗：{st.session_state['preload_csv_err']}")
    st.session_state["preload_csv_err"] = None

# ── 登入關卡 ──────────────────────────────────────────────
if not st.session_state["logged_in"]:
    render_login_page(CONFIG["MAX_ATTEMPTS"])
    st.stop()

# ── 資料載入與過濾 ────────────────────────────────────────
IS_ADMIN = st.session_state["role"] == "admin"
data_loaded = False
region_data = None

_pd = st.session_state["preloaded_data"]
if _pd and isinstance(_pd, (tuple, list)) and len(_pd) == 5:
    data, df_m, df_l, raw_bytes, region_map = _pd
    if data is None or df_m is None or df_l is None:
        st.warning("⚠️ 預載資料不完整（部分欄位為空），請重新上傳或聯絡管理員。")
        data = df_m = df_l = region_map = None
        data_loaded = False
    else:
        region = st.session_state["assigned_region"]
        union = st.session_state["assigned_union"]

        if region:
            # 取得該區域內所有實際有財報的社名（去 NaN 以容錯真實 Excel 空白）
            region_data = data[data["區域"] == region].copy()
            actual_unions_in_reg = set(region_data["社名"].dropna().unique())

            # 建立 strip 後的對照表，容錯真實 Excel 空白/全半形差異
            _norm_to_orig = {
                u.strip(): u for u in actual_unions_in_reg if isinstance(u, str)
            }
            _target = (union or "").strip()

            if _target and _target in _norm_to_orig:
                # 【個社模式】：登入名稱是一個實際存在的社
                data = data[data["社名"] == _norm_to_orig[_target]].copy()
                st.session_state["is_district_office"] = False
            else:
                # 【區會模式】：登入名稱不在財報清單中，視為管理單位
                st.session_state["is_district_office"] = True
                if union:
                    st.warning(
                        f"⚠️ 找不到『{union}』，已切換為 {region} 區會模式；"
                        "請聯絡管理員更新資料。"
                    )
                if region_data.empty:
                    st.warning("該區目前尚無報表資料，請先上傳資料庫。")
                    st.stop()
                data = region_data.copy()

            target_snos = data["社號"].unique()
            df_m = df_m[df_m["社號"].isin(target_snos)].copy()
            df_l = df_l[df_l["社號"].isin(target_snos)].copy()
        else:
            # Admin 模式
            st.session_state["is_district_office"] = False

        data_loaded = True

if st.session_state["preloaded_csv"]:
    df_csv_full, raw_csv_bytes = st.session_state["preloaded_csv"]
    union = st.session_state["assigned_union"]
    region = st.session_state["assigned_region"]
    is_dist = st.session_state.get("is_district_office", False)

    if union and not is_dist:
        # 個社：僅顯示自身資料
        df_csv = df_csv_full[df_csv_full["社名"] == union.strip()].copy()
    elif region:
        # 區會或管理員：查看該區域內所有社（需 region_map，無 Excel 時無法歸屬）
        _pd = st.session_state.get("preloaded_data")
        if _pd and isinstance(_pd, (tuple, list)) and len(_pd) == 5:
            rm = _pd[4]
            target_names = [n for n, r in rm.items() if r == region]
            df_csv = df_csv_full[df_csv_full["社名"].isin(target_names)].copy()
        else:
            # 無 Excel 區域歸屬資料，無法做區域過濾 → 退而求其次顯示全部
            df_csv = df_csv_full.copy()
    else:
        df_csv = df_csv_full.copy()
    data_loaded = True

# ── 管理員側邊欄 ──────────────────────────────────────────
if IS_ADMIN:
    with st.sidebar:
        st.markdown(
            '<span class="sidebar-label">📂 資料匯入</span>', unsafe_allow_html=True
        )
        uploaded_xl = st.file_uploader(
            "Excel (風險診斷)", type=["xlsx"], label_visibility="collapsed"
        )
        uploaded_csv = st.file_uploader(
            "CSV (財務明細)", type=["csv"], label_visibility="collapsed"
        )

        if uploaded_xl:
            try:
                raw_bytes = uploaded_xl.getvalue()
                data, df_m, df_l, region_pws, region_map = process_excel_final(
                    raw_bytes, CONFIG["THRESHOLDS"], CONFIG["SHEETS"]
                )
                st.session_state.update(
                    preloaded_passwords=region_pws,
                    preloaded_data=(data, df_m, df_l, raw_bytes, region_map),
                )
                data_loaded = True
                st.session_state["xl_msg"] = (
                    "success",
                    "✅ Excel 解析成功，資料已載入。",
                )
            except Exception as e:
                st.session_state["preloaded_data"] = None
                st.session_state["preloaded_passwords"] = {}
                st.session_state["xl_msg"] = ("error", f"❌ Excel 解析失敗：{e}")
                # 清掉當前 run 的 local 變數，避免下方渲染繼續用舊資料
                data = df_m = df_l = region_map = None
                raw_bytes = None  # type: ignore[assignment]
                data_loaded = False

        if st.session_state["xl_msg"]:
            _t, _m = st.session_state["xl_msg"]
            if _t == "success":
                st.success(_m)
            else:
                st.error(_m)

        if uploaded_csv:
            try:
                raw_csv_bytes = uploaded_csv.getvalue()
                df_csv = process_csv_final(raw_csv_bytes)
                st.session_state["preloaded_csv"] = (df_csv, raw_csv_bytes)
                data_loaded = True
                st.session_state["csv_msg"] = (
                    "success",
                    "✅ CSV 解析成功，資料已載入。",
                )
            except Exception as e:
                st.session_state["csv_msg"] = ("error", f"❌ CSV 解析失敗：{e}")

        if st.session_state["csv_msg"]:
            _t, _m = st.session_state["csv_msg"]
            if _t == "success":
                st.success(_m)
            else:
                st.error(_m)

        if st.session_state["preloaded_data"] or st.session_state["preloaded_csv"]:
            st.markdown("<hr>", unsafe_allow_html=True)
            st.markdown(
                '<span class="sidebar-label">🔗 分享功能</span>', unsafe_allow_html=True
            )
            if st.button(
                "🚀 生成分享連結",
                use_container_width=True,
                disabled=st.session_state["share_generating"],
            ):
                st.session_state["share_generating"] = True
                try:
                    if not supabase:
                        st.error("❌ 雲端服務未設定，無法產生分享連結。")
                    else:
                        params = []
                        if st.session_state["preloaded_data"]:
                            f_xl = f"xl_{uuid.uuid4().hex[:8]}.xlsx"
                            supabase.storage.from_(CONFIG["BUCKET_NAME"]).upload(
                                f_xl,
                                st.session_state["preloaded_data"][3],
                                file_options={
                                    "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                                },
                            )
                            params.append(f"file={f_xl}")
                        if st.session_state["preloaded_csv"]:
                            f_csv = f"csv_{uuid.uuid4().hex[:8]}.csv"
                            supabase.storage.from_(CONFIG["BUCKET_NAME"]).upload(
                                f_csv,
                                st.session_state["preloaded_csv"][1],
                                file_options={"content-type": "text/csv"},
                            )
                            params.append(f"csv={f_csv}")
                        if params:
                            st.session_state["latest_share_url"] = (
                                f"{CONFIG['APP_BASE_URL']}/?{'&'.join(params)}"
                            )
                except Exception as e:
                    _m = str(e)
                    if any(k in _m for k in _CLOUD_ERR):
                        st.error("☁️ 雲端服務暫停中，無法產生分享連結。請通知管理員恢復後再試。")
                    else:
                        st.error(f"❌ 上傳失敗：{_m}")
                finally:
                    st.session_state["share_generating"] = False
            if st.session_state["latest_share_url"]:
                st.code(st.session_state["latest_share_url"], language="text")

if not data_loaded:
    render_welcome_page(
        is_admin=IS_ADMIN,
        is_district_office=st.session_state.get("is_district_office", False),
        has_share_link=bool(shared_file or shared_csv),
    )
    st.stop()

# ── 標題 ──────────────────────────────────────────────────
if st.session_state.get("is_district_office"):
    # 區會模式
    disp_title = f"{st.session_state['assigned_region']}區會"
elif st.session_state.get("assigned_union"):
    # 個社模式
    disp_title = st.session_state["assigned_union"]
else:
    # Admin 或未分配區域
    disp_title = st.session_state["assigned_region"] or "全台"

# 智能避開重複的「儲互社」字眼
if "儲互社" in disp_title:
    display_text = f"{disp_title} 分析系統"
else:
    display_text = f"{disp_title} 儲互社分析系統"

st.markdown(
    f"<h1 class='responsive-h1'>📊 {html.escape(display_text)}</h1>",
    unsafe_allow_html=True,
)

# ── 導覽側邊欄 ────────────────────────────────────────────
with st.sidebar:
    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown(
        '<span class="sidebar-label">🧭 系統導覽</span>', unsafe_allow_html=True
    )

    nav_options = []
    if st.session_state["preloaded_data"]:
        nav_options.append("📊 社務診斷")
    if st.session_state["preloaded_csv"]:
        nav_options.append("⚖️ 財報明細")
    if not nav_options:
        nav_options = ["👋 歡迎頁面"]

    if st.session_state["nav_selection"] not in nav_options:
        st.session_state["nav_selection"] = nav_options[0]

    st.session_state["nav_selection"] = st.radio(
        "選擇功能模組",
        nav_options,
        label_visibility="collapsed",
        index=nav_options.index(st.session_state["nav_selection"]),
    )

    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown(
        '<span class="sidebar-label">👤 帳號權限</span>', unsafe_allow_html=True
    )
    if IS_ADMIN:
        badge_cls, badge_txt = "badge-admin", "🔑 管理員模式"
    else:
        disp_name = (
            st.session_state["assigned_union"] or st.session_state["assigned_region"]
        )
        badge_cls, badge_txt = (
            "badge-viewer",
            f"👁️ 訪客：{html.escape(str(disp_name or ''))}",
        )
    st.markdown(f'<div class="{badge_cls}">{badge_txt}</div>', unsafe_allow_html=True)
    if not st.session_state["confirm_logout"]:
        if st.button("🚪 登出系統", use_container_width=True):
            st.session_state["confirm_logout"] = True
            st.rerun()
    else:
        st.warning("⚠️ 確定要登出嗎？")
        _cy, _cn = st.columns(2)
        if _cy.button("✅ 確定登出", use_container_width=True):
            for k, v in _DEFAULTS.items():
                st.session_state[k] = v
            # 清除密碼欄位，防止登出後仍顯示前一次密碼
            st.session_state["pwd_input"] = ""
            st.rerun()
        if _cn.button("❌ 取消", use_container_width=True):
            st.session_state["confirm_logout"] = False
            st.rerun()

# ── 頁面路由 ──────────────────────────────────────────────
if st.session_state["nav_selection"] == "📊 社務診斷":
    render_overview_page(
        data,
        df_m,
        df_l,
        region_data,
        CONFIG,
        assigned_union=st.session_state.get("assigned_union"),
        is_district_office=st.session_state.get("is_district_office", False),
    )

elif st.session_state["nav_selection"] == "⚖️ 財報明細":
    render_war_room_page(df_csv, IS_ADMIN, CONFIG)

else:
    st.info("👋 歡迎！請由左側上傳資料或選擇功能模組。")
