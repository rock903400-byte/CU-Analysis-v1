# AGENTS.md — deploy/

**唯一上線來源**：GitHub `rock903400-byte/CU-Analysis-v1` → Streamlit Cloud 自動 rebuild（1–3 分）
線上 app：https://cu-analysis-v1-vizgphhwjwmfkvrrktdjte.streamlit.app

## 指令

```bash
streamlit run app.py              # 開發
pytest tests/ -v                  # 全部 114 個
pytest tests/test_xxx.py -v       # 單檔
pytest tests/test_xxx.py::TestX::test_y -v  # 單一測試
python tests/sim_100_journeys.py  # 70 旅程 AppTest 模擬
python tests/sim_1000_users.py    # 1000 情境 + AppTest 模擬
python tests/sim_10k_users.py     # 10000 人壓力測試
python tests/probe_cloud.py       # 線上 HTTP 探測（100 probes）
```

```bash
# Linux / macOS
make fmt       # black（全 repo）
make lint      # flake8
make type      # mypy
make test      # pytest -v
make verify    # lint + type + test（一錯就停）
make all       # fmt + verify

# Windows (pwsh 7)
pwsh scripts/all.ps1            # fmt → lint → type → test（一錯就停）
pwsh scripts/all.ps1 -SkipFmt   # 跳過 fmt
pwsh scripts/all.ps1 -SkipType  # 跳過 mypy
```

CI（`.github/workflows/ci.yml`）：push/PR main 自動跑 `black --check → flake8 → mypy → pytest --cov`。注意 CI 的 `black --check` 只掃指定目錄（`app.py config.py common/ components/ data/ services/ views/ charts/`），而 `make fmt` 格式化全 repo。

mypy 只掃 `app.py config.py common/ components/ data/ services/ views/ charts/`，跳過 `tests/`。`pyproject.toml` 已寬鬆：`ignore_missing_imports=true`、關閉 `var-annotated` / `call-overload` / `attr-defined`，其餘 `arg-type` 仍要修。

## 架構

`app.py` 主入口，執行順序：
1. `_DEFAULTS` session state 初始化（**所有 key 都在這定義**，第 42 行）
2. 雲端預載：`?file=xxx` → `cloud.py` → `excel_processor.py` → `st.session_state.preloaded_data`
3. `?csv=xxx` → `csv_processor.py` → `st.session_state.preloaded_csv`
4. 登入關卡 → 資料過濾 → 路由（overview / war_room）

```
app.py
 ├─ components/    onboarding（歡迎頁）, charts（瀑布/YoY/趨勢/排名）, metrics（KPI 卡）
 ├─ views/         overview（風險診斷）, war_room（財務戰情室，6 tabs）
 ├─ services/      auth, cloud（Supabase）, diagnosis_service（燈號）, finance_service（YoY/瀑布）
 ├─ data/          excel_processor（Excel→5-tuple）, csv_processor（CSV→DataFrame）
 ├─ charts/        style（Plotly 全域樣式）
 └─ common/        classifier, cleaning, constants, dates, thresholds, utils
```

## 業務規則（不可任意修改）

- 個社模式用「本社」標籤；區會/管理員用「區域平均」或「全台平均」
- 股市燈號：紅漲＝好、綠跌＝壞（社員/股金/收入/淨利/淨值比），綠漲＝壞、紅跌＝壞（開支/逾放/負債比/支出）
- 風險燈號字串在 `common/classifier.py` 與 `tests/test_classifier.py` **兩邊都要同步**（hardcode 字串）
- CSV 年月是字串 `YYYYMM`（非 datetime），`diagnosis_service.py` 自行 `pd.to_datetime(format="%Y%m")`
- `preloaded_data` 為 5-tuple：`(data, df_m, df_l, raw_bytes, region_map)`，索引 0‑4
- `df_l` 可能為空：過濾後先 guard 再算 YoY，否則 `NaT - DateOffset` 噴 TypeError
- `st.query_params.get("file")` 只讀第一個值（Streamlit 限制）
- `MAX_ATTEMPTS = 5`（`config.py:70`），admin 密碼 fallback 是 `""`（**無任何後門字串**，需在 secrets 設定 `admin_password`）

