import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { check } from './check.mjs';

test('successful jobs and conditional skipped lanes pass', () => {
  check({ build: { result: 'success' }, nightly: { result: 'skipped' } }, ['nightly']);
});

test('required skipped jobs fail even when another job succeeds', () => {
  assert.throws(() => check({ build: { result: 'success' }, tests: { result: 'skipped' } }), /tests=skipped/);
});

test('a conditional lane cannot fail or cancel', () => {
  for (const result of ['failure', 'cancelled']) {
    assert.throws(() => check({ build: { result: 'success' }, nightly: { result } }, ['nightly']), /nightly=/);
  }
});

for (const result of ['failure', 'cancelled', 'queued', undefined]) {
  test(`a ${result} job fails the gate`, () => {
    assert.throws(() => check({ build: { result: 'success' }, tests: { result } }), /tests=/);
  });
}

for (const results of [null, [], {}, { build: { result: 'skipped' } }]) {
  test(`missing completed checks fail: ${JSON.stringify(results)}`, () => {
    assert.throws(() => check(results));
  });
}

for (const [results, status] of [
  ['{"build":{"result":"success"}}', 0],
  ['{"build":{"result":"failure"}}', 1],
  ['invalid json', 1],
]) {
  test(`CLI returns ${status} for ${results}`, () => {
    const process = spawnSync('node', [fileURLToPath(new URL('./check.mjs', import.meta.url))], {
      env: { ...globalThis.process.env, GATE_RESULTS: results },
      encoding: 'utf8',
    });
    assert.equal(process.status, status, process.stderr);
  });
}

test('CLI accepts only named conditional skips', () => {
  const process = spawnSync('node', [fileURLToPath(new URL('./check.mjs', import.meta.url))], {
    env: { ...globalThis.process.env,
      GATE_RESULTS: '{"build":{"result":"success"},"nightly":{"result":"skipped"}}',
      GATE_ALLOW_SKIPPED: ' docker, nightly ',
    },
    encoding: 'utf8',
  });
  assert.equal(process.status, 0, process.stderr);
});
