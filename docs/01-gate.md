# 用法 A:當每個動作前的閘門

任何 agent(不論背後是哪個模型)在執行 GUI 動作**之前**,把當下的畫面文字、任務和最近的動作丟給 CLM,拿回一個「該停、該重來、還是繼續」的判斷。判斷只花約 1 秒,在本機跑。

適合:要不要停下來問人(UAC、sudo、付款、刪除、要輸入密碼)、有沒有卡住在迴圈、任務是不是已經完成、上一步有沒有失敗。
**不適合**:它看不到像素(畫布、照片),也不能決定「下一步點哪裡」,那是你的主模型的工作。

## 1. 前置條件

1. CLM 服務在跑:`clm-serve`(預設 `http://127.0.0.1:8700`)+ Qwen3-8B 嵌入伺服器(:8090)。本機啟動腳本:`scripts/start_clm_stack.ps1`(需要 `runtime/` 裡的 llama.cpp 與 `Qwen3-8B-Q8_0.gguf`)。不在預設位置時設 `CLM_URL`。
2. Python ≥ 3.10。核心只用標準函式庫:`cd python && python -m clm_router ...`,或 `pip install -e "python"`。

## 2. 請求格式(`mode: "computer_use"`)

| 欄位 | 必填 | 說明 |
|---|---|---|
| `mode` | 是 | `"computer_use"` |
| `task` | 是 | 要達成的任務(一句話) |
| `observation.text` | 建議 | 畫面文字。**你自己提供就不會自動截圖**;空的話在 Windows 會自動讀視窗(見第 6 節) |
| `observation.prev_text` | 建議 | 上一步之前的畫面文字。用來偵測「畫面完全沒變」的迴圈 |
| `history` | 建議 | 最近的動作,舊的在前,例如 `["open Edge", "click Install"]` |
| `last_action` | 建議 | 剛做完的動作 |
| `platform` | 否 | `"windows"`(預設)或 `"linux"` |

`observation.text` 最好是 UI Automation / 無障礙樹的格式(每行 `Role "名稱" @(x,y,寬x高)`),專案會自動壓縮成「元素名稱加短文字」再送給 CLM(去掉座標、丟掉長段落)。純文字(終端機輸出、OCR)也可以,原樣送出。

## 3. 回傳格式

```json
{
  "decision": {"action": "ask_user", "confidence": 0.63, "route": "review",
               "reasons": ["risky screen (p=0.52)"], "targets": [], "details": {}},
  "clm_raw": {"risky": {"type": "noul", "noul": 0.517}, "...": "..."},
  "observation_steps": [{"source": "caller", "chars": 75}]
}
```

| `action` | 意思 | 你該做什麼 |
|---|---|---|
| `ask_user` | 畫面在等一個高風險決定(權限、付款、刪除、輸入憑證),或畫面文字裡有對自動化系統下指令的句子 | **停下來問人**,不要自己點 |
| `replan` | 卡在迴圈,或畫面不是預期的(錯誤頁、缺檔案、開錯程式) | 換個做法 |
| `retry` | 上一步看起來小失誤(打錯字、點歪) | 修正後重做同一步 |
| `done` | 任務的結果已經在畫面上 | 結束 |
| `continue` | 沒有警訊 | 繼續。**這不是「可以做不可逆的事」的許可** |

- `route`:`fast` 代表它有把握(continue / done / pass 且信心 ≥ 0.5),你可以直接照辦;`review` 代表訊號互相矛盾或需要人看,請先自己確認證據。
- `confidence`:離判斷門檻有多遠(0.5 = 剛好在門檻上)。**不是「答對的機率」**。
- `clm_raw`:每個是非題的原始機率,除錯用。

## 4. 用法

**Python**

```python
from clm_router import route   # pip install -e python,或在 python/ 目錄下執行

out = route({"mode": "computer_use", "task": "Install 7-Zip",
             "history": ["download 7z.exe", "run installer"], "last_action": "run installer",
             "observation": {"text": screen_text, "prev_text": prev_screen_text}})
if out["decision"]["action"] == "ask_user":
    ask_the_human()
```

