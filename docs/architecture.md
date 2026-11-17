# Architecture

## Admin authoring and approved grading packages (2026-11-12)

KG/semantic retrieval now also supports the admin authoring step. An administrator
selects source excerpts, optionally requests a separate authoring model proposal,
edits the reference answer/rubric, then explicitly publishes a grading package.
Published question/rubric revisions are immutable; editing creates a new draft.
Learner submissions use the approved PostgreSQL package, including its source
evidence in every Medical request, without runtime KG/vector search. Attempts
pin the revision and package hash. The previous runtime vector/hybrid branches
remain separate experimental configurations. This does not revise historical
benchmark results. See [workflow, configuration and verification](authoring-approved-package.md).

## Boundaries

The system is a modular monolith. HTTP routers translate requests, services enforce business rules, repositories handle persistence, and infrastructure implementations sit behind small protocols. This keeps one deployable backend while preserving replaceable AI and storage boundaries.

```text
Browser -> Next.js -> FastAPI routers -> domain services -> repositories -> PostgreSQL
                                      -> RAG service -> Retriever protocol
                                                     -> LLMProvider protocol
                                      -> Document service -> FileStorage protocol
```

Business modules never call a vendor model SDK. `MockLLMProvider`, `MockEmbeddingProvider`, and `MockRetriever` allow deterministic development without credentials. `APIProvider` and `LocalProvider` are explicit unimplemented boundaries, not fake integrations.

## Backend modules

- `core`: configuration, async database session, security, logging, and errors
- `modules/auth` and `modules/users`: identity and authorization
- `modules/specialties` and `modules/topics`: learning taxonomy
- `modules/documents`: source metadata and the lightweight PostgreSQL concept graph
- `modules/questions`, `modules/exams`, `modules/progress`, `modules/recommendations`: persistence foundation only
- `ai/providers`, `ai/retrieval`, `ai/rag`: provider contracts and safe mock orchestration
- `storage`: file persistence contract and local implementation

## Key decisions

1. **Modular monolith before microservices.** Current scale and workflows do not justify distributed transactions or messaging infrastructure.
2. **Async SQLAlchemy.** API I/O remains non-blocking and the same session boundary is dependency-injected for tests.
3. **Explicit migration command.** Application replicas never mutate schema at startup.
4. **Dimensionless pgvector column for the foundation.** The chosen embedding model will determine dimension later; vector indexes are deferred until then.
5. **Local file storage behind a protocol.** An object-storage implementation can replace it without changing document rules.
6. **Fail closed for providers.** Unknown configured providers return an availability error; there is no implicit paid API call.
7. **JWT access token only.** Adequate for prototype scope; refresh, revocation, and production browser storage are deferred and documented.

## Error and observability model

Every request receives or propagates an `X-Request-ID`. Expected domain errors retain a stable code and HTTP status. Validation uses the same envelope. Unexpected errors are logged with stack trace server-side and hidden from clients unless debug is enabled.

## Security limits

File extension and MIME must agree, size is bounded before persistence, supplied filenames are reduced to a basename, and physical storage names are generated UUIDs. This is not malware scanning. A production ingestion boundary still needs content inspection, quarantine, authorization review, rate limiting, audit logging, and object-store controls.

