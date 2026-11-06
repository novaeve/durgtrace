import http from "node:http";

export const TOOL_HTTP_TIMEOUT_MS = 8 * 60 * 60 * 1000;

export function postJson(url, body, signal, timeoutMs = TOOL_HTTP_TIMEOUT_MS) {
  return new Promise((resolve, reject) => {
    const data = Buffer.from(JSON.stringify(body));
    const request = http.request(url, {
      method: "POST", signal,
      headers: {"Content-Type": "application/json", "Content-Length": data.length},
    }, response => {
      const chunks = [];
      response.on("data", chunk => chunks.push(chunk));
      response.on("error", reject);
      response.on("end", () => {
        try {
          const reply = JSON.parse(Buffer.concat(chunks).toString("utf8"));
          if (response.statusCode < 200 || response.statusCode >= 300) {
            throw new Error(`SMDD boundary HTTP ${response.statusCode}: ${reply.error?.message ?? "request failed"}`);
          }
          if (reply.error) throw new Error(reply.error.message);
          resolve(reply.result);
        } catch (error) { reject(error); }
      });
    });
    request.setTimeout(timeoutMs, () => request.destroy(new Error("SMDD tool HTTP deadline exceeded")));
    request.on("error", reject);
    request.end(data);
  });
}
