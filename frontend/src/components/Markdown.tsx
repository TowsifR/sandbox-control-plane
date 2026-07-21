import { useEffect, useRef, useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { Download } from "lucide-react"

// Renders a ```mermaid block as an SVG. mermaid is imported lazily (~500KB) so it loads only once a diagram
// appears; securityLevel "strict" blocks scripts/HTML in the agent-generated source, and a bad diagram falls back to its text.
function Mermaid({ chart }: { chart: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const [svg, setSvg] = useState<string>() // set only on a successful render; gates the download button
  useEffect(() => {
    let alive = true
    void import("mermaid").then(async ({ default: mermaid }) => {
      mermaid.initialize({ startOnLoad: false, theme: "dark", securityLevel: "strict" })
      const id = "m" + Math.random().toString(36).slice(2)
      try {
        const { svg } = await mermaid.render(id, chart)
        if (alive && ref.current) {
          ref.current.innerHTML = svg
          setSvg(svg)
        }
      } catch {
        if (alive && ref.current) ref.current.textContent = chart
      }
    })
    return () => {
      alive = false
    }
  }, [chart])

  // Save the diagram to disk — the sandbox is ephemeral, so this is how a design outlives it.
  function download() {
    if (!svg) return
    const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }))
    const a = document.createElement("a")
    a.href = url
    a.download = "diagram.svg"
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="group relative my-2">
      <div ref={ref} className="flex justify-center [&_svg]:max-w-full" />
      {svg && (
        <button
          type="button"
          onClick={download}
          title="Download SVG"
          className="absolute right-1 top-1 rounded p-1 text-muted-foreground opacity-0 transition hover:text-foreground group-hover:opacity-100"
        >
          <Download className="size-4" />
        </button>
      )}
    </div>
  )
}

// Markdown for assistant replies: real headings/lists/tables/code, plus rendered mermaid diagrams. The
// long class list styles the rendered children (no typography plugin in this project).
export function Markdown({ children }: { children: string }) {
  return (
    <div className="text-sm leading-relaxed [&_a]:underline [&_h1]:mt-3 [&_h1]:mb-1 [&_h1]:text-base [&_h1]:font-semibold [&_h2]:mt-3 [&_h2]:mb-1 [&_h2]:font-semibold [&_h3]:mt-2 [&_h3]:font-semibold [&_ol]:my-1.5 [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:my-1.5 [&_pre]:my-2 [&_pre]:overflow-x-auto [&_pre]:rounded-md [&_pre]:bg-background [&_pre]:p-2.5 [&_pre]:text-xs [&_table]:my-2 [&_table]:block [&_table]:overflow-x-auto [&_td]:border [&_td]:border-border [&_td]:px-2 [&_td]:py-1 [&_th]:border [&_th]:border-border [&_th]:px-2 [&_th]:py-1 [&_ul]:my-1.5 [&_ul]:list-disc [&_ul]:pl-5 [&_code]:font-mono">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ className, children, ...props }) {
            const lang = /language-(\w+)/.exec(className || "")?.[1]
            if (lang === "mermaid") return <Mermaid chart={String(children).trim()} />
            return (
              <code className={className} {...props}>
                {children}
              </code>
            )
          },
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  )
}
