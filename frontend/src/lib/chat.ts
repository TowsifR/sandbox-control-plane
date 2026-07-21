// Chat client for a sandbox's opencode agent, proxied through the control plane — each SSE event triggers a message refetch.

const BASE = "/api"

export type ChatMessage = { id: string; role: "user" | "assistant"; text: string }

type ServerMsg = { id: string; type: string; content?: { type: string; text?: string }[] }

// The API doesn't echo the user's prompt (user messages come back with empty content), so the page
// tracks those locally — from the server we take only the assistant's replies.
export function assistantMessages(raw: unknown): ChatMessage[] {
  const list = (Array.isArray(raw) ? raw : ((raw as { data?: ServerMsg[] })?.data ?? [])) as ServerMsg[]
  return list
    .filter((m) => m.type === "assistant")
    .map((m) => ({
      id: m.id,
      role: "assistant" as const,
      text: (m.content ?? [])
        .filter((p) => p.type === "text")
        .map((p) => p.text ?? "")
        .join(""),
    }))
    .filter((m) => m.text !== "")
}

export const chat = {
  createSession: (id: string) =>
    fetch(`${BASE}/sandboxes/${id}/chat/sessions`, { method: "POST" })
      .then((r) => r.json())
      .then((d) => d.data.id as string),

  messages: (id: string, sid: string) =>
    fetch(`${BASE}/sandboxes/${id}/chat/sessions/${sid}/messages`)
      .then((r) => r.json())
      .then(assistantMessages),

  prompt: (id: string, sid: string, text: string) =>
    fetch(`${BASE}/sandboxes/${id}/chat/sessions/${sid}/prompt`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ text }),
    }),

  events: (id: string, sid: string) =>
    new EventSource(`${BASE}/sandboxes/${id}/chat/sessions/${sid}/events`),
}
