import { lookup } from "node:dns/promises";
import { isIP } from "node:net";

export const FETCH_URL_MS = 20_000;
export const FETCH_URL_BODY_CAP = 80_000;
export const BLOCKED_PORTS = new Set([8010, 31950, 4880, 3190, 8787]);

export type FetchUrlOk = { ok: true; url: string; chars: number; body: string };
export type FetchUrlFail = { ok: false; blocked?: boolean; error: string; hint: string };
export type FetchUrlResult = FetchUrlOk | FetchUrlFail;

const PRIVATE_V4 = /^(0\.|10\.|127\.|169\.254\.|192\.168\.|172\.(1[6-9]|2\d|3[0-1])\.)/;

export function ipv4Private(address: string): boolean {
  return PRIVATE_V4.test(address);
}

export function ipv6Private(address: string): boolean {
  const host = address.toLowerCase().replace(/^\[|\]$/g, "");
  if (host === "::1" || host === "0:0:0:0:0:0:0:1") return true;
  if (host.startsWith("fe80:") || host.startsWith("fc") || host.startsWith("fd")) return true;
  const mapped = host.match(/::ffff:(\d+\.\d+\.\d+\.\d+)$/i);
  return Boolean(mapped && ipv4Private(mapped[1]));
}

export function hostnameLooksLocal(hostname: string): boolean {
  const host = hostname.replace(/^\[|\]$/g, "").toLowerCase();
  if (!host || host === "localhost" || host === "::1" || host === "0.0.0.0") return true;
  if (host.endsWith(".local") || host.endsWith(".localhost") || host.endsWith(".internal")) return true;
  const ip = isIP(host);
  if (ip === 4) return ipv4Private(host);
  if (ip === 6) return ipv6Private(host);
  return false;
}

export async function assertPublicHttpUrl(raw: string): Promise<{ url: URL } | FetchUrlFail> {
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    return { ok: false, blocked: true, error: "invalid_url", hint: "Pass a full http(s) URL." };
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    return { ok: false, blocked: true, error: "scheme_blocked", hint: "Only http and https are allowed." };
  }
  const port = url.port ? Number(url.port) : url.protocol === "https:" ? 443 : 80;
  if (BLOCKED_PORTS.has(port)) {
    return {
      ok: false,
      blocked: true,
      error: "port_blocked",
      hint: `Port ${port} is reserved for local robots/backends. Use public pages only.`,
    };
  }
  if (hostnameLooksLocal(url.hostname)) {
    return {
      ok: false,
      blocked: true,
      error: "host_blocked",
      hint: "Localhost, private, and link-local addresses are blocked.",
    };
  }
  try {
    const answers = await lookup(url.hostname, { all: true });
    if (answers.some((row) => hostnameLooksLocal(row.address))) {
      return {
        ok: false,
        blocked: true,
        error: "host_blocked",
        hint: "That hostname resolves to a private or loopback address.",
      };
    }
  } catch {
    return { ok: false, blocked: true, error: "unresolved", hint: "Could not resolve the hostname." };
  }
  return { url };
}

export type SearchHit = { title: string; url: string; snippet: string };
export type WebSearchOk = { ok: true; query: string; hits: SearchHit[] };
export type WebSearchResult = WebSearchOk | FetchUrlFail;

function stripHtml(text: string): string {
  return text
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(Number(n)))
    .replace(/\s+/g, " ")
    .trim();
}

function decodeDuckHref(href: string, base: string): string {
  try {
    const abs = new URL(href, base);
    const uddg = abs.searchParams.get("uddg");
    return uddg ? uddg : abs.href;
  } catch {
    return href;
  }
}

/** Parse DuckDuckGo html.duckduckgo.com result cards. */
export function parseSearchHtml(html: string, base = "https://html.duckduckgo.com"): SearchHit[] {
  const hits: SearchHit[] = [];
  const seen = new Set<string>();
  const blockRe =
    /class="result__a"[^>]*href="([^"]+)"[^>]*>([\s\S]*?)<\/a>[\s\S]{0,1200}?class="result__snippet"[^>]*>([\s\S]*?)<\/a>/gi;
  let match: RegExpExecArray | null;
  while ((match = blockRe.exec(html)) && hits.length < 12) {
    const url = decodeDuckHref(match[1].replace(/&amp;/g, "&"), base);
    if (!url || seen.has(url)) continue;
    seen.add(url);
    hits.push({
      title: stripHtml(match[2]).slice(0, 200),
      url,
      snippet: stripHtml(match[3]).slice(0, 400),
    });
  }
  if (hits.length) return hits;
  const titleRe = /class="result__a"[^>]*href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/gi;
  while ((match = titleRe.exec(html)) && hits.length < 12) {
    const url = decodeDuckHref(match[1].replace(/&amp;/g, "&"), base);
    if (!url || seen.has(url)) continue;
    seen.add(url);
    hits.push({ title: stripHtml(match[2]).slice(0, 200), url, snippet: "" });
  }
  return hits;
}

const SEARCH_UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";
const DDG_SEARCH_MS = 8_000;

type CrossrefItem = {
  DOI?: string;
  URL?: string;
  title?: string[];
  abstract?: string;
  resource?: { primary?: { URL?: string } };
};

function rankHit(hit: SearchHit): number {
  const text = `${hit.title} ${hit.url} ${hit.snippet}`.toLowerCase();
  let score = 0;
  if ((text.includes("fluorescein") || text.includes("fluorescence")) && text.includes("calibration")) score += 3;
  if (/\bv3\b/.test(text) || text.includes("version 3")) score += 2;
  if (text.includes("protocols.io")) score += 1;
  if (text.includes("plate reader") || text.includes("plate-reader")) score += 1;
  return score;
}

