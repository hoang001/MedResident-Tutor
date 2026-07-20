# Development roadmap

## Phase 1: Foundation

Current phase. Establish monorepo, relational schema, auth, authorization, validated document upload, safe provider interfaces, frontend shell, tests, Docker, and documentation.

## Phase 2: Document ingestion

Implement extraction state transitions and idempotent jobs. Start with TXT/Markdown, then put PDF extraction/OCR behind an interface. Persist sections and chunks, record provenance, quarantine failures, and add retry/observability tests. Do not use real patient material.

## Phase 3: RAG

Select and evaluate an embedding provider and dimension, add vector migration/index, implement retrieval filters and citations, then evaluate recall before adding reranking. Add a real LLM only behind the provider interface, with grounding and abstention tests.

## Phase 4: Exam and grading

Add question/exam CRUD, attempts, deterministic multiple-choice scoring, and rubric-based human review. Evaluate any future LLM-assisted grading separately; it must be auditable and must not silently assign authoritative scores.

## Phase 5: Progress and recommendations

Derive learning results from graded attempts, define transparent weakness metrics, and produce explainable learning-content recommendations. Add learner controls to dismiss recommendations.

## Phase 6: Knowledge Graph integration

Add validated concept management and PostgreSQL recursive traversal. Measure whether graph signals improve retrieval before considering GraphRAG or another database. Neo4j is not assumed.

## Phase 7: Evaluation and deployment

Create offline retrieval/answer evaluation sets, security and privacy review, audit logging, rate limits, backup/restore tests, PostgreSQL migration CI, production token/session design, monitoring, and controlled deployment. Clearly preserve the boundary between education and clinical decision support.

