# 筆畫輸入法改善計劃（執行用）

> 本文件由代碼庫分析報告衍生，供負責執行改善嘅 agent 使用。
> 開始之前必讀：`README.md`、`docs/AI_BACKGROUND.md`、`docs/AI_RULES.md`、`docs/AI_WORKFLOWS.md`。

## 0. 總目標

將產品由「逐字全碼打字 + 事後詞組建議」提升為對齊 macOS 筆劃輸入法／香港 G6 傳統嘅完整 IME：**縮碼、詞組輸入、模糊容錯、誠實嘅排名數據、唔騎劫鍵盤**。兩個引擎（Python 參考實作 vs JS 運行時）回歸單一真源。

## 1. 全局約束（每個 PR 都要守）

- **永遠唔好手改生成數據**：`chrome-extension/data/*.json`、`data/stroke_db.msgpack` 只能經 `scripts/` 重新生成，PR 描述要寫明用咗邊個 script。
- Python 3.11+；擴充功能保持 MV3 + content script 可用嘅標準 API；非必要唔加 runtime dependency。
- 改 key mapping、快捷鍵、數據格式、排名預設值 ⇒ 必須同步更新 `README.md` + 相關 docs，並喺 PR 描述附**改動前後嘅具體字例排序對比**（AI_WORKFLOWS 嘅 ranking playbook）。
- 每個行為改動配 pytest 測試；涉及 `chrome-extension/` 數據或 manifest 時行 `python scripts/package_extension.py` 驗證。
- 預設行為向後兼容：新功能（五筆劃模式、數字鍵盤、關聯字等）用設定開關加入，**預設值唔好改動現有用家體驗**（唯一例外係 P0 嘅 bug 修復）。
- 每個 Phase 一個獨立 PR，可單獨合併；T3.1（JS 測試基建）建議提前做，保護之後所有 JS 改動。

## 2. 階段總覽同依賴

| Phase | 內容 | 主要檔案 | 依賴 |
|---|---|---|---|
| P0 | 鍵盤攔截 bug + 文字插入修復 | `chrome-extension/content.js`, `manifest.json` | 無 |
| P1 | 排名數據誠實化（n-gram 統一、字頻、繁簡標記、共享設定） | `scripts/`, `src/stroke_input/`, `chrome-extension/data/` | 最好先完成 T3.1 |
| P2 | 功能對齊 macOS/G6（縮碼、模糊、關聯字、詞組輸入、UI） | export scripts + `content.js` | P1 嘅數據管道 |
| P3 | 工程健康（JS 測試、清死 code、效能、文件） | 全 repo | 可提前（T3.1/T3.2 獨立） |

---

## Phase 0 — 鍵盤騎劫同文字插入（純 JS，最高優先）

**背景**：而家嘅 `content.js` 會喺 IME 關閉時吞埋 backtick、開著時吞 Ctrl/Cmd+L 等系統快捷鍵、唔理焦點全局攔截字母、連 password 欄都拦截。

### T0.1 修飾鍵同焦點門控
- **做法**：`handleKeyDown` 入面，處理筆畫鍵（`STROKE_KEYS`）同數字鍵之前加 `if (e.ctrlKey || e.metaKey || e.altKey) return;`；筆畫鍵再加焦點門控：`isTextInput(document.activeElement)` 為 false 就唔攔截（直接 return 放人）。
- **檔案**：`chrome-extension/content.js`（`handleKeyDown`，約 617–690 行）。
- **驗收**：IME 開著＋中文模式下，`Cmd/Ctrl+L`、`Cmd+J`、`Cmd+1–9` 正常運作；焦點喺按鈕/空白頁面時撳 j/k/l 唔會入咗 IME。

### T0.2 無條件攔截修復
- **做法**：Escape 同 PageUp 只喺有活躍輸入狀態（`strokeSeq.length > 0 || phraseMode || candidates.length > 0`）先 `preventDefault`；`isTextInput` 剔除 `"password"`（或者改為設定項，預設唔拦截 password）；backtick toggle 維持（係開關所必需），但配合 T0.5 提供改鍵。
- **驗收**：無輸入狀態下 Escape 可以閂網站 modal；password 欄打 j/k/l 出返英文字。

### T0.3 React/框架兼容插入
- **做法**：`insertText`（約 503–523 行）改用 `targetElement.setRangeText(text, start, end, "end")`，跟手 dispatch `new InputEvent("input", { bubbles: true, inputType: "insertText", data: text })`；若需兼容更舊 React，用 native value setter（`Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(...)`）。contenteditable 維持 `execCommand("insertText")`（保 undo）。
- **驗收**：手動測試 React 受控 input（例如用 React 官方 playground）、普通 input、textarea、contenteditable 四類；undo（Ctrl+Z）喺 input/textarea 可用就加分。

