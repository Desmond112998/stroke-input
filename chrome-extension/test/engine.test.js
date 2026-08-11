"use strict";

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const Engine = require(path.join(__dirname, "..", "engine.js"));

describe("StrokeInputEngine.dedup", () => {
  it("keeps the highest-frequency encoding per character", () => {
    const input = [
      ["11", "二", 0.5],
      ["12", "二", 0.9],
      ["1", "一", 0.8],
    ];
    const out = Engine.dedup(input);
    assert.equal(out.length, 2);
    const er = out.find((r) => r[1] === "二");
    assert.deepEqual(er, ["12", "二", 0.9]);
  });
});

describe("StrokeInputEngine.computeScore", () => {
    it("scores static frequency alone when context is empty", () => {
      const score = Engine.computeScore(["1", "一", 0.8], {});
      assert.ok(Math.abs(score - Engine.DEFAULT_WEIGHTS.staticFreq * 0.8) < 1e-9);
    });

    it("applies user frequency capped at USER_FREQ_CAP", () => {
      const low = Engine.computeScore(["1", "一", 0], {
        userFreq: { 一: Engine.USER_FREQ_CAP / 2 },
      });
      const high = Engine.computeScore(["1", "一", 0], {
        userFreq: { 一: Engine.USER_FREQ_CAP * 2 },
      });
      assert.ok(Math.abs(low - Engine.DEFAULT_WEIGHTS.userFreq * 0.5) < 1e-9);
      assert.ok(Math.abs(high - Engine.DEFAULT_WEIGHTS.userFreq * 1.0) < 1e-9);
    });

    it("applies bigram and trigram context", () => {
      const score = Engine.computeScore(["323554234", "係", 0.5], {
        lastSelectedChar: "就",
        prevSelectedChar: "就",
        bigrams: { 就: { 係: 1.0 } },
        trigrams: { 就: { 就: { 係: 0.5 } } },
      });
      const w = Engine.DEFAULT_WEIGHTS;
      const expected = w.staticFreq * 0.5 + w.bigram * 1.0 + w.trigram * 0.5;
      assert.ok(Math.abs(score - expected) < 1e-9);
    });

    it("applies traditional boost for script tag t", () => {
      const plain = Engine.computeScore(["1", "體", 0.5], {});
      const boosted = Engine.computeScore(["1", "體", 0.5, "t"], {});
      assert.ok(Math.abs(boosted - plain - Engine.TRADITIONAL_BOOST) < 1e-9);
    });

    it("applies recency and position scores", () => {
      const now = 1_700_000_000;
      const score = Engine.computeScore(["1", "一", 0], {
        userTimestamps: { 一: now },
        nowSec: now,
        strokeSeq: [1],
        userPositions: { "1": { 一: [0, 0] } },
      });
      const w = Engine.DEFAULT_WEIGHTS;
      const prox = Engine.WEIGHT_STROKE_PROXIMITY * 1.0; // exact-complete
      assert.ok(
        Math.abs(score - (w.recency * 1.0 + w.position * 1.0 + prox)) < 1e-9
      );
    });
  });

describe("StrokeInputEngine.searchPrefix", () => {
  const records = [
    ["1", "一", 0.99],
    ["11", "二", 0.98],
    ["12", "丁", 0.5],
    ["2", "丨", 0.9],
    ["21", "十", 0.95],
  ];

  it("returns exact prefix matches sorted by score", () => {
    const out = Engine.searchPrefix([1], records, {});
    assert.deepEqual(
      out.map((r) => r[1]),
      ["一", "二", "丁"]
    );
  });

  it("supports wildcard matching", () => {
    const out = Engine.searchPrefix([1, 6], records, {});
    const chars = out.map((r) => r[1]).sort();
    assert.deepEqual(chars, ["丁", "二"]);
  });

  it("returns empty for empty prefix", () => {
    assert.deepEqual(Engine.searchPrefix([], records, {}), []);
  });
});

