import { useState, useRef, useEffect } from "react";
import { Send, Loader2 } from "lucide-react";
import { streamQuery } from "../api";

interface Message {
  role: "user" | "assistant";
  content: string;
}

export default function AskPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() || streaming) return;

    const query = input.trim();
    setInput("");
    setStreaming(true);

    // Add user message + empty assistant placeholder
    setMessages((prev) => [
      ...prev,
      { role: "user", content: query },
      { role: "assistant", content: "" },
    ]);

    await streamQuery(
      query,
      // onChunk — append each piece to the last message
      (chunk) => {
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = {
            role: "assistant",
            content: next[next.length - 1].content + chunk,
          };
          return next;
        });
      },
      // onDone
      () => setStreaming(false),
      // onError
      (msg) => {
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (!last.content) {
            next[next.length - 1] = { role: "assistant", content: `Error: ${msg}` };
          }
          return next;
        });
        setStreaming(false);
      }
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-8 py-5 border-b border-gray-800">
        <h1 className="text-xl font-semibold">Ask OrgMind</h1>
        <p className="text-sm text-gray-400">
          Query your organisation's decision history
        </p>
      </div>

      <div className="flex-1 overflow-auto px-8 py-6 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-600 mt-16">
            <p className="text-4xl mb-3">🧠</p>
            <p className="text-lg">Ask anything about past decisions</p>
            <p className="text-sm mt-1">
              e.g. "Why did we choose PostgreSQL?" or "What database decisions conflict?"
            </p>
          </div>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-2xl px-4 py-3 rounded-xl text-sm leading-relaxed whitespace-pre-wrap ${
                m.role === "user"
                  ? "bg-indigo-600 text-white"
                  : "bg-gray-800 text-gray-100"
              }`}
            >
              {m.content || (
                <span className="text-gray-500 italic">Thinking…</span>
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={handleSubmit}
        className="px-8 py-4 border-t border-gray-800 flex gap-3"
      >
        <input
          className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          placeholder="Ask a question about your decisions…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={streaming}
        />
        <button
          type="submit"
          disabled={streaming || !input.trim()}
          className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 px-4 py-2 rounded-lg transition-colors"
        >
          {streaming ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <Send size={16} />
          )}
        </button>
      </form>
    </div>
  );
}
