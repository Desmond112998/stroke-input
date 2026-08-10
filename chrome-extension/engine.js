/**
 * Stroke Input — pure ranking / search / phrase-prediction helpers.
 *
 * Dual-mode module:
 * - Browser content script: attaches to globalThis.StrokeInputEngine
 * - Node tests: module.exports = { ... }
 *
 * Ranking defaults match ``stroke_input.config.ranking`` / ranking_config.json.
 */
(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.StrokeInputEngine = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  /** Defaults mirrored from src/stroke_input/config/ranking.py */
  const BUILTIN_WEIGHTS = Object.freeze({
    staticFreq: 0.35,
    userFreq: 0.20,
    bigram: 0.15,
    trigram: 0.15,
    recency: 0.10,
    position: 0.05,
  });

  let activeWeights = Object.assign({}, BUILTIN_WEIGHTS);
  let USER_FREQ_CAP = 100;
  let RECENCY_TAU_SEC = 30 * 86400;
  let TRADITIONAL_BOOST = 0.05;
  let TRIGRAM_BADGE_MIN = 0.02;
  // Match quality is only applied when a record has an explicit isExact flag
  // (fuzzy path). Untagged prefix results keep parity with static-only scores.
  let WEIGHT_MATCH_QUALITY = 0.1;
  let MATCH_QUALITY_EXACT = 1.0;
  let MATCH_QUALITY_FUZZY = 0.5;

  const BEAM_WIDTH = 5;
  const BEAM_DEPTH = 3;
  const BEAM_MIN_PROB = 1e-5;
  const BEAM_MAX_RESULTS = 9;
  /** Cap scored prefix results to keep first-stroke latency bounded (T3.3). */
  const SEARCH_RESULT_CAP = 200;
  const WILDCARD_RE_CACHE_MAX = 256;
  const _wildcardReCache = new Map();

  /**
   * Apply ranking_config.json (or partial overrides).
   * @param {object} cfg
   */
  function setConfig(cfg) {
    if (!cfg || typeof cfg !== "object") return;
    if (cfg.weights && typeof cfg.weights === "object") {
      activeWeights = Object.assign({}, BUILTIN_WEIGHTS, cfg.weights);
    }
    if (typeof cfg.userFreqCap === "number") USER_FREQ_CAP = cfg.userFreqCap;
    if (typeof cfg.recencyTauDays === "number") {
      RECENCY_TAU_SEC = cfg.recencyTauDays * 86400;
    }
    if (typeof cfg.traditionalBoost === "number") {
      TRADITIONAL_BOOST = cfg.traditionalBoost;
    }
    if (typeof cfg.trigramBadgeMinContribution === "number") {
      TRIGRAM_BADGE_MIN = cfg.trigramBadgeMinContribution;
    }
    if (typeof cfg.weightMatchQuality === "number") {
      WEIGHT_MATCH_QUALITY = cfg.weightMatchQuality;
    }
    if (cfg.weights && typeof cfg.weights.matchQuality === "number") {
      WEIGHT_MATCH_QUALITY = cfg.weights.matchQuality;
    }
    if (typeof cfg.matchQualityExact === "number") {
      MATCH_QUALITY_EXACT = cfg.matchQualityExact;
    }
    if (typeof cfg.matchQualityFuzzy === "number") {
      MATCH_QUALITY_FUZZY = cfg.matchQualityFuzzy;
    }
  }

  function getConfig() {
    return {
      weights: Object.assign({}, activeWeights),
      userFreqCap: USER_FREQ_CAP,
      recencyTauSec: RECENCY_TAU_SEC,
      traditionalBoost: TRADITIONAL_BOOST,
      trigramBadgeMinContribution: TRIGRAM_BADGE_MIN,
      weightMatchQuality: WEIGHT_MATCH_QUALITY,
      matchQualityExact: MATCH_QUALITY_EXACT,
      matchQualityFuzzy: MATCH_QUALITY_FUZZY,
    };
  }

  function recordIsExact(record) {
    return !record || record.isExact !== false;
  }

  function tagRecord(record, isExact) {
    const tagged = record.slice();
    if (record.length > 3) {
      for (let i = 3; i < record.length; i++) tagged[i] = record[i];
    }
    tagged.isExact = isExact;
    return tagged;
  }

  function dedupPreferExact(results) {
    const seen = new Map();
    for (const r of results) {
      const ch = r[1];
      const prev = seen.get(ch);
      if (!prev) {
        seen.set(ch, r);
        continue;
      }
      const rExact = recordIsExact(r);
      const pExact = recordIsExact(prev);
      if (rExact && !pExact) {
        seen.set(ch, r);
      } else if (rExact === pExact && r[2] > prev[2]) {
        seen.set(ch, r);
      }
    }
    return Array.from(seen.values());
  }

  function compareByExactThenScore(a, b, scoreCtx) {
    const ae = recordIsExact(a);
    const be = recordIsExact(b);
    if (ae !== be) return ae ? -1 : 1;
    return computeScore(b, scoreCtx) - computeScore(a, scoreCtx);
  }

  /**
   * @param {Array} record  [seq, char, staticFreq, scriptTag?]
   *   scriptTag optional: "t" (trad-only) | "s" (simp-only)
   */
  function computeScore(record, ctx) {
    ctx = ctx || {};
    const weights = ctx.weights || activeWeights;
    const char = record[1];
    const staticFreq = record[2];
    const scriptTag = record[3];

    const userFreq = ctx.userFreq || {};
    const cap = ctx.userFreqCap !== undefined ? ctx.userFreqCap : USER_FREQ_CAP;
    const userScore = Math.min((userFreq[char] || 0) / cap, 1.0);

    let bigramScore = 0;
    const last = ctx.lastSelectedChar || "";
    const bigrams = ctx.bigrams || {};
    if (last && bigrams[last]) {
      bigramScore = bigrams[last][char] || 0;
    }

    let trigramScore = 0;
    const prev = ctx.prevSelectedChar || "";
    const trigrams = ctx.trigrams || {};
    if (prev && last && trigrams[prev] && trigrams[prev][last]) {
      trigramScore = trigrams[prev][last][char] || 0;
    }

    let recencyScore = 0;
    const ts = (ctx.userTimestamps || {})[char];
    if (ts) {
      const nowSec = ctx.nowSec !== undefined ? ctx.nowSec : Date.now() / 1000;
      const tau = ctx.recencyTauSec !== undefined ? ctx.recencyTauSec : RECENCY_TAU_SEC;
      const deltaSec = Math.max(0, nowSec - ts);
      recencyScore = Math.exp(-deltaSec / tau);
    }

    let positionScore = 0;
    const strokeSeq = ctx.strokeSeq || [];
    const seqKey = strokeSeq.join("");
    const pins = ctx.userPins || {};
    if (seqKey && pins[seqKey] && pins[seqKey][char]) {
      positionScore = 1.0;
    } else {
      const positions = ctx.userPositions || {};
      if (seqKey && positions[seqKey] && positions[seqKey][char]) {
        const ranks = positions[seqKey][char];
        if (ranks.length > 0) {
          const avgRank = ranks.reduce((a, b) => a + b, 0) / ranks.length;
          positionScore = 1.0 / (1.0 + avgRank);
        }
      }
    }

    let score =
      weights.staticFreq * staticFreq +
      weights.userFreq * userScore +
      weights.bigram * bigramScore +
      weights.trigram * trigramScore +
      weights.recency * recencyScore +
      weights.position * positionScore;

    // Explicit isExact (boolean) enables match-quality term for fuzzy ranking.
    if (record.isExact === true || record.isExact === false) {
      const mqW =
        ctx.weightMatchQuality !== undefined
          ? ctx.weightMatchQuality
          : WEIGHT_MATCH_QUALITY;
      const mq =
        record.isExact
          ? ctx.matchQualityExact !== undefined
            ? ctx.matchQualityExact
            : MATCH_QUALITY_EXACT
          : ctx.matchQualityFuzzy !== undefined
            ? ctx.matchQualityFuzzy
            : MATCH_QUALITY_FUZZY;
      score += mqW * mq;
    }

    const tradBoost =
      ctx.traditionalBoost !== undefined ? ctx.traditionalBoost : TRADITIONAL_BOOST;
    if (scriptTag === "t") {
      score += tradBoost;
    }
    return score;
  }

  function trigramContribution(record, ctx) {
    ctx = ctx || {};
    const weights = ctx.weights || activeWeights;
    const char = record[1];
    const prev = ctx.prevSelectedChar || "";
    const last = ctx.lastSelectedChar || "";
    const trigrams = ctx.trigrams || {};
    if (!(prev && last && trigrams[prev] && trigrams[prev][last])) return 0;
    return weights.trigram * (trigrams[prev][last][char] || 0);
  }

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

  function wildcardRegex(prefix) {
    const key = prefix.join(",");
    let re = _wildcardReCache.get(key);
    if (!re) {
      const pattern =
        "^" + prefix.map((s) => (s === 6 ? "[1-5]" : String(s))).join("");
      re = new RegExp(pattern);
      if (_wildcardReCache.size >= WILDCARD_RE_CACHE_MAX) {
        _wildcardReCache.clear();
      }
      _wildcardReCache.set(key, re);
    }
    return re;
  }

  function rankAndCap(results, scoreCtx, cap) {
    const limit = cap === undefined ? SEARCH_RESULT_CAP : cap;
    const scored = results.map((r) => ({ r: r, s: computeScore(r, scoreCtx) }));
    scored.sort((a, b) => b.s - a.s);
    if (scored.length > limit) scored.length = limit;
    return scored.map((x) => x.r);
  }

  function searchPrefix(prefix, allRecords, ctx) {
    if (!prefix || !prefix.length) return [];
    allRecords = allRecords || [];
    const hasWildcard = prefix.includes(6);
    let results;

    if (!hasWildcard) {
      const pfx = prefix.join("");
      results = [];
      let lo = 0;
      let hi = allRecords.length;
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
      const re = wildcardRegex(prefix);
      results = [];
      for (let i = 0; i < allRecords.length; i++) {
        if (re.test(allRecords[i][0])) {
          results.push(allRecords[i]);
        }
      }
    }

    const unique = dedup(results);
    const scoreCtx = Object.assign({}, ctx || {}, { strokeSeq: prefix });
    const cap =
      ctx && ctx.searchResultCap !== undefined
        ? ctx.searchResultCap
        : SEARCH_RESULT_CAP;
    return rankAndCap(unique, scoreCtx, cap);
  }

  const EXACT_THRESHOLD = 3;
  const STROKE_CODES = [1, 2, 3, 4, 5];

  /**
   * Exact prefix search, with one-stroke fuzzy substitution when |exact| < 3.
   * Exact matches always precede fuzzy matches.
   */
  function searchWithFuzzy(prefix, allRecords, ctx) {
    const exactRaw = searchPrefix(prefix, allRecords, ctx);
    if (
      !prefix ||
      !prefix.length ||
      prefix.includes(6) ||
      exactRaw.length >= EXACT_THRESHOLD
    ) {
      return exactRaw;
    }

    const exact = exactRaw.map((r) => tagRecord(r, true));
    const seen = new Set(exact.map((r) => r[1]));
    const fuzzy = [];
    const scoreCtx = Object.assign({}, ctx || {}, { strokeSeq: prefix });

    for (let pos = 0; pos < prefix.length; pos++) {
      const original = prefix[pos];
      if (original === 6) continue;
      for (const sub of STROKE_CODES) {
        if (sub === original) continue;
        const modified = prefix.slice();
        modified[pos] = sub;
        const matches = searchPrefix(modified, allRecords, scoreCtx);
        for (const rec of matches) {
          if (!seen.has(rec[1])) {
            seen.add(rec[1]);
            fuzzy.push(tagRecord(rec, false));
          }
        }
      }
    }

    fuzzy.sort((a, b) => compareByExactThenScore(a, b, scoreCtx));
    return exact.concat(fuzzy);
  }

  /**
   * Merge full-stroke and wubi-hua indexes (dedupe by char; exact before fuzzy).
   */
  function searchMerged(prefix, primaryRecords, secondaryRecords, ctx, opts) {
    opts = opts || {};
    const searchFn = opts.fuzzy ? searchWithFuzzy : searchPrefix;
    const primary = searchFn(prefix, primaryRecords, ctx);
    const scoreCtx = Object.assign({}, ctx || {}, { strokeSeq: prefix });
    if (!secondaryRecords || !secondaryRecords.length) {
      return primary;
    }
    const secondary = searchFn(prefix, secondaryRecords, ctx);
    return dedupPreferExact(primary.concat(secondary)).sort((a, b) =>
      compareByExactThenScore(a, b, scoreCtx)
    );
  }

  /**
   * G6-style phrase-by-code lookup (T2.4).
   * Records: sorted [code, phrase, freq]. Prefix match via binary search.
   * Returns tagged copies with record[4] === "phrase".
   */
  function searchPhrasesByCode(prefix, phraseRecords, opts) {
    opts = opts || {};
    const minLen = opts.minLen !== undefined ? opts.minLen : 2;
    const cap = opts.cap !== undefined ? opts.cap : 40;
    if (!prefix || prefix.length < minLen) return [];
    if (!phraseRecords || !phraseRecords.length) return [];
    if (prefix.includes(6)) return []; // wildcard not applied to phrase codes (MVP)

    const pfx = prefix.join("");
    let lo = 0;
    let hi = phraseRecords.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (phraseRecords[mid][0] < pfx) lo = mid + 1;
      else hi = mid;
    }
    const hits = [];
    for (let i = lo; i < phraseRecords.length; i++) {
      const seq = phraseRecords[i][0];
      if (!seq.startsWith(pfx)) break;
      const tagged = phraseRecords[i].slice();
      while (tagged.length < 5) tagged.push(null);
      tagged[4] = "phrase";
      hits.push(tagged);
    }
    hits.sort((a, b) => b[2] - a[2] || (a[1] < b[1] ? -1 : 1));
    if (hits.length > cap) hits.length = cap;
    return hits;
  }

  /**
   * Top association characters from bigrams for mid-typing injection.
   */
  function associationChars(prevChar, bigrams, limit) {
    limit = limit === undefined ? 2 : limit;
    if (!prevChar || !bigrams || !bigrams[prevChar]) return [];
    return Object.entries(bigrams[prevChar])
      .sort((a, b) => b[1] - a[1])
      .slice(0, limit)
      .map(([ch]) => ch);
  }

  function predictPhrase(seed, bigrams, trigrams, opts) {
    if (!seed) return [];
    bigrams = bigrams || {};
    trigrams = trigrams || {};
    opts = opts || {};
    const depth = opts.maxDepth !== undefined ? opts.maxDepth : BEAM_DEPTH;
    const beamWidth = opts.beamWidth !== undefined ? opts.beamWidth : BEAM_WIDTH;
    const maxResults = opts.maxResults !== undefined ? opts.maxResults : BEAM_MAX_RESULTS;

    const vocab = new Set();
    for (const p of Object.keys(bigrams)) {
      vocab.add(p);
      for (const c of Object.keys(bigrams[p])) vocab.add(c);
    }
    if (vocab.size === 0) return [];

    let beam = [{ phrase: seed, negLogProb: 0, steps: 0 }];
    const collected = [];

    for (let step = 0; step < depth; step++) {
      if (!beam.length) break;
      const next = [];
      for (const state of beam) {
        const ph = state.phrase;
        const prev2 = ph.length >= 2 ? ph[ph.length - 2] : null;
        const prev1 = ph.length >= 1 ? ph[ph.length - 1] : null;

        for (const char of vocab) {
          let triScore = 0;
          if (prev2 && prev1 && trigrams[prev2] && trigrams[prev2][prev1]) {
            triScore = trigrams[prev2][prev1][char] || 0;
          }
          let biScore = 0;
          if (prev1 && bigrams[prev1]) biScore = bigrams[prev1][char] || 0;
          const p =
            triScore > 0
              ? 0.6 * triScore + 0.3 * biScore + 0.1 * 0.001
              : biScore > 0
                ? 0.7 * biScore + 0.3 * 0.001
                : 0;
          if (p < BEAM_MIN_PROB) continue;
          next.push({
            phrase: ph + char,
            negLogProb: state.negLogProb - Math.log(p),
            steps: state.steps + 1,
          });
        }
      }
      if (!next.length) break;
      next.sort((a, b) => a.negLogProb - b.negLogProb);
      beam = next.slice(0, beamWidth);
      for (const s of beam) {
        if (s.phrase.length > seed.length) {
          const avgLogProb = -s.negLogProb / s.steps;
          collected.push({ phrase: s.phrase, score: Math.exp(avgLogProb) });
        }
      }
    }

    const seen = new Set();
    const unique = [];
    for (const c of collected.sort((a, b) => b.score - a.score)) {
      if (!seen.has(c.phrase)) {
        seen.add(c.phrase);
        unique.push(c);
        if (unique.length >= maxResults) break;
      }
    }
    return unique;
  }

  /**
   * Learned phrases stored under userPositions["__phrases__"] (T3.4).
   * Value is an array of hit markers or a numeric count.
   */
  function learnedPhrasesFor(seed, userPositions, limit) {
    limit = limit === undefined ? 9 : limit;
    if (!seed || !userPositions) return [];
    const store = userPositions["__phrases__"];
    if (!store || typeof store !== "object") return [];
    const out = [];
    for (const phrase of Object.keys(store)) {
      if (!phrase || phrase[0] !== seed || phrase.length < 2) continue;
      const hits = store[phrase];
      const count = Array.isArray(hits) ? hits.length : Number(hits) || 0;
      if (count <= 0) continue;
      out.push({
        phrase: phrase,
        score: Math.min(1, 0.45 + count * 0.08),
        isLearned: true,
      });
    }
    out.sort((a, b) => b.score - a.score);
    return out.slice(0, limit);
  }

  /**
   * Auto-pin when the last `threshold` recorded ranks for (seq, char) are all 0.
   * Mutates `pins` map: { seqKey: { char: true } }.
   */
  function maybeAutoPin(seqKey, char, userPositions, pins, threshold) {
    threshold = threshold === undefined ? 3 : threshold;
    if (!seqKey || !char || !userPositions || !pins) return false;
    const ranks =
      userPositions[seqKey] && userPositions[seqKey][char]
        ? userPositions[seqKey][char]
        : null;
    if (!ranks || ranks.length < threshold) return false;
    const recent = ranks.slice(-threshold);
    if (!recent.every((r) => r === 0)) return false;
    if (!pins[seqKey]) pins[seqKey] = {};
    if (pins[seqKey][char]) return true;
    pins[seqKey][char] = true;
    return true;
  }

  return {
    DEFAULT_WEIGHTS: BUILTIN_WEIGHTS,
    get USER_FREQ_CAP() {
      return USER_FREQ_CAP;
    },
    get RECENCY_TAU_SEC() {
      return RECENCY_TAU_SEC;
    },
    get TRADITIONAL_BOOST() {
      return TRADITIONAL_BOOST;
    },
    get TRIGRAM_BADGE_MIN() {
      return TRIGRAM_BADGE_MIN;
    },
    BEAM_WIDTH,
    BEAM_DEPTH,
    BEAM_MIN_PROB,
    BEAM_MAX_RESULTS,
    SEARCH_RESULT_CAP,
    setConfig,
    getConfig,
    computeScore,
    trigramContribution,
    dedup,
    dedupPreferExact,
    searchPrefix,
    searchWithFuzzy,
    searchMerged,
    searchPhrasesByCode,
    associationChars,
    learnedPhrasesFor,
    maybeAutoPin,
    predictPhrase,
    EXACT_THRESHOLD,
    recordIsExact,
    get WEIGHT_MATCH_QUALITY() {
      return WEIGHT_MATCH_QUALITY;
    },
    get MATCH_QUALITY_EXACT() {
      return MATCH_QUALITY_EXACT;
    },
    get MATCH_QUALITY_FUZZY() {
      return MATCH_QUALITY_FUZZY;
    },
  };
});
