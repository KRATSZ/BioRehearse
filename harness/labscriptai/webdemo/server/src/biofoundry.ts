/** Thin harness adapter; the Python workflow is the sole state/volume implementation. */
import { readFileSync } from "node:fs";
import { Type } from "typebox";
import type { AgentTool } from "@earendil-works/pi-agent-core";

export function biofoundryUrl(): string {
  const config = JSON.parse(readFileSync(new URL("../../../biofoundry/config.json", import.meta.url), "utf8"));
  return `http://${config.host}:${config.port}`;
}

export async function biofoundryRequest(operation: "status" | "advance") {
  const base = biofoundryUrl();
  const response = await fetch(`${base}/api/status`, { signal: AbortSignal.timeout(5000) });
  if (!response.ok) throw new Error(`Biofoundry status HTTP ${response.status}`);
  const { state, current_step, plan } = await response.json();
  if (operation === "advance") {
    // No tool exists to fabricate a manual acknowledgement. UI confirmations are explicit.
    if (current_step?.kind === "manual") {
      return { blocked: true, reason: "MANUAL_CONFIRMATION_REQUIRED", current_step, url: base };
    }
    if (current_step) {
      const result = await fetch(`${base}/api/advance`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ simulation_id: state.simulation_id, step_id: current_step.id }),
        signal: AbortSignal.timeout(5000),
      });
      const payload = await result.json();
      if (!result.ok) return { blocked: true, ...payload };
      return { simulated: true, status: payload.status, step_id: payload.event.step_id,
               measurement: null, url: base };
    }
  }
  return { simulation_id: state.simulation_id, mode: state.mode, status: state.status,
           current_step, experiment_elapsed_s: state.experiment_elapsed_s,
           event_count: state.events.length, result: state.result,
           validation_scope: plan.validation_scope, unknowns: plan.unknowns, url: base };
}

export function buildBiofoundryTool(): AgentTool {
  return {
    name: "biofoundry", label: "Biofoundry digital workflow",
    description: "Inspect or advance the current, simulation-only cell-free GFP workflow. Start scripts/biofoundry.py first. Manual steps always wait for explicit UI confirmation; no real equipment or measurements. Use compile_biofoundry to generate and check a typed plan.",
    parameters: Type.Object({ operation: Type.Union([Type.Literal("status"), Type.Literal("advance")]) }),
    executionMode: "sequential",
    execute: async (_id, args) => {
      let payload;
      try {
        payload = await biofoundryRequest((args as { operation: "status" | "advance" }).operation);
      } catch (error) {
        payload = { blocked: true, reason: "BIOFOUNDRY_UNAVAILABLE", detail: String(error),
                    start: "/usr/bin/python3 scripts/biofoundry.py" };
      }
      return { content: [{ type: "text", text: JSON.stringify(payload) }], details: { payload } };
    },
  };
}
