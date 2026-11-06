import fs from "node:fs";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { postJson } from "./transport.mjs";

export default function (pi: ExtensionAPI) {
  const base = process.env.SMDD_BOUNDARY_URL;
  if (!base) throw new Error("SMDD_BOUNDARY_URL is required");
  async function post(body: unknown, signal?: AbortSignal) {
    return await postJson(base + "/mcp", body, signal);
  }
  pi.registerProvider("smdd-deepseek", {
    baseUrl: base + "/v1", apiKey: "local-boundary", api: "openai-completions",
    models: [{id: "deepseek-v4.1-flash", name: "SMDD DeepSeek V4.1 Flash", reasoning: false,
      input: ["text"], cost: {input: 0, output: 0, cacheRead: 0, cacheWrite: 0}, contextWindow: 262144, maxTokens: 65536,
      compat: {supportsStore: false, supportsDeveloperRole: false, supportsReasoningEffort: false, supportsUsageInStreaming: true, maxTokensField: "max_tokens"}}],
  });
  const definitions = JSON.parse(fs.readFileSync("/opt/bridge/tool_schemas.json", "utf8"));
  for (const tool of definitions) {
    pi.registerTool({name: tool.name, label: tool.name, description: tool.description, promptSnippet: tool.description, parameters: tool.parameters,
      async execute(id, params, signal) {
        const result = await post({jsonrpc: "2.0", id, method: "tools/call", params: {name: tool.name, arguments: params}}, signal);
        return {content: result.content, details: {smddTool: tool.name, taskComplete: result.taskComplete === true}};
      },
    });
  }
  pi.on("tool_result", (event, ctx) => {
    if (event.toolName === "submit" && event.content.some(c => c.type === "text" && c.text.startsWith("Submission accepted:"))) {
      setTimeout(() => { ctx.abort(); ctx.shutdown(); }, 0);
    }
  });
  pi.on("tool_call", async (event, ctx) => {
    const result = await post({jsonrpc: "2.0", id: `guard-${Date.now()}`, method: "tools/call", params: {name: "protocol_guard", arguments: {name: event.toolName, input: event.input}}});
    const value = JSON.parse(result.content[0].text);
    if (value.taskComplete) {
      setTimeout(() => { ctx.abort(); ctx.shutdown(); }, 0);
      return {block: true, reason: "Submission accepted. Task complete."};
    }
    if (value.reason) return {block: true, reason: value.reason};
  });
  pi.on("before_agent_start", async (_event, ctx) => {
    const config = JSON.parse(fs.readFileSync("/agent/sol-pi.json", "utf8"));
    const tools = pi.getAllTools().map(t => ({name: t.name, parameters: t.parameters}));
    fs.writeFileSync("/workspace/.pi/loaded-runtime.json", JSON.stringify({provider: ctx.model?.provider, model: ctx.model?.id, config, tools, activeTools: pi.getActiveTools()}, null, 2));
    if (ctx.model?.provider !== "smdd-deepseek" || ctx.model?.id !== "deepseek-v4.1-flash") throw new Error("SMDD model mismatch");
    for (const flag of ["actionFusion", "observationPack", "evidencePreservingReducer", "onlineContextCompact"]) if (config[flag] !== true) throw new Error(`SoL-Pi ${flag} disabled`);
    if (!tools.some(t => t.name === "obs_recall")) throw new Error("SoL-Pi ObservationPack not loaded");
  });
}
