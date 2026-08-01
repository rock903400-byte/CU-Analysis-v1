import sys
from pathlib import Path
from unittest.mock import patch
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from components.risk_matrix import render_risk_matrix


def test_risk_matrix_render():
    data = pd.DataFrame(
        [
            {
                "社名": "測試社",
                "貸放比": 0.6,
                "逾放比": 0.01,
                "診斷狀態": "📊 一般狀態",
                "現有社員": 100,
                "建議留意事項": "",
            }
        ]
    )
    thresholds = {
        "high_risk_ovd": 0.03,
        "liquidity_loan": 0.8,
    }

    with (
        patch("streamlit.plotly_chart") as mock_chart,
        patch("streamlit.markdown") as mock_markdown,
    ):
        render_risk_matrix(data, thresholds, "#F0F4F8")
        assert mock_chart.called
        assert mock_markdown.called