### T0.4 highlight 狀態機修復
- **做法**：↑/↓ 翻頁後 `highlightIdx` 唔好設 -1，設新頁第 0 位；入 phrase mode 時 reset `highlightIdx = 0`；明確定義「Space = 上屏 highlight（預設第一候選），PageDown = 翻頁」，同 README 對齊。
- **驗收**：翻頁後撳 Enter/Space 一定上到字；行為同 README Controls 表一致。

### T0.5 最簡 options page
- **做法**：`manifest.json` 加 `options_ui`；新增 `options.html/options.js`，設定存 `chrome.storage.local`：`toggleKey`（預設 backtick）、`interceptPassword`（預設 false）。`content.js` 初始化時讀設定。
- **驗收**：改鍵後新鍵生效、舊鍵還原成普通輸入；設定跨 tab 同步（可重用 background.js 廣播機制）。

---

## Phase 1 — 排名數據誠實化

**背景**：bigram（max-normalized，中位 0.46）同 trigram（add-k 概率，中位 0.0033）尺度差 140 倍令 trigram 形同虛設；字頻只覆蓋 11% 字且係線性映射；詞頻齋睇詞長；繁簡判斷用錯誤嘅碼位 heuristic。

### T1.1 統一 n-gram 數據管道
- **做法**：`generate_cantonese_data.py` 唔再自己產生 max-normalized bigram 表；改為將廣東話詞組同手挑詞對（而家 `("香","港",2.0)` 嗰啲）**作為語料條目**注入統一語料，然後由 `NgramModel.build_from_phrases` 一次過建模型，`ngram_export.py` 導出 `bigrams.json` 同 `trigrams.json`（同一尺度嘅平滑概率）。**修改 `NgramModel.build_from_phrases` 將 `PhraseEntry.frequency` 計入 count**（例如 count = 1 + round(freq × k)，公式寫入 docstring）。刪走 `export_for_chrome.py` 入面 bigrams/phrases「已存在就 skip」嘅邏輯，全部改為确定性重新生成。
- **檔案**：`scripts/generate_cantonese_data.py`、`scripts/export_for_chrome.py`、`src/stroke_input/data/ngram_model.py`、`tests/test_ngram_model.py`。
- **驗收**：`bigrams.json` 同 `trigrams.json` 由同一 exporter 產出；pytest 覆蓋 frequency-weighted counting；重新生成後 PR 附「香港／我哋／唔該」等字嘅上文下文 top-5 對比。

### T1.2 排名權重重校（配 T1.1）
- **做法**：統一尺度之後重校 JS 權重，令 trigram 有實際影響力；`isTrigramDriven` 嘅 ★ 徽章改為有貢獻門檻（例如 trigram 項對總分貢獻 > 0.02 先著燈）。
- **驗收**：pytest/JS 測試鎖定具體字例排序（AI_WORKFLOWS ranking playbook）；PR 附改動前後對比。

### T1.3 繁簡標記：用返 Conway 源數據
- **做法**：`scripts/download_stroke_data.py` 唔再 `rstrip('^*')` 抌走標記 —— 先查 Conway 數據倉庫確認 `^`/`*` 嘅確切語義，然後喺 `CharacterRecord` 加 `script_flag` 欄位（serializer 格式要兼容或升版）；export 時喺 `strokes.json` 每筆加可選第 4 欄；`content.js` 讀取時兼容舊格式；**刪除 `frequency_ranker.py` 嘅 `_is_likely_traditional` 碼位 heuristic**，改用料件自帶標記。
- **驗收**：pytest 用已知字斷言（錢/鐘=簡體標記唔再攞繁體加分；學/國=繁體加分）；錯誤加分案例消失。

### T1.4 字頻映射改 Zipfian + 評估真語料
- **做法**：`parse_ranking` 嘅線性映射 `1.0 - i/total` 改為 Zipf 式衰減（例如 `freq = (rank_1 / (i + s))` 歸一化，常數寫入 docstring 並註明出處）；**另開調查項**：搵有明確許可嘅繁體/港式字頻表（任何新數據源必須按 AI_RULES 記錄來源、license、生成路徑），搵唔到就先保留 Conway 排名 + Zipfian。
- **驗收**：頭部常用字（的一是）同中位字嘅分數差距明顯拉開；文件記錄公式同理據。

### T1.5 共享排名設定（codegen 單一真源）
- **做法**：新增 script 由 Python 常數生成 `chrome-extension/data/ranking_config.json`（權重、USER_FREQ_CAP、RECENCY_TAU、MATCH_QUALITY 等）；`content.js` 開機 fetch 呢份設定，刪走 JS 入面 hardcode 嘅同名常數；`manifest.json` 嘅 `web_accessible_resources` 加返份新檔。
- **驗收**：pytest 斷言 JSON 同 Python 常數一致；JS 讀唔到檔時有 embedded fallback；註釋唔再講 "aligned" 而係真對齊。

