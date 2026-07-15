import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

const STYLES: Record<string, string> = {
  running: "text-emerald-400 border-emerald-400/30 bg-emerald-400/10",
  provisioning: "text-amber-400 border-amber-400/30 bg-amber-400/10",
  deleting: "text-zinc-400 border-zinc-400/30 bg-zinc-400/10",
  deleted: "text-zinc-500 border-zinc-500/30 bg-zinc-500/10",
  error: "text-red-400 border-red-400/30 bg-red-400/10",
  unknown: "text-zinc-500 border-zinc-500/30 bg-zinc-500/10",
}

export function StatusBadge({ phase }: { phase: string }) {
  return (
    <Badge variant="outline" className={cn("font-mono text-xs", STYLES[phase] ?? STYLES.unknown)}>
      {phase}
    </Badge>
  )
}
