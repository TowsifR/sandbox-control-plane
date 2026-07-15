import { Link } from "react-router-dom"
import { SquareTerminal, Trash2 } from "lucide-react"

import { Button, buttonVariants } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { StatusBadge } from "@/components/StatusBadge"
import type { SandboxInfo } from "@/types"

export function SandboxTable({
  sandboxes,
  onDelete,
}: {
  sandboxes: SandboxInfo[]
  onDelete: (id: string) => void
}) {
  if (sandboxes.length === 0) {
    return (
      <div className="rounded-md border bg-card p-12 text-center text-sm text-muted-foreground">
        No sandboxes yet — create one to get started.
      </div>
    )
  }

  return (
    <div className="overflow-hidden rounded-md border bg-card">
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/40 hover:bg-muted/40">
            <TableHead>ID</TableHead>
            <TableHead>Owner</TableHead>
            <TableHead>Size</TableHead>
            <TableHead>Image</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sandboxes.map((s) => (
            <TableRow key={s.id}>
              <TableCell className="font-mono text-xs">{s.id}</TableCell>
              <TableCell>{s.owner}</TableCell>
              <TableCell>{s.size}</TableCell>
              <TableCell className="font-mono text-xs text-muted-foreground">{s.image}</TableCell>
              <TableCell>
                <StatusBadge phase={s.phase} />
              </TableCell>
              <TableCell className="text-right">
                <div className="flex justify-end gap-1">
                  {s.phase === "running" ? (
                    <Link
                      to={`/sandboxes/${s.id}/terminal`}
                      className={buttonVariants({ variant: "ghost", size: "sm" })}
                    >
                      <SquareTerminal className="mr-1 size-4" /> Terminal
                    </Link>
                  ) : (
                    <Button variant="ghost" size="sm" disabled>
                      <SquareTerminal className="mr-1 size-4" /> Terminal
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-muted-foreground hover:text-red-400"
                    onClick={() => onDelete(s.id)}
                  >
                    <Trash2 className="size-4" />
                  </Button>
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
