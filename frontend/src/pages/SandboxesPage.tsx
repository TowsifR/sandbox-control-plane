import { useCallback, useEffect, useState } from "react"

import { CreateSandboxDialog } from "@/components/CreateSandboxDialog"
import { SandboxTable } from "@/components/SandboxTable"
import { api } from "@/lib/api"
import type { SandboxInfo } from "@/types"

export function SandboxesPage() {
  const [sandboxes, setSandboxes] = useState<SandboxInfo[]>([])

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

  return (
    <div className="min-h-svh">
      <header className="border-b">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-6">
          <span className="font-mono font-semibold">sandbox-control-plane</span>
          <CreateSandboxDialog onCreated={refresh} />
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-6 py-8">
        <div className="mb-5">
          <h1 className="text-lg font-semibold">Sandboxes</h1>
          <p className="text-sm text-muted-foreground">
            Provision and manage ephemeral agent sandboxes.
          </p>
        </div>
        <SandboxTable sandboxes={sandboxes} onDelete={remove} />
      </main>
    </div>
  )
}
