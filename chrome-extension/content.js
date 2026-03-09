// 筆畫輸入法 Chrome Extension - Content Script
// Stroke Input Method for Chinese character input in the browser

(function () {
  "use strict";

  // ── Constants ──────────────────────────────────────────────────
  const STROKE_KEYS = { j: 1, k: 2, l: 3, u: 4, i: 5, o: 6 };
  const STROKE_SYMBOLS = { 1: "一", 2: "丨", 3: "丿", 4: "丶", 5: "乙", 6: "＊" };
  const PAGE_SIZE = 9;
  const TOGGLE_KEY = "`"; // backtick to toggle on/off

  // ── State ──────────────────────────────────────────────────────
  let active = false;
  let chineseMode = true; // true = 中文, false = 英文 (Shift toggles)
  let strokeSeq = [];
  let allRecords = []; // sorted [seq, char, freq]
  let phrases = {};    // first_char -> [[phrase, freq], ...]
  let candidates = [];
  let page = 0;
  let phraseMode = false;
  let phraseList = [];
  let phrasePage = 0;
  let lastSelectedChar = "";
  let dataLoaded = false;
  let targetElement = null;

  // Shift-toggle tracking: detect bare Shift press (down→up with no other key)
  let shiftDown = false;
  let shiftUsedWithOther = false;

  // Drag state
  let dragging = false;
  let dragOffsetX = 0;
  let dragOffsetY = 0;

  // ── Data Loading ───────────────────────────────────────────────
  async function loadData() {
    if (dataLoaded) return;
    try {
      const [strokeResp, phraseResp] = await Promise.all([
        fetch(chrome.runtime.getURL("data/strokes.json")),
        fetch(chrome.runtime.getURL("data/phrases.json")),
      ]);
      allRecords = await strokeResp.json();
      phrases = await phraseResp.json();
      dataLoaded = true;
      console.log(`[筆畫] Loaded ${allRecords.length} characters, ${Object.keys(phrases).length} phrase buckets`);
    } catch (e) {
      console.error("[筆畫] Failed to load data:", e);
    }
  }

  // ── Trie-like prefix search on sorted array ────────────────────
  function searchPrefix(prefix) {
    if (!prefix) return [];
    const pfx = prefix.join("");
    const results = [];

    // Binary search for first entry >= prefix
    let lo = 0, hi = allRecords.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (allRecords[mid][0] < pfx) lo = mid + 1;
      else hi = mid;
    }

    // Collect all entries that start with prefix
    for (let i = lo; i < allRecords.length; i++) {
      const seq = allRecords[i][0];
      if (!seq.startsWith(pfx)) break;
      results.push(allRecords[i]);
    }

    // Sort by frequency descending
    results.sort((a, b) => b[2] - a[2]);
    return results;
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
      overlay.style.bottom = "auto";
      overlay.style.transform = "none";
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

    // Strokes display
    const modeLabel = chineseMode ? "中" : "英";
    const symbols = strokeSeq.map((s) => STROKE_SYMBOLS[s] || "?").join(" ");
    strokesEl.textContent = chineseMode ? symbols : "";

    // Update status with current mode
    const statusEl = overlay.querySelector("#stroke-input-status");
    statusEl.textContent = `${modeLabel} | \` 開關 | Shift 中英切換`;

    // Candidates or phrases
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

    // Clear strokes
    strokeSeq = [];
    candidates = [];
    page = 0;

    // Show phrases
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

    // Insert remaining characters (first char already inserted)
    const remaining = item[0].slice(1);
    if (remaining) insertText(remaining);

    // Clear phrase mode
    phraseMode = false;
    phraseList = [];
    phrasePage = 0;
    lastSelectedChar = "";
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
      return; // don't prevent default
    }
    // Any other key while Shift is held means it's a combo, not a toggle
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
        strokeSeq = [];
        candidates = [];
        phraseMode = false;
        phraseList = [];
        page = 0;
      }
      render();
      return;
    }

    if (!active) return;

    // In English mode, let everything through
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
      // If in phrase mode, exit it first
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
      // No candidates — let the key through
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
      // No strokes — let backspace through to delete text normally
      return;
    }

    // Escape
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      strokeSeq = [];
      candidates = [];
      phraseMode = false;
      phraseList = [];
      page = 0;
      phrasePage = 0;
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

    // Any other key while strokes are active — let it through but clear state
    // (e.g. Enter, Tab, etc.)
  }

  // ── Shift key-up handler for Chinese/English toggle ─────────
  function handleKeyUp(e) {
    if (e.key === "Shift") {
      // Bare Shift press (no other key pressed while Shift was held)
      if (shiftDown && !shiftUsedWithOther && active) {
        chineseMode = !chineseMode;
        // Clear stroke state when switching to English
        if (!chineseMode) {
          strokeSeq = [];
          candidates = [];
          phraseMode = false;
          phraseList = [];
          page = 0;
          phrasePage = 0;
        }
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
    console.log("[筆畫] Stroke Input Method loaded. Press ` to toggle, Shift for 中/英.");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
