# 安裝給 Codex、OpenCode、Pi

共用兩個文字工具：`clm_gate` 判斷 GUI 畫面，`clm_review_image` 檢查圖片描述。Codex、OpenCode 使用 stdio MCP；Pi 使用 `clm-router` skill 加 CLI。三者走相同的輸入驗證、CLM 請求與結果格式。

## 一次安裝

在專案根目錄執行（安裝程式需要 Python 3.11+；路由器本身支援 3.10+）：

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -e './python[mcp]'
./.venv/Scripts/python.exe scripts/install_agents.py
./.venv/Scripts/python.exe scripts/install_agents.py --apply
```

第一個 installer 指令只預覽。第二個才寫入設定，修改既有檔案前會建立 `.clm-backup-時間戳記` 備份；重複安裝且內容相同時不寫檔。

安裝位置：

| Agent | MCP | Skill |
|---|---|---|
| Codex | `~/.codex/config.toml` 的 `mcp_servers.clm-gate` | `~/.codex/skills/clm-router/` |
| OpenCode | `~/.config/opencode/opencode.json` 的 `mcp.clm-gate` | `~/.config/opencode/skills/clm-router/` |
| Pi | 透過 CLI 使用 | `~/.pi/agent/skills/clm-router/` |

預設遵循 `CODEX_HOME`、`XDG_CONFIG_HOME`、`PI_CODING_AGENT_DIR`。`--home C:/Users/steven` 指定使用者目錄並忽略這些路徑覆寫；`--agents codex pi` 可以只安裝部分 agent。`--python` 指定已安裝本套件的 Python；`--clm-url` 指定後端，預設 `http://127.0.0.1:8700`。

安裝程式會先檢查指定 Python 可從專案外匯入套件，並在任何寫入之前解析既有設定。它保留其他 MCP、模型及偏好設定。若已有非本程式管理的 Codex `clm-gate`，會停止並要求先處理衝突。若 OpenCode 使用 `opencode.jsonc`，會停止，請手動合併下面的設定，避免兩份設定互相覆蓋。

```json
{
  "mcp": {
    "clm-gate": {
      "type": "local",
      "command": ["D:/clm/.venv/Scripts/python.exe", "-m", "clm_router.mcp_server"],
      "enabled": true,
      "timeout": 90000,
      "environment": {
        "CLM_URL": "http://127.0.0.1:8700",
        "CLM_TIMEOUT": "60",
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

此安裝流程安裝 CLM 的整合，不下載 Codex／OpenCode／Pi 客戶端或模型。移動、刪除本專案或 `.venv` 後，請用新路徑重新安裝。安裝後重新開啟 agent；Pi 也可用 `/reload` 重新載入 skill。

## 後端與使用方式

若本機已有 `runtime/llama`、`runtime/models/Qwen3-8B-Q8_0.gguf` 及 CLM serving dependencies：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_clm_stack.ps1
```

腳本重用健康服務，等待啟動最多 180 秒，可用 `-TimeoutSeconds` 調整；新啟動程序的 stdout/stderr 位於 `runtime/*-start.*.log`。MCP 啟動不會自動載入模型，模型服務須另外啟動。

Codex／OpenCode 可以直接要求：「用 clm_gate 判斷這個畫面」，並提供任務與畫面文字。Pi 可輸入 `/skill:clm-router`。CLI 範例：

```powershell
./.venv/Scripts/clm-router-tool.exe clm_gate examples/gate_tool.json
./.venv/Scripts/clm-router.exe examples/computer_use.json
```

`clm-router-tool` 與 MCP 都只接受呼叫端提供的文字；`clm-router` 是原有 route CLI，沒有畫面文字時會嘗試觀察桌面。工具輸入檔支援 UTF-8（含 BOM），`-` 接受 UTF-8 stdin。成功輸出 JSON 到 stdout；錯誤輸出 JSON 到 stderr 並回傳非零 exit code。`CLM_TIMEOUT` 控制 HTTP timeout 秒數，預設 60。

這次改善加入後端回答完整性與有限機率 `[0,1]` 驗證，避免缺值被當成零；空白觀察無法產生路由建議。圖片區域 `id=0` 可正常使用，重複或無效 id 會報錯。既有校準字串與判斷閾值保留。

## 驗證與移除

```powershell
./.venv/Scripts/python.exe -m pip install -e './python[dev]'
./.venv/Scripts/python.exe -m pytest python/tests -q
cargo test --manifest-path rust/Cargo.toml --locked
./.venv/Scripts/python.exe examples/mcp_smoke.py
codex mcp get clm-gate --json
opencode mcp list
```

`mcp_smoke.py` 使用真實 CLM，會檢查工具註冊、UAC、記事本、相符與不符圖片，以及空白輸入拒絕。一般單元測試不需要模型服務。

移除時刪除 Codex 設定中的 `# BEGIN clm-router managed integration` 到 `# END clm-router managed integration` 區塊、OpenCode 的 `mcp.clm-gate`，以及三個 agent 的 `skills/clm-router` 資料夾。備份可供比對復原；若之後有其他設定變更，請勿整份覆蓋回舊備份。

官方格式依據：[Codex MCP](https://developers.openai.com/codex/mcp/)、[OpenCode MCP](https://opencode.ai/docs/mcp-servers/)、[Pi skills](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/docs/skills.md)。
