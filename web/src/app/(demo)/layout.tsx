import Link from "next/link";
import { NavLinks } from "../nav-links";

/* The demo shell: left sidebar on desktop, top bar on mobile. Wraps every
   demo page (coverage, assess, agent, how-it-works, review); the landing
   page at / lives outside this group and is full-bleed. The logo links back
   to the landing. */

function LogoMark({ compact = false }: { compact?: boolean }) {
  return (
    <Link href="/" className="flex items-center gap-3">
      <div className="w-8 h-8 rounded-sm bg-primary/10 flex items-center justify-center shrink-0">
        <span className="text-primary font-semibold text-sm">T4</span>
      </div>
      <span
        className={(compact ? "text-lg" : "text-xl") + " font-semibold text-foreground"}
      >
        TERE4AI v2
      </span>
    </Link>
  );
}

export default function DemoLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col md:flex-row">
      <aside className="hidden md:flex md:w-64 md:shrink-0 md:flex-col bg-sidebar text-sidebar-foreground border-r border-sidebar-border">
        <div className="px-4 py-4">
          <LogoMark />
        </div>
        <NavLinks />
        <footer className="mt-auto px-4 py-4 text-xs text-muted-foreground space-y-3">
          <p>thin read-only demo</p>
          <p>
            TERE4AI provides engineering and documentation support. It does not
            certify EU AI Act compliance and does not replace legal review,
            conformity assessment, or competent-authority interpretation.
          </p>
        </footer>
      </aside>

      <div className="md:hidden border-b border-sidebar-border bg-sidebar text-sidebar-foreground">
        <div className="px-4 py-3">
          <LogoMark compact />
        </div>
        <NavLinks />
        <p className="border-t border-sidebar-border px-4 py-2 text-xs text-muted-foreground">
          Engineering support, not legal advice or certification.
        </p>
      </div>

      <main id="main-content" className="flex-1 min-w-0">
        {children}
      </main>

      <footer className="md:hidden border-t border-border px-4 py-4 text-xs text-muted-foreground">
        <p>
          TERE4AI provides engineering and documentation support. It does not
          certify EU AI Act compliance and does not replace legal review,
          conformity assessment, or competent-authority interpretation.
        </p>
      </footer>
    </div>
  );
}
