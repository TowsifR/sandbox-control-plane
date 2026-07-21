import { BrowserRouter, Route, Routes } from "react-router-dom"

import { ChatPage } from "@/pages/ChatPage"
import { SandboxesPage } from "@/pages/SandboxesPage"
import { TerminalPage } from "@/pages/TerminalPage"

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<SandboxesPage />} />
        <Route path="/sandboxes/:id/terminal" element={<TerminalPage />} />
        <Route path="/sandboxes/:id/chat" element={<ChatPage />} />
      </Routes>
    </BrowserRouter>
  )
}
