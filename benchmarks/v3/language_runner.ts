/**
 * GLM-4.7-Flash extension of the v2 portfolio authoring harness.
 *
 * This file deliberately leaves the v2 author unchanged.  It imports the
 * registered compiler/tool and extracts the v2 authoring prompt from the
 * frozen source at runtime; the only model-route change is the explicitly
 * whitelisted, free GLM endpoint.  There is no fallback provider.
 */
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PAPER = path.resolve(HERE, "../..");
const PROJECT_CANDIDATES = [
  process.env.BIOFOUNDRY_PROJECT,
  path.resolve(PAPER, "../../../..", "Flexagent/Opentrons-Lab-Agent"),
  path.join(PAPER, "release/BioRehearse/harness"),
].filter((value): value is string => Boolean(value));
const PROJECT = PROJECT_CANDIDATES.find((value) => existsSync(path.join(value, "labscriptai/webdemo/server/src/biofoundry-author.ts"))) || PROJECT_CANDIDATES[0];
const AUTHOR = path.join(PROJECT, "labscriptai/webdemo/server/src/biofoundry-author.ts");
const GLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4";
const GLM_MODEL = process.env.BIOFOUNDRY_GLM_MODEL || "glm-4.7-flash";
const MAX_OUTPUT_TOKENS = 8192;

export const MODEL_ROUTE = {
  provider: "zai",
  model: GLM_MODEL,
  api: "openai-completions",
  base_url: GLM_BASE_URL,
  free_model_whitelist: [GLM_MODEL],
  fallback: null,
  max_output_tokens: MAX_OUTPUT_TOKENS,
  cost_assumption: { input_cny_per_million: 0, output_cny_per_million: 0, cache_read_cny_per_million: 0 },
  tool_choice: process.env.BIOFOUNDRY_FORCE_TOOL_CHOICE || "auto",
};

function sha256(text: string): string {
  return createHash("sha256").update(text).digest("hex");
}

function model(): any {
  const key = process.env.GLM_API_KEY || "";
  if (!key) throw new Error("GLM_API_KEY is unavailable; no provider fallback is permitted");
  return {
    id: GLM_MODEL,
    name: GLM_MODEL,
    api: "openai-completions",
    provider: "zai",
    baseUrl: GLM_BASE_URL,
    reasoning: true,
    input: ["text"],
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    contextWindow: GLM_MODEL === "glm-4.7-flash" ? 200000 : 128000,
    maxTokens: MAX_OUTPUT_TOKENS,
    compat: {
      supportsStore: false,
      supportsDeveloperRole: false,
      supportsReasoningEffort: false,
      supportsUsageInStreaming: true,
      supportsFinishReason: true,
      maxTokensField: "max_tokens",
      requiresToolResultName: false,
      requiresAssistantAfterToolResult: false,
      requiresThinkingAsText: false,
      thinkingFormat: "zai",
      zaiToolStream: false,
      supportsStrictMode: false,
    },
  };
}

/** Extract the exact portfolio system prompt from the unchanged v2 author. */
export function authorPrompt(sources: unknown): { prompt: string; source_sha256: string; raw: string } {
  const source = readFileSync(AUTHOR, "utf8");
  const start = source.indexOf("export async function authorPortfolio");
  if (start < 0) throw new Error("authorPortfolio function not found");
  const body = source.slice(start);
  const match = body.match(/systemPrompt:`([\s\S]*?)`/);
  if (!match) throw new Error("portfolio system prompt not found");
  const raw = match[1];
  const prompt = raw.replace("${JSON.stringify(sources)}", JSON.stringify(sources));
  return { prompt, source_sha256: sha256(raw), raw };
}

async function loadHarness(): Promise<{ Agent: any; AgentTool: any; streamSimple: any; Type: any; buildPortfolioCompiler: any }> {
  const packageRoot = path.join(PROJECT, "labscriptai/webdemo/node_modules");
  const [agentCore, piAi, typebox, author] = await Promise.all([
    import(pathToFileURL(path.join(packageRoot, "@earendil-works/pi-agent-core/dist/index.js")).href),
    import(pathToFileURL(path.join(packageRoot, "@earendil-works/pi-ai/dist/compat.js")).href),
    import(pathToFileURL(path.join(packageRoot, "typebox/build/index.mjs")).href),
    import(pathToFileURL(AUTHOR).href),
  ]);
  return { Agent: agentCore.Agent, AgentTool: undefined, streamSimple: piAi.streamSimple, Type: typebox.Type, buildPortfolioCompiler: author.buildPortfolioCompiler };
}

export async function authorGlm(request: string, sources: unknown) {
  const key = process.env.GLM_API_KEY || "";
  if (!key) throw new Error("GLM_API_KEY is unavailable; no provider fallback is permitted");
  let accepted: any = null;
  let clarification: any = null;
  let attempts = 0;
  const trace: any[] = [];
  const promptMeta = authorPrompt(sources);
  const harness = await loadHarness();
  const tool = harness.buildPortfolioCompiler((value: any) => {
    attempts += 1;
    if (value.ok) accepted = value;
  });
  const clarify: any = {
    name: "request_clarification",
    label: "Ask for required planning information",
    description: "Ask one concise question when required request values are missing, ambiguous or contradictory; do not guess.",
    parameters: harness.Type.Object({ missing_fields: harness.Type.Array(harness.Type.String(), { minItems: 1 }), question: harness.Type.String() }),
    executionMode: "sequential",
    execute: async (_id, args: any) => {
      clarification = args;
      return { content: [{ type: "text", text: JSON.stringify(args) }], details: { payload: args } };
    },
  };
  const agent = new harness.Agent({
    initialState: {
      model: model(),
      thinkingLevel: "low",
      messages: [],
      tools: [tool, clarify],
      systemPrompt: promptMeta.prompt,
    },
    streamFn:
      process.env.BIOFOUNDRY_FORCE_TOOL_CHOICE === "required"
        ? (m: any, c: any, o: any) => harness.streamSimple(m, c, { ...o, toolChoice: "required" })
        : harness.streamSimple,
    getApiKey: async () => key,
    toolExecution: "sequential",
    shouldStopAfterTurn: () => Boolean(accepted) || Boolean(clarification) || attempts >= 3,
  });
  agent.subscribe((event) => {
    if (["message_end", "tool_execution_start", "tool_execution_end"].includes(event.type)) trace.push(event);
  });
  await agent.prompt(request);
  return {
    ok: Boolean(accepted),
    code: clarification ? "CLARIFICATION_REQUIRED" : accepted ? "COMPILED" : "BLOCKED",
    clarification,
    request,
    provider: MODEL_ROUTE.provider,
    model: MODEL_ROUTE.model,
    api: MODEL_ROUTE.api,
    tool_choice: MODEL_ROUTE.tool_choice,
    trace,
    generated: accepted,
    attempts,
    prompt_sha256: promptMeta.source_sha256,
    source_author: path.relative(PAPER, AUTHOR),
    scope: "Digital planning only; provider usage and nominal pricing are retained separately",
  };
}

function cleanJson(value: unknown): unknown {
  if (value === undefined) return null;
  try {
    return JSON.parse(JSON.stringify(value));
  } catch {
    return { serialization_error: true };
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url))) {
  void (async () => {
    try {
      const input = JSON.parse(readFileSync(0, "utf8")) as { request: string; sources: unknown };
      const result = await authorGlm(input.request, input.sources);
      process.stdout.write(JSON.stringify(cleanJson(result)));
    } catch (error) {
      process.stderr.write(String(error));
      process.exitCode = 1;
    }
  })();
}
