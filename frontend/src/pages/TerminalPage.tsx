import { useEffect, useRef } from "react"
import { Link, useParams } from "react-router-dom"
import { ChevronLeft } from "lucide-react"
import { Terminal } from "@xterm/xterm"
import { FitAddon } from "@xterm/addon-fit"
import "@xterm/xterm/css/xterm.css"

export function TerminalPage() {
  const { id } = useParams()
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!ref.current) return
    const term = new Terminal({
      fontFamily: "'Geist Mono Variable', ui-monospace, monospace",
      fontSize: 13,
      cursorBlink: true,
      theme: { background: "#09090b", foreground: "#e4e4e7" },
    })
    const fit = new FitAddon()
    term.loadAddon(fit)
    term.open(ref.current)
    fit.fit()

    const proto = location.protocol === "https:" ? "wss" : "ws"
    const ws = new WebSocket(`${proto}://${location.host}/api/sandboxes/${id}/terminal`)
    ws.binaryType = "arraybuffer"
    ws.onopen = () => term.writeln("\x1b[90m— connected —\x1b[0m")
    ws.onmessage = (e) =>
      term.write(typeof e.data === "string" ? e.data : new Uint8Array(e.data as ArrayBuffer))
    ws.onerror = () => term.writeln("\r\n\x1b[31m— connection error —\x1b[0m")
    ws.onclose = () => term.writeln("\r\n\x1b[90m— disconnected —\x1b[0m")
    term.onData((d) => ws.readyState === WebSocket.OPEN && ws.send(d))

    const onResize = () => fit.fit()
    window.addEventListener("resize", onResize)
    return () => {
      window.removeEventListener("resize", onResize)
      ws.close()
      term.dispose()
    }
  }, [id])

  return (
    <div className="flex h-svh flex-col">
      <header className="flex h-12 shrink-0 items-center gap-2 border-b px-4">
        <Link to="/" className="text-muted-foreground hover:text-foreground">
          <ChevronLeft className="size-4" />
        </Link>
        <span className="font-mono text-sm">{id}</span>
        <span className="text-xs text-muted-foreground">terminal</span>
      </header>
      <div ref={ref} className="min-h-0 flex-1 bg-[#09090b] p-2" />
    </div>
  )
}
