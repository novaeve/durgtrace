import http from "node:http";
import assert from "node:assert/strict";
import { postJson, TOOL_HTTP_TIMEOUT_MS } from "./bridge/transport.mjs";

const server = http.createServer((request, response) => {
  const chunks = [];
  request.on("data", c => chunks.push(c));
  request.on("end", () => {
    const body = JSON.parse(Buffer.concat(chunks).toString());
    if (body.action === "error") {
      response.writeHead(500, {"Content-Type":"application/json"});
      response.end(JSON.stringify({error:{message:"deliberate transport test"}}));
    } else {
      setTimeout(() => { response.writeHead(200, {"Content-Type":"application/json"}); response.end(JSON.stringify({result:{content:[{type:"text",text:"DELAYED_OK"}]}})); }, body.action === "slow" ? 310000 : 200);
    }
  });
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
const url = `http://127.0.0.1:${server.address().port}/mcp`;
try {
  assert.equal(TOOL_HTTP_TIMEOUT_MS, 28800000);
  await assert.rejects(postJson(url,{action:"error"}), /HTTP 500: deliberate transport test/);
  const controller = new AbortController();
  const pending = postJson(url,{action:"short"},controller.signal);
  controller.abort();await assert.rejects(pending, error => error.name === "AbortError");
  await assert.rejects(postJson(url,{action:"short"},undefined,30),/deadline exceeded/);
  console.log("FAST_TRANSPORT_CASES_PASSED");
  const start = Date.now();const result = await postJson(url,{action:"slow"});
  assert.equal(result.content[0].text,"DELAYED_OK");assert(Date.now()-start >= 310000);
  console.log(JSON.stringify({passed:true,delayed_response_ms:Date.now()-start,timeout_ms:TOOL_HTTP_TIMEOUT_MS}));
} finally { server.closeAllConnections();server.close(); }