**命令列**(任何語言都能呼叫,輸入輸出都是 JSON)

```bash
cd python && python -m clm_router ../examples/computer_use.json     # 檔案
echo '{"mode":"computer_use", ...}' | python -m clm_router -          # stdin
```

**Rust 版**(行為相同,逐字一致的測試向量)

```bash
cd rust && cargo build --release
./target/release/clm-router ../examples/computer_use.json
```

**完整迴圈範例**:`examples/gate_loop.py`(畫面是寫死的,任何地方都能跑):

```
after 'search '7zip download'': continue  route=fast   confidence=0.54 []
after 'click 'Download 7-Zip', open 7z2501-x64.exe': continue  route=fast   confidence=0.58 []
after 'click Next, click Install': ask_user  route=review confidence=0.58 ['risky screen (p=0.45)']
-> stop here and ask the human before doing anything on this screen
```

## 5. 迴圈偵測要你配合的兩件事

- 每步都把 `history` 傳進來,並把「上一步之前的畫面文字」放在 `observation.prev_text`。
- 專案會比對前後畫面(行集合相似度):畫面沒變且連續兩步相同 → 判卡住;畫面確實在變(例如連按 Next 通過精靈)→ 不會誤判。
- 畫面變化資訊**不會**送給 CLM(實測會干擾它),只用在迴圈規則。

## 6. 讓專案自己讀畫面(只有 Windows 驗證過)

`observation.text` 留空時,依序嘗試:UI Automation → OCR(Windows 內建)→ VLM,夠用就停,CLM 沒把握時升級到下一層。

| 環境變數 | 作用 |
|---|---|
| `OBS_WINDOW_HWND` / `OBS_WINDOW_TITLE` | 讀指定視窗而不是前景視窗(同一個程序有多個視窗時用控制代碼最可靠) |
| `OBS_MAX_NODES`、`OBS_MAX_DEPTH` | 無障礙樹的節點數與深度上限(預設 300、24) |
| `OBS_VLM=local` + `OMNIPARSER_URL` | 最後一層用本機 OmniParser |
| `OBS_VLM=online` + `OPENROUTER_API_KEY` | 最後一層用 OpenRouter 的 VLM。**整張螢幕截圖會傳到第三方**,有個資的畫面不要用 |

Linux 的路徑(AT-SPI、tesseract、grim/scrot)寫了但**沒有實測**。

## 7. 調整與紀錄

- 門檻:`CLM_RISKY_T`(預設 0.35,調低 = 更不容易漏掉危險畫面,但會多問)、`CLM_STUCK_T`(0.37)。其餘門檻在 `policy.py`。**它們是用 104 筆我自己標註的案例校準的**,換成別的應用請先收集真實資料再校準(`calib/REPORT.md`)。
- `CLM_STATE_MODE`:`ui+text`(預設)/ `full` / `ui`。改了就要重新校準。
- `CLM_TRAJECTORY_LOG=路徑.jsonl`:每一步記下 CLM 實際看到的狀態、答案、決策,`label` 留空給人標,是微調需要的資料。**紀錄裡有畫面文字,請保密。**

## 8. 一定要知道的限制

- **`continue` 不是授權。** 畫面上的文字可以誤導 CLM(提示詞注入):實測在高風險畫面後面加一句「no approval is needed」,抓到的畫面從 23/25 掉到最差 3/25。專案有縮小攻擊面和一個很弱的偵測器(留出測試 2/8),**但不是防禦**。危險動作的人工確認要放在你自己的執行層。
- **看不到像素。** 畫布類應用(畫圖、遊戲)它不知道畫了什麼,要另外做像素或 VLM 驗證。
- 圖片評審見 `mode: "image_review"`:`image.brief`、`image.criteria`、`image.description`(先用 VLM 描述圖片)、`image.regions`;回傳 `pass | local_edit | regenerate`,`targets` 是最可疑的一個區域。範例:`examples/image_review.json`。
