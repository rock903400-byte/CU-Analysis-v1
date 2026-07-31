"""
全域配置與常數
"""

import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st
from pydantic import BaseModel, field_validator

from common.thresholds import DEFAULT_THRESHOLDS, load_thresholds


class ThresholdsConfig(BaseModel):
    high_risk_ovd: float
    liquidity_loan: float
    idle_loan: float
    stable_loan_min: float
    stable_loan_max: float
    ovd_safe_line: float
    high_risk_income_ratio: float
    high_risk_loan_ratio: float
    high_risk_ovd_ratio: float
    savings_good: float
    provision_good: float

    @field_validator(
        "high_risk_ovd",
        "liquidity_loan",
        "idle_loan",
        "stable_loan_min",
        "stable_loan_max",
        "ovd_safe_line",
        "high_risk_income_ratio",
        "high_risk_loan_ratio",
        "high_risk_ovd_ratio",
        "savings_good",
        "provision_good",
    )
    @classmethod
    def must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"門檻值必須 > 0，收到: {v}")
        return v


ACCOUNT_CODES = {
    "shares": "3101",
    "loans": "1311",
    "profit": "3319",
}


def safe_secrets():
    try:
        list(st.secrets.keys())  # 主動觸發惰性解析；沒 secrets 檔才會在這拋錯
        return st.secrets
    except Exception:
        return {}


def get_config():
    _secrets = safe_secrets()
    raw = {
        "BUCKET_NAME": _secrets.get("BUCKET_NAME", "excel-reports"),
        "APP_BASE_URL": "https://cu-analysis-v1-vizgphhwjwmfkvrrktdjte.streamlit.app",
        "MAX_ATTEMPTS": 5,
        "THEME_BG": "#F0F4F8",
        "SHEETS": {
            "MAIN": "社務及資金運用情形",
            "LOAN": "放款及逾期放款",
            "REGION": "區域分類表",
        },
        "THRESHOLDS": load_thresholds(_secrets),
    }
    ThresholdsConfig(**raw["THRESHOLDS"])
    return raw


APP_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;600;700&display=swap');