### T1.6 package_extension.py 補齊驗證
- **做法**：`REQUIRED_FILES` 加 `data/bigrams.json`、`data/trigrams.json`、`data/cantonese_freq.json`（同埋 T1.5 嘅 `ranking_config.json`）；可選加數據新鮮度檢查（比對 source TSV mtime 同輸出 JSON mtime，過舊就警告）。
- **驗收**：刪走任何一份必需 JSON 後行 `python scripts/package_extension.py` 會 fail fast。

---

## Phase 2 — 功能對齊 macOS／G6

### T2.1 五筆劃模式（頭四尾一）—— 最高價值功能
- **做法**：export 階段為每隻 **stroke_count > 5** 嘅字生成縮碼記錄 `頭4畫 + 尾1畫`（例：毓 31555），輸出**獨立檔案** `data/strokes_wubi.json`（唔好混入主索引，避免污染預設前綴搜尋）；`content.js` 加設定 `wubiHuaMode`（預設關），開啟時搜尋同時查兩份索引並合併去重。≤5 畫嘅字縮碼＝全碼，唔使重複收錄。
- **檔案**：`scripts/export_for_chrome.py`（或新 script）、`content.js`、`options.html`、`tests/`（export 測試：毓 → "31555" 存在）。
- **驗收**：開啟模式後打 31555 揀到毓；關閉時行為同而家一模一樣；README 加呢個模式嘅說明。

### T2.2 JS 模糊搜尋（對齊 Python InferenceEngine）
- **做法**：port `_EXACT_THRESHOLD = 3` 邏輯：exact prefix 結果 < 3 時，對每個位置逐個替換 1–5（跳過原位同萬用位），用現成 binary search 查每個變體；結果標 `is_exact=false`，排名時引入 match quality 項（exact 1.0 / fuzzy 0.5，權重取自 T1.5 共享設定），保證 exact 唔會被 fuzzy 蓋過（AI_RULES 底線）。
- **驗收**：JS 測試 mirror `tests/test_inference_engine.py` 嘅案例；打錯一畫都仲見到目標字（排 exact 之後）。

### T2.3 打字途中關聯字
- **做法**：候選列表非空且有上文（`lastSelectedChar`）時，將上文嘅 top bigram 接續字／詞組第二字以視覺區分嘅形式插入候選位第 2/3 位（macOS「關聯字顯示為第二或第三個候選字」做法）；設定開關，預設開。
- **驗收**：打完「香」之後再打任何筆畫，「港」以關聯字身份出現喺前列並有標記；唔影響正常筆畫匹配嘅第一位。

### T2.4 詞組直接輸入（G6 式，可選做）
- **做法**：export 階段為詞組生成「頭字頭三畫 + 尾字頭三畫」六碼（二字詞可「頭字頭三 + 尾字頭三」），輸出 `phrases_by_code.json`；`content.js` 喺輸入滿 6 碼時同時查詞組碼表，詞組候選帶「詞」徽章同字候選並列。設定開關。
- **驗收**：打「丿一丨丶丶一」可以直接上「香港」；詞組同單字候選冇衝突（詞組排獨立區或標記清晰）。
- **備註**：依賴 T1.1 嘅統一管道；工程量係 P2 最大，可以放喺 P2 最後。

### T2.5 候選窗跟游標
- **做法**：input/textarea 用 `getBoundingClientRect()` 定位 overlay 到文字框附近（預設框下方左對齊，clamp 喺 viewport 內）；contenteditable 用 `getSelection().getRangeAt(0).getBoundingClientRect()`；拖曳過之後記住手動位置。
- **驗收**：三種可輸入元素下 overlay 都出喺輸入點附近；長頁面 scroll 後位置正確或自動隱藏。

### T2.6 數字鍵盤輸入 + 中文標點
- **做法**：設定開啟後 `e.code` 為 `Numpad1`–`Numpad6` 時餵筆畫（數字行繼續做揀字）；中文模式下撳 `, . ? ! ; :` 等喺空 buffer 時直接上屏全形標點（對照表寫死，設定可關）。
- **驗收**：Numpad 可以完整打字；中文模式打逗號出「，」。

---

## Phase 3 — 工程健康

