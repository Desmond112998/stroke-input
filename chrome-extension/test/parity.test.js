"use strict";

/**
 * Python↔JS ranking parity check.
 *
 * After T1.5, weight constants are shared via ranking_config / config.ranking.
 * Static-only scores (plus traditional boost from Conway "t" tag) should match.
 */

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const Engine = require(path.join(__dirname, "..", "engine.js"));
const fixturePath = path.join(__dirname, "fixtures", "ranking_parity.json");
const fixture = JSON.parse(fs.readFileSync(fixturePath, "utf8"));

describe("ranking parity fixture", () => {
  it("documents JS weights matching engine.js defaults", () => {
    assert.equal(fixture.js_weights.staticFreq, Engine.DEFAULT_WEIGHTS.staticFreq);
    assert.equal(fixture.js_weights.userFreq, Engine.DEFAULT_WEIGHTS.userFreq);
    assert.equal(fixture.js_weights.bigram, Engine.DEFAULT_WEIGHTS.bigram);
    assert.equal(fixture.js_weights.trigram, Engine.DEFAULT_WEIGHTS.trigram);
    assert.equal(fixture.js_weights.recency, Engine.DEFAULT_WEIGHTS.recency);
    assert.equal(fixture.js_weights.position, Engine.DEFAULT_WEIGHTS.position);
    assert.equal(fixture.js_weights.userFreqCap, Engine.USER_FREQ_CAP);
  });

  it("records that Python and JS weights are aligned", () => {
    assert.equal(fixture.aligned, true);
    assert.equal(
      fixture.python_weights.staticFreq,
      fixture.js_weights.staticFreq
    );
  });

  it("JS static-only score matches Python FrequencyRanker", () => {
    assert.equal(fixture.aligned, true);
    for (const c of fixture.cases) {
      const jsScore = Engine.computeScore(c.record, {});
      assert.ok(
        Math.abs(jsScore - c.python_score) < 1e-4,
        `${c.id}: js=${jsScore} python=${c.python_score}`
      );
    }
  });
});