/** Parse Crossref /works JSON into title+url+snippet hits. */
export function parseCrossrefWorks(body: string): SearchHit[] {
  let parsed: { message?: { items?: CrossrefItem[] } };
  try {
    parsed = JSON.parse(body) as { message?: { items?: CrossrefItem[] } };
  } catch {
    return [];
  }
  const hits: SearchHit[] = [];
  const seen = new Set<string>();
  for (const item of parsed.message?.items ?? []) {
    const title = (item.title ?? []).join(" ").trim();
    const doi = item.DOI ?? "";
    const url = item.resource?.primary?.URL || (doi ? `https://doi.org/${doi}` : item.URL ?? "");
    if (!url || seen.has(url)) continue;
    seen.add(url);
    hits.push({
      title: stripHtml(title).slice(0, 200),
      url,
      snippet: stripHtml(item.abstract || doi).slice(0, 400),
    });
  }
  return hits.sort((a, b) => rankHit(b) - rankHit(a)).slice(0, 12);
}

async function searchDuckDuckGo(q: string): Promise<WebSearchResult> {
  const raw = "https://html.duckduckgo.com/html/";
  const checked = await assertPublicHttpUrl(raw);
  if (!("url" in checked)) return checked;
  try {
    const response = await fetch(checked.url, {
      method: "POST",
      redirect: "manual",
      headers: {
        Accept: "text/html",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": SEARCH_UA,
      },
      body: new URLSearchParams({ q }).toString(),
      signal: AbortSignal.timeout(DDG_SEARCH_MS),
    });
    const location = response.headers.get("location");
    if (location && response.status >= 300 && response.status < 400) {
      const bounced = await fetchPublicUrl(new URL(location, checked.url).href);
      if (!bounced.ok) return bounced;
      return { ok: true, query: q, hits: parseSearchHtml(bounced.body, bounced.url) };
    }
    if (!response.ok) {
      return {
        ok: false,
        error: `http_${response.status}`,
        hint: `Search POST returned ${response.status}.`,
      };
    }
    const body = (await response.text()).slice(0, FETCH_URL_BODY_CAP);
    return { ok: true, query: q, hits: parseSearchHtml(body, checked.url.href) };
  } catch (error) {
    const name = error instanceof Error ? error.name : "";
    if (name === "AbortError" || name === "TimeoutError") {
      return { ok: false, error: "timeout", hint: "DuckDuckGo HTML search timed out." };
    }
    return {
      ok: false,
      error: "network",
      hint: error instanceof Error ? error.message : "Could not search.",
    };
  }
}

async function searchCrossref(q: string): Promise<WebSearchResult> {
  const raw = `https://api.crossref.org/works?query=${encodeURIComponent(q)}&rows=12`;
  const checked = await assertPublicHttpUrl(raw);
  if (!("url" in checked)) return checked;
  try {
    const response = await fetch(checked.url, {
      method: "GET",
      headers: { Accept: "application/json", "User-Agent": "LabscriptAI/1.0" },
      signal: AbortSignal.timeout(FETCH_URL_MS),
    });
    if (!response.ok) {
      return {
        ok: false,
        error: `http_${response.status}`,
        hint: `Crossref GET returned ${response.status}.`,
      };
    }
    const body = (await response.text()).slice(0, FETCH_URL_BODY_CAP);
    return { ok: true, query: q, hits: parseCrossrefWorks(body) };
  } catch (error) {
    const name = error instanceof Error ? error.name : "";
    if (name === "AbortError" || name === "TimeoutError") {
      return { ok: false, error: "timeout", hint: "Crossref search timed out (20 s)." };
    }
    return {
      ok: false,
      error: "network",
      hint: error instanceof Error ? error.message : "Could not search.",
    };
  }
}

export async function searchPublicWeb(query: string): Promise<WebSearchResult> {
  const q = query.trim().slice(0, 300);
  if (!q) return { ok: false, error: "empty_query", hint: "Pass a search query." };
  const [ddg, xref] = await Promise.all([searchDuckDuckGo(q), searchCrossref(q)]);
  if (ddg.ok && ddg.hits.length) return ddg;
  if (xref.ok && xref.hits.length) return xref;
  if (ddg.ok) return ddg;
  return xref;
}

export async function fetchPublicUrl(raw: string, hops = 0): Promise<FetchUrlResult> {
  const checked = await assertPublicHttpUrl(raw);
  if (!("url" in checked)) return checked;
  if (hops > 4) {
    return { ok: false, blocked: true, error: "redirect_limit", hint: "Too many redirects." };
  }
  try {
    const response = await fetch(checked.url, {
      method: "GET",
      redirect: "manual",
      headers: { Accept: "text/html,text/plain,application/json,text/markdown,*/*" },
      signal: AbortSignal.timeout(FETCH_URL_MS),
    });
    const location = response.headers.get("location");
    if (location && response.status >= 300 && response.status < 400) {
      return fetchPublicUrl(new URL(location, checked.url).href, hops + 1);
    }
    if (!response.ok) {
      return {
        ok: false,
        error: `http_${response.status}`,
        hint: `GET ${checked.url.href} returned ${response.status}.`,
      };
    }
    const body = (await response.text()).slice(0, FETCH_URL_BODY_CAP);
    return { ok: true, url: checked.url.href, chars: body.length, body };
  } catch (error) {
    const name = error instanceof Error ? error.name : "";
    if (name === "AbortError" || name === "TimeoutError") {
      return { ok: false, error: "timeout", hint: "Public GET timed out (20 s)." };
    }
    return {
      ok: false,
      error: "network",
      hint: error instanceof Error ? error.message : "Could not fetch URL.",
    };
  }
}