describe("StrokeInputEngine.predictPhrase", () => {
  it("predicts continuations from bigrams", () => {
    const bigrams = {
      香: { 港: 1.0, 蕉: 0.5 },
      港: { 人: 0.8 },
    };
    const out = Engine.predictPhrase("香", bigrams, {}, { maxDepth: 2, maxResults: 5 });
    assert.ok(out.length > 0);
    assert.equal(out[0].phrase[0], "香");
    assert.ok(out.some((p) => p.phrase === "香港" || p.phrase.startsWith("香港")));
  });

  it("returns empty for empty seed", () => {
    assert.deepEqual(Engine.predictPhrase("", { 香: { 港: 1 } }, {}), []);
  });
});

describe("StrokeInputEngine.searchWithFuzzy", () => {
  const records = [
    ["1", "一", 0.99],
    ["11", "二", 0.98],
    ["12", "丁", 0.5],
    ["2", "丨", 0.9],
    ["21", "十", 0.95],
    ["31555", "毓", 0.4],
  ];

  it("adds fuzzy matches when exact count is below threshold", () => {
    // Prefix [4] has no exact match; substituting 4→1 yields 一
    const out = Engine.searchWithFuzzy([4], records, {});
    assert.ok(out.some((r) => r[1] === "一" && r.isExact === false));
  });

  it("keeps all exact matches before any fuzzy match", () => {
    const out = Engine.searchWithFuzzy([1], records, {});
    const exactIdx = out
      .map((r, i) => (r.isExact !== false && r[0].startsWith("1") ? i : -1))
      .filter((i) => i >= 0);
    // With ≥3 exact for prefix [1], fuzzy is suppressed
    assert.ok(out.length >= 3);
    assert.ok(out.every((r) => r.isExact !== false));
    assert.equal(exactIdx.length, out.length);
  });

  it("never lets fuzzy outrank exact for the same query", () => {
    // Only one exact for [2] (丨); fuzzy will add more
    const sparse = [
      ["2", "丨", 0.01],
      ["1", "一", 0.99],
      ["3", "丿", 0.98],
    ];
    const out = Engine.searchWithFuzzy([2], sparse, {});
    const firstFuzzy = out.findIndex((r) => r.isExact === false);
    const lastExact = out.reduce(
      (acc, r, i) => (r.isExact !== false ? i : acc),
      -1
    );
    if (firstFuzzy >= 0 && lastExact >= 0) {
      assert.ok(lastExact < firstFuzzy);
    }
  });
});

describe("StrokeInputEngine.searchMerged", () => {
  const primary = [
    ["31554325", "毓", 0.4],
    ["1", "一", 0.9],
  ];
  const wubi = [["31555", "毓", 0.4]];

  it("finds wubi short codes when secondary index is provided", () => {
    const out = Engine.searchMerged([3, 1, 5, 5, 5], primary, wubi, {}, {});
    assert.ok(out.some((r) => r[1] === "毓"));
  });

  it("ignores wubi index when secondary is null", () => {
    const out = Engine.searchMerged([3, 1, 5, 5, 5], primary, null, {}, {});
    assert.equal(out.length, 0);
  });
});

describe("StrokeInputEngine.associationChars", () => {
  it("returns top bigram followers sorted by score", () => {
    const out = Engine.associationChars("香", { 香: { 港: 0.9, 蕉: 0.5, 煙: 0.1 } }, 2);
    assert.deepEqual(out, ["港", "蕉"]);
  });

  it("returns empty without context", () => {
    assert.deepEqual(Engine.associationChars("", { 香: { 港: 1 } }, 2), []);
  });
});

describe("StrokeInputEngine.match quality", () => {
  it("exact tagged score beats fuzzy tagged score for same base", () => {
    const exact = Object.assign(["1", "一", 0.5], { isExact: true });
    const fuzzy = Object.assign(["1", "一", 0.5], { isExact: false });
    assert.ok(Engine.computeScore(exact, {}) > Engine.computeScore(fuzzy, {}));
  });
});

