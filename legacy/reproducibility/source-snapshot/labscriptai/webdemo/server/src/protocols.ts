import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { loadDemoEnv } from "./env.ts";

export const PROTOCOLS_API_BASE = "https://www.protocols.io/api/v4/protocols";
export const FETCH_PROTOCOL_MS = 20_000;
export const PROTOCOL_MARKDOWN_CAP = 80_000;

export type ProtocolSource = "cache" | "live";

export interface ProtocolRecord {
  doi: string;
  version: string;
  title: string;
  markdown: string;
  source: ProtocolSource;
  fetched_at: string;
  url: string;
}

export interface FetchProtocolOk {
  ok: true;
  protocol: ProtocolRecord;
}

export interface FetchProtocolFail {
  ok: false;
  error: string;
  hint: string;
}

export type FetchProtocolResult = FetchProtocolOk | FetchProtocolFail;

export type FetchLike = (
  input: string,
  init?: { headers?: Record<string, string>; signal?: AbortSignal }
) => Promise<{
  ok: boolean;
  status: number;
  statusText: string;
  json: () => Promise<unknown>;
}>;

export function protocolsIoToken(): string {
  return (
    process.env.LABSCRIPTAI_PROTOCOLSIO_ACCESS_TOKEN ||
    process.env.PROTOCOLSIO_ACCESS_TOKEN ||
    ""
  ).trim();
}

export function protocolCacheDisabled(force?: boolean): boolean {
  return Boolean(force) || process.env.LABSCRIPTAI_PROTOCOL_NO_CACHE === "1";
}

export function goalMentionsProtocol(text: string): boolean {
  return /protocols\.io|10\.17504\b|\bigem\b|fluorescein/i.test(text);
}

/** Pull a protocols.io DOI or URI plus optional /vN from free text. */
export function extractProtocolRef(text: string): { id: string; version?: string } | null {
  const doi = text.match(/10\.17504\/protocols\.io\.([A-Za-z0-9._-]+)(?:\/v(\d+))?/i);
  if (doi) {
    return {
      id: `10.17504/protocols.io.${doi[1]}`,
      version: doi[2],
    };
  }
  const uri = text.match(/protocols\.io\/(?:view\/)?([A-Za-z0-9._-]+)(?:\/v(\d+))?/i);
  if (uri && !/^api$/i.test(uri[1])) {
    return { id: uri[1], version: uri[2] };
  }
  return null;
}

export function protocolCacheDir(webdemoRoot?: string): string {
  const root = webdemoRoot ?? loadDemoEnv().webdemoRoot;
  return path.join(root, "eval", "igem_fluorescein_operator", "protocol");
}

