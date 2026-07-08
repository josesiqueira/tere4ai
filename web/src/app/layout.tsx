import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "TERE4AI v2, structural coverage",
  description:
    "Read-only demo: EU AI Act structural mirror, coverage matrix, and source traceability.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased min-h-screen flex flex-col font-sans`}
      >
        <header className="border-b border-border">
          <div className="container mx-auto px-3 sm:px-4 py-3 sm:py-4 flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
              <span className="text-primary font-bold text-sm">T4</span>
            </div>
            <span className="text-xl font-semibold bg-gradient-to-r from-primary to-primary/70 bg-clip-text text-transparent">
              TERE4AI v2
            </span>
            <nav className="ml-auto flex items-center gap-4 text-sm font-medium">
              <Link href="/" className="transition-colors hover:text-primary">
                Coverage
              </Link>
              <Link href="/assess" className="transition-colors hover:text-primary">
                Assess
              </Link>
            </nav>
            <span className="hidden sm:inline text-xs text-muted-foreground">
              thin read-only demo
            </span>
          </div>
        </header>
        <main id="main-content" className="flex-1">
          {children}
        </main>
        <footer className="border-t border-border">
          <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-4 sm:py-6 space-y-3">
            <p className="text-xs text-muted-foreground">
              TERE4AI provides engineering and documentation support. It does not
              certify EU AI Act compliance and does not replace legal review,
              conformity assessment, or competent-authority interpretation.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
