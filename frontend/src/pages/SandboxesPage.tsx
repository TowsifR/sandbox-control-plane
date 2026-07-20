import { useCallback, useEffect, useState } from "react"
import { Plus } from "lucide-react"

import { CreateSandboxDialog } from "@/components/CreateSandboxDialog"
import { SandboxTable } from "@/components/SandboxTable"
import { Button } from "@/components/ui/button"
import { api } from "@/lib/api"
import { PERSONAS } from "@/lib/personas"
import { cn } from "@/lib/utils"
import type { Persona, SandboxInfo } from "@/types"

export function SandboxesPage() {
  const [sandboxes, setSandboxes] = useState<SandboxInfo[]>([])
  const [dialogOpen, setDialogOpen] = useState(false)
  const [preset, setPreset] = useState<Persona | undefined>()

  const refresh = useCallback(() => {
    api.list().then(setSandboxes).catch(() => {})
  }, [])

  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 3000)
    return () => clearInterval(t)
  }, [refresh])

  async function remove(id: string) {
    await api.remove(id).catch(() => {})
    refresh()
  }

  function openDialog(persona?: Persona) {
    setPreset(persona)
    setDialogOpen(true)
  }

  return (
    <div className="min-h-svh">
      <header className="border-b">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-6">
          <span className="font-mono font-semibold">sandbox-control-plane</span>
          <Button size="sm" onClick={() => openDialog()}>
            <Plus className="mr-1 size-4" /> New Sandbox
          </Button>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-6 py-8">
        <div className="mb-5">
          <h1 className="text-lg font-semibold">Sandboxes</h1>
          <p className="text-sm text-muted-foreground">
            Provision and manage ephemeral agent sandboxes.
          </p>
        </div>

        <section className="mb-8">
          <h2 className="mb-2 text-sm font-medium text-muted-foreground">Start from a persona</h2>
          <div className="grid gap-3 sm:max-w-2xl sm:grid-cols-2">
            {PERSONAS.map((p) => (
              <button
                key={p.id}
                onClick={() => openDialog(p.id)}
                className="rounded-lg border bg-card p-4 text-left transition-colors hover:border-ring hover:bg-muted/40"
              >
                <div className="flex items-center gap-2 font-medium">
                  <span className="text-lg">{p.emoji}</span>
                  {p.id}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">{p.blurb}</p>
                <div className="mt-3 flex gap-1.5 text-[0.7rem]">
                  <Cap label="edit" on={p.caps.edit} />
                  <Cap label="bash" on={p.caps.bash} />
                </div>
              </button>
            ))}
          </div>
        </section>

        <h2 className="mb-2 text-sm font-medium text-muted-foreground">Your sandboxes</h2>
        <SandboxTable sandboxes={sandboxes} onDelete={remove} />
      </main>

      <CreateSandboxDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        presetPersona={preset}
        onCreated={refresh}
      />
    </div>
  )
}

// A capability of the persona's enforced guardrail, rendered as a badge.
function Cap({ label, on }: { label: string; on: boolean }) {
  return (
    <span
      className={cn(
        "rounded px-1.5 py-0.5 font-mono",
        on
          ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
          : "bg-muted text-muted-foreground"
      )}
    >
      {label} {on ? "✓" : "✗"}
    </span>
  )
}