describe("StrokeInputEngine.stroke proximity ranking", () => {
  it("ranks exact-complete short chars above long high-freq chars", () => {
    const records = [
      ["1", "一", 0.03],
      ["1325", "冇", 0.97],
      ["111125134154544", "諗", 0.88, "t"],
      ["1251112", "車", 0.88, "t"],
    ];
    const out = Engine.searchPrefix([1], records, {});
    assert.equal(out[0][1], "一");
    assert.ok(out.findIndex((r) => r[1] === "冇") < out.findIndex((r) => r[1] === "諗"));
  });

  it("applies only a small traditional boost (tie-breaker)", () => {
    assert.ok(Engine.TRADITIONAL_BOOST <= 0.015);
  });
});

describe("StrokeInputEngine.searchPhrasesByCode", () => {
  const records = [
    ["312441", "香港", 0.9],
    ["312441", "香江", 0.3],
    ["441312", "港香", 0.1],
    ["111222", "一二", 0.5],
  ];

  it("finds 香港 under G6 code 312441", () => {
    const out = Engine.searchPhrasesByCode([3, 1, 2, 4, 4, 1], records, {});
    assert.ok(out.some((r) => r[1] === "香港" && r[4] === "phrase"));
  });

  it("supports progressive prefix match", () => {
    const out = Engine.searchPhrasesByCode([3, 1, 2], records, { minLen: 2 });
    assert.ok(out.some((r) => r[1] === "香港"));
    assert.ok(!out.some((r) => r[1] === "一二"));
  });

  it("returns empty below minLen", () => {
    assert.deepEqual(
      Engine.searchPhrasesByCode([3], records, { minLen: 2 }),
      []
    );
  });
});

describe("StrokeInputEngine.searchPrefix cap", () => {
  it("limits results to SEARCH_RESULT_CAP", () => {
    const records = [];
    for (let i = 0; i < 250; i++) {
      records.push(["1" + String(i).padStart(3, "0"), "字", 0.5 - i * 0.001]);
    }
    // Use distinct chars so dedup keeps all
    for (let i = 0; i < 250; i++) {
      records[i][1] = String.fromCodePoint(0x4e00 + i);
    }
    records.sort((a, b) => (a[0] < b[0] ? -1 : 1));
    const out = Engine.searchPrefix([1], records, {});
    assert.ok(out.length <= Engine.SEARCH_RESULT_CAP);
    assert.equal(out.length, Engine.SEARCH_RESULT_CAP);
  });
});

describe("StrokeInputEngine.learnedPhrasesFor", () => {
  it("returns phrases starting with seed ordered by hit count", () => {
    const positions = {
      __phrases__: {
        香港: [1, 1, 1],
        香蕉: [1],
        澳門: [1, 1],
      },
    };
    const out = Engine.learnedPhrasesFor("香", positions, 5);
    assert.deepEqual(
      out.map((p) => p.phrase),
      ["香港", "香蕉"]
    );
  });
});

describe("StrokeInputEngine.maybeAutoPin", () => {
  it("pins after threshold consecutive rank-0 selections", () => {
    const positions = { jk: { 你: [0, 0, 0] } };
    const pins = {};
    assert.equal(Engine.maybeAutoPin("jk", "你", positions, pins, 3), true);
    assert.equal(pins.jk["你"], true);
  });

  it("does not pin when ranks are mixed", () => {
    const positions = { jk: { 你: [0, 1, 0] } };
    const pins = {};
    assert.equal(Engine.maybeAutoPin("jk", "你", positions, pins, 3), false);
    assert.deepEqual(pins, {});
  });
});

describe("StrokeInputEngine.pins affect position score", () => {
  it("pinned char gets full position weight", () => {
    const unpinned = Engine.computeScore(["12", "你", 0], {
      strokeSeq: [1, 2],
    });
    const pinned = Engine.computeScore(["12", "你", 0], {
      strokeSeq: [1, 2],
      userPins: { "12": { 你: true } },
    });
    const prox = Engine.WEIGHT_STROKE_PROXIMITY * 1.0;
    assert.ok(
      Math.abs(pinned - (Engine.DEFAULT_WEIGHTS.position * 1.0 + prox)) < 1e-9
    );
    assert.ok(pinned > unpinned);
  });
});
