"use strict";

/**
 * Python↔JS ranking parity check.
 *
 * Until T1.5 ships a shared ranking_config.json, JS and Python weights diverge.
 * This test:
 * 1. Always verifies the fixture documents the drift (aligned === false).
 * 2. Marks score equality as todo — turns green after alignment.
 */

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const Engine = require(path.join(__dirname, "..", "engine.js"));
const fixturePath = path.join(__dirname, "fixtures", "ranking_parity.json");
const fixture = JSON.parse(fs.readFileSync(fixturePath, "utf8"));

describe("ranking parity fixture", () => {
  it("documents current JS weights matching engine.js", () => {
    assert.equal(fixture.js_weights.staticFreq, Engine.DEFAULT_WEIGHTS.staticFreq);
    assert.equal(fixture.js_weights.userFreq, Engine.DEFAULT_WEIGHTS.userFreq);
    assert.equal(fixture.js_weights.bigram, Engine.DEFAULT_WEIGHTS.bigram);
    assert.equal(fixture.js_weights.trigram, Engine.DEFAULT_WEIGHTS.trigram);
    assert.equal(fixture.js_weights.recency, Engine.DEFAULT_WEIGHTS.recency);
    assert.equal(fixture.js_weights.position, Engine.DEFAULT_WEIGHTS.position);
    assert.equal(fixture.js_weights.userFreqCap, Engine.USER_FREQ_CAP);
  });

  it("records that Python and JS are not yet aligned", () => {
    // Flip to true in T1.5 when ranking_config.json is the single source of truth.
    assert.equal(fixture.aligned, false);
    assert.notDeepEqual(
      {
        staticFreq: fixture.python_weights.staticFreq,
        userFreq: fixture.python_weights.userFreq,
      },
      {
        staticFreq: fixture.js_weights.staticFreq,
        userFreq: fixture.js_weights.userFreq,
      }
    );
  });

  it("JS static-only score matches DEFAULT_WEIGHTS * freq", () => {
    for (const c of fixture.cases) {
      if (c.context_boost) continue;
      const jsScore = Engine.computeScore(c.record, {});
      const expected = Engine.DEFAULT_WEIGHTS.staticFreq * c.record[2];
      assert.ok(
        Math.abs(jsScore - expected) < 1e-9,
        `${c.id}: js=${jsScore} expectedStatic=${expected}`
      );
    }
  });

  // Known drift until T1.5 — kept as todo so CI stays green while still
  // tracking the work item. Remove `{ todo: true }` when aligned === true.
  it("JS composite score matches Python FrequencyRanker", { todo: !fixture.aligned }, () => {
    assert.equal(fixture.aligned, true, "enable after shared ranking_config.json");
    for (const c of fixture.cases) {
      const jsScore = Engine.computeScore(c.record, {});
      assert.ok(
        Math.abs(jsScore - c.python_score) < 1e-4,
        `${c.id}: js=${jsScore} python=${c.python_score}`
      );
    }
  });
});
