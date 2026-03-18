const BASE = import.meta.env.VITE_API_URL ?? "/api/v1";

export async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

/** Returns an EventSource-like async generator for SSE streaming. */
export function streamQuery(query: string): EventSource {
  const url = `${BASE}/query?q=${encodeURIComponent(query)}`;
  return new EventSource(url);
}
