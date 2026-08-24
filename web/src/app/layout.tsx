import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "TERE4AI: the EU AI Act as a knowledge graph coding agents can call",
  description:
    "Open-source MCP server: deterministic EU AI Act risk classification, requirements traced to byte-exact legal text, judged HLEG alignments, and requirement-to-code traceability.",
};

/* Root layout carries only the document shell and fonts. The demo pages
   (coverage, assess, agent, how-it-works, review) get the sidebar shell from
   the (demo) route-group layout; the landing page at / is full-bleed. */
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased font-sans`}>
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:border focus:border-border focus:bg-background focus:px-3 focus:py-2 focus:text-sm focus:font-medium"
        >
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}
