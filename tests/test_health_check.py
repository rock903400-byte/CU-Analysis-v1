import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from components.health_check import render_health_check


def test_health_check_render():
    data = pd.DataFrame(
        [
            {
                "社名": "測試社",
                "社號": "001",
                "現有社員": 100,
                "現有股金": 5_000_000,
                "貸放比": 0.6,
                "儲蓄率": 0.85,
                "逾放比": 0.01,
                "開支比": 0.95,
                "開支比(年)": 0.95,
                "診斷狀態": "📊 一般狀態",
                "建議留意事項": "",
                "社員成長率(12M)": 0.05,
                "股金成長率(12M)": 0.05,
            }
        ]
    )
    df_m = pd.DataFrame(
        [
            {
                "社號": "001",
                "年月": pd.Timestamp("2023-12-01"),
                "社員數": 100,
                "貸放比": 0.6,
                "儲蓄率": 0.85,
            },
            {
                "社號": "001",
                "年月": pd.Timestamp("2024-12-01"),
                "社員數": 100,
                "貸放比": 0.6,
                "儲蓄率": 0.85,
            },
        ]
    )
    df_l = pd.DataFrame(
        [
            {
                "社號": "001",
                "年月": pd.Timestamp("2023-12-01"),
                "逾放比": 0.01,
                "開支比": 0.95,
                "提撥率": 0.02,
            },
            {
                "社號": "001",
                "年月": pd.Timestamp("2024-12-01"),
                "逾放比": 0.01,
                "開支比": 0.95,
                "提撥率": 0.02,
            },
        ]
    )

    with (
        patch("streamlit.selectbox", return_value="測試社") as mock_select,
        patch("streamlit.markdown") as mock_markdown,
        patch("streamlit.plotly_chart") as mock_chart,
        patch("streamlit.columns") as mock_columns,
    ):

        mock_columns.side_effect = lambda n: [MagicMock() for _ in range(n)]

        render_health_check(data, df_m, df_l, None, "#F0F4F8")

        assert mock_select.called
        assert mock_markdown.called
        assert mock_chart.called
        assert mock_columns.called
