---
name: MedResident Tutor
description: Academic source-linked study and authoring workspace
colors:
  navy: "#142d4e"
  navy-deep: "#10253f"
  ink: "#1c3049"
  muted: "#5d6d80"
  accent: "#0b7779"
  accent-hover: "#075f62"
  surface: "#fff"
  background: "#f4f6f9"
  soft: "#eaf4f3"
  line: "#d9e2ec"
  focus: "#0b7779"
  danger: "#a02836"
  danger-soft: "#fff1f2"
  success: "#176244"
  success-soft: "#edf7f2"
  warning: "#825a12"
  warning-soft: "#fff5df"
  info-soft: "#edf3fb"
  input-line: "#a8b8ca"
  nav-hover: "#223e60"
  nav-current: "#254969"
  nav-outline: "#45647e"
  nav-text: "#d5e0ec"
  nav-muted: "#b5cadf"
  badge-neutral: "#edf0f5"
typography:
  display:
    fontFamily: '"Source Sans 3", "Segoe UI", Arial, sans-serif'
    fontSize: "2.6rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  headline:
    fontFamily: '"Source Sans 3", "Segoe UI", Arial, sans-serif'
    fontSize: "1.9rem"
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: "-0.02em"
  title:
    fontFamily: '"Source Sans 3", "Segoe UI", Arial, sans-serif'
    fontSize: "1.35rem"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "-0.02em"
  body:
    fontFamily: '"Segoe UI", Arial, sans-serif'
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: '"Segoe UI", Arial, sans-serif'
    fontSize: "0.875rem"
    fontWeight: 600
    lineHeight: 1.6
rounded:
  badge: "5px"
  control: "7px"
  message: "8px"
  popover: "10px"
  panel: "12px"
spacing:
  compact: "8px"
  control-gap: "10px"
  inline: "12px"
  small: "16px"
  row: "20px"
  section: "24px"
  panel: "26px"
  layout: "28px"
  feature: "32px"
  gutter: "36px"
components:
  button-primary:
    backgroundColor: "{colors.navy}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "10px 18px"
  button-primary-hover:
    backgroundColor: "{colors.navy-deep}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.navy}"
    rounded: "{rounded.control}"
    padding: "10px 18px"
  button-text:
    backgroundColor: "transparent"
    textColor: "{colors.accent}"
    rounded: "{rounded.control}"
    padding: "8px 4px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "11px 12px"
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "26px"
  badge:
    backgroundColor: "{colors.badge-neutral}"
    textColor: "{colors.muted}"
    rounded: "{rounded.badge}"
    padding: "4px 10px"
  nav-current:
    backgroundColor: "{colors.nav-current}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "10px 12px"
---

# Design System: MedResident Tutor

## Overview

**Creative North Star: "Academic source-linked workspace"**

The pinned academic direction uses navy navigation, teal links, white working surfaces and a cool ground. Its character comes from clear Vietnamese type, purposeful SVG icons, ruled data lists and source-aware reading. This name describes the implemented direction; it is not a separate brand proposal.

Operate mode supports choosing, answering, reviewing and authoring. Read mode gives source content a comfortable measure and preserves its structure. The shipped implementation is the authority: `apps/frontend/app/ui-theme.css` loads after `globals.css`, whose unoverridden reading and form rules still apply. This record replaces the former green/teal horizontal-navigation system under the user's explicit redesign brief.

**Key Characteristics:**

- Academic navy shell with restrained teal interaction cues.
- Flat, bordered work surfaces and ruled lists rather than uniform card grids.
- Distinct student and content-administration navigation.
- Readable sources, explicit execution labels and visible recovery states.

## Colors

The frontmatter preserves exact reused CSS values; names follow the shipped custom properties and recurring component roles. Sidecar tonal ramps are synthesized OKLCH preview strips, not additional shipped color tokens.

### Primary

**Academic Navy** (`navy`, `navy-deep`) carries sidebar, headings, primary actions and their hover state.

### Secondary

**Source Teal** (`accent`, `accent-hover`, `soft`, `focus`) carries links, selected tabs, checked controls, reading notices and keyboard focus. Focus intentionally shares the accent value.

### Tertiary

**Semantic state pairs** (`success`, `warning`, `danger` and soft grounds) express saved, attention and failure states. `info-soft` supports informative notices and secondary-action hover. Retain explanatory text or icons.

### Neutral

Reading Ink and Muted Ink support content and metadata. White, Cool Ground and Rule (`surface`, `background`, `line`) separate content and page ground. Navigation tones supply pale text, hover/current surfaces and an inset outline. Input Rule and Neutral Badge provide quiet boundaries and metadata.

**The Action Hierarchy Rule.** Navy carries the primary task; teal identifies links, focus and selection. Use semantic colors for status, with a written explanation.

## Typography

**Display Font:** Source Sans 3, with Segoe UI and Arial fallbacks, for all headings and the wordmark.

**Body Font:** Segoe UI, Arial, sans-serif. Controls inherit this stack.

**Character:** A sourced sans heading voice and compact body text support Vietnamese study sessions. The self-hosted upright variable font supports weights 200–900 and uses `font-display: swap`; no remote font request is needed.

### Hierarchy

