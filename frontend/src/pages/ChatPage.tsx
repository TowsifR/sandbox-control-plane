import { useEffect, useRef, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { ChevronLeft, Send } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"
import { chat, type ChatMessage } from "@/lib/chat"

export function ChatPage() {
  const { id } = useParams()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState("")
  const [sessionId, setSessionId] = useState<string>()
  const [error, setError] = useState<string>()
  const [busy, setBusy] = useState(false)
  const [pending, setPending] = useState(false) // waiting on the agent's reply — drives the typing dots
  const endRef = useRef<HTMLDivElement>(null)

  // Merge the server's assistant messages by id (so a streaming reply updates in place), keeping the
  // locally-tracked user messages. Appending on first-sight keeps the order chronological.
  function mergeAssistants(server: ChatMessage[]) {
    setMessages((prev) => {
      if (server.some((m) => !prev.some((p) => p.id === m.id))) setPending(false) // reply arrived
      const next = [...prev]
      for (const m of server) {
        const i = next.findIndex((x) => x.id === m.id)
        if (i === -1) next.push(m)
        else next[i] = m
      }
      return next
    })
  }

  useEffect(() => {
    if (!id) return
    let es: EventSource | undefined
    let cancelled = false
    chat
      .createSession(id)
      .then((sid) => {
        if (cancelled) return
        setSessionId(sid)
        es = chat.events(id, sid)
        es.onmessage = () => chat.messages(id, sid).then(mergeAssistants).catch(() => {})
      })
      .catch(() => {
        if (!cancelled) setError("Couldn't reach the agent — make sure the sandbox is running.")
      })
    return () => {
      cancelled = true
      es?.close()
    }
  }, [id])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, pending])

  async function send() {
    if (!id || !sessionId || !input.trim() || busy) return
    const text = input.trim()
    setInput("")
    setMessages((prev) => [...prev, { id: `local-${Date.now()}`, role: "user", text }])
    setPending(true) // the reply isn't token-streamed, so show a "thinking" indicator until it lands
    setBusy(true)
    try {
      await chat.prompt(id, sessionId, text)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex h-svh flex-col">
      <header className="flex h-12 shrink-0 items-center gap-2 border-b px-4">
        <Link to="/" className="text-muted-foreground hover:text-foreground">
          <ChevronLeft className="size-4" />
        </Link>
        <span className="font-mono text-sm">{id}</span>
        <span className="text-xs text-muted-foreground">chat</span>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col gap-4 p-4">
          {messages.length === 0 && (
            <p className="m-auto text-sm text-muted-foreground">
              {error ?? (sessionId ? "Ask the agent something." : "Connecting…")}
            </p>
          )}
          {messages.map((m) => (
            <div key={m.id} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
              <div
                className={cn(
                  "max-w-[80%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap",
                  m.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted"
                )}
              >
                {m.text}
              </div>
            </div>
          ))}
          {pending && (
            <div className="flex justify-start">
              <div className="flex gap-1 rounded-lg bg-muted px-3 py-3">
                {[0, 1, 2].map((i) => (
                  <span
                    key={i}
                    className="size-1.5 animate-bounce rounded-full bg-muted-foreground/60"
                    style={{ animationDelay: `${i * 0.15}s` }}
                  />
                ))}
              </div>
            </div>
          )}
          <div ref={endRef} />
        </div>
      </div>

      <div className="mx-auto w-full max-w-3xl p-4 pt-0">
        <form
          onSubmit={(e) => {
            e.preventDefault()
            send()
          }}
          className="flex gap-2"
        >
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={sessionId ? "Message the agent…" : "Connecting…"}
            disabled={!sessionId}
          />
          <Button type="submit" size="icon" disabled={!sessionId || !input.trim() || busy}>
            <Send className="size-4" />
          </Button>
        </form>
      </div>
    </div>
  )
}
