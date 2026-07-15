// Mirrors the backend Pydantic models (sandbox_control_plane/sandboxes/models.py).

export type Size = "small" | "medium" | "large"

export type Phase = "provisioning" | "running" | "deleting" | "deleted" | "unknown"

export interface SandboxInfo {
  id: string
  owner: string
  size: string
  image: string
  phase: string
  namespace: string | null
}

export interface SandboxRequest {
  owner: string
  size: Size
  image: string
  ttl: number // seconds
}
