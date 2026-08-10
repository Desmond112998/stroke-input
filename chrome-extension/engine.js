/**
 * Stroke Input — pure ranking / search / phrase-prediction helpers.
 *
 * Dual-mode module:
 * - Browser content script: attaches to globalThis.StrokeInputEngine
 * - Node tests: module.exports = { ... }
 *
 * No DOM / chrome.* APIs. All state is passed in via context objects.
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

  /** Default ranking weights used by the Chrome extension runtime. */
  const DEFAULT_WEIGHTS = Object.freeze({
    staticFreq: 0.30,
    userFreq: 0.25,
    bigram: 0.15,
    trigram: 0.15,
    recency: 0.10,
    position: 0.05,
  });

  const USER_FREQ_CAP = 50;
  const RECENCY_TAU_SEC = 30 * 86400;
  const BEAM_WIDTH = 5;
  const BEAM_DEPTH = 3;
  const BEAM_MIN_PROB = 1e-5;
  const BEAM_MAX_RESULTS = 9;

  /**
   * Composite ranking score for a stroke record.
   *
   * @param {[string, string, number]} record  [seq, char, staticFreq]
   * @param {object} ctx
   * @param {Record<string, number>} [ctx.userFreq]
   * @param {Record<string, number>} [ctx.userTimestamps]  Unix seconds
   * @param {Record<string, Record<string, number[]>>} [ctx.userPositions]
   * @param {number[]} [ctx.strokeSeq]
   * @param {string} [ctx.lastSelectedChar]
   * @param {string} [ctx.prevSelectedChar]
   * @param {Record<string, Record<string, number>>} [ctx.bigrams]
   * @param {Record<string, Record<string, Record<string, number>>>} [ctx.trigrams]
   * @param {typeof DEFAULT_WEIGHTS} [ctx.weights]
   * @param {number} [ctx.nowSec]  Unix seconds; defaults to Date.now()/1000
   * @returns {number}
   */
  function computeScore(record, ctx) {
    ctx = ctx || {};
    const weights = ctx.weights || DEFAULT_WEIGHTS;
    const char = record[1];
    const staticFreq = record[2];

    const userFreq = ctx.userFreq || {};
    const userScore = Math.min((userFreq[char] || 0) / USER_FREQ_CAP, 1.0);

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
      const deltaSec = Math.max(0, nowSec - ts);
      recencyScore = Math.exp(-deltaSec / RECENCY_TAU_SEC);
    }

    let positionScore = 0;
    const strokeSeq = ctx.strokeSeq || [];
    const seqKey = strokeSeq.join("");
    const positions = ctx.userPositions || {};
    if (seqKey && positions[seqKey] && positions[seqKey][char]) {
      const ranks = positions[seqKey][char];
      if (ranks.length > 0) {
        const avgRank = ranks.reduce((a, b) => a + b, 0) / ranks.length;
        positionScore = 1.0 / (1.0 + avgRank);
      }
    }

    return (
      weights.staticFreq * staticFreq +
      weights.userFreq * userScore +
      weights.bigram * bigramScore +
      weights.trigram * trigramScore +
      weights.recency * recencyScore +
      weights.position * positionScore
    );
  }

  /**
   * Keep highest-frequency encoding per character.
   * @param {Array<[string, string, number]>} results
   * @returns {Array<[string, string, number]>}
   */
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

  /**
   * Prefix search over a sorted [seq, char, freq] array.
   *
   * @param {number[]} prefix  stroke codes 1-6 (6 = wildcard)
   * @param {Array<[string, string, number]>} allRecords  sorted by seq string
   * @param {object} [ctx]  passed to computeScore for ranking
   * @returns {Array<[string, string, number]>}
   */
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
      const pattern = "^" + prefix.map((s) => (s === 6 ? "[1-5]" : String(s))).join("");
      const re = new RegExp(pattern);
      results = [];
      for (let i = 0; i < allRecords.length; i++) {
        if (re.test(allRecords[i][0])) {
          results.push(allRecords[i]);
        }
      }
    }

    const unique = dedup(results);
    const scoreCtx = Object.assign({}, ctx || {}, { strokeSeq: prefix });
    unique.sort((a, b) => computeScore(b, scoreCtx) - computeScore(a, scoreCtx));
    return unique;
  }

  /**
   * Beam-search phrase continuations from a seed character/string.
   *
   * @param {string} seed
   * @param {Record<string, Record<string, number>>} bigrams
   * @param {Record<string, Record<string, Record<string, number>>>} [trigrams]
   * @param {{ maxDepth?: number, beamWidth?: number, maxResults?: number }} [opts]
   * @returns {Array<{ phrase: string, score: number }>}
   */
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

  return {
    DEFAULT_WEIGHTS,
    USER_FREQ_CAP,
    RECENCY_TAU_SEC,
    BEAM_WIDTH,
    BEAM_DEPTH,
    BEAM_MIN_PROB,
    BEAM_MAX_RESULTS,
    computeScore,
    dedup,
    searchPrefix,
    predictPhrase,
  };
});
