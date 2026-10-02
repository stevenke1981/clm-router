# CLM router

CLM-v0.1-8B 只做「給定 state,對你提供的選項/問題打分」,不能生成、也不看圖(純文字)。
所以流程是:**畫面/圖片 → 文字描述 → CLM 判斷 → 把判斷+原始資料轉給主模型**。

## 使用說明(三種用法)

其他模型要怎麼用這個專案,依你的情況選一種(都可以搭配使用):

| 用法 | 說明 | 文件 |
|---|---|---|
| **A. 動作前的閘門** | 任何 agent 迴圈在每個 GUI 動作前先問 CLM:該停、重來、還是繼續(Python / 命令列 / Rust) | [docs/01-gate.md](docs/01-gate.md) |
| **B. 轉交給主模型** | CLM 預檢後,把判斷與原始資料一起送給 Claude、GPT、Ollama 等任何主模型(`--send`,或自己組提示詞) | [docs/02-handoff.md](docs/02-handoff.md) |
| **C. 當工具給模型呼叫** | 提供 **MCP 伺服器**(Claude Code 已實測)與 function calling 範例,讓模型自己決定何時檢查 | [docs/03-tool-mcp.md](docs/03-tool-mcp.md) |

最快的試用:`pip install -e "python[mcp]"` → `python examples/gate_loop.py`(用法 A 範例)→ `python examples/mcp_smoke.py`(用法 C 的協定冒煙測試)。需要先啟動 CLM 服務(見用法 A 第 1 節)。

## 流程

1. 呼叫端提供文字化的觀察(UI 文字/無障礙樹/OCR,或圖片的描述與各區域描述)。
2. `POST {CLM_URL}/v1/systemone` 一次問多題(實測 CLM 對**是非題(`noul`)**最準,多選題零樣本很差,所以全部用是非題)。
3. `policy` 把答案轉成決策(決策樹,門檻見「校準」):
   - `computer_use`: `ask_user`(畫面等待高風險決定)> `done` > `replan`(歷史迴圈規則,或 CLM 認為卡住/畫面非預期)> `retry`(上一步失敗)> `continue`。
   - `image_review`: `regenerate`(整張根本錯誤)> `pass`(滿足每項條件)> `local_edit`;`targets` 是最可疑的一個區域,完整排名在 `details.region_scores`。
4. `route=fast`(continue/done/pass 且信心 ≥ 0.5)→ 主模型直接執行;否則 `review` → 主模型要重新檢查證據。信心 < 0.5 代表訊號互相矛盾,觀察層會升級到下一層重新觀察。
5. `--send` 時把 `{clm_decision, clm_raw, context}` 轉給主模型。

## 使用

```powershell
pip install contrastive-lm ; vllm serve Qwen/Qwen3-8B --served-model-name qwen3-8b --runner pooling --max-model-len 2048 --port 8090
clm-serve                                  # CLM API :8700

# Python (純標準庫)
cd python ; python -m clm_router ..\examples\computer_use.json [--send]
# Rust
cd rust ; cargo run --release -- ..\examples\image_review.json [--send]
```

