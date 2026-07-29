"use client";

/* Sidebar navigation with active-route highlighting. Read-only demo shell. */

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BookOpenCheck,
  ClipboardList,
  Bot,
  Workflow,
  UserCheck,
} from "lucide-react";

const ITEMS = [
  { href: "/", label: "Coverage", icon: BookOpenCheck },
  { href: "/assess", label: "Assess", icon: ClipboardList },
  { href: "/agent", label: "Agent", icon: Bot },
  { href: "/how-it-works", label: "How it works", icon: Workflow },
  { href: "/review", label: "Review", icon: UserCheck },
];

export function NavLinks() {
  const pathname = usePathname();
  return (
    <nav
      aria-label="Main"
      className="flex flex-row gap-1 overflow-x-auto px-2 pb-1 md:flex-col md:overflow-visible md:pb-0"
    >
      {ITEMS.map(({ href, label, icon: Icon }) => {
        const active =
          href === "/" ? pathname === "/" : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={
              "flex shrink-0 items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors " +
              (active
                ? "bg-sidebar-accent text-sidebar-accent-foreground"
                : "text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground")
            }
          >
            <Icon className="h-4 w-4" aria-hidden="true" />
            <span>{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