## 易踩的坑

**`excel_processor.py:process_excel_final`**
- `_get_value` 是 `common.dates.get_value` 的 alias（第 12 行），**不要再寫巢狀同名函式**（過去 bug：誤用巢狀 `get_v` 導致共享連結全壞）
- 提撥率可能缺欄，先 `if "提撥率" in df_l_raw.columns` 檢查；"無逾期" 保留為 `-1.0` sentinel，下游顯示邏輯檢查 `x == -1`
- 百分比清洗（`defensive_clean_series`）每欄規則不同
- **Cache buster**：函式內 `_VER` 與模組層 `_CACHE_VER` **兩處都要 bump**（目前 v7）
- 合併鍵一律用「社號」
- 改完必跑 `pytest tests/test_excel_processor.py::TestProcessExcelFinal`

**`views/` 資料 Guard**
- 所有使用 `df_m` 或 `df_l` 的地方必須先 `if x is None: return` 再呼叫 `.empty`，否則 AppTest 和正式環境都會 crash

**`tests/SafeSessionState` 沒有 `.get()`**
- `at.session_state` 是 `SafeSessionState` 代理，不支援 `.get()`
- 必須用 `"key" in at.session_state and at.session_state["key"]` 或 `try/except KeyError`
- 誤用會噴 `AttributeError: get not found in session_state`，整趟旅程變 `completed=False`

**`tests/conftest.py` autouse 清除 `st.cache_data`**
- 每次測試後自動 `st.cache_data.clear()`，避免跨測試快取干擾
- 新增 AppTest 測試通常不用自己管 cache，但如果加的是純函數 cache 測試，要自己手動 clear

**`load_thresholds`（`common/thresholds.py`）**
- 從 `secrets["thresholds"]` 讀，缺欄 fallback 到 `DEFAULT_THRESHOLDS`
- `ThresholdsConfig`（Pydantic）強制所有門檻值 `> 0`，否則拋 `ValueError`

**生成分享連結 debounce**
- `app.py` 用 `share_generating` 鎖定 + disabled 按鈕 + `try/finally` 重置
- 測試注意 disabled button 無法被 AppTest click

**`rate_ratio` 燈號語意**（`services/diagnosis_service.py`）
- `green/yellow/red/gray`，gray 代表「資料不足」（None 或 NaN）
- 任何下游 UI 接 `rate_ratio` 回傳值必須處理 `gray`（不可當成 `green` 預設）

**`classifier.classify` NaN guard**（`common/classifier.py:4-11`）
- 任一關鍵欄位（`eOvd, eLoan, R0, R1, memG, shrG, M0-3, S0-3`）為 None/NaN → 回傳 `"⏸️ 資料不足"`
- 改 `classify` 邏輯後，務必 bump `excel_processor.py` 內的 `_VER` / `_CACHE_VER`

**URL 參數長度驗證**（`app.py:70`）
- `_MAX_PARAM_LEN = 256`，超過則 `st.error` 並忽略
- 防 DoS / 損壞連結

**Streamlit 1.56 行為**
- `use_container_width=True` 在 Streamlit 1.42+ 已有 deprecation warning（功能不受影響，但 CI 輸出會多一行）
- `axis=1` 在 pandas 3 仍可用但 deprecation warning

**Streamlit Cloud secrets TOML 區塊順序**
- **頂層 key 必須寫在第一個 `[section]` 之前**，否則會被靜默丟棄（不報錯）
- 症狀：`safe_secrets().get("admin_password")` 回空、`list(st.secrets.keys())` 找不到那個 key
- 正確順序：所有 `BUCKET_NAME = "..."` / `admin_password = "..."` 寫最上面，再寫 `[supabase]` `[thresholds]`
- 錯誤示範：`[supabase]` 後面寫 `BUCKET_NAME = "..."` → 解析後 key 消失

