import test from "node:test";
import assert from "node:assert/strict";

import {
  api,
  get,
  http,
  newRequestId,
  post,
  withRequestId,
} from "./api.js";

function fakeResponse({ status = 200, body = "", statusText = "" } = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText,
    text: async () => body,
  };
}

function withFetch(t, respond) {
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (path, init) => {
    calls.push({ path, init });
    return respond(path, init);
  };
  t.after(() => {
    globalThis.fetch = original;
  });
  return calls;
}

test("api parses JSON, null bodies and plain text", async (t) => {
  const calls = withFetch(t, (path) => {
    if (path === "/json") return fakeResponse({ body: '{"ok":true}' });
    if (path === "/empty") return fakeResponse({ body: "" });
    return fakeResponse({ body: "plain", status: 200 });
  });
  assert.deepEqual(await api("/json"), { ok: true });
  assert.equal(await api("/empty"), null);
  assert.equal(await api("/text"), "plain");
  assert.deepEqual(calls[0].init.headers, { "Content-Type": "application/json" });
});

test("api keeps method/body options and allows an injected fetch", async () => {
  let seen = null;
  const payload = await api("/api/group/say", {
    method: "POST",
    body: '{"message":"hi"}',
    fetchImpl: async (path, init) => {
      seen = { path, init };
      return fakeResponse({ body: '{"turn":{}}' });
    },
  });
  assert.deepEqual(payload, { turn: {} });
  assert.equal(seen.path, "/api/group/say");
  assert.equal(seen.init.method, "POST");
  assert.equal(seen.init.body, '{"message":"hi"}');
});

test("api raises the server detail with status, body and code", async (t) => {
  withFetch(t, () => fakeResponse({
    status: 423,
    statusText: "Locked",
    body: JSON.stringify({ detail: { detail: "paused", error: "paused" }, extra: 1 }),
  }));
  await assert.rejects(api("/api/group/say"), (error) => {
    assert.equal(error.message, "paused");
    assert.equal(error.status, 423);
    assert.equal(error.code, "paused");
    assert.equal(error.body.extra, 1);
    return true;
  });
});

test("api falls back to status text for an empty error body", async (t) => {
  withFetch(t, () => fakeResponse({ status: 500, statusText: "Boom" }));
  await assert.rejects(api("/api/state"), (error) => {
    assert.equal(error.message, "Boom");
    assert.equal(error.status, 500);
    assert.equal(error.code, "");
    return true;
  });
});

test("get and post use the same fetch layer", async (t) => {
  const calls = withFetch(t, () => fakeResponse({ body: "{}" }));
  await get("/api/state");
  await post("/api/dev/reset", {});
  await post("/api/friends/alice");
  assert.equal(calls[0].init.method, undefined);
  assert.equal(calls[1].init.method, "POST");
  assert.equal(calls[1].init.body, "{}");
  assert.equal(calls[2].init.method, "POST");
  assert.equal(calls[2].init.body, undefined);
});

test("request ids are only added when supplied", () => {
  assert.deepEqual(withRequestId({ message: "hi" }), { message: "hi" });
  assert.deepEqual(withRequestId({ message: "hi" }, "r-1"), {
    message: "hi",
    request_id: "r-1",
  });
  const one = newRequestId("test");
  const two = newRequestId("test");
  assert.match(one, /^test-/);
  assert.notEqual(one, two);
});

test("http helpers mirror the HTTP request schemas", async (t) => {
  const calls = withFetch(t, () => fakeResponse({ body: "{}" }));

  await http.groupSay({
    message: "hello",
    characters: ["alice", "emily"],
    timeout: 50,
    requestId: "req-1",
  });
  await http.groupWhisper({ to: "mia", message: "psst", timeout: 50 });
  await http.dm({ character: "alice", message: "hi" });
  await http.dmHistory("alice", { beforeId: 12 });
  await http.takesNext({ force: true, requestId: "req-2" });
  await http.clockAdvance({ run: true, minutes: 5 });
  await http.runBeat({ beat: "cafe", transport: "local", forceShare: true });
  await http.tellAlice({ secret: "s", key: "k" });

  assert.deepEqual(JSON.parse(calls[0].init.body), {
    message: "hello",
    characters: ["alice", "emily"],
    timeout: 50,
    request_id: "req-1",
  });
  assert.deepEqual(JSON.parse(calls[1].init.body), {
    to: "mia",
    message: "psst",
    timeout: 50,
  });
  assert.deepEqual(JSON.parse(calls[2].init.body), {
    character: "alice",
    message: "hi",
  });
  assert.equal(calls[3].path, "/api/dm/alice?limit=100&before_id=12");
  assert.deepEqual(JSON.parse(calls[4].init.body), {
    force: true,
    request_id: "req-2",
  });
  assert.deepEqual(JSON.parse(calls[5].init.body), {
    offscreen: false,
    minutes: 5,
    run: true,
  });
  assert.deepEqual(JSON.parse(calls[6].init.body), {
    beat: "cafe",
    transport: "local",
    force_share: true,
  });
  assert.deepEqual(JSON.parse(calls[7].init.body), { secret: "s", key: "k" });
});
