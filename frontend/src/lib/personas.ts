// The persona catalog — kept in step with the platform's Composition `_personas` + XRD enum (kubernetes-iac).
import type { Persona } from "@/types"

export interface PersonaInfo {
  id: Persona
  emoji: string
  blurb: string
  caps: { edit: boolean; bash: boolean } // the enforced guardrail — mirrors the OpenCode permissions
}

export const PERSONAS: PersonaInfo[] = [
  { id: "builder", emoji: "🔨", blurb: "Writes and runs code", caps: { edit: true, bash: true } },
  {
    id: "architect",
    emoji: "📐",
    blurb: "Designs systems (read-only, diagrams)",
    caps: { edit: false, bash: false },
  },
]

export const personaById = (id: string): PersonaInfo | undefined =>
  PERSONAS.find((p) => p.id === id)