html, body, [data-testid="stAppViewContainer"] {{
    font-family: 'Noto Sans TC', sans-serif !important;
    background-color: {theme_bg} !important;
    color: #1A202C !important;
    font-size: 18px !important;
}}
[data-testid="stMainBlockContainer"] {{
    max-width: 100% !important;
    padding-top: 4rem !important;
    padding-left: 1.5rem !important;
    padding-right: 1.5rem !important;
    padding-bottom: 1.5rem !important;
}}
.responsive-h1 {{ font-size: 2.5rem; font-weight: 700; margin-bottom: 2rem !important; color: #1E293B; }}
.responsive-h2 {{ font-size: 2rem;   font-weight: 700; margin-bottom: 1.5rem !important; color: #1E293B; }}
.stButton > button {{
    min-height: 52px !important; font-size: 18px !important;
    border-radius: 12px !important; font-weight: 600 !important;
}}
.stTextInput input {{
    min-height: 52px !important; font-size: 18px !important; border-radius: 12px !important;
}}
[data-baseweb="select"] {{ min-height: 52px !important; font-size: 18px !important; }}
.stTabs [data-baseweb="tab"] {{
    font-size: 18px !important; font-weight: 600 !important; padding: 10px 20px !important;
}}
[data-testid="stMetricValue"], [data-testid="stMetricValue"] > div {{ font-size: 2.2rem !important; font-weight: 700 !important; word-break: break-all !important; overflow-wrap: anywhere !important; white-space: normal !important; line-height: 1.2 !important; text-overflow: clip !important; overflow: visible !important; }}
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] > div {{ font-size: 1.1rem !important; font-weight: 600 !important; word-break: break-word !important; white-space: normal !important; text-overflow: clip !important; overflow: visible !important; }}
[data-testid="metric-container"] {{ overflow: visible !important; }}
    [data-testid="stDataFrame"] {{ font-size: 18px !important; }}
    [data-testid="stDataFrame"] td {{ font-size: 18px !important; padding: 10px 8px !important; }}
    [data-testid="stDataFrame"] th {{ font-size: 18px !important; padding: 10px 8px !important; }}

/* 手機版：DataFrame 橫向捲動 */
@media (max-width: 640px) {{
    [data-testid="stDataFrame"] > div {{
        overflow-x: auto !important;
        -webkit-overflow-scrolling: touch !important;
    }}
    [data-testid="stDataFrame"] table {{
        min-width: 600px !important;
    }}
}}
@media (max-width: 640px) {{
    html, body, [data-testid="stAppViewContainer"] {{ font-size: 18px !important; }}
    [data-testid="stMainBlockContainer"] {{
        padding-left: 1rem !important; padding-right: 1rem !important; padding-top: 3.5rem !important;
    }}
    .stat-card {{ min-height: auto !important; }}
    .responsive-h1 {{ font-size: 2rem !important; }}
    .responsive-h2 {{ font-size: 1.6rem !important; }}
    [data-testid="stMetricValue"], [data-testid="stMetricValue"] > div {{ font-size: 2rem !important; word-break: break-all !important; white-space: normal !important; text-overflow: clip !important; overflow: visible !important; }}
    .stButton > button {{ min-height: 56px !important; font-size: 18px !important; }}
    [data-baseweb="select"] {{ min-height: 56px !important; font-size: 18px !important; }}
    .stTabs [data-baseweb="tab"] {{ font-size: 16px !important; padding: 12px 16px !important; }}
    .card-criteria {{ font-size: 1.1rem !important; padding: 10px 14px !important; }}
    .reason-text {{ font-size: 1.1rem !important; }}
    .name-tag {{ font-size: 1.1rem !important; padding: 6px 14px !important; }}
    [data-testid="stDataFrame"] {{ font-size: 18px !important; }}
    [data-testid="stCheckboxContainer"] {{ min-height: 56px !important; }}
    [data-testid="stExpander"] summary {{ min-height: 56px !important; padding: 14px 16px !important; }}
    .stDownloadButton > button {{ min-height: 56px !important; }}

/* 手機版：4 欄自動疊疊為單欄 */
    [data-testid="stHorizontalBlock"] > div[data-testid="column"] {{
        min-width: 0 !important;
        width: 100% !important;
        flex: 1 1 100% !important;
        max-width: 100% !important;
    }}
}}
[data-testid="stSidebar"] {{ background-color: #1E293B !important; }}
[data-testid="stSidebar"][aria-expanded="true"] {{ min-width: 280px !important; }}
[data-testid="stSidebar"] * {{ color: #E2E8F0 !important; }}
[data-testid="stSidebar"] hr {{ border-color: #334155 !important; margin: 1.5rem 0 !important; }}

/* 手機版：側邊欄抽屜式 */
@media (max-width: 640px) {{
    [data-testid="stSidebar"] {{
        position: fixed !important;
        top: 0;
        left: 0;
        height: 100vh;
        width: 85vw !important;
        max-width: 320px !important;
        z-index: 9999 !important;
        transform: translateX(-100%);
        transition: transform 0.3s ease !important;
        box-shadow: 4px 0 20px rgba(0,0,0,0.2);
    }}
    [data-testid="stSidebar"][aria-expanded="true"] {{
        transform: translateX(0) !important;
    }}
    [data-testid="stSidebar"] > div:first-child {{
        height: 100vh;
        overflow-y: auto;
    }}
    /* 側邊欄開關按鈕 */
    [data-testid="collapsedControl"] {{
        display: block !important;
        position: fixed !important;
        top: 1rem;
        left: 1rem;
        z-index: 10000 !important;
        background: #1E293B !important;
        color: #E2E8F0 !important;
        border: 1px solid #475569 !important;
        border-radius: 8px !important;
        padding: 0.5rem 1rem !important;
    }}
    /* 遮罩層 */
    .sidebar-overlay {{
        display: none;
        position: fixed;
        top: 0; left: 0; right: 0; bottom: 0;
        background: rgba(0,0,0,0.5);
        z-index: 9998;
    }}
    .sidebar-overlay.visible {{
        display: block;
    }}
}}
[data-testid="stSidebar"] .stButton > button {{
    background: #334155; color: #E2E8F0 !important; border: 1px solid #475569;
    border-radius: 10px; padding: 0.5rem 1rem; font-weight: 600;
    width: 100%; min-height: 52px !important;
}}
[data-testid="stSidebar"] .stButton > button:hover {{
    background: #475569; border-color: #64748B; transform: translateY(-1px);
}}
[data-testid="stSidebar"] [data-baseweb="select"] {{ min-height: 52px !important; font-size: 18px !important; }}
[data-testid="stSidebar"] .stCheckboxContainer {{ min-height: 52px !important; }}
[data-testid="stSidebar"] .stCheckboxContainer label {{ font-size: 18px !important; }}
.stCodeBlock {{ border-radius: 10px !important; background: #0F172A !important; border: 1px solid #334155 !important; }}
[data-testid="stVerticalBlockBorderWrapper"] {{
    border-radius: 20px !important; background: white !important;
    padding: 1.5rem !important; box-shadow: 0 10px 25px rgba(0,0,0,0.05) !important;
}}
.stat-card {{
    background: white; border-radius: 14px; border: 1px solid #E2E8F0;
    margin-bottom: 1rem; min-height: 200px; display: flex; flex-direction: column; overflow: hidden;
}}
.card-header {{ padding: 12px; color: #FFF !important; font-weight: 700; text-align: center; font-size: 1.2rem; }}
.hdr-red    {{ background: linear-gradient(135deg, #EF4444, #991B1B); }}
.hdr-orange {{ background: linear-gradient(135deg, #F59E0B, #92400E); }}
.hdr-blue   {{ background: linear-gradient(135deg, #3B82F6, #1E40AF); }}
.hdr-green  {{ background: linear-gradient(135deg, #10B981, #065F46); }}
.name-tag {{
    display: inline-block; background: #F1F5F9; color: #1A202C !important;
    padding: 5px 12px; border-radius: 10px; margin: 4px;
    font-size: 1.1rem; border: 1px solid #CBD5E1; font-weight: 600;
}}
.card-criteria {{
    font-size: 1.1rem; color: #475569; background: #F8FAFC;
    border-bottom: 1px solid #E2E8F0; padding: 8px 14px; line-height: 1.6;
}}
.union-item {{ margin: 4px 0; }}
.reason-text {{
    font-size: 1.1rem; color: #92400E; padding: 2px 4px 4px 14px;
}}
.badge-admin  {{ background: #DCFCE7; color: #166534 !important; border-radius: 8px; padding: 10px; text-align: center; font-size: 1.1rem; font-weight: 700; border: 1px solid #86EFAC; margin-bottom: 1rem; }}
.badge-viewer {{ background: #FEF3C7; color: #92400E !important; border-radius: 8px; padding: 10px; text-align: center; font-size: 1.1rem; font-weight: 700; border: 1px solid #FCD34D; margin-bottom: 1rem; }}
.sidebar-label {{ font-size: 1.1rem; font-weight: 600; color: #94A3B8; margin-bottom: 0.5rem; display: block; }}
.alert-box   {{ padding: 15px; border-radius: 10px; margin-bottom: 1rem; font-size: 1.1rem; font-weight: 600; border: 1px solid transparent; }}
.alert-error   {{ background-color: #FEF2F2; color: #991B1B; border-color: #FEE2E2; }}
.alert-warning {{ background-color: #FFFBEB; color: #92400E; border-color: #FEF3C7; }}
[data-testid="stCaption"], .stCaption {{ font-size: 1rem !important; color: #475569 !important; }}
.stAlert {{ font-size: 1.1rem !important; }}
.stAlert p {{ font-size: 1.1rem !important; }}
[data-testid="stCheckboxContainer"] {{ min-height: 48px !important; }}
[data-testid="stCheckboxContainer"] label {{ font-size: 1.1rem !important; }}
[data-testid="stExpander"] {{ min-height: 48px !important; }}
[data-testid="stExpander"] summary {{ font-size: 1.1rem !important; padding: 12px 16px !important; min-height: 48px !important; }}
[data-baseweb="tag"] {{ font-size: 1rem !important; padding: 4px 10px !important; }}
.stDownloadButton > button {{ min-height: 52px !important; font-size: 18px !important; }}

/* === Onboarding 歡迎頁 === */
.welcome-hero {{
    text-align: center;
    padding: 2rem 1rem 1rem 1rem;
    margin-bottom: 1.5rem;
}}
.welcome-title {{
    font-size: 2.6rem;
    font-weight: 700;
    color: #1E293B;
    margin-bottom: 0.5rem !important;
}}
.welcome-subtitle {{
    font-size: 1.25rem;
    color: #475569;
    margin: 0;
}}
.step-card {{
    background: white;
    border-radius: 16px;
    padding: 1.5rem 1rem;
    text-align: center;
    box-shadow: 0 4px 12px rgba(0,0,0,0.06);
    border: 1px solid #E2E8F0;
    height: 100%;
    min-height: 220px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}}
.step-card:hover {{
    transform: translateY(-3px);
    box-shadow: 0 8px 20px rgba(0,0,0,0.1);
}}
.step-num {{
    width: 44px;
    height: 44px;
    border-radius: 50%;
    color: white;
    font-size: 1.5rem;
    font-weight: 700;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 0.75rem;
}}
.step-1 {{ background: linear-gradient(135deg, #3B82F6, #1E40AF); }}
.step-2 {{ background: linear-gradient(135deg, #F59E0B, #92400E); }}
.step-3 {{ background: linear-gradient(135deg, #10B981, #065F46); }}
.step-icon {{
    font-size: 2.2rem;
    margin-bottom: 0.5rem;
}}
.step-card h3 {{
    font-size: 1.3rem;
    font-weight: 700;
    color: #1E293B;
    margin: 0.5rem 0;
}}
.step-card p {{
    font-size: 1rem;
    color: #475569;
    line-height: 1.5;
    margin: 0;
}}

/* === 狀態色票圖例 === */
.legend-card {{
    border-radius: 12px;
    padding: 1rem 0.5rem;
    text-align: center;
    border: 2px solid;
    height: 100%;
    min-height: 130px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
}}
.legend-emoji {{ font-size: 1.8rem; margin-bottom: 0.3rem; }}
.legend-card strong {{ font-size: 1.05rem; font-weight: 700; }}
.legend-desc {{ font-size: 0.9rem; margin: 0.2rem 0 0 0; opacity: 0.85; }}
.legend-red    {{ background: #FEF2F2; color: #991B1B; border-color: #FCA5A5; }}
.legend-orange {{ background: #FFFBEB; color: #92400E; border-color: #FCD34D; }}
.legend-blue   {{ background: #EFF6FF; color: #1E40AF; border-color: #93C5FD; }}
.legend-green  {{ background: #F0FDF4; color: #166534; border-color: #86EFAC; }}
.legend-gray   {{ background: #F8FAFC; color: #475569; border-color: #CBD5E1; }}

/* === 角色化 CTA === */
.cta-box {{
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1.25rem 1.5rem;
    border-radius: 14px;
    border: 1px solid;
    font-size: 1.1rem;
    line-height: 1.6;
    margin-top: 1rem;
}}
.cta-icon {{ font-size: 2rem; flex-shrink: 0; }}
.cta-admin  {{ background: #F0FDF4; border-color: #86EFAC; color: #166534; }}
.cta-viewer {{ background: #FFFBEB; border-color: #FCD34D; color: #92400E; }}

/* === 手機版 onboarding === */
@media (max-width: 640px) {{
    .welcome-title {{ font-size: 1.9rem !important; }}
    .welcome-subtitle {{ font-size: 1.05rem !important; }}
    .step-card {{ min-height: auto; padding: 1.2rem 0.8rem; }}
    .step-card h3 {{ font-size: 1.15rem; }}
    .step-card p {{ font-size: 0.95rem; }}
    .legend-card {{ min-height: 110px; padding: 0.8rem 0.4rem; }}
    .legend-emoji {{ font-size: 1.5rem; }}
    .legend-card strong {{ font-size: 0.95rem; }}
    .legend-desc {{ font-size: 0.8rem; }}
    .cta-box {{ font-size: 1rem; padding: 1rem; }}
}}
</style>
"""
