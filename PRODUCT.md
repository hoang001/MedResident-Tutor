# MedResident Tutor

<!-- impeccable:product-schema 1 -->

## Platform

Web: existing Next.js App Router / React / TypeScript frontend, plain CSS and a shared API client.

## Users

Vietnamese medical residents reading source-linked materials, practicing and reviewing saved work; administrators managing documents and authoring, checking and publishing questions.

## Product Purpose

Provide a usable study MVP: find material or an available exercise, read and answer, inspect the saved result and sources, then return to the same learning history. Administrators work beside supporting excerpts and save drafts separately from publication. This is a study project, not a university portal or a formal medical competency assessment system.

## Capabilities and Constraints

- Student navigation: Tổng quan (`/dashboard`), Thư viện học tập (`/knowledge`), Bài tập (`/learn`), Lịch sử & kết quả (`/history`) and Tiến độ học tập (`/progress`). Account viewing and logout use actual authenticated data.
- Secondary resources: Sách & mục lục (`/sources`), Khung chương trình (`/curriculum`) and ungraded Tự ôn theo tài liệu (`/exams`). These do not promise a complete curriculum, examination service or validated learning pathway.
- Admin navigation: Ngân hàng câu hỏi (`/admin/questions`) and Tài liệu & nguồn (`/admin/documents`), with a switch back to study. No full user-management backend is claimed.
- Catalog search, metadata filters, pagination and latest-attempt status reflect the current account. Available-question counts exclude KG suggestions without grading packages.
- Practice preserves per-account browser drafts and submission idempotency. History opens the saved question/answer/result snapshot and evidence; viewing does not regrade against the current rubric. Valid Medical output remains visible if Teaching feedback fails, with explicit retry.
- Structured exercises use authored answers and criteria, with limitations disclosed. Mock and replay retain their true execution labels. Reading completion, self-study activity and simulated scores do not establish medical mastery.
- Authoring supports manual question/answer/criterion editing beside source selection and excerpt preview, validation, drafts, revisions and separate publication. App publication is not medical expert approval. Disabled automatic authoring is disclosed without blocking manual work.
- Document listing and upload use real endpoints. Upload saves a file; this screen does not run OCR, extraction or indexing. Listing uses up to 100 recent documents under the current API.
- Profile editing and password changes are not implemented; the account screen provides viewing and logout without inert edit controls.

Small authorized read API additions support catalogs, authoring configuration and personal history. Existing endpoints and permission boundaries remain. No backend rewrite, migrations for styling, changed grading/model contracts, provider changes, KG/ontology edits, historical-data edits or model execution are authorized by this redesign.

## Evidence on Hand

The explicit redesign brief, `docs/ui/ux-audit.md`, `docs/ui/surface-direction.md`, `docs/ui/ui-completion-report.md` and implemented frontend/API define scope. The handoff packet records preservation of 102 questions (100 available, 2 drafts), saved attempts, source mappings and study records. These are a dated baseline, not hardcoded UI metrics. Existing benchmark, fixture, model and research artifacts remain in the repository.

## Product Principles

- Prioritize reading, source verification and task continuity.
- Use the requested academic navy/teal identity, light grounds and Vietnamese typography; retain MedResident Tutor's own wordmark.
- Separate student study tasks from administration and development tools.
- Distinguish loading, empty, failed, partial and saved states honestly; retain work and warn before discarding edits.
- Preserve source IDs, content, locators, PDF pages, hashes, version identity and review caveats while presenting readable labels.
- Do not invent medical content, performance metrics, references, backend capabilities or assessment guarantees.

## Accessibility & Inclusion

Visible labels, keyboard operation, clear focus, status text alongside color, readable contrast and desktop/tablet/mobile reflow are required. Clinical images retain aspect ratio, source attribution, licensing and evidence coordinates. Generated images do not substitute for clinical evidence.

## Context provenance

Updated under the explicit replacement brief, superseding the former green/teal direction and frontend-only constraint and permitting necessary small API additions. The scope remains an MVP using existing data, providers, grading and knowledge graph. Validation results and limitations belong in the completion report; this document does not independently certify clinical content or production readiness.