- **Display:** public introduction; becomes 2rem below 600px.
- **Headline:** shared page heading; becomes 1.55rem below 600px. Its 1.15 line height survives from the base stylesheet.
- **Title:** section headings; becomes 1.2rem below 600px. Subsections use 1.1rem; question rows use 1.05rem.
- **Body:** normal UI copy uses the body role. Source prose uses line height 1.85, a maximum 75ch measure and pre-wrapping.
- **Label:** filters and compact controls use the label role; general form labels inherit body size at weight 600. Helpers use 0.875rem regular; badges use 0.8rem at weight 600.
- **Score:** tabular figures; result total is 2.25rem, weight 700, line height 1.2, reduced to 2rem below 600px.

Font source, pinned Adobe commit, byte counts, SHA-256 hashes and OFL 1.1 license are recorded in `apps/frontend/public/fonts/sources.json` and `LICENSE-Source-Sans-3.md`.

## Layout

The desktop shell has a sticky 232px sidebar and an 80px account header. General content caps at 1120px with 36px side gutters and 36px/48px vertical margins. Admin authoring may expand to 1320px with 32px gutters. Auth caps at 1100px with a 460px form column. Ordinary cards cap at 760px unless explicitly wide.

Spacing entries are recurring observed values, not a mathematical scale or CSS variables. Main work columns use 24px or 28px gaps. Prose caps at 75ch; supporting page copy caps at 65ch.

- **At 1150px and below:** exercise and authoring columns stack; answer/source panels lose sticky positioning; authoring uses question/source tabs; upload sections stack.
- **At 900px and below:** sidebar becomes a modal navigation drawer, header becomes 72px, gutters become 24px, dashboard stacks and auth context copy is hidden.
- **At 600px and below:** gutters become 16px, panel padding becomes 20px, headings/actions and results stack, admin tables become labelled rows. Statistics remain two columns.
- Specialized inherited reading/structured-choice adjustments at 820px and 560px remain in `globals.css`.

**The Task Surface Rule.** Use lists or tables for collections, prose for reading and adjacent source/editing regions for authoring. Select the surface according to the task.

## Elevation & Depth

Panels and result lists are flat, with thin rules and no resting or hover shadow. The account popover is the floating exception: `0 8px 30px #10253f24`. Modal navigation and zoom use translucent navy backdrops. Current navigation uses an inset one-pixel outline.

Content arrival fades opacity .96 to 1 over .18s with `cubic-bezier(.16,1,.3,1)` only when reduced motion is not requested. Buttons use .15s background/border transitions. Source chevrons rotate with native open state without an added animation.

## Shapes

Badges are lightly rounded rectangles; controls use gentle corners and panels the largest shared radius. Account avatars are circular. Borders are normally one pixel; invalid controls use a two-pixel danger border. Focus uses a three-pixel outline with a three-pixel offset, white inside dark navigation. Clinical images preserve aspect ratio in a clipped dark canvas.

## Components

### Buttons

Primary, secondary, text and icon buttons share a minimum 44px hit height and weight 600. Secondary buttons have a rule-colored border, informational hover ground and darker hover border. Text/icon controls use transparent grounds with soft hover fills. Disabled opacity is .5 with a not-allowed cursor; busy labels explain processing.

### Inputs / Fields

Fields have white grounds, input-rule borders and the control shape. Inputs/selects have a minimum 46px height. Keep visible labels, associated helpers and `aria-invalid` error text. Checkbox/radio controls remain native and teal. Auth validation focuses confirmation when passwords mismatch.

### Chips / Status

`Badge` supplies neutral, info, success, warning and danger metadata variants. Topic filters remain buttons with `aria-pressed`. Content tabs expose `aria-current` or `aria-selected`, a teal bottom rule and soft hover ground.

### Cards / Containers

Shared bordered panels group coherent tasks. Data/result lists use separators rather than nested cards. Table headers use the page ground and compact muted type; mobile admin cells retain `data-label` labels.

### Navigation

`AppShell` separates learning from content administration. Current sidebar links use a navy-blue fill and inset border; supplementary resources form a separate group. Account uses native `details`; mobile navigation uses a native modal `dialog` with close/Escape behavior. Preserve the first-focus skip link and main-content target.

### Evidence and results

`PracticeResult` presents saved total, stage state, criteria, stored feedback, reference answer and sources. Source disclosures use visible right/down CSS chevrons; structured-result sources retain native markers. Human-readable evidence labels are presentation only: original IDs, titles, contents, pages and provenance stay stored unchanged. Structured scoring and mock Medical/Teaching results retain distinct explanations. Image zoom preserves attribution, licensing and annotation coordinates.

### Loading / Empty / Error / Saved

Reuse `Loading`, `EmptyState` and `Alert` with actionable next steps. Loading placeholders are static; errors use alerts and shared notices use status announcements. Keep valid partial results and failed-request drafts visible; feedback retry is explicit. Never represent an empty response as fabricated activity.

## Do's and Don'ts

### Do:

- **Do** reuse the navy action hierarchy, teal selection and visible keyboard focus.
- **Do** keep source text, page locators, image attribution and saved-result identity accessible.
- **Do** distinguish mock, replay and authored-answer scoring in plain Vietnamese.
- **Do** retain errors, partial results and unsaved work with a clear recovery action.

### Don't:

- **Don't** turn reading completion or simulated scores into medical mastery claims.
- **Don't** label app publication as medical expert approval without evidence.
- **Don't** expose provider debugging, raw JSON or generated technical IDs as student titles.
- **Don't** replace source evidence with generated images or copy institutional branding.
- **Don't** add controls for unavailable backend capabilities.

Not canonized: inherited `.eyebrow` styling is compatibility code, not a reusable invitation to add kickers; former green palette/horizontal navigation rules are superseded. Specialized legacy selectors remain implementation detail rather than new system tokens.
