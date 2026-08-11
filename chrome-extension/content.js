// 筆畫輸入法 Chrome Extension - Content Script
// Stroke Input Method for Chinese character input in the browser
// Enhanced with Cantonese frequency, trigram model, recency, position-aware ranking

(function () {
  "use strict";

  // ── Constants ──────────────────────────────────────────────────
  const STROKE_KEYS = { j: 1, k: 2, l: 3, u: 4, i: 5, o: 6 };
  const STROKE_SYMBOLS = { 1: "一", 2: "丨", 3: "丿", 4: "丶", 5: "乙", 6: "＊" };
  const NUMPAD_STROKE_CODES = {
    Numpad1: 1,
    Numpad2: 2,
    Numpad3: 3,
    Numpad4: 4,
    Numpad5: 5,
    Numpad6: 6,
  };
  const CN_PUNCTUATION = {
    ",": "，",
    ".": "。",
    "?": "？",
    "!": "！",
    ";": "；",
    ":": "：",
  };
  const PAGE_SIZE = 9;
  const DEFAULT_SETTINGS = Object.freeze({
    toggleKey: "`",
    interceptPassword: false,
    wubiHuaMode: false,
    showAssociations: true,
    numpadStrokes: false,
    chinesePunctuation: true,
    g6PhraseCodes: true,
  });
  let settings = {
    toggleKey: DEFAULT_SETTINGS.toggleKey,
    interceptPassword: DEFAULT_SETTINGS.interceptPassword,
    wubiHuaMode: DEFAULT_SETTINGS.wubiHuaMode,
    showAssociations: DEFAULT_SETTINGS.showAssociations,
    numpadStrokes: DEFAULT_SETTINGS.numpadStrokes,
    chinesePunctuation: DEFAULT_SETTINGS.chinesePunctuation,
    g6PhraseCodes: DEFAULT_SETTINGS.g6PhraseCodes,
  };

  // Pure helpers live in engine.js (loaded before this script).
  const Engine = globalThis.StrokeInputEngine;
  if (!Engine) {
    console.error("[筆畫] StrokeInputEngine missing — is engine.js loaded?");
  }

  // Max rank history per (strokeSeqKey, char)
  const MAX_RANK_HISTORY = 20;

  // ── State ──────────────────────────────────────────────────────
  let active = false;
  let chineseMode = true; // true = 中文, false = 英文 (Shift toggles)
  let strokeSeq = [];
  let allRecords = []; // sorted [seq, char, freq]
  let wubiRecords = []; // 頭四尾一 index (optional)
  let phrasesByCode = []; // G6 [code, phrase, freq] sorted by code
  let phrases = {};    // first_char -> [[phrase, freq], ...]
  let associationSet = new Set(); // chars injected as mid-typing associations
  let bigrams = {};    // char -> {char2: score, ...}
  let trigrams = {};   // prev2 -> {prev1 -> {char: score}} — new
  let candidates = [];
  let page = 0;
  let phraseMode = false;
  let phraseList = [];
  let phrasePage = 0;
  let lastSelectedChar = "";
  let prevSelectedChar = "";   // second-to-last for trigram context — new
  let dataLoaded = false;
  let targetElement = null;
  let highlightIdx = -1; // arrow-key highlight index within current page (-1 = none)

  // User frequency store (in-memory, persisted to chrome.storage) — v2 format
  let userFreq = {};         // char -> count
  let userTimestamps = {};   // char -> last-selection Unix timestamp (seconds) — new
  let userPositions = {};    // strokeSeqKey -> {char -> [rank, ...]} — new
  let userPins = {};         // strokeSeqKey -> {char: true} (T3.4 / C2)
  let userFreqDirty = false;
  let userFreqSaveTimer = null;
  let wildcardRefreshTimer = null;

  // Shift-toggle tracking: detect bare Shift press (down→up with no other key)
  let shiftDown = false;
  let shiftUsedWithOther = false;

  // Drag state
  let dragging = false;
  let dragOffsetX = 0;
  let dragOffsetY = 0;
  let overlayManualPosition = false;
  let dragMoved = false;

  // ── User Frequency Persistence (v2 format) ────────────────────
  function loadUserFreq() {
    try {
      chrome.storage.local.get(["userFreqV2"], (data) => {
        if (chrome.runtime.lastError) return;
        const stored = data.userFreqV2;
        if (stored && typeof stored === "object") {
          if (stored.v === 2) {
            // v2 format
            userFreq       = stored.counts      || {};
            userTimestamps = stored.timestamps  || {};
            userPositions  = stored.positions   || {};
            userPins       = stored.pins        || {};
          } else {
            // legacy flat format upgrade
            userFreq = stored;
            userTimestamps = {};
            userPositions  = {};
            userPins       = {};
          }
        }
      });
    } catch (e) {}
  }

  function saveUserFreq() {
    if (!userFreqDirty) return;
    try {
      const payload = {
        v: 2,
        counts: userFreq,
        timestamps: userTimestamps,
        positions: userPositions,
        pins: userPins,
      };
      chrome.storage.local.set({ userFreqV2: payload }, () => {
        if (chrome.runtime.lastError) return;
        userFreqDirty = false;
      });
    } catch (e) {}
  }

  function bumpUserFreq(char, rank) {
    // Count
    userFreq[char] = (userFreq[char] || 0) + 1;
    // Timestamp (recency)
    userTimestamps[char] = Date.now() / 1000; // Unix seconds
    // Position-aware: record rank if provided
    if (rank !== undefined) {
      const seqKey = strokeSeq.join("");
      if (!userPositions[seqKey]) userPositions[seqKey] = {};
      if (!userPositions[seqKey][char]) userPositions[seqKey][char] = [];
      const ranks = userPositions[seqKey][char];
      ranks.push(rank);
      if (ranks.length > MAX_RANK_HISTORY) ranks.shift();
      if (Engine && Engine.maybeAutoPin) {
        Engine.maybeAutoPin(seqKey, char, userPositions, userPins, 3);
      }
    }
    userFreqDirty = true;
    // Debounce save: write at most every 5 seconds
    if (!userFreqSaveTimer) {
      userFreqSaveTimer = setTimeout(() => {
        saveUserFreq();
        userFreqSaveTimer = null;
      }, 5000);
    }
  }

  // ── Global State Sync ──────────────────────────────────────────
  function broadcastState(updates) {
    try {
      chrome.runtime.sendMessage({ type: "setState", ...updates });
    } catch (e) {}
  }

  try {
    chrome.runtime.onMessage.addListener((msg) => {
      if (msg.type === "stateChanged") {
        if (msg.active !== undefined && msg.active !== active) {
          active = msg.active;
          if (active) {
            loadData();
            if (overlay) overlay.classList.add("active");
          } else {
            if (overlay) overlay.classList.remove("active");
            resetInputState();
          }
          render();
        }
        if (msg.chineseMode !== undefined && msg.chineseMode !== chineseMode) {
          chineseMode = msg.chineseMode;
          if (!chineseMode) resetInputState();
          render();
        }
      }
    });
  } catch (e) {}

  function resetInputState() {
    strokeSeq = [];
    candidates = [];
    phraseMode = false;
    phraseList = [];
    page = 0;
    phrasePage = 0;
    highlightIdx = -1;
    lastSelectedChar = "";
    prevSelectedChar = "";
    consecutiveChars = [];
  }

  // ── Data Loading ───────────────────────────────────────────────
  async function loadData() {
    if (dataLoaded) return;
    try {
      const [
        strokeResp,
        phraseResp,
        bigramResp,
        trigramResp,
        rankingResp,
        wubiResp,
        phraseCodeResp,
      ] = await Promise.all([
        fetch(chrome.runtime.getURL("data/strokes.json")),
        fetch(chrome.runtime.getURL("data/phrases.json")),
        fetch(chrome.runtime.getURL("data/bigrams.json")),
        fetch(chrome.runtime.getURL("data/trigrams.json")).catch(() => null),
        fetch(chrome.runtime.getURL("data/ranking_config.json")).catch(() => null),
        fetch(chrome.runtime.getURL("data/strokes_wubi.json")).catch(() => null),
        fetch(chrome.runtime.getURL("data/phrases_by_code.json")).catch(() => null),
      ]);
      allRecords = await strokeResp.json();
      phrases = await phraseResp.json();
      bigrams = await bigramResp.json();
      trigrams = trigramResp ? await trigramResp.json() : {};
      wubiRecords = wubiResp ? await wubiResp.json() : [];
      phrasesByCode = phraseCodeResp ? await phraseCodeResp.json() : [];
      if (rankingResp && Engine) {
        try {
          Engine.setConfig(await rankingResp.json());
        } catch (e) {}
      }
      dataLoaded = true;
      loadUserFreq();
      console.log(
        `[筆畫] Loaded ${allRecords.length} characters, ` +
        `${wubiRecords.length} wubi entries, ` +
        `${phrasesByCode.length} phrase codes, ` +
        `${Object.keys(phrases).length} phrase buckets`
      );
    } catch (e) {
      console.error("[筆畫] Failed to load data:", e);
    }
  }

  // ── Ranking / search / phrase helpers (delegated to engine.js) ─
  function rankingContext() {
    return {
      userFreq,
      userTimestamps,
      userPositions,
      userPins,
      strokeSeq,
      lastSelectedChar,
      prevSelectedChar,
      bigrams,
      trigrams,
    };
  }

  function computeScore(record) {
    return Engine.computeScore(record, rankingContext());
  }

  function searchPrefix(prefix) {
    const secondary = settings.wubiHuaMode ? wubiRecords : null;
    let results = Engine.searchMerged(
      prefix,
      allRecords,
      secondary,
      rankingContext(),
      { fuzzy: true }
    );

    // Mid-typing associations (macOS-style): inject top bigram followers at slots 2–3
    associationSet = new Set();
    if (
      settings.showAssociations &&
      lastSelectedChar &&
      results.length > 0
    ) {
      const assoc = Engine.associationChars(lastSelectedChar, bigrams, 2);
      const existing = new Set(results.map((r) => r[1]));
      const injected = [];
      for (const ch of assoc) {
        if (existing.has(ch)) continue;
        // Synthetic record: empty seq, char, bigram score as freq
        const score =
          (bigrams[lastSelectedChar] && bigrams[lastSelectedChar][ch]) || 0.5;
        injected.push(["", ch, score, null, "assoc"]);
        associationSet.add(ch);
      }
      if (injected.length) {
        const head = results.slice(0, 1);
        const rest = results.slice(1);
        results = head.concat(injected, rest);
      }
    }

    // G6 phrase-by-code (頭字頭三 + 尾字頭三): merge with character candidates
    if (
      settings.g6PhraseCodes &&
      Engine.searchPhrasesByCode &&
      phrasesByCode.length &&
      prefix.length >= 2
    ) {
      const phraseHits = Engine.searchPhrasesByCode(prefix, phrasesByCode, {
        minLen: 2,
        cap: 30,
      });
      if (phraseHits.length) {
        if (prefix.length >= 6) {
          // Full six-code: phrase hits lead so「香港」is easy to pick
          results = phraseHits.concat(results);
        } else {
          const head = results.slice(0, 1);
          const rest = results.slice(1);
          results = head.concat(phraseHits, rest);
        }
      }
    }
    return results;
  }

  function predictPhrase(seed, maxDepth) {
    return Engine.predictPhrase(seed, bigrams, trigrams, {
      maxDepth: maxDepth,
    });
  }

  // ── Phrase Learning (B3) ───────────────────────────────────────
  // Track consecutive selections for auto-learning
  let consecutiveChars = [];

  function autoLearnPhrase() {
    if (consecutiveChars.length >= 2) {
      const phrase = consecutiveChars.join("");
      // Consumed by Engine.learnedPhrasesFor when building phrase suggestions (T3.4)
      if (!userPositions["__phrases__"]) userPositions["__phrases__"] = {};
      if (!userPositions["__phrases__"][phrase]) {
        userPositions["__phrases__"][phrase] = [];
      }
      userPositions["__phrases__"][phrase].push(1);
      if (userPositions["__phrases__"][phrase].length > MAX_RANK_HISTORY) {
        userPositions["__phrases__"][phrase].shift();
      }
      userFreqDirty = true;
    }
    // Keep the last character so the next pick can extend the learned chain
    consecutiveChars = consecutiveChars.slice(-1);
  }
  // When Chrome reloads the extension, old content scripts remain alive.
  // Signal any previous instance to self-destruct via a custom event.
  window.dispatchEvent(new CustomEvent("__stroke_input_cleanup__"));

  let destroyed = false;
  window.addEventListener("__stroke_input_cleanup__", () => {
    // A newer instance has loaded — tear down this one
    destroyed = true;
    if (overlay) {
      overlay.remove();
      overlay = null;
    }
  });

  // ── UI Creation ────────────────────────────────────────────────
  let overlay = null;

  function createOverlay() {
    if (overlay) return;
    // Remove any orphaned overlay elements left in the DOM
    document.querySelectorAll("#stroke-input-overlay").forEach(el => el.remove());

    overlay = document.createElement("div");
    overlay.id = "stroke-input-overlay";
    overlay.innerHTML = `
      <div id="stroke-input-strokes"></div>
      <div id="stroke-input-candidates"></div>
      <div id="stroke-input-phrases"></div>
      <div id="stroke-input-page"></div>
      <div id="stroke-input-status">筆畫輸入法 · 選項頁可改開關鍵</div>
    `;
    document.body.appendChild(overlay);

    // Dragging — after a real drag, keep the manual position (T2.5)
    overlay.addEventListener("mousedown", (e) => {
      if (e.target.closest(".stroke-candidate, .stroke-phrase")) return;
      dragging = true;
      dragMoved = false;
      const rect = overlay.getBoundingClientRect();
      dragOffsetX = e.clientX - rect.left;
      dragOffsetY = e.clientY - rect.top;
      e.preventDefault();
    });
    document.addEventListener("mousemove", (e) => {
      if (!dragging) return;
      dragMoved = true;
      overlay.style.left = (e.clientX - dragOffsetX) + "px";
      overlay.style.top = (e.clientY - dragOffsetY) + "px";
      overlay.style.right = "auto";
    });
    document.addEventListener("mouseup", () => {
      if (dragging && dragMoved) overlayManualPosition = true;
      dragging = false;
    });
  }

  function clampOverlayPosition(left, top) {
    const margin = 8;
    const ow = overlay.offsetWidth || 340;
    const oh = overlay.offsetHeight || 120;
    const maxLeft = Math.max(margin, window.innerWidth - ow - margin);
    const maxTop = Math.max(margin, window.innerHeight - oh - margin);
    return {
      left: Math.min(Math.max(margin, left), maxLeft),
      top: Math.min(Math.max(margin, top), maxTop),
    };
  }

  /** Position overlay near the caret / text field (unless user dragged it). */
  function positionOverlayNearCaret() {
    if (!overlay || !active || overlayManualPosition || dragging) return;
    const el = targetElement && isTextInput(targetElement)
      ? targetElement
      : (isTextInput(document.activeElement) ? document.activeElement : null);
    if (!el) return;

    let anchor = null;
    if (el.isContentEditable) {
      try {
        const sel = document.getSelection();
        if (sel && sel.rangeCount > 0) {
          const r = sel.getRangeAt(0).getBoundingClientRect();
          if (r && (r.width > 0 || r.height > 0 || r.top !== 0 || r.left !== 0)) {
            anchor = r;
          }
        }
      } catch (e) {}
    }
    if (!anchor) {
      try {
        if (typeof el.getBoundingClientRect === "function") {
          anchor = el.getBoundingClientRect();
        }
      } catch (e) {}
    }
    if (!anchor) return;

    const margin = 8;
    let left = anchor.left;
    let top = anchor.bottom + margin;
    const oh = overlay.offsetHeight || 120;
    if (top + oh > window.innerHeight - margin) {
      top = Math.max(margin, anchor.top - oh - margin);
    }
    const pos = clampOverlayPosition(left, top);
    overlay.style.left = pos.left + "px";
    overlay.style.top = pos.top + "px";
    overlay.style.right = "auto";
  }

  // ── UI Rendering ───────────────────────────────────────────────
  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function isTrigramDriven(record) {
    // Badge only when trigram contributes meaningfully to the composite score
    if (!Engine) return false;
    const contrib = Engine.trigramContribution(record, rankingContext());
    return contrib >= (Engine.TRIGRAM_BADGE_MIN || 0.02);
  }

  function render() {
    if (!overlay) return;

    const strokesEl = overlay.querySelector("#stroke-input-strokes");
    const candidatesEl = overlay.querySelector("#stroke-input-candidates");
    const phrasesEl = overlay.querySelector("#stroke-input-phrases");
    const pageEl = overlay.querySelector("#stroke-input-page");

    const modeLabel = chineseMode ? "中" : "英";
    const symbols = strokeSeq.map((s) => STROKE_SYMBOLS[s] || "?").join(" ");

    // Auto-commit hint: show ↵ badge when only 1 candidate
    const isUnique = candidates.length === 1 && !phraseMode;
    strokesEl.innerHTML = chineseMode
      ? (symbols ? `<span>${symbols}</span>${isUnique ? ' <span class="auto-commit-hint" title="唯一候選，按空格上屏">↵</span>' : ""}` : "")
      : "";

    const statusEl = overlay.querySelector("#stroke-input-status");
    statusEl.innerHTML =
      `<span class="stroke-mode-badge ${chineseMode ? "cn" : "en"}">${modeLabel}</span> ` +
      `<kbd>${escapeHtml(settings.toggleKey)}</kbd> 開關 · <kbd>Shift</kbd> 中英 · <kbd>◀▶</kbd> 選字 · <kbd>▲▼</kbd> 翻頁`;

    if (phraseMode && phraseList.length > 0) {
      candidatesEl.innerHTML = "";
      const start = phrasePage * PAGE_SIZE;
      const pageItems = phraseList.slice(start, start + PAGE_SIZE);
      phrasesEl.innerHTML = pageItems
        .map((p, i) => `<span class="stroke-phrase${i === highlightIdx ? " highlighted" : ""}" data-idx="${i}"><span class="num">${i + 1}.</span>${p[0]}</span>`)
        .join("");
      const totalPages = Math.ceil(phraseList.length / PAGE_SIZE);
      pageEl.textContent = totalPages > 1 ? `← ${phrasePage + 1}/${totalPages} →` : "";
    } else {
      phrasesEl.innerHTML = "";
      const start = page * PAGE_SIZE;
      const pageItems = candidates.slice(start, start + PAGE_SIZE);
      candidatesEl.innerHTML = pageItems
        .map((r, i) => {
          const badges = [];
          if (isTrigramDriven(r)) {
            badges.push('<span class="tri-badge" title="觸發：上文脈絡">★</span>');
          }
          if (r[4] === "phrase") {
            badges.push('<span class="phrase-badge" title="詞組碼">詞</span>');
          }
          if (r[4] === "assoc" || associationSet.has(r[1])) {
            badges.push('<span class="assoc-badge" title="關聯字">聯</span>');
          }
          if (r.isExact === false) {
            badges.push('<span class="fuzzy-badge" title="模糊匹配">∼</span>');
          }
          return `<span class="stroke-candidate${i === highlightIdx ? " highlighted" : ""}" data-idx="${i}"><span class="num">${i + 1}.</span>${badges.join("")}${escapeHtml(r[1])}</span>`;
        })
        .join("");
      const totalPages = Math.ceil(candidates.length / PAGE_SIZE);
      pageEl.textContent = totalPages > 1 ? `← ${page + 1}/${totalPages} →` : "";
    }

    positionOverlayNearCaret();
  }

  function refreshCandidates() {
    phraseMode = false;
    phraseList = [];
    phrasePage = 0;
    // C4: default highlight = 0 (first candidate pre-selected)
    highlightIdx = 0;
    if (wildcardRefreshTimer) {
      clearTimeout(wildcardRefreshTimer);
      wildcardRefreshTimer = null;
    }
    if (strokeSeq.length === 0) {
      candidates = [];
      page = 0;
      render();
      return;
    }
    const run = () => {
      candidates = searchPrefix(strokeSeq);
      page = 0;
      render();
    };
    // Debounce wildcard scans (full-table regex) slightly (T3.3)
    if (strokeSeq.includes(6)) {
      wildcardRefreshTimer = setTimeout(run, 40);
      return;
    }
    run();
  }

  // ── Text Insertion ─────────────────────────────────────────────
  function insertText(text) {
    if (!targetElement) return;

    targetElement.focus();

    // For contenteditable elements — execCommand keeps native undo
    if (targetElement.isContentEditable) {
      document.execCommand("insertText", false, text);
      return;
    }

    // For input/textarea — prefer setRangeText; fall back to native setter
    // so React/Vue controlled inputs observe the change.
    const start = targetElement.selectionStart ?? targetElement.value.length;
    const end = targetElement.selectionEnd ?? start;

    if (typeof targetElement.setRangeText === "function") {
      targetElement.setRangeText(text, start, end, "end");
    } else {
      const proto =
        targetElement.tagName === "TEXTAREA"
          ? HTMLTextAreaElement.prototype
          : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
      const next =
        targetElement.value.slice(0, start) + text + targetElement.value.slice(end);
      if (setter) {
        setter.call(targetElement, next);
      } else {
        targetElement.value = next;
      }
      targetElement.selectionStart = targetElement.selectionEnd = start + text.length;
    }

    targetElement.dispatchEvent(
      new InputEvent("input", {
        bubbles: true,
        cancelable: false,
        inputType: "insertText",
        data: text,
      })
    );
  }

  // ── Selection Handlers ─────────────────────────────────────────
  function selectCandidate(idx) {
    const start = page * PAGE_SIZE;
    const globalIdx = start + idx;
    const item = candidates[globalIdx];
    if (!item) return;

    const text = item[1];
    const isPhraseCand = item[4] === "phrase" || (typeof text === "string" && text.length > 1);
    insertText(text);

    if (isPhraseCand) {
      prevSelectedChar =
        text.length >= 2 ? text[text.length - 2] : lastSelectedChar;
      lastSelectedChar = text[text.length - 1];
      for (const ch of text) bumpUserFreq(ch, globalIdx);
      consecutiveChars = consecutiveChars.concat(Array.from(text));
      autoLearnPhrase();
    } else {
      prevSelectedChar = lastSelectedChar;
      lastSelectedChar = text;
      bumpUserFreq(text, globalIdx);
      consecutiveChars.push(text);
      autoLearnPhrase();
    }

    strokeSeq = [];
    candidates = [];
    page = 0;

    // Follow-up suggestions from the last committed character
    const seed = lastSelectedChar;
    const staticPhrases = (phrases[seed] && phrases[seed].length > 0)
      ? phrases[seed].map(p => ({ phrase: p[0], score: p[1], isStatic: true }))
      : [];
    const learned = Engine.learnedPhrasesFor
      ? Engine.learnedPhrasesFor(seed, userPositions, 9)
      : [];
    const beamPhrases = predictPhrase(seed)
      .filter(p => p.phrase.length > 1)
      .map(p => ({ ...p, isStatic: false }));

    const seen = new Set();
    const merged = [];
    for (const group of [staticPhrases, learned, beamPhrases]) {
      for (const p of group) {
        if (seen.has(p.phrase)) continue;
        seen.add(p.phrase);
        merged.push(p);
      }
    }

    if (merged.length > 0) {
      phraseMode = true;
      phraseList = merged.map(p => [p.phrase, p.score]);
      phrasePage = 0;
      highlightIdx = 0;
    }
    render();
  }

  function selectPhrase(idx) {
    const start = phrasePage * PAGE_SIZE;
    const item = phraseList[start + idx];
    if (!item) return;

    const remaining = item[0].slice(1);
    if (remaining) {
      insertText(remaining);
      // Track frequency for each character in the phrase
      for (const ch of remaining) {
        bumpUserFreq(ch);
      }
      // Auto-learn the full phrase
      const fullPhrase = item[0];
      for (const ch of fullPhrase) consecutiveChars.push(ch);
      autoLearnPhrase();
      // Advance context: last two chars of the completed phrase
      prevSelectedChar = fullPhrase.length >= 2 ? fullPhrase[fullPhrase.length - 2] : lastSelectedChar;
      lastSelectedChar = fullPhrase[fullPhrase.length - 1];
    }

    phraseMode = false;
    phraseList = [];
    phrasePage = 0;
    render();
  }

  // ── Keyboard Handler ───────────────────────────────────────────
  function isTextInput(el) {
    if (!el) return false;
    if (el.isContentEditable) return true;
    const tag = el.tagName;
    if (tag === "TEXTAREA") return true;
    if (tag === "INPUT") {
      const type = (el.type || "").toLowerCase();
      const allowed = ["text", "search", "url", "email", ""];
      if (settings.interceptPassword) allowed.push("password");
      return allowed.includes(type);
    }
    return false;
  }

  function hasComposition() {
    return strokeSeq.length > 0 || phraseMode || candidates.length > 0 || phraseList.length > 0;
  }

  function applySettings(raw) {
    if (!raw || typeof raw !== "object") return;
    if (typeof raw.toggleKey === "string" && raw.toggleKey.length > 0) {
      settings.toggleKey = raw.toggleKey;
    }
    if (typeof raw.interceptPassword === "boolean") {
      settings.interceptPassword = raw.interceptPassword;
    }
    if (typeof raw.wubiHuaMode === "boolean") {
      settings.wubiHuaMode = raw.wubiHuaMode;
    }
    if (typeof raw.showAssociations === "boolean") {
      settings.showAssociations = raw.showAssociations;
    }
    if (typeof raw.numpadStrokes === "boolean") {
      settings.numpadStrokes = raw.numpadStrokes;
    }
    if (typeof raw.chinesePunctuation === "boolean") {
      settings.chinesePunctuation = raw.chinesePunctuation;
    }
    if (typeof raw.g6PhraseCodes === "boolean") {
      settings.g6PhraseCodes = raw.g6PhraseCodes;
    }
  }

  function loadSettings() {
    try {
      chrome.storage.local.get(["imeSettings"], (data) => {
        if (chrome.runtime.lastError) return;
        applySettings(data.imeSettings);
      });
    } catch (e) {}
  }

  function handleKeyDown(e) {
    if (destroyed) return;

    // Track Shift for bare-press detection
    if (e.key === "Shift") {
      shiftDown = true;
      shiftUsedWithOther = false;
      return;
    }
    if (shiftDown) {
      shiftUsedWithOther = true;
    }

    // Never steal modified shortcuts (Ctrl/Cmd/Alt + key)
    const hasModifier = e.ctrlKey || e.metaKey || e.altKey;

    // Toggle IME on/off (configurable; default backtick)
    if (e.key === settings.toggleKey && !hasModifier) {
      e.preventDefault();
      e.stopPropagation();
      active = !active;
      if (active) {
        loadData();
        chineseMode = true;
        overlayManualPosition = false;
        overlay.classList.add("active");
        targetElement = isTextInput(document.activeElement)
          ? document.activeElement
          : targetElement;
      } else {
        overlay.classList.remove("active");
        resetInputState();
      }
      broadcastState({ active, chineseMode });
      render();
      return;
    }

    if (!active) return;
    if (!chineseMode) return;

    // Remember the focused text input
    if (isTextInput(document.activeElement)) {
      targetElement = document.activeElement;
    }

    const key = e.key.toLowerCase();

    // Optional numpad stroke entry (T2.6) — number row still selects candidates
    if (
      settings.numpadStrokes &&
      NUMPAD_STROKE_CODES[e.code] !== undefined &&
      !hasModifier
    ) {
      if (!isTextInput(document.activeElement)) return;
      e.preventDefault();
      e.stopPropagation();
      if (phraseMode) {
        phraseMode = false;
        phraseList = [];
        phrasePage = 0;
      }
      strokeSeq.push(NUMPAD_STROKE_CODES[e.code]);
      refreshCandidates();
      return;
    }

    // Chinese punctuation when buffer empty (T2.6)
    if (
      settings.chinesePunctuation &&
      !hasModifier &&
      strokeSeq.length === 0 &&
      !phraseMode &&
      CN_PUNCTUATION[e.key] !== undefined
    ) {
      if (!isTextInput(document.activeElement)) return;
      e.preventDefault();
      e.stopPropagation();
      insertText(CN_PUNCTUATION[e.key]);
      return;
    }

    // Stroke keys — only when focus is in a text field, never with modifiers
    if (STROKE_KEYS[key] !== undefined) {
      if (hasModifier) return;
      if (!isTextInput(document.activeElement)) return;
      e.preventDefault();
      e.stopPropagation();
      if (phraseMode) {
        phraseMode = false;
        phraseList = [];
        phrasePage = 0;
      }
      strokeSeq.push(STROKE_KEYS[key]);
      refreshCandidates();
      return;
    }

    // Number keys 1-9 — select candidate/phrase (block Cmd/Ctrl/Alt)
    if (e.key >= "1" && e.key <= "9") {
      if (hasModifier) return;
      const num = parseInt(e.key, 10) - 1;
      if (phraseMode && phraseList.length > 0) {
        e.preventDefault();
        e.stopPropagation();
        selectPhrase(num);
        return;
      }
      if (candidates.length > 0) {
        e.preventDefault();
        e.stopPropagation();
        selectCandidate(num);
        return;
      }
      return;
    }

    // Backspace
    if (e.key === "Backspace") {
      if (phraseMode) {
        e.preventDefault();
        e.stopPropagation();
        phraseMode = false;
        phraseList = [];
        phrasePage = 0;
        render();
        return;
      }
      if (strokeSeq.length > 0) {
        e.preventDefault();
        e.stopPropagation();
        strokeSeq.pop();
        refreshCandidates();
        return;
      }
      return;
    }

    // Escape — only intercept when there is an active composition
    if (e.key === "Escape") {
      if (!hasComposition()) return;
      e.preventDefault();
      e.stopPropagation();
      resetInputState();
      render();
      return;
    }

    // ── Arrow key navigation for candidates/phrases ──────────────
    const hasCandidates = phraseMode ? phraseList.length > 0 : candidates.length > 0;

    // ArrowRight: move highlight forward
    if (e.key === "ArrowRight" && hasCandidates) {
      e.preventDefault();
      e.stopPropagation();
      const currentList = phraseMode ? phraseList : candidates;
      const currentPage = phraseMode ? phrasePage : page;
      const start = currentPage * PAGE_SIZE;
      const pageCount = Math.min(PAGE_SIZE, currentList.length - start);
      if (highlightIdx < pageCount - 1) {
        highlightIdx++;
      } else {
        // Wrap to next page if available
        const totalPages = Math.ceil(currentList.length / PAGE_SIZE);
        if ((phraseMode ? phrasePage : page) < totalPages - 1) {
          if (phraseMode) phrasePage++; else page++;
          highlightIdx = 0;
        }
      }
      render();
      return;
    }

    // ArrowLeft: move highlight backward
    if (e.key === "ArrowLeft" && hasCandidates) {
      e.preventDefault();
      e.stopPropagation();
      if (highlightIdx > 0) {
        highlightIdx--;
      } else if (highlightIdx === 0) {
        // Wrap to previous page if available
        if ((phraseMode ? phrasePage : page) > 0) {
          if (phraseMode) phrasePage--; else page--;
          const currentList = phraseMode ? phraseList : candidates;
          const currentPage = phraseMode ? phrasePage : page;
          const start = currentPage * PAGE_SIZE;
          const pageCount = Math.min(PAGE_SIZE, currentList.length - start);
          highlightIdx = pageCount - 1;
        }
      } else {
        // highlightIdx === -1, start from end of page
        const currentList = phraseMode ? phraseList : candidates;
        const currentPage = phraseMode ? phrasePage : page;
        const start = currentPage * PAGE_SIZE;
        const pageCount = Math.min(PAGE_SIZE, currentList.length - start);
        highlightIdx = pageCount - 1;
      }
      render();
      return;
    }

    // ArrowDown: next page (keep first candidate highlighted)
    if (e.key === "ArrowDown" && hasCandidates) {
      e.preventDefault();
      e.stopPropagation();
      if (phraseMode) {
        const total = Math.ceil(phraseList.length / PAGE_SIZE);
        if (phrasePage < total - 1) { phrasePage++; highlightIdx = 0; }
      } else {
        const total = Math.ceil(candidates.length / PAGE_SIZE);
        if (page < total - 1) { page++; highlightIdx = 0; }
      }
      render();
      return;
    }

    // ArrowUp: previous page (keep first candidate highlighted)
    if (e.key === "ArrowUp" && hasCandidates) {
      e.preventDefault();
      e.stopPropagation();
      if (phraseMode) {
        if (phrasePage > 0) { phrasePage--; highlightIdx = 0; }
      } else {
        if (page > 0) { page--; highlightIdx = 0; }
      }
      render();
      return;
    }

    // Enter: confirm highlighted candidate/phrase
    if (e.key === "Enter" && hasCandidates && highlightIdx >= 0) {
      e.preventDefault();
      e.stopPropagation();
      if (phraseMode) {
        selectPhrase(highlightIdx);
      } else {
        selectCandidate(highlightIdx);
      }
      return;
    }

    // Space = commit highlighted (or unique) candidate; never just "page"
    if (e.key === " ") {
      if (candidates.length === 0 && phraseList.length === 0) return;
      e.preventDefault();
      e.stopPropagation();

      if (candidates.length === 1 && !phraseMode) {
        selectCandidate(0);
        return;
      }
      const idx = highlightIdx >= 0 ? highlightIdx : 0;
      if (phraseMode) selectPhrase(idx);
      else selectCandidate(idx);
      return;
    }

    // PageDown = next page
    if (e.key === "PageDown") {
      if (!hasComposition()) return;
      e.preventDefault();
      e.stopPropagation();
      highlightIdx = 0;
      if (phraseMode) {
        const total = Math.ceil(phraseList.length / PAGE_SIZE);
        if (phrasePage < total - 1) phrasePage++;
      } else {
        const total = Math.ceil(candidates.length / PAGE_SIZE);
        if (page < total - 1) page++;
      }
      render();
      return;
    }

    // PageUp = previous page — only when composing
    if (e.key === "PageUp") {
      if (!hasComposition()) return;
      e.preventDefault();
      e.stopPropagation();
      highlightIdx = 0;
      if (phraseMode) {
        if (phrasePage > 0) phrasePage--;
      } else {
        if (page > 0) page--;
      }
      render();
      return;
    }
  }

  function handleKeyUp(e) {
    if (destroyed) return;
    if (e.key === "Shift") {
      if (shiftDown && !shiftUsedWithOther && active) {
        chineseMode = !chineseMode;
        if (!chineseMode) resetInputState();
        broadcastState({ chineseMode });
        render();
      }
      shiftDown = false;
      shiftUsedWithOther = false;
    }
  }

  // ── Click handlers for candidates ──────────────────────────────
  function handleOverlayClick(e) {
    const cand = e.target.closest(".stroke-candidate");
    if (cand) {
      const idx = parseInt(cand.dataset.idx);
      selectCandidate(idx);
      return;
    }
    const phrase = e.target.closest(".stroke-phrase");
    if (phrase) {
      const idx = parseInt(phrase.dataset.idx);
      selectPhrase(idx);
      return;
    }
  }

  // ── Init ───────────────────────────────────────────────────────
  function init() {
    createOverlay();
    overlay.addEventListener("click", handleOverlayClick);
    document.addEventListener("keydown", handleKeyDown, true);
    document.addEventListener("keyup", handleKeyUp, true);

    loadSettings();
    try {
      chrome.storage.onChanged.addListener((changes, area) => {
        if (area !== "local" || !changes.imeSettings) return;
        applySettings(changes.imeSettings.newValue);
        render();
      });
    } catch (e) {}

    // Restore global state on load
    try {
      chrome.runtime.sendMessage({ type: "getState" }, (resp) => {
        if (chrome.runtime.lastError || !resp) return;
        active = !!resp.active;
        chineseMode = resp.chineseMode !== false;
        if (active) {
          loadData();
          if (overlay) overlay.classList.add("active");
        }
        render();
      });
    } catch (e) {}

    // Save user frequency on page unload
    window.addEventListener("beforeunload", () => {
      saveUserFreq();
    });

    window.addEventListener(
      "scroll",
      () => {
        if (active && !overlayManualPosition) positionOverlayNearCaret();
      },
      true
    );
    window.addEventListener("resize", () => {
      if (active && !overlayManualPosition) positionOverlayNearCaret();
    });

    console.log("[筆畫] Stroke Input Method loaded. Toggle key and options are configurable.");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
