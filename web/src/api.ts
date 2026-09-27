import { useCallback, useEffect, useState } from "react";
import type { StreamEvent } from "./types";

export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") ?? "http://localhost:8787";

export async function getJSON<T>(path: string, signal?: AbortSignal): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}${path}`, { signal });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new Error(`Can't reach the CI-Sense API at ${API_BASE}. Is the server running?`);
  }
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    throw new Error(body?.detail ?? `Request failed (${resp.status})`);
  }
  return resp.json() as Promise<T>;
}

export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    getJSON<T>(path, controller.signal)
      .then((d) => setData(d))
      .catch((err: Error) => {
        if (err.name !== "AbortError") setError(err.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [path, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { data, error, loading, reload };
}

/** POSTs to the SSE endpoint and hands each parsed event to onEvent. */
export async function streamTriage(runId: string, onEvent: (e: StreamEvent) => void, signal: AbortSignal) {
  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}/api/triage/${encodeURIComponent(runId)}/stream`, {
      method: "POST",
      headers: { Accept: "text/event-stream" },
      signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") return;
    throw new Error(`Can't reach the CI-Sense API at ${API_BASE}. Is the server running?`);
  }
  if (!resp.ok || !resp.body) {
    const body = await resp.json().catch(() => null);
    throw new Error(body?.detail ?? `Request failed (${resp.status})`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary: number;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const data = block
        .split("\n")
        .filter((line) => line.startsWith("data: "))
        .map((line) => line.slice(6))
        .join("\n");
      if (data) onEvent(JSON.parse(data) as StreamEvent);
    }
  }
}
