disposition: fix

No approved comp or separate QUALITY BAR card: intentionally code-led under the pinned academic brief. DESIGN.md and design-system.md await the required documenter handoff. Source sampling is limited to the provided primary frontend files and evidence; no browser or model was run for this review.

## persistence

Fail pending the already-planned documentation handoff: PRODUCT.md exists, but DESIGN.md still describes the former green/teal palette, horizontal navigation, and previous layout; docs/ui/design-system.md does not exist despite the completion report linking it. This is outstanding delivery work, not an unapproved design change. PRODUCT.md's old backend constraint is superseded by the supplied latest user request allowing small API additions.

Code-led status makes comp-phase state, approved-comp records, and comp-diff reports inapplicable. FORM's seed:8890582f24906581 is corroborated by .impeccable/questions/roll.json and its persisted seed record; the contract contains the public reference rather than the raw key.

Evidence passes: desktop.png, mobile.png, tablet.png, all 34 named after captures, and all six contact sheets exist and decode. Widths are 1440, 390, or 768 as named; full-page captures include document tops. The galleries show the intended route contents without blank render regions. The history captures show a loaded saved attempt. No second detector pass was run; the supplied detector result is []. Browser assertion and idempotency records report passing disposable-database checks with zero model requests and zero main-database writes. This review does not independently re-run those checks or certify medical content.

## fidelity

| Element or promise | State | Evidence |
| --- | --- | --- |
| TYPE | contradicted | apps/frontend/app/ui-theme.css:2 makes the headings and own-product wordmark inherit Segoe UI/Arial. Hierarchy and Vietnamese legibility are present, but the craft floor explicitly refuses a platform sans as an own-world display voice. The user pins academic sans typography, not these system faces. |
| MATERIAL | match | Deliberately flat, bordered document and task surfaces match the academic operating workspace. Clinical raster imagery remains visible, proportionate, and attributed; no simulated physical material or decorative medical illustration is used. |
| GROUND | match | ui-theme.css:1 supplies white surfaces, cool gray-blue #f4f6f9 ground, navy #142d4e, and teal #0b7779. These are visible in the captures and match OWN-WORLD's named color families; no exact comp color was promised. |
| THESIS | match | Student catalog, saved history, library, and admin workspace are separate, visible destinations. Captures show task-oriented lists and forms. |
| OWN-WORLD | match except TYPE above | Navy navigation and primary actions, teal links, source-centered content, and lists/tables follow the pinned academic identity. No university branding is borrowed. |
| STORY | contradicted in source naming | The learning/result and authoring paths are visible, but StructuredResult.tsx:21 prints raw evidence titles. after-student-structured-result-390.png and -768.png expose “Evidence for CLINICAL_DEMO_V2_CASE01_SU01/SU02” as source labels, contrary to the user's plain Vietnamese, nontechnical student flow. PracticeResult.tsx:40 has the same direct-title rendering path. |
| FIRST VIEWPORT | match | 232px desktop navigation, account header, one clear initial learning action, real zero-history state, and a compact mobile header are visible. The first viewport reads as a personal study workspace with a route to start learning. Tablet history and narrow forms reflow without whole-page horizontal overflow. |
| FORM: task continuity | match | The supplied browser records cover retained answers, saved snapshot identity, manual Teaching retry, and a single attempt after a committed response is lost. Partial-result captures retain Medical output and disclose missing feedback. |
| FORM: sources open at criteria | contradicted in disclosure affordance | PracticeResult.tsx:20 and :40 use source-details summaries, while ui-theme.css:8 changes the summary to display:flex without supplying an icon. In after-student-result-390.png, “Đề và câu trả lời đã nộp” and “Synthetic evidence A” look like static section headings. Their collapsed content is not visibly discoverable. Structured result disclosures retain the native triangle. |
| Responsive adaptation | adaptation | Desktop side-by-side authoring becomes question/source tabs on mobile, and practice becomes a single column. Both are explicitly allowed by original request sections 4C and 5 and the direction contract. |
| Truth and execution labels | match | Synthetic test question/source text is labeled; mock scores and feedback are explicitly simulated. Admin publication is explicitly separated from medical expert approval. Clinical result attribution and licensing remain visible. The supplied packet states fixtures live only in the disposable test DB. |

## ceiling

The pinned world calls for readable academic task surfaces rather than ornament. Lists, rules, role-specific navigation, restrained state colors, clear form labels, and source-aligned authoring are used. A sourced Vietnamese display face and visible disclosure mechanics remain unused native finishing devices; no separate quality-card composition or decorative asset obligation is inferred.

## material_fixes

1. STORY / user request sections 6–7: give student source disclosures readable Vietnamese labels using actual document/source metadata or an honest neutral fallback; suppress generated technical evidence titles such as CLINICAL_DEMO_V2_CASE01_SU01 in StructuredResult.tsx:21 and PracticeResult.tsx:40 while preserving stored IDs, contents, locators, and provenance.
2. FORM / source discoverability: add a consistent visible expanded/collapsed indicator to source-details summaries in PracticeResult.tsx and ui-theme.css:8; make the saved answer and each source obviously openable in both result and history views.
3. Floor / TYPE: source and self-host a licensed Vietnamese-capable sans for the wordmark and heading voice through ui-theme.css:2; retain the current compact academic hierarchy and verify 390px wraps after applying it. No new UI framework is needed.
4. Persistence / required handoff: complete the planned documenter pass so DESIGN.md and docs/ui/design-system.md accurately describe the shipped navy/teal tokens, typography, shell, responsive rules, states, and asset/font provenance; update the completion report's pending review/check text and links before delivery.

## keep

Keep the role-specific task navigation, honest mock and expert-review labels, unmodified saved results/provenance, retained-answer recovery, and source-aligned manual authoring while fixing.
