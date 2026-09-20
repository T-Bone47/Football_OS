import { useCallback, useEffect, useState } from "react";
import Sidebar from "@/components/Sidebar";
import CommandPalette from "@/components/CommandPalette";

export default function AppShell({ children }) {
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  useEffect(() => { const onKey = (event) => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); setOpen(true); } }; window.addEventListener("keydown", onKey); return () => window.removeEventListener("keydown", onKey); }, []);
  return <div className="app-shell" data-testid="application-shell"><Sidebar /><main className="workspace"><div className="global-command-bar"><button className="global-command-button" onClick={() => setOpen(true)} data-testid="global-command-button"><span>Search players, clubs, matches, actions</span><kbd>⌘ K</kbd></button></div>{children}</main><CommandPalette open={open} onClose={close} /></div>;
}