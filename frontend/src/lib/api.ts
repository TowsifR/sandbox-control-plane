import type { SandboxInfo, SandboxRequest } from "@/types"

const BASE = "/api"

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return (await res.json()) as T
}

export const api = {
  list: () => fetch(`${BASE}/sandboxes`).then((r) => json<SandboxInfo[]>(r)),

  get: (id: string) => fetch(`${BASE}/sandboxes/${id}`).then((r) => json<SandboxInfo>(r)),

  create: (body: SandboxRequest) =>
    fetch(`${BASE}/sandboxes`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => json<SandboxInfo>(r)),

  remove: async (id: string) => {
    const r = await fetch(`${BASE}/sandboxes/${id}`, { method: "DELETE" })
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
  },
}
