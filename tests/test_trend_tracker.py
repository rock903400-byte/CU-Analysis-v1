import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from components.trend_tracker import render_trend_tracker


def test_trend_tracker_render():
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
                "社名": "測試社",
                "年月": pd.Timestamp("2024-12-01"),
                "社員數": 100,
                "貸放比": 0.6,
                "儲蓄率": 0.85,
            }
        ]
    )
    df_l = pd.DataFrame(
        [
            {
                "社號": "001",
                "年月": pd.Timestamp("2024-12-01"),
                "逾放比": 0.01,
                "開支比": 0.95,
                "提撥率": 0.02,
            }
        ]
    )

    preloaded_data = (data, df_m, df_l, b"", {})

    with (
        patch("streamlit.selectbox") as mock_select,
        patch("streamlit.multiselect", return_value=["測試社"]) as mock_multi,
        patch("streamlit.checkbox", return_value=True) as mock_checkbox,
        patch("streamlit.plotly_chart") as mock_chart,
        patch("streamlit.columns") as mock_columns,
        patch("streamlit.caption") as mock_caption,
    ):

        mock_select.side_effect = ["2024-12", "2024-12"]
        mock_columns.side_effect = lambda spec: [
            MagicMock() for _ in (spec if isinstance(spec, list) else range(spec))
        ]

        render_trend_tracker(data, df_m, df_l, None, "#F0F4F8", preloaded_data)

        assert mock_select.called
        assert mock_multi.called
        assert mock_checkbox.called
        assert mock_chart.called
        assert mock_columns.called
        assert mock_caption.called