**Supabase Free tier inactivity 防暫停**（`.github/workflows/keepalive.yml`）
- Free tier 專案 **7 天低活動自動 pause**，DNS 被回收後無法用 Storage API 喚醒
- keepalive 打的是 **`/rest/v1/`（database API）**，不是 Storage API（後者可能不算 activity）
- 排程每天 UTC 06:00 / 18:00 各跑一次
- **ping 失敗判定**（`f2add11`）：`000`（DNS/連線失敗）與空值都算 failure——**不要只查空字串**，curl 連線失敗時 `%{http_code}` 輸出的是 `000`（非空），舊寫法會誤判 alive 讓 recover 永不觸發
- **防呆**：ping 前檢查 `SUPABASE_URL` 是否包含 `SUPABASE_PROJECT_REF`，不含直接 fail（避免打到錯專案還自以為成功）
- `recover` job 是兩階段：先查 Management API status → `ACTIVE_HEALTHY` 跳過；`PAUSED` / **`INACTIVE`** 才 POST `/rest/v1/projects/{ref}/restore`
- 注意 Management API 的 paused 狀態字串是 **`INACTIVE`**（不是 `PAUSED`），兩者都要認
- 自動 Restore 需要 GitHub Secrets：`SUPABASE_PAT`（Personal Access Token）和 `SUPABASE_PROJECT_REF`
- 如果 Restore 也失敗 → 自動開 GitHub issue（`ops` label）通知
- PAT 用完後建議到 https://supabase.com/dashboard/account/tokens 撤銷重長
- **實測記錄**：2026-08-05 CUSA-App 曾被 pause（`f2add11` 前的舊 workflow 天天假綠勾沒人發現），修正後靠此機制自動 Restore 成功、ping 回復 `401`（有回應即 active）
- 偵錯技巧：`gh run list --workflow=keepalive.yml --limit 50` 看歷史，`gh run view <id> --log` 看實際 HTTP code

**`app.py` 雲端錯誤分類**（`app.py` 頂層 `_CLOUD_ERR` tuple）
- 分享連結下載/上傳的 `except` 會比對錯誤字串是否為雲端連線問題（DNS/ConnectionError）
- 是 → 顯示「☁️ 雲端服務暫停中，請通知管理員」
- 否 → 顯示原始錯誤（便於 debug）
- 如果要改錯誤分類邏輯，改 `_CLOUD_ERR` tuple 即可

**`preload_err` 自動清空**（`app.py` preload 區段）
- 成功載入後會自動清空 Excel 與 CSV 兩個錯誤旗標
- 手動 reset：`st.session_state.pop("preload_err", None)` / `pop("preload_csv_err", None)`

## 測試

| 檔案 | 性質 |
|------|------|
| `test_*.py`（13 個） | pytest 114 cases（含 `conftest.py` autouse fixture） |
| `sim_100_journeys.py` | 70 旅程 AppTest 模擬，產 `sim_100_REPORT.md` |
| `sim_1000_users.py` | 1000 情境 + AppTest，產 `sim_1000_results.json` |
| `sim_10k_users.py` | 10000 人壓力測試，產 `sim_10k_results.json` |
| `probe_cloud.py` | 線上 HTTP 探測（100 probes） |
| `manual_human_journey.py` | 手動 E2E 計數，元素改動後要更新預期值 |

- `tests/test_classifier.py` 硬編碼狀態字串，改 `common/classifier.py` 要同步
- `.json` 檔已被 `.gitignore` 排除（`*.json` 規則涵蓋），sim 結果只在本地留存

## 部署

1. `git add → commit → push main`
2. Streamlit Cloud 自動 rebuild（1–3 分）
3. 勿 `--force` push
4. Secrets 在 Streamlit Cloud Dashboard 設定（模板 `.streamlit/secrets_template.toml`，`admin_password` 必填，**不要**留 `666` 之類預設）
