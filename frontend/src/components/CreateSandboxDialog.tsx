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
import type { Size } from "@/types"

// Kept in step with the Kyverno allowlist (kubernetes-iac: sandbox-policies/image-allowlist.yaml).
const IMAGES = ["busybox:1.36", "python:3.12-slim", "node:20-slim", "sandbox-opencode:dev"]

export function CreateSandboxDialog({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false)
  const [owner, setOwner] = useState("")
  const [size, setSize] = useState<Size>("small")
  const [image, setImage] = useState(IMAGES[0])
  const [ttl, setTtl] = useState(120)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      await api.create({ owner, size, image, ttl })
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
            <Input
              id="owner"
              value={owner}
              onChange={(e) => setOwner(e.target.value)}
              placeholder="alice"
              required
            />
          </div>
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
