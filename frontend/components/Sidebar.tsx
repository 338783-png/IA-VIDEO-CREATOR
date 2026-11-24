"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/", label: "Accueil", icon: "⌂" },
  { href: "/new", label: "Nouveau projet", icon: "+" },
  { href: "/library", label: "Bibliothèque", icon: "▤" },
  { href: "/references", label: "Références", icon: "◎" },
  { href: "/characters", label: "Personnages", icon: "☺" },
  { href: "/storyboard", label: "Storyboard", icon: "▦" },
  { href: "/editor", label: "Éditeur", icon: "✂" },
  { href: "/exports", label: "Exportations", icon: "⇩" },
];

export default function Sidebar() {
  const path = usePathname();
  const active = (href: string) =>
    href === "/" ? path === "/" : path.startsWith(href) || (href === "/editor" && path.startsWith("/projects")) || (href === "/references" && path.startsWith("/styles"));
  return (
    <aside className="border-b border-border bg-surface lg:sticky lg:top-0 lg:h-screen lg:w-60 lg:shrink-0 lg:border-b-0 lg:border-r">
      <Link href="/" className="flex items-center gap-3 px-4 py-4">
        <span className="grid h-10 w-10 place-items-center rounded-xl bg-accent text-sm font-black text-white">AI</span>
        <span className="leading-tight">
          <span className="block font-bold">AI VIDEO EDITOR</span>
          <span className="block text-xs text-muted">PROF IA</span>
        </span>
      </Link>
      <nav aria-label="Navigation principale" className="flex gap-1 overflow-x-auto px-2 pb-2 lg:flex-col lg:overflow-visible lg:px-3">
        {NAV.map((n) => (
          <Link key={n.href} href={n.href}
            className={`flex shrink-0 items-center gap-3 rounded-lg px-3 py-2 text-sm transition ${active(n.href) ? "bg-accent text-white" : "text-muted hover:bg-surface-2 hover:text-foreground"}`}>
            <span aria-hidden className="w-4 text-center">{n.icon}</span>{n.label}
          </Link>
        ))}
      </nav>
      <p className="hidden px-5 pt-6 text-[11px] leading-relaxed text-muted lg:block">
        Traitement 100 % local.<br />Aucune publication automatique.
      </p>
    </aside>
  );
}
