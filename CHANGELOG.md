# CHANGELOG

本檔記錄 `deploy/` 子系統的重大變更。最近的變更列在最上面。

格式依據 [Keep a Changelog](https://keepachangelog.com/zh-TW/)，版本未定號前以「Unreleased」標示。

---

## Unreleased

### Added
- **Onboarding 引導流程**（`components/onboarding.py`）：取代原本冷冰冰的「👋 歡迎使用」一行提示
  - 3 步驟視覺化卡（📂 上傳 → 🔗 分享 → 📊 分析），hover 微動畫
  - 5 色狀態圖例（🚨 特別關懷 / ⚠️ 流動性緊繃 / 💤 資金閒置 / ✅ 穩健模範 / 📊 一般狀態）
  - 角色化 CTA：管理員／區會／個社顯示不同引導文字
  - 雲端分享連結讀取失敗時顯示明確錯誤
  - 首次登入橫幅提示（4 色速覽），使用者可一鍵永久關閉
- **CSS 設計系統**（`config.py`）：新增 `.step-card` / `.legend-card` / `.cta-box` / `.first-time-tip` 等元件樣式，含手機版 RWD

### Changed
- **Supabase 防暫停白魔法失效修正**（`.github/workflows/keepalive.yml`, `f2add11` / `d30db13`）：修掉「天天假綠勾」的 bug——ping 的失敗判定原本只檢查空字串，curl 連線失敗時 `%{http_code}` 傳的是 `000`（非空）導致永遠誤判 alive、recover 永不觸發；改為 `000` 與空值都算 failure，新增 `SUPABASE_URL` 含 `PROJECT_REF` 防呆，recover 改兩階段（先查 Management API status，`PAUSED`/`INACTIVE` 才 restore）。2026-08-05 CUSA-App 曾被 pause 後靠此自動恢復成功。
- **重構**：移除 `data/utils.py` 與 `data/classifier.py` 兩個純 re-export 的空殼檔，9 處 import 統一改為直接從 `common.*` 引用，減少 indirection。
- **穩定性**：`requirements.txt` 套件版本全數 pin 死（`streamlit==1.56.0` / `pandas==3.0.2` / `plotly==6.6.0` / `pydantic==2.12.5` / `supabase==2.28.3` / `openpyxl==3.1.5` / `pytest==9.0.3`），避免上游套件升級造成的 silent break。
- **可發現性**：經營總覽與財務戰情室的所有 metric tooltip 改為中性語言（「正值＝增加,負值＝減少」），不再依賴顏色判讀，色盲友善
- **Supabase 防暫停強化**（`.github/workflows/keepalive.yml`）：Ping endpoint 從 `/storage/v1/bucket` 改為 `/rest/v1/`（database API，確保算入 activity），加 `--retry 3`，排程增至每日 06:00 / 18:00 兩次；新增 `recover` job 在 ping 失敗時透過 Management API 自動 Restore；恢復失敗時自動開 GitHub issue 通知

### Added
- **雲端錯誤友善訊息**（`app.py`）：新增 `_CLOUD_ERR` tuple 分類 DNS / ConnectionError，分享連結下載/上傳失敗時顯示「☁️ 雲端服務暫停中」而非原始錯誤

### Verified
- 66 個 pytest 全部通過（5.83s）
- 17 個 app 模組（含新 `components.onboarding`）皆可正常 import
- `streamlit.testing.v1.AppTest` 煙霧測試通過，無 exception

---

## 2026 — 系統成熟期

### 經營總覽（views/overview.py）
- 個社模式：四項核心指標（社員總數、股金總額、開支比、逾放比）改顯示「本社」自身數值，區會/管理員維持區域/全台平均（`1ee5105`）
- 全站切換股市紅綠燈邏輯：紅漲=好 / 綠跌=壞（社員成長、股金增、收入增、淨利增、淨值比增）；綠漲=壞 / 紅跌=好（開支比升、逾放比升、負債比升、支出增）（`1ee5105`）
- 個社健檢頁新增「與區域/全台平均對比」柱狀圖
- 趨勢追蹤：預設顯示近 36 個月，支援多社別比較 + 平均線

### 財務戰情室（views/war_room.py）
- 新增「財務診斷」頁籤：負債比、淨值比、開支比、本期損益四項指標含 YoY delta 與綠/黃/紅燈號（`76f1f06`）
- 新增「深度分析」頁籤：年度科目變動偵測（YoY 異常）、關鍵科目 Top 10 排名（支援雙年度對比）
- 損益表 / 資產負債表：可選「對比上月」/「對比去年」自動計算增減金額與增減率
- YoY 對比改採「同期月份公平比對」：今年 6 個月比去年 6 個月（不再誤判）（`1bfb4aa` / `7484c76` / `b9de4c4`）
- 提撥率為 0 時顯示「無逾期」（`2e84e96`）
- 移除錯誤的放款利息收入率計算（科目代碼不正確）（`7f52409`）
- 歷年趨勢燈號改用「開支比 + 加權平均利率 + 損益」三項（`c13accd`）
- 資產負債表自動勾稽（資產 = 負債 + 權益），不平衡時紅字警告

### 風險分類引擎（common/classifier.py）
- 特別關懷判定：2/5 原則 — 連兩年虧損 / 貸放比過低且衰退 / 高逾放且惡化 / 人數連三年衰退 / 股金連三年衰退，觸發任 2 項 → 🚨 特別關懷
- 歷經多次調整：c4/c5 由兩年衰退改為三年衰退（`99b3bac` / `847cc56`）
- 觸發原因說明文字優化，避免誤判邊界條件（`5ea6a55`）
- 狀態雷達：四色卡片（特別關懷 / 流動性緊繃 / 資金閒置 / 穩健模範）顯示社名與觸發原因（`f0800da`）

### 架構重構
- 抽出 `common/` 共用套件，三子系統（deploy / 下載工具 / 報告工具）統一清洗 / 分類 / 門檻邏輯（`ae55f6a`）
- `thresholds` 統一由 deploy 為 single source of truth，新增 `savings_good` 與 `provision_good`（`46a59f5`）
- `pydantic` 校驗 `ThresholdsConfig`：門檻值必須 > 0，否則啟動失敗
- `excel_processor.process_excel_final` 與 `csv_processor.process_csv_final` 用 `@st.cache_data` 快取

### 高齡 / 手機友善
- Mobile responsive：4 欄自動疊為單欄、側邊欄抽屜式、DataFrame 橫向捲動、Plotly 響應式（`bacc99f`）
- 基礎字體 18px（手機 16px），按鈕高度 52px，觸控區域加大（`2e92822` / `f00170f`）
- 圖表禁止誤觸縮放，工具列只保留「截圖下載」
- 金額統一中文單位（萬元 / 億元），不使用 `$` 符號
- 登出按鈕二次確認，防止誤觸
- 上傳訊息持久顯示於側邊欄，不會自動消失
- 深度分析改為上下排列，方便手機閱讀（`ef3b6ee`）

### 資料處理
- `data/excel_processor.py`：5 分頁 → 3 分頁（社務及資金運用 / 放款及逾期 / 區域分類表），含民國年自動轉西元
- 支援「無逾期」字串識別（提撥率欄位）
- 防禦性清洗：`儲蓄率` / `開支比` 自動除 100 還原為小數
- `process_excel_final` 自動 rename `收支比 → 開支比`

### 雲端 / 部署
- Supabase Storage：上傳 xlsx / csv 後產生 `?file=...&csv=...` 分享連結
- 雲端預載路徑：分享連結 → 自動下載 → 自動登入
- 區會模式 vs 個社模式：依登入名稱是否在財報清單中自動判定
- 部署到 Streamlit Cloud：push `main` 即自動 rebuild

### 測試
- 66 個 pytest 全部通過
- 涵蓋：風險分類（`test_classifier.py`，含 2/5 原則所有邊界）、Excel 解析（`test_excel_processor.py`，含過去 `get_v`/`_get_value` bug 迴歸）、財務計算（`test_finance_service.py`，含 YoY 異常偵測 / 瀑布圖）、門檻校驗（`test_config.py`）、公用工具（`test_data_utils.py`，含民國年轉換 / 數字格式化）
- `process_excel_final` 端對端測試確保 5-tuple 結構正確

### 文檔
- `AGENTS.md`：5KB 完整記載架構、踩坑、近期變更、高風險函式、易踩坑點
- `README.md`：含模組結構圖、權限矩陣、技術棧
- `docs/操作手冊.html` + `docs/training.html`：給使用者看的訓練教材

---

## 2025 — 系統成長期

### 早期功能
- 風險診斷 2/5 原則雛形 + 視覺化雷達
- 財務戰情室：KPI 卡 / 瀑布圖 / 排名 Top 10 / 趨勢
- 雲端分享連結（Supabase Storage）
- 三種身份：admin / 區會 / 個社，自動判斷模式
- 密碼鎖定機制（5 次錯誤鎖定）
- 雲端預載 Excel / CSV 路徑

### 架構定型
- `app.py` 主入口，session state 統一管理
- `views/` 渲染層、`services/` 邏輯層、`data/` 處理層、`common/` 共用層
- `config.py` 集中常數與 CSS

### 重大 bug 修復（學到的教訓）
- `get_v` 命名衝突導致巢狀函式取錯值，雲端預載全壞 → 統一改為模組層 `_get_value`（`4d14c8a`）
- 提撥率欄位缺失時 `.fillna(0)` 對純量 crash → 改用 `if "提撥率" in columns` 先檢查
- `df_l` 為空時 `NaT - DateOffset` TypeError → 先 `df_l.empty` guard
- `st.secrets._parse()` 私有 API 被移除 → 改用單純 `st.secrets`
- `st.query_params.get()` 是單值，`?file=a&file=b` 只讀第一個 → 改為單檔案設計

---

## 2024 以前 — 系統初創

- 從父層 `Credit-Union-Analysis new/` 歷史備份中拆出 `deploy/` 子系統
- 確立兩條 pipeline 架構：Excel 風險診斷 + CSV 財報戰情室
- 開始建立 pytest 基礎建設
- `initial commit of deploy/ source tree`（`d00943e`）

---

## 統計

- 總 commit 數：57
- 主要貢獻者：Wind（47）、rock903400-byte（27）
- 測試數：66（100% 通過）
- 生產 Python 程式碼：~1,870 行（不含 tests / tools / HTML）
- 線上服務：https://cu-analysis-v1-vizgphhwjwmfkvrrktdjte.streamlit.app