### T3.1 JS 測試基建（建議提前到 P0/P1 之前）
- **做法**：將 `content.js` 嘅純函數（`searchPrefix`、`computeScore`、`dedup`、`predictPhrase`）抽入 `chrome-extension/engine.js`，用 `window` 掛載 + `module.exports` guard 嘅雙模式寫法；用 Node 內置 `node:test` 寫測試（**唔加任何依賴**）；加 Python↔JS parity fixture：pytest 導出固定輸入嘅預期 top-N，JS 測試讀同一份 fixture 斷言一致。可順手加 `.github/workflows` 行 `pytest` + `node --test`。
- **驗收**：`node --test chrome-extension/test/` 通過；parity fixture 捉到而家嘅權重漂移（呢個測試一開始應該係紅嘅，T1.5 後轉綠）。

### T3.2 清走死管道 + 補 Conway 測試
- **做法**：grep 確認冇 import 之後，刪 `src/stroke_input/data/parser.py`、`scripts/download_data.py`、`tests/test_parser.py`、`data/dictionary.txt`、`data/graphics.txt`（30MB）；為 `download_stroke_data.py` 嘅 `expand_sequence_regex`／`parse_stroke_data` 補 pytest；修正 `你` 嘅過時驗證註釋（實際係 `[3,2,3,5,2,3,4]`）。
- **驗收**：`pytest` 全綠；repo 體積大減；`git grep` 冇殘留引用。

### T3.3 效能
- **做法**：`searchPrefix` 改為每筆記錄計一次分再 partial sort / top-K（候選上限例如 200）；萬用字元路徑 precompile regex 並 debounce；export 時每字變體設上限（按頻率留 top N，罕見字而家有成 90 個變體）；中期可研究數據搬入 service worker 或轉 binary 格式減每 tab 開銷（而家每 tab parse ~4.9MB JSON、heap ~37MB）。
- **驗收**：首畫（前綴 "1"，而家要即時排 9,177 字）喺一般文書機無可感知延遲；功能測試全綠。

### T3.4 學習功能接通或刪除
- **做法**：`autoLearnPhrase` 寫入嘅 `userPositions["__phrases__"]` 而家係 write-only —— 二揀一：(a) 喺詞組建議合併時讀返出嚟做 boost（接通），或 (b) 刪走成個功能（刪除）。JS 補返 Python 已有嘅 pins / auto-pin，或者喺 Python 側降級，兩邊重新對齊。
- **驗收**：揀邊條路都要喺 PR 寫明決定同理據；冇再存在 write-only 數據。

### T3.5 文件修正
- **做法**：README 刪 `gui/`、`output/` 嘅描述，補 `trigrams.json`（同埋今次新增嘅 `ranking_config.json` 等）；`docs/AI_BACKGROUND.md` 更新 data flow；`STORE_LISTING.md` 嘅「不收集任何資料」改為準確表述（本地儲存使用習慣）；補返 `check_keys.py`、`generate_screenshots.py` 嘅說明。
- **驗收**：文件同代碼一致；新加入嘅功能全部有 README 記載。

---

## 3. 建議 PR 切分

| PR | 內容 | 風險 |
|---|---|---|
| 1 | T3.1 JS 測試基建 + parity fixture（fixture 暫時紅可以 xfail/skip 標記） | 低 |
| 2 | P0 全部（T0.1–T0.5） | 低中（觸及鍵盤處理，需手測三種輸入元素） |
| 3 | T3.2 清死 code | 低 |
| 4 | P1 全部（T1.1–T1.6）—— 數據重新生成，PR 附排序對比 | 中高（排名改變係用家可見） |
| 5–8 | P2 每項一個 PR（T2.1 → T2.2 → T2.3/T2.5/T2.6 → T2.4） | 中 |
| 9 | T3.3 + T3.4 + T3.5 | 低中 |

## 4. 風險同注意事項

- **排名改動係用家可見**：P1 合併前一定要附具體字例嘅 before/after，並確認「exact 唔被 fuzzy 蓋過」、「廣東話口語字（係唔咗嘅冇）排頭」兩條底線有測試鎖住。
- **數據格式改動要兼容**：`strokes.json` 加第 4 欄時 `content.js` 必須容忍舊格式，避免升級期間白屏。
- **新數據源（字頻表）有 license 審查**（AI_RULES）：CC-CEDICT 係 CC BY-SA 4.0，Conway 係 CC-BY-4.0；任何新語料都要同等級嘅明確許可，寧缺勿濫。
- **手測清單**（每個涉及 `content.js` 嘅 PR 都要過）：普通 input、textarea、contenteditable（例如 Google Docs 類除外，佢哋用 canvas）、React 受控組件、iframe 內欄位（已知限制，文件要寫明）、中英模式切換、跨 tab 開關同步。
- **已知架構限制唔使今期解決**：cross-origin iframe、Shadow DOM、Google Docs 類 canvas 編輯器 —— 喺 README 如實列明就得。
