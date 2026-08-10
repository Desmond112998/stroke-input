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
    assert.ok(Math.abs(score - 0.30 * 0.8) < 1e-9);
  });

  it("applies user frequency capped at USER_FREQ_CAP", () => {
    const low = Engine.computeScore(["1", "一", 0], {
      userFreq: { 一: 25 },
    });
    const high = Engine.computeScore(["1", "一", 0], {
      userFreq: { 一: 100 },
    });
    assert.ok(Math.abs(low - 0.25 * 0.5) < 1e-9);
    assert.ok(Math.abs(high - 0.25 * 1.0) < 1e-9);
  });

  it("applies bigram and trigram context", () => {
    const score = Engine.computeScore(["323554234", "係", 0.5], {
      lastSelectedChar: "就",
      prevSelectedChar: "就",
      bigrams: { 就: { 係: 1.0 } },
      trigrams: { 就: { 就: { 係: 0.5 } } },
    });
    // 0.30*0.5 + 0.15*1.0 + 0.15*0.5 = 0.15 + 0.15 + 0.075 = 0.375
    assert.ok(Math.abs(score - 0.375) < 1e-9);
  });

  it("applies recency and position scores", () => {
    const now = 1_700_000_000;
    const score = Engine.computeScore(["1", "一", 0], {
      userTimestamps: { 一: now },
      nowSec: now,
      strokeSeq: [1],
      userPositions: { "1": { 一: [0, 0] } },
    });
    // recency=1.0 → 0.10; position=1/(1+0)=1 → 0.05
    assert.ok(Math.abs(score - 0.15) < 1e-9);
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
