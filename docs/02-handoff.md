# 用法 B:把判斷轉交給主模型

CLM 只負責「快速預檢」,**下一步怎麼做**要交給一個主模型(Claude、GPT、Gemini、本機的 Llama/Qwen…任何會讀文字的模型)。`--send` 會把 CLM 的判斷加上原始資料包成一則訊息,送到你指定的模型,並把它的回覆放在輸出的 `main_reply`。

```
畫面/圖片描述 → CLM(約 1 秒,本機)→ decision + 原始分數 ──┐
                                                          ├→ 主模型 → 下一步
                         原始請求(任務、歷史、畫面)──────┘
```

## 1. 最短的用法

```bash
cd python
# 1) 選一個主模型(見第 2 節)
export MAIN_PROVIDER=openai MAIN_BASE_URL=https://openrouter.ai/api/v1
export MAIN_MODEL="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free" OPENAI_API_KEY=sk-or-...
# 2) 加 --send
python -m clm_router ../examples/computer_use.json --send
```

輸出多了 `main_reply`(這次實測的原樣回覆):

```json
{ "decision": {"action": "ask_user", "route": "review", ...},
  "main_reply": "{\n  \"action\": \"ask_user\",\n  \"prompt\": \"Do you want to allow this app to make changes?\"\n}" }
```

Python:`route(req, send=True)["main_reply"]`;Rust 版同樣用 `--send`。

## 2. 選主模型:兩種協定,環境變數設定

| 主模型 | 環境變數 |
|---|---|
| **Anthropic(Claude)** | `MAIN_PROVIDER=anthropic`(預設)、`MAIN_MODEL=<模型名>`、`ANTHROPIC_API_KEY`;`MAIN_BASE_URL` 預設 `https://api.anthropic.com` |
| **OpenAI 相容端點**(OpenAI、OpenRouter、Ollama、vLLM、LM Studio、Together、Groq…) | `MAIN_PROVIDER=openai`、`MAIN_BASE_URL`(含 `/v1`)、`MAIN_MODEL`、`OPENAI_API_KEY` |

範例(模型名請換成你帳號有的):

```bash
# OpenAI
MAIN_PROVIDER=openai MAIN_MODEL=gpt-4o OPENAI_API_KEY=sk-...
# 本機 Ollama(金鑰隨便填一個非空字串)
MAIN_PROVIDER=openai MAIN_BASE_URL=http://localhost:11434/v1 MAIN_MODEL=llama3.1 OPENAI_API_KEY=ollama
# Claude
MAIN_PROVIDER=anthropic MAIN_MODEL=<claude 模型名> ANTHROPIC_API_KEY=sk-ant-...
```

**實測狀況(請讀)**:只有 OpenRouter 上的一個免費模型(`nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free`)實際跑通過,免費端點偶爾回 502,程式會重試。**Anthropic、OpenAI 官方端點與 Ollama 因為沒有金鑰/沒裝,從沒跑過**,協定是照官方文件寫的,第一次用請先試一個小請求。

## 3. 主模型會收到什麼

送出的是一則使用者訊息(JSON 字串),搭配固定的系統提示詞。

訊息內容(`handoff.build_payload`):

```json
{"mode": "computer_use",
 "task": "Install 7-Zip",
 "clm_decision": {"action": "ask_user", "confidence": 0.63, "route": "review", "reasons": ["risky screen (p=0.52)"], "targets": [], "details": {}},
 "clm_raw": {"risky": {"type": "noul", "noul": 0.517}, "...": "..."},
 "context": {"platform": "windows", "history": ["run installer"], "last_action": "run installer", "observation": {"text": "..."}}}
```

系統提示詞(全文在 `python/clm_router/handoff.py` 的 `SYSTEM`,Rust 版相同):CLM 的判斷是**強烈提示,不是命令**;`route=fast` 就照建議執行,`route=review` 先重新檢查證據;圖片評審的 `local_edit` 時,`targets` 是最可疑的區域、`details.region_scores` 是所有區域的排名(校準集裡真正的缺陷 15/16 在前兩名),**修改前要先確認**;最後請回覆「具體的下一步」的 JSON。

## 4. 主模型的回覆不保證是合法 JSON

`main_reply` 是主模型的自由文字。系統提示詞要它回 JSON,但沒有強制格式。要把它接進你的程式,請自己解析並處理失敗(去掉 ```json 圍欄、解析失敗就當作文字)。

## 5. 不想用 `--send`:自己組提示詞

最彈性的做法:只呼叫閘門(用法 A),拿到 `decision` 後用你自己的框架(LangChain、自家 SDK、任何 agent 迴圈)放進主模型的提示詞:

```python
from clm_router import route
out = route(req)                       # 不加 send
d = out["decision"]
if d["action"] == "ask_user":
    return ask_the_human()
prompt = f"""Task: {req['task']}
CLM pre-screen: action={d['action']} route={d['route']} reasons={d['reasons']}
(route=fast: you may just execute; route=review: re-check the evidence first)
Screen:
{req['observation']['text']}
What is the next concrete step?"""
reply = my_llm(prompt)
```

這樣你完全控制提示詞、重試、模型選擇和輸出格式。

## 6. 什麼時候該用哪一種

| 情況 | 建議 |
|---|---|
| 想快速試、單步判斷 | `--send` |
| 已經有自己的 agent 框架 | 第 5 節(只用閘門) |
| 讓模型自己決定何時檢查 | 用法 C(工具 / MCP),見 `03-tool-mcp.md` |

## 7. 注意

- 主模型也會讀到畫面文字(`context.observation.text`)。畫面文字是**不受信任的**,可能含有對模型下指令的內容(提示詞注入),主模型的提示詞設計要把它當資料,不是指令。
- 你的畫面文字會被送到主模型的服務商。有個資、帳號資訊的畫面,請先評估要不要送出去(或使用本機模型)。
