# Frontend baseline — 2026-11-05

Captured from source before refinement; screenshots before changes were not captured. No measured pre-change visual/accessibility score is claimed.

Scope: dashboard, curriculum/library/sources, self-study exams, AI simulation, progress, authentication and admin documents/questions. Stack: Next.js 16.2, React 19.2, TypeScript, App Router, plain global CSS; no external UI library. Existing centralized bearer-token client handles errors/401 and per-account draft storage. Exams and reader already warn for unsaved changes. Existing Playwright suites cover practice/client, retry, bank and study. No standalone frontend unit runner.

Git was already dirty across backend/frontend/docs/data. Existing files were read and changed incrementally; no reset, commit or push. Backend/data work is untouched.

| ID | Priority | Confirmed source issue | Remedy |
|---|---|---|---|
| F1 | P1 | Admin question/rubric edits replaced or abandoned without warning | Dirty-state guard for open/new/navigation/unload |
| F2 | P2 | Navigation has no current-page indication or skip link | aria-current, underline, keyboard skip target |
| F3 | P2 | Input/textarea lack authored focus state; button contrast can be strengthened | Shared focus and darker accent (existing contrast already passes AA) |
| F4 | P2 | Dashboard/progress show empty guidance before data resolves | Separate loading and empty output |
| F5 | P2 | Admin document screen uses English and lacks result announcements | Vietnamese labels, alert/status |
| F6 | P2 | Password mismatch leaves focus on submit without recovery | Focus confirmation field |
| F7 | P2 | Simulation reset clears a nonempty answer without confirmation | Confirm before reset |
| F8 | P2 | Each rubric criterion repeats full evidence content | Disclose content/metadata with details, retain selectors and preview |

Impeccable engine 0.1.18, skill 4.8.0 installed project-wide with no hooks. Init/document adapted from explicit supplied brief; critique/audit used source evidence and two independent agent reviews. Applied harden/adapt/polish playbooks. No Live mode.

Detector baseline: 3 source aesthetic warnings (side-tab borders), not 3 functional defects. Quotation/citation borders have legitimate semantic grouping purposes; do not treat these as WCAG failures. Independent source-only critique: 24/40 provisional Nielsen score, not a measured visual score. Audit before: a11y 2, performance 3, theming 2, responsive 2, integrity 2 (11/20, reviewer judgment only).