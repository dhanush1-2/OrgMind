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

/**
 * Stream SSE chunks from the query endpoint using fetch (works cross-origin).
 * Calls onChunk for each text piece, onDone when finished, onError on failure.
 */
export async function streamQuery(
  query: string,
  onChunk: (text: string) => void,
  onDone: () => void,
  onError: (msg: string) => void
): Promise<void> {
  const url = `${BASE}/query?q=${encodeURIComponent(query)}`;
  try {
    const res = await fetch(url, { headers: { Accept: "text/event-stream" } });
    if (!res.ok || !res.body) {
      onError(`Backend returned ${res.status}`);
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        if (!line.startsWith("data:")) continue;
        const raw = line.slice(5).trim();
        if (raw === "[DONE]") { onDone(); return; }
        try {
          const parsed = JSON.parse(raw);
          if (parsed.error) { onError(parsed.error); return; }
          if (parsed.chunk) onChunk(parsed.chunk);
        } catch {
          // ignore malformed lines
        }
      }
    }
    onDone();
  } catch (e) {
    onError((e as Error).message ?? "Network error");
  }
}
