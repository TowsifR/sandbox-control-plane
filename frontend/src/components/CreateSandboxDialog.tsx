import { type FormEvent, useState } from "react"
import { Plus } from "lucide-react"

import { Button, buttonVariants } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { api } from "@/lib/api"
import { PERSONAS, personaById } from "@/lib/personas"
import { cn } from "@/lib/utils"
import type { Persona, Size } from "@/types"

// Kept in step with the Kyverno allowlist (kubernetes-iac: sandbox-policies/image-allowlist.yaml).
const IMAGES = ["busybox:1.36", "python:3.12-slim", "node:20-slim", "sandbox-opencode:dev"]

type Mode = "persona" | "image"

export function CreateSandboxDialog({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState<Mode>("persona") // the flagship path; image is one click away
  const [owner, setOwner] = useState("")
  const [size, setSize] = useState<Size>("small")
  const [persona, setPersona] = useState<Persona>("builder")
  const [image, setImage] = useState(IMAGES[0])
  const [ttl, setTtl] = useState(120)
  const [busy, setBusy] = useState(false)

  const caps = personaById(persona)?.caps

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      // Send exactly one of persona/image — the platform uses whichever is present.
      await api.create({ owner, size, ttl, ...(mode === "persona" ? { persona } : { image }) })
      setOpen(false)
      setOwner("")
      onCreated()
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger className={buttonVariants({ size: "sm" })}>
        <Plus className="mr-1 size-4" /> New Sandbox
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New sandbox</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="owner">Owner</Label>
            <Input id="owner" value={owner} onChange={(e) => setOwner(e.target.value)} required />
          </div>

          <div className="grid grid-cols-2 gap-1 rounded-lg bg-muted p-1 text-sm">
            {(["persona", "image"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                className={cn(
                  "rounded-md py-1 font-medium capitalize transition-colors",
                  mode === m ? "bg-background shadow-sm" : "text-muted-foreground hover:text-foreground"
                )}
              >
                {m}
              </button>
            ))}
          </div>

          {mode === "persona" ? (
            <div className="space-y-2">
              <Label>Persona</Label>
              <Select value={persona} onValueChange={(v) => v && setPersona(v as Persona)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PERSONAS.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.emoji} {p.id}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {caps && (
                <p className="text-xs text-muted-foreground">
                  {personaById(persona)?.blurb} · edit {caps.edit ? "✓" : "✗"} · bash{" "}
                  {caps.bash ? "✓" : "✗"}
                </p>
              )}
            </div>
          ) : (
            <div className="space-y-2">
              <Label>Image</Label>
              <Select value={image} onValueChange={(v) => v && setImage(v)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {IMAGES.map((i) => (
                    <SelectItem key={i} value={i} className="font-mono">
                      {i}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="space-y-2">
            <Label>Size</Label>
            <Select value={size} onValueChange={(v) => v && setSize(v as Size)}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="small">small</SelectItem>
                <SelectItem value="medium">medium</SelectItem>
                <SelectItem value="large">large</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="ttl">TTL (seconds)</Label>
            <Input
              id="ttl"
              type="number"
              min={10}
              value={ttl}
              onChange={(e) => setTtl(Number(e.target.value))}
            />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={busy || !owner}>
              {busy ? "Creating…" : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
