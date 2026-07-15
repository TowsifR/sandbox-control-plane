import { BrowserRouter, Route, Routes } from "react-router-dom"

import { SandboxesPage } from "@/pages/SandboxesPage"
import { TerminalPage } from "@/pages/TerminalPage"

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<SandboxesPage />} />
        <Route path="/sandboxes/:id/terminal" element={<TerminalPage />} />
      </Routes>
    </BrowserRouter>
  )
}
