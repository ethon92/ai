# 知行｜Education AI Operations Agent

以教育機構分校招生為情境的 Mini ERP + 對話式 AI Agent MVP。使用者可自然語言多輪對談，查詢各分校的 SQLite 資料。

## 功能

- SQLite Mini ERP：`branches`、`students`、`enrollments` 三張關聯資料表。
- 營運總覽：招生月增減、招生預警與營收摘要。
- 分校資料助理：以自然語言多輪查詢分校資料，對話歷史會提供給 Agent 作為上下文。
- 分校查詢：分校基本資料、學生名冊、報名明細、月度招生與營收。
- LangGraph Agent 提供分校搜尋、基本資料、名冊、報名明細、月度摘要及跨分校比較工具；可用 Ollama 或 OpenRouter 免費模型路由。Agent 僅讀取資料，不建立或修改資料。
- CSV 匯出；介面名冊不顯示學生電話等聯絡資訊。

## 快速啟動（Windows PowerShell）

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
streamlit run app.py
```

初次啟動會自動建立 `data/mini_erp.db` 並載入模擬資料。預設使用 Ollama（`.env` 中的 `OLLAMA_MODEL`），請先啟動 Ollama 並確保模型支援工具呼叫。沒有可用模型時，可暫時將 `AI_PROVIDER=demo` 作為有限的離線示範；自然語言多輪對談需使用 Ollama 或 OpenRouter。

## 啟用模型

編輯 `.env`：

- Ollama：設定 `AI_PROVIDER=ollama`、`OLLAMA_MODEL`，並先在本機啟動 Ollama、下載支援工具呼叫的模型。
- OpenRouter：設定 `AI_PROVIDER=openrouter`、`OPENROUTER_API_KEY`；預設模型為 `openrouter/free`，可用 `OPENROUTER_MODEL` 覆寫。Agent 不會把電話送給模型；報名明細查詢也會在傳給模型前移除學生姓名。

重啟 Streamlit 後生效。Agent 工具限於受控的分校資料查詢，不提供任意 SQL 或資料寫入能力。部署到 Community Cloud 時，請在 App 的 Secrets 貼入：

```toml
AI_PROVIDER = "openrouter"
OPENROUTER_API_KEY = "你的 OpenRouter API 金鑰"
OPENROUTER_MODEL = "openrouter/free"
```

Community Cloud 無法直接連到你電腦上的 `localhost` Ollama，因此部署時使用 OpenRouter API。`openrouter/free` 會路由到當下可用且支援所需能力的免費模型；免費模型有使用量限制且實際模型可能變動。更多資訊見 [OpenRouter 免費模型路由](https://openrouter.ai/openrouter/free)。

## 專案結構

```text
app.py           Streamlit 對話介面及分校查詢畫面
agent.py         LangGraph 對話 Agent、模型 Provider 與唯讀查詢工具
db.py            SQLite schema、種子資料與查詢函式
config.py        本機環境變數與 Streamlit Cloud Secrets 設定讀取
requirements.txt Python 套件
.env.example     模型與資料庫設定範本
```

## MVP 邊界

目前日期相關模擬資料會在啟動時建立，營收以報名金額加總作為示範指標。月份比較使用最新資料月份與前一月份。此專案不代表任何真實機構資料或正式 ERP。