export function cacheSlug(id: string, version: string): string {
  if (/6zrhf56/i.test(id) && String(version).replace(/^v/i, "") === "3") {
    return "igem_6zrhf56_v3";
  }
  const cleaned = id.replace(/^https?:\/\/(dx\.)?doi\.org\//i, "");
  const slug = cleaned.replace(/[^A-Za-z0-9]+/g, "_").replace(/^_|_$/g, "").toLowerCase();
  return `${slug}_v${version || "latest"}`;
}

export function cachePaths(
  id: string,
  version: string,
  webdemoRoot?: string
): { dir: string; md: string; meta: string } {
  const dir = protocolCacheDir(webdemoRoot);
  const base = cacheSlug(id, version);
  return { dir, md: path.join(dir, `${base}.md`), meta: path.join(dir, `${base}.meta.json`) };
}

function capMarkdown(text: string): string {
  const trimmed = text.trim();
  return trimmed.length <= PROTOCOL_MARKDOWN_CAP
    ? trimmed
    : trimmed.slice(0, PROTOCOL_MARKDOWN_CAP);
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function protocolObject(payload: unknown): Record<string, unknown> | null {
  const root = asRecord(payload);
  if (!root) return null;
  return asRecord(root.protocol) ?? asRecord(root.payload) ?? root;
}

export function protocolToMarkdown(payload: unknown): { title: string; doi: string; version: string; markdown: string } {
  const proto = protocolObject(payload) ?? {};
  const title = asString(proto.title) || "Untitled protocol";
  const doiRaw = asString(proto.doi) || asString(proto.uri);
  const doi = doiRaw.replace(/^(https?:\/\/)?(dx\.)?doi\.org\//i, "");
  const uriVersion = `${asString(proto.version_uri)} ${asString(proto.uri)} ${asString(proto.url)}`.match(
    /\/v(\d+)/i
  );
  const version =
    uriVersion?.[1] ||
    (proto.version_id != null && String(proto.version_id).trim()
      ? String(proto.version_id)
      : "unknown");
  const sections: string[] = [`# ${title}`];
  if (doi) sections.push(`DOI: ${doi}`);
  if (version !== "unknown") sections.push(`Version: ${version}`);
  for (const [heading, key] of [
    ["Description", "description"],
    ["Before start", "before_start"],
    ["Guidelines", "guidelines"],
    ["Warning", "warning"],
    ["Materials", "materials_text"],
  ] as const) {
    const body = asString(proto[key]).trim();
    if (body) sections.push(`## ${heading}\n\n${body}`);
  }
  const steps = Array.isArray(proto.steps) ? proto.steps : [];
  if (steps.length) {
    const lines = steps.map((step, index) => {
      const rec = asRecord(step) ?? {};
      const text = asString(rec.step) || asString(rec.title) || asString(rec.text);
      return `${index + 1}. ${text.trim() || "(empty step)"}`;
    });
    sections.push(`## Steps\n\n${lines.join("\n\n")}`);
  }
  return { title, doi, version, markdown: capMarkdown(sections.join("\n\n")) };
}

function readCache(id: string, version: string, webdemoRoot?: string): ProtocolRecord | null {
  const { md, meta } = cachePaths(id, version, webdemoRoot);
  if (!existsSync(md)) return null;
  try {
    const markdown = capMarkdown(readFileSync(md, "utf8"));
    if (!markdown) return null;
    const extra = existsSync(meta)
      ? (JSON.parse(readFileSync(meta, "utf8")) as Partial<ProtocolRecord>)
      : {};
    return {
      doi: extra.doi || id,
      version: extra.version || version,
      title: extra.title || id,
      markdown,
      source: "cache",
      fetched_at: extra.fetched_at || "",
      url: extra.url || `${PROTOCOLS_API_BASE}/${id}`,
    };
  } catch {
    return null;
  }
}

function writeCache(record: ProtocolRecord, id: string, version: string, webdemoRoot?: string): void {
  const { dir, md, meta } = cachePaths(id, version, webdemoRoot);
  mkdirSync(dir, { recursive: true });
  writeFileSync(md, record.markdown, "utf8");
  writeFileSync(
    meta,
    JSON.stringify(
      {
        doi: record.doi,
        version: record.version,
        title: record.title,
        fetched_at: record.fetched_at,
        url: record.url,
        source: "live",
      },
      null,
      2
    ),
    "utf8"
  );
}

function fail(error: string, hint: string): FetchProtocolFail {
  return { ok: false, error, hint };
}

export async function fetchProtocol(input: {
  doi?: string;
  version?: string;
  force?: boolean;
  goalText?: string;
  fetchImpl?: FetchLike;
  now?: () => Date;
  webdemoRoot?: string;
}): Promise<FetchProtocolResult> {
  loadDemoEnv();
  const fromArgs = (input.doi || "").trim();
  const fromGoal = extractProtocolRef(input.goalText || "");
  const id = fromArgs.replace(/^https?:\/\/(dx\.)?doi\.org\//i, "") || fromGoal?.id || "";
  if (!id) {
    return fail(
      "missing_protocol_id",
      "Pass doi (e.g. 10.17504/protocols.io.6zrhf56) or mention a protocols.io DOI in the goal."
    );
  }
  const explicitVersion = (input.version || fromGoal?.version || "").replace(/^v/i, "");
  const version = explicitVersion || (/6zrhf56/i.test(id) ? "3" : "latest");
  const apiId = version && version !== "latest" ? `${id}/v${version}` : `${id}/latest`;
  const url = `${PROTOCOLS_API_BASE}/${apiId}?content_format=markdown`;

  if (!protocolCacheDisabled(input.force)) {
    const cached = readCache(id, version, input.webdemoRoot);
    if (cached) return { ok: true, protocol: { ...cached, source: "cache" } };
  }

  const token = protocolsIoToken();
  if (!token) {
    return fail(
      "missing_token",
      "Set LABSCRIPTAI_PROTOCOLSIO_ACCESS_TOKEN (or PROTOCOLSIO_ACCESS_TOKEN) in labscriptai/webdemo/.env. Public GET still needs a client access token from https://www.protocols.io/developers"
    );
  }

  const fetchImpl = input.fetchImpl ?? (globalThis.fetch as FetchLike);
  let payload: unknown;
  try {
    const response = await fetchImpl(url, {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/json",
      },
      signal: AbortSignal.timeout(FETCH_PROTOCOL_MS),
    });
    if (!response.ok) {
      return fail(
        `http_${response.status}`,
        response.status === 404
          ? "Protocol not found. Check the DOI and version (this eval pins v3)."
          : `protocols.io returned ${response.status} ${response.statusText}.`
      );
    }
    payload = await response.json();
  } catch (error) {
    const name = error instanceof Error ? error.name : "";
    if (name === "AbortError" || name === "TimeoutError") {
      return fail("timeout", "protocols.io request timed out (20 s). Retry, or use the on-disk cache.");
    }
    return fail(
      "network",
      error instanceof Error ? error.message : "Could not reach protocols.io."
    );
  }

  const parsed = protocolToMarkdown(payload);
  const record: ProtocolRecord = {
    doi: parsed.doi || id,
    version: parsed.version !== "unknown" ? parsed.version : version,
    title: parsed.title,
    markdown: parsed.markdown,
    source: "live",
    fetched_at: (input.now ?? (() => new Date()))().toISOString(),
    url,
  };
  if (!record.markdown) {
    return fail("empty_protocol", "protocols.io returned no steps or description.");
  }
  try {
    writeCache(record, id, version, input.webdemoRoot);
  } catch {
    // Cache is best-effort; the live record is still usable.
  }
  return { ok: true, protocol: record };
}
