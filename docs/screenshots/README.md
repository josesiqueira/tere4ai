# Demo UI screenshots (paper artifacts)

The m1-/m2-/m3- files are the original milestone captures. The
light/dark pairs below were produced 2026-07-10 from the live demo UI
(Next.js on port 3111, facade on 8008, published graph
build-3b753e5e9297) with Playwright at 1440px width, light and dark via
prefers-color-scheme emulation. The assess flow uses the "hospital
triage" preset; classification runs through the real facade and the
deterministic ladder (free, no model call).

- coverage_{light,dark}.png: the M1 coverage matrix and Act structure.
- review_{light,dark}.png: the human review queue (41 flagged norms with
  span citations, pending alignment and cross-reference counts).
- assess_{light,dark}.png: the describe-system form with the preset filled.
- assess_result_{light,dark}.png: the classification card: high_risk via
  Annex III point 5, rule trace, judge verdict, calibrated status, span
  citations, and the audit export (envelope JSON download + permalink).

Regenerate: start the facade (`uvicorn tere4ai.http_facade.app:app --port
8008`) and the web app on port 3111 (`npm run dev -- -p 3111`), then script
the same captures.
