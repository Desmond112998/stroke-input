// 筆畫輸入法 Chrome Extension - Content Script
// Stroke Input Method for Chinese character input in the browser
// Enhanced with Cantonese frequency, bigram model, and user adaptation

(function () {
  "use strict";

  // ── Constants ──────────────────────────────────────────────────
  const STROKE_KEYS = { j: 1, k: 2, l: 3, u: 4, i: 5, o: 6 };
  const STROKE_SYMBOLS = { 1: "一", 2: "丨", 3: "丿", 4: "丶", 5: "乙", 6: "＊" };
  const PAGE_SIZE = 9;
  const TOGGLE_KEY = "`"; // backtick to toggle on/off

  // Ranking weights
  const W_STATIC_FREQ = 0.35;
  const W_USER_FREQ = 0.30;
  const W_BIGRAM = 0.25;
  const W_STROKE_PROXIMITY = 0.10;

  // User frequency normalization cap
  const USER_FREQ_CAP = 50;
  // Max stroke distance for proximity scoring
  const STROKE_PROX_MAX = 10;

  // ── State ──────────────────────────────────────────────────────
  let active = false;
  let chineseMode = true; // true = 中文, false = 英文 (Shift toggles)
  let strokeSeq = [];
  let allRecords = []; // sorted [seq, char, freq]
  let phrases = {};    // first_char -> [[phrase, freq], ...]
  let bigrams = {};    // char -> {char2: score, ...}
  let candidates = [];
  let page = 0;
  let phraseMode = false;
  let phraseList = [];
  let phrasePage = 0;
  let lastSelectedChar = "";
  let dataLoaded = false;
  let targetElement = null;

  // User frequency store (in-memory, persisted to chrome.storage)
  let userFreq = {};       // char -> count
  let userFreqDirty = false;
  let userFreqSaveTimer = null;

  // Shift-toggle tracking: detect bare Shift press (down→up with no other key)
  let shiftDown = false;
  let shiftUsedWithOther = false;

  // Drag state
  let dragging = false;
  let dragOffsetX = 0;
  let dragOffsetY = 0;

  // ── User Frequency Persistence ─────────────────────────────────
  function loadUserFreq() {
    try {
      chrome.storage.local.get(["userFreq"], (data) => {
        if (chrome.runtime.lastError) return;
        if (data.userFreq && typeof data.userFreq === "object") {
          userFreq = data.userFreq;
        }
      });
    } catch (e) {}
  }

  function saveUserFreq() {
    if (!userFreqDirty) return;
    try {
      chrome.storage.local.set({ userFreq }, () => {
        if (chrome.runtime.lastError) return;
        userFreqDirty = false;
      });
    } catch (e) {}
  }

  function bumpUserFreq(char) {
    userFreq[char] = (userFreq[char] || 0) + 1;
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
  }

  // ── Data Loading ───────────────────────────────────────────────
  async function loadData() {
    if (dataLoaded) return;
    try {
      const [strokeResp, phraseResp, bigramResp] = await Promise.all([
        fetch(chrome.runtime.getURL("data/strokes.json")),
        fetch(chrome.runtime.getURL("data/phrases.json")),
        fetch(chrome.runtime.getURL("data/bigrams.json")),
      ]);
      allRecords = await strokeResp.json();
      phrases = await phraseResp.json();
      bigrams = await bigramResp.json();
      dataLoaded = true;
      loadUserFreq();
      console.log(
        `[筆畫] Loaded ${allRecords.length} characters, ` +
        `${Object.keys(phrases).length} phrase buckets, ` +
        `${Object.keys(bigrams).length} bigram entries`
      );
    } catch (e) {
      console.error("[筆畫] Failed to load data:", e);
    }
  }

  // ── Ranking ────────────────────────────────────────────────────
  function computeScore(record) {
    const char = record[1];
    const staticFreq = record[2]; // already 0-1

    // User frequency (normalized to 0-1)
    const rawUserFreq = userFreq[char] || 0;
    const userScore = Math.min(rawUserFreq / USER_FREQ_CAP, 1.0);

    // Bigram score: how likely is this char to follow lastSelectedChar
    let bigramScore = 0;
    if (lastSelectedChar && bigrams[lastSelectedChar]) {
      bigramScore = bigrams[lastSelectedChar][char] || 0;
    }

    // Stroke proximity: prefer chars whose stroke count is close to input length
    const strokeCount = record[0].length;
    const inputLen = strokeSeq.length;
    const distance = Math.abs(strokeCount - inputLen);
    const proximityScore = Math.max(0, 1 - distance / STROKE_PROX_MAX);

    return (
      W_STATIC_FREQ * staticFreq +
      W_USER_FREQ * userScore +
      W_BIGRAM * bigramScore +
      W_STROKE_PROXIMITY * proximityScore
    );
  }

  // ── Trie-like prefix search on sorted array ────────────────────
  function dedup(results) {
    const seen = new Map();
    for (const r of results) {
      const ch = r[1];
      if (!seen.has(ch) || r[2] > seen.get(ch)[2]) {
        seen.set(ch, r);
      }
    }
    return Array.from(seen.values());
  }

  function searchPrefix(prefix) {
    if (!prefix) return [];
    const hasWildcard = prefix.includes(6);
    let results;

    if (!hasWildcard) {
      const pfx = prefix.join("");
      results = [];
      let lo = 0, hi = allRecords.length;
      while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (allRecords[mid][0] < pfx) lo = mid + 1;
        else hi = mid;
      }
      for (let i = lo; i < allRecords.length; i++) {
        const seq = allRecords[i][0];
        if (!seq.startsWith(pfx)) break;
        results.push(allRecords[i]);
      }
    } else {
      const pattern = "^" + prefix.map(s => s === 6 ? "[1-5]" : String(s)).join("");
      const re = new RegExp(pattern);
      results = [];
      for (let i = 0; i < allRecords.length; i++) {
        if (re.test(allRecords[i][0])) {
          results.push(allRecords[i]);
        }
      }
    }

    const unique = dedup(results);
    // Sort by composite score (descending)
    unique.sort((a, b) => computeScore(b) - computeScore(a));
    return unique;
  }

  // ── UI Creation ────────────────────────────────────────────────
  let overlay = null;

  function createOverlay() {
    if (overlay) return;
    overlay = document.createElement("div");
    overlay.id = "stroke-input-overlay";
    overlay.innerHTML = `
      <div id="stroke-input-strokes"></div>
      <div id="stroke-input-candidates"></div>
      <div id="stroke-input-phrases"></div>
      <div id="stroke-input-page"></div>
      <div id="stroke-input-status">筆畫輸入法 | \` 開關 | Shift 中英切換</div>
    `;
    document.body.appendChild(overlay);

    // Dragging
    overlay.addEventListener("mousedown", (e) => {
      if (e.target.closest(".stroke-candidate, .stroke-phrase")) return;
      dragging = true;
      const rect = overlay.getBoundingClientRect();
      dragOffsetX = e.clientX - rect.left;
      dragOffsetY = e.clientY - rect.top;
      e.preventDefault();
    });
    document.addEventListener("mousemove", (e) => {
      if (!dragging) return;
      overlay.style.left = (e.clientX - dragOffsetX) + "px";
      overlay.style.top = (e.clientY - dragOffsetY) + "px";
      overlay.style.right = "auto";
    });
    document.addEventListener("mouseup", () => { dragging = false; });
  }

  // ── UI Rendering ───────────────────────────────────────────────
  function render() {
    if (!overlay) return;

    const strokesEl = overlay.querySelector("#stroke-input-strokes");
    const candidatesEl = overlay.querySelector("#stroke-input-candidates");
    const phrasesEl = overlay.querySelector("#stroke-input-phrases");
    const pageEl = overlay.querySelector("#stroke-input-page");

    const modeLabel = chineseMode ? "中" : "英";
    const symbols = strokeSeq.map((s) => STROKE_SYMBOLS[s] || "?").join(" ");
    strokesEl.textContent = chineseMode ? symbols : "";

    const statusEl = overlay.querySelector("#stroke-input-status");
    statusEl.textContent = `${modeLabel} | \` 開關 | Shift 中英切換`;

    if (phraseMode && phraseList.length > 0) {
      candidatesEl.innerHTML = "";
      const start = phrasePage * PAGE_SIZE;
      const pageItems = phraseList.slice(start, start + PAGE_SIZE);
      phrasesEl.innerHTML = pageItems
        .map((p, i) => `<span class="stroke-phrase" data-idx="${i}"><span class="num">${i + 1}.</span>${p[0]}</span>`)
        .join("");
      const totalPages = Math.ceil(phraseList.length / PAGE_SIZE);
      pageEl.textContent = totalPages > 1 ? `${phrasePage + 1}/${totalPages}` : "";
    } else {
      phrasesEl.innerHTML = "";
      const start = page * PAGE_SIZE;
      const pageItems = candidates.slice(start, start + PAGE_SIZE);
      candidatesEl.innerHTML = pageItems
        .map((r, i) => `<span class="stroke-candidate" data-idx="${i}"><span class="num">${i + 1}.</span>${r[1]}</span>`)
        .join("");
      const totalPages = Math.ceil(candidates.length / PAGE_SIZE);
      pageEl.textContent = totalPages > 1 ? `${page + 1}/${totalPages}` : "";
    }
  }

  function refreshCandidates() {
    phraseMode = false;
    phraseList = [];
    phrasePage = 0;
    if (strokeSeq.length === 0) {
      candidates = [];
      page = 0;
    } else {
      candidates = searchPrefix(strokeSeq);
      page = 0;
    }
    render();
  }

  // ── Text Insertion ─────────────────────────────────────────────
  function insertText(text) {
    if (!targetElement) return;

    targetElement.focus();

    // For contenteditable elements
    if (targetElement.isContentEditable) {
      document.execCommand("insertText", false, text);
      return;
    }

    // For input/textarea
    const start = targetElement.selectionStart;
    const end = targetElement.selectionEnd;
    const val = targetElement.value;
    targetElement.value = val.slice(0, start) + text + val.slice(end);
    targetElement.selectionStart = targetElement.selectionEnd = start + text.length;

    // Fire input event so frameworks (React etc.) pick up the change
    targetElement.dispatchEvent(new Event("input", { bubbles: true }));
  }

  // ── Selection Handlers ─────────────────────────────────────────
  function selectCandidate(idx) {
    const start = page * PAGE_SIZE;
    const item = candidates[start + idx];
    if (!item) return;

    const char = item[1];
    insertText(char);
    lastSelectedChar = char;

    // Track user frequency
    bumpUserFreq(char);

    strokeSeq = [];
    candidates = [];
    page = 0;

    if (phrases[char] && phrases[char].length > 0) {
      phraseMode = true;
      phraseList = phrases[char];
      phrasePage = 0;
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
      // Set last selected to the final character for bigram continuity
      lastSelectedChar = item[0][item[0].length - 1];
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
      return ["text", "search", "url", "email", "password", ""].includes(type);
    }
    return false;
  }

  function handleKeyDown(e) {
    // Track Shift for bare-press detection
    if (e.key === "Shift") {
      shiftDown = true;
      shiftUsedWithOther = false;
      return;
    }
    if (shiftDown) {
      shiftUsedWithOther = true;
    }

    // Toggle with backtick
    if (e.key === TOGGLE_KEY && !e.ctrlKey && !e.altKey && !e.metaKey) {
      e.preventDefault();
      e.stopPropagation();
      active = !active;
      if (active) {
        loadData();
        chineseMode = true;
        overlay.classList.add("active");
        targetElement = document.activeElement;
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

    // Stroke keys
    if (STROKE_KEYS[key] !== undefined) {
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

    // Number keys 1-9
    if (e.key >= "1" && e.key <= "9" && !e.ctrlKey && !e.altKey) {
      const num = parseInt(e.key) - 1;
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

    // Escape
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      resetInputState();
      render();
      return;
    }

    // Page Down / Space for next page
    if (e.key === "PageDown" || (e.key === " " && (candidates.length > 0 || phraseList.length > 0))) {
      e.preventDefault();
      e.stopPropagation();
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

    // Page Up
    if (e.key === "PageUp") {
      e.preventDefault();
      e.stopPropagation();
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

    console.log("[筆畫] Stroke Input Method loaded. Press ` to toggle, Shift for 中/英.");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
