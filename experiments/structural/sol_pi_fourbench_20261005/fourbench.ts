import fs from "node:fs";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
  const base = process.env.FOURBENCH_BOUNDARY_URL;
  if (!base) throw new Error("FOURBENCH_BOUNDARY_URL is required");
  pi.registerProvider("fourbench-deepseek", {
    baseUrl: base + "/v1", apiKey: "local-boundary", api: "openai-completions",
    models: [{ id: "deepseek-v4.1-flash", name: "Fourbench DeepSeek v4.1 Flash", reasoning: false,
      input: ["text"], cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
      contextWindow: 262144, maxTokens: 65536,
      compat: { supportsStore: false, supportsDeveloperRole: false,
        supportsReasoningEffort: false, supportsUsageInStreaming: true, maxTokensField: "max_tokens" },
    }],
  });
  pi.on("tool_call", async (event) => {
    const response = await fetch(base + "/guard", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: event.toolName, input: event.input }),
    });
    if (!response.ok) return { block: true, reason: "Runtime integrity guard unavailable" };
    const value = await response.json();
    if (value.reason) return { block: true, reason: value.reason };
  });
  pi.on("before_agent_start", async (_event, ctx) => {
    const config = JSON.parse(fs.readFileSync("/agent/sol-pi.json", "utf8"));
    const tools = pi.getAllTools().map(t => ({ name: t.name, parameters: t.parameters }));
    const loaded = { provider: ctx.model?.provider, model: ctx.model?.id, config, tools,
      activeTools: pi.getActiveTools() };
    fs.writeFileSync("/workspace/.pi/loaded-runtime.json", JSON.stringify(loaded, null, 2));
    if (ctx.model?.provider !== "fourbench-deepseek" || ctx.model?.id !== "deepseek-v4.1-flash") {
      throw new Error("Fourbench model/provider mismatch");
    }
    for (const flag of ["actionFusion", "observationPack", "evidencePreservingReducer", "onlineContextCompact"]) {
      if (config[flag] !== true) throw new Error(`SoL-Pi ${flag} disabled`);
    }
    if (!tools.some(t => t.name === "obs_recall")) throw new Error("ObservationPack did not load");
  });
}
