import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { NavLinks } from "./nav-links";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "TERE4AI v2, structural coverage",
  description:
    "Read-only demo: EU AI Act structural mirror, coverage matrix, and source traceability.",
};

function LogoMark({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
        <span className="text-primary font-bold text-sm">T4</span>
      </div>
      <span
        className={
          (compact ? "text-lg" : "text-xl") +
          " font-semibold bg-gradient-to-r from-primary to-primary/70 bg-clip-text text-transparent"
        }
      >
        TERE4AI v2
      </span>
    </div>
  );
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased min-h-screen flex flex-col md:flex-row font-sans`}
      >
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:border focus:border-border focus:bg-background focus:px-3 focus:py-2 focus:text-sm focus:font-medium"
        >
          Skip to content
        </a>

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
      </body>
    </html>
  );
}