環境變數: `CLM_URL`(預設 http://127.0.0.1:8700)、`MAIN_PROVIDER`(`anthropic`|`openai`,後者為任何 OpenAI 相容端點)、
`MAIN_MODEL`(例如 `claude-sonnet-5-5`,或你的 GPT 模型名)、`MAIN_BASE_URL`、`ANTHROPIC_API_KEY` / `OPENAI_API_KEY`。

離線測試:`python examples/mock_clm_server.py` 啟動假的 CLM 服務。

## 注意

- 閾值是在 104 + 48 筆手寫案例上擬合的起手值,需用真實軌跡重新校準(見下方「校準」與 `calib/REPORT.md`);官方 SOTA 數字來自 fine-tune,zero-shot 準確度請自行驗證。
- 官方說明 CLM 的多模態版本預計 2026-10 發布;屆時圖片可直接餵 CLM,不必先轉文字。
- 判斷不是安全邊界:高風險動作仍應在 executor 層做權限檢查。

## 觀察層(畫面 → 文字)

`computer_use` 請求沒有提供 `observation.text` 時,會自動由便宜到貴依序嘗試,夠用就停:

| 層 | 來源 | 備註 |
|---|---|---|
| a11y | Windows UI Automation(`scripts/uia_dump.ps1`)/ Linux AT-SPI(`scripts/atspi_dump.py`) | 免費、約 50 ms |
| ocr | Windows 內建 `Windows.Media.Ocr`(`scripts/ocr.ps1`)/ Linux `tesseract` | 免費、本機 |
| vlm | `OBS_VLM=local` → OmniParser;`OBS_VLM=online` → OpenRouter | 見下 |

CLM 信心不足(`low confidence`)時,自動升級到下一層重新觀察再問一次;`observation_steps` 會記錄每次用了哪一層。
呼叫端自己帶 `observation.text` 時不會重新觀察。VLM 預設關閉,必須明確設定:

```powershell
# 本地 OmniParser(POST /parse/ ,需自行啟動 omnitool/omniparserserver)
$env:OBS_VLM="local"; $env:OMNIPARSER_URL="http://127.0.0.1:8000"

# 線上免費(預設 nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free,可用 OBS_ONLINE_MODEL 換)
$env:OBS_VLM="online"; $env:OPENROUTER_API_KEY="sk-or-..."
```

**隱私**:`online` 會把整張螢幕截圖傳到第三方;免費模型是否記錄/訓練請自行確認條款,不要在有密碼、個資的畫面使用。
`image_review` 若沒給 `image.description` 但給了 `image.path`,且 `OBS_VLM=online`,會用線上 VLM 先描述圖片再交給 CLM。
腳本以 `-ExecutionPolicy Bypass` 單次呼叫,不改系統的執行原則。

## 校準

`calib/` 有電腦操作 104 筆、圖片評審 48 筆的手工標註案例與評估腳本,完整結果與限制見 `calib/REPORT.md`(**請先讀限制:標註是助手自己寫的,數字偏樂觀**)。

| 項目 | 做法 | 結果 |
|---|---|---|
| `risky` | 問「畫面是否正等待不可逆/提權/花錢/外傳/憑證的決定」,門檻 0.30(`CLM_RISKY_T`) | 精確率 0.92 / 召回 0.92 |
| `stuck` | 歷史重複規則 **或** CLM ≥ 0.35(`CLM_STUCK_T`);規則會參考 change 訊號 | 精確率 0.88 / 召回 1.00 |
| `next` | 五選一零樣本只有 16–29%,改成是非題決策樹(risky > done > loop > unexpected > small failure > continue) | CV 正確率 0.74 |
| 圖片評審 | 「是否滿足每項條件」+「是否根本錯誤」決策樹;區域只取分數最高的一個 | CV 正確率 0.85(原本 0.65) |

- **change 訊號**:呼叫端在 `observation.prev_text` 放上一步的觀察文字即可自動比對;只用於迴圈規則,不送給 CLM(送了反而變差)。
- **所有門檻都綁定送給 CLM 的確切文字**(CLM 取最後一個 token)。改動提問或狀態格式後必須重新校準,見 `calib/REPORT.md` 第 3 節。
- 重新校準流程:`python calib/eval_next2.py` → `python calib/eval_final.py`;圖片:`python calib/eval_image.py`。
- 端對端驗證:`python calib/check_prod.py`、`python calib/check_image_prod.py --rust`。

## 實測:用 Paint 畫蠟筆小新(`demos/`)

`python demos/paint_shinchan.py` 會在 Windows 11 小畫家(繁中介面)畫出蠟筆小新風格的半身像,並用 RecordScreen 錄影。
每一步:讀 Paint 無障礙樹 → 真 CLM 判斷(`ask_user` 就停)→ 才執行滑鼠操作;填色前用像素檢查區域是否封閉,填完驗證顏色面積、漏色就 Ctrl+Z;
結尾截圖 → 線上 VLM 描述 → CLM 圖片評審。成果:`demos/shinchan_result.png`,日誌:`demos/paint_run.json`。

實測中學到的(都已寫進程式):
- **無障礙樹看不到畫面像素**:CLM 對「整張畫布被填成黑色」的狀態仍判 `continue`。畫圖這類任務必須有像素/VLM 層驗證,CLM 閘門只能擋住對話框、提權這類「文字能看出來」的風險。
- **Ctrl+A 會讓 Paint 自動切到「選取」工具**,之後的拖曳不會畫線;重新選回筆刷。
- **填色工具有容差,抗鋸齒邊緣會讓顏色漏出去**,這是非決定性的:同樣的順序有時成功有時整張變色。解法:先填差異最大的顏色(白→黑,再填膚色)、填前檢查封閉、填後驗證並復原。
- **RecordScreen 的「單一視窗」模式錄不到 Paint**(WinUI 視窗,輸出全黑,只有游標);要改錄整個桌面(`--window` 可強制單一視窗)。
- 遠端桌面(RDP)視窗被最小化時,任何截圖/錄影都會失敗(「控制代碼無效」/ gdigrab error 5)。
- CLM 圖片評審對最後成果給 `pass`(信心 0.77);對尖角沒填黑的前一版給 `local_edit`。但它的 `targets` 無意義,因為 VLM 描述沒有按 `[region] 描述` 格式輸出,區域名稱被誤解析成 `[0]`。

## 實測:用瀏覽器操作 Google Flow 生成圖片(`demos/flow_step.py`)

流程:在 Chrome 新視窗開 `flow.google.com`(沿用既有登入)→ 新增專案 → 輸入提示詞 → 生成(Nano Banana 2,畫面上寫明「使用 0 點」)→ 開啟圖片 → 下載(1K 原始大小)→ 用 VLM + CLM 檢查下載的檔案。
`flow_step.py` 一次做一個動作(`look / click / clickxy / type / key / shot`),**每個動作前都先讀頁面、讓真的 CLM 判斷**,`ask_user` 就拒絕。

實測發現並修正(Python 與 Rust 都已更新):
- **Chrome 的網頁內容不一定在無障礙樹裡**:樹是延遲建立的,休眠後再查要幾秒;而且觀察層的預設深度 8 太淺,網頁內容在更深處(現在預設 24,`OBS_MAX_DEPTH` 可調)。
- 只檢查「有沒有 `Document` 節點」會被騙:Chrome 會先給一個沒有子節點的 `Document`。現在改成檢查它底下有沒有內容,沒有就自動補上 OCR(頁面文字排在前面)。
- 多個 Chrome 視窗共用同一個程序,用標題找視窗不可靠;新增 `OBS_WINDOW_HWND`(精確指定視窗控制代碼)與 `scripts/find_window.ps1`。
- VLM 區域解析:`\s*` 會吃掉換行,把 `[key regions]` 標題行當成區域並吞掉下一行;改為 `observe.parse_regions()`(有測試)。

Flow 本身要注意的:
- 頁面上「垃圾桶(移至垃圾桶)」緊鄰「下載」,下載選單裡還有「升級」(訂閱推銷)與提升畫質選項;程式只依**元素名稱**點擊,不用座標猜。
- 帳戶點數即將用盡的橫幅就在頁面上;「新增 AI 點數」是購買連結,絕不點擊。
- 這次流程中 CLM 的閘門全部是 `continue`:沒有遇到登入、付款、刪除確認這類畫面,**閘門的攔截能力在這個測試裡沒有被檢驗到**。
- 圖片檢查:符合需求 → `pass`(meets 0.945);同一張圖配上錯誤需求(藍色跑車)→ `local_edit`(meets 0.25)。能分辨「符合/不符合」,但「整張根本錯誤」的問題(`global_fault`)只有 0.07,應該要判 `regenerate` 卻沒有。

## 對照 Jev 技能文件後的結論

詳見 `calib/REPORT.md` 第 5 節。
- 文件的**原則**有效(原子化、只問是非題、策略放程式碼);它的**寫法細節**(true/false 長判準、物件式選項)在 CLM v0.1 上反而變差,別照搬。
- **`risky` 可以被畫面上的文字騙過**(抓到的高風險畫面 23/25 → 最差 3/25),網頁、文件這類不受信任的內容尤其要小心。`injection_signal()` 只是弱絆線(留出測試 2/8),**CLM 的 `risky=false` 不能當授權**,敏感動作必須在執行層做人工確認。

## 縮小攻擊面、重新校準,以及官方貼文的啟發

詳見 `calib/REPORT.md` 第 6、7 節。
- **`compact.py`**:送給 CLM 的畫面只保留結構化元素與短文字(預設 `ui+text`,`CLM_STATE_MODE` 可改 `full` / `ui`)。準確度沒損失,狀態文字縮小 40–75%,對長句注入明顯更抗(最差 6/25→20/25),但**短句注入仍可繞過,不是防禦**。因為送出的文字變了,所有門檻已重新校準(CV 正確率 0.74→0.80)。
- **候選動作排名(`/v1/rank`)零樣本不能用**(正常 0.12、出錯 0.00,隨機 0.20),貼文的 81.6% 來自微調。
- **用 52 筆資料微調投影頭沒有效果**(樣本外 AUC 持平或略差),瓶頸是資料量。新增 `CLM_TRAJECTORY_LOG=路徑.jsonl`:選擇性記錄 CLM 實際看到的狀態、答案與決策(`label` 留空給人填),累積可信標註後再微調。**紀錄含畫面文字,請保密。**

## 授權

Apache License 2.0(與 [CLM](https://github.com/Contrastive-LM/CLM) 相同),見 `LICENSE` 與 `NOTICE`。本專案不包含 CLM 的程式碼或權重,只透過 HTTP 呼叫它。
`demos/` 的蠟筆小新描圖範例**不附參考圖**(有著作權),請自備圖片放到 `demos/ref/` 後用 `vectorize.py` 轉換。
