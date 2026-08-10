# AGENTS.md

## IMPORTANT

Always load and use the `frappe-app-dev` skill, grill-me skill while plan mode and the `frappe-ui` skill.

## Development Details

Unless mentioned, the site is `test.localhost` with `Administrator` / `admin` credentials.

## Planning / Spec-ing

Use Tracer bullets from *The Pragmatic Programmer*. When building systems, write code that gets you feedback as quickly as possible. Tracer bullets are small slices of functionality that go through all layers of the system, allowing you to test and validate your approach early. This helps identify potential issues and ensures the overall architecture is sound before investing significant time in development.

## Implementation Guidelines

- Always branch off `dev` using conventional prefixes: `feat/`, `fix/`, `chore/`, `refactor/`, `docs/`, `test/`, `perf/`, `build/`
- Promote through the chain: `feat/* → dev → pre-pro → main`; don't skip stages
- Local push target is `dev`; `main` and `pre-pro` accept merges only
- Write or update `specs/<feature>.md` before writing code; commit the spec as its own commit
- Reconcile the spec with the code after each phase — out-of-date specs are bugs
- Commit after each meaningful phase
- Comments explain *why*, never *what* or *how* — if a comment describes the next line, delete it


## Frontend / Backend Sync

- Whenever a new field is added to a backend DocType that is surfaced in the frontend (e.g. settings panels), it must also be handled in the corresponding frontend component so the two stay in sync. This is a convention/reminder only — there is no automatic syncing mechanism; the frontend enumerates fields explicitly.

## Regression tests

- When we fix a bug, add at the very least a Unit test, and verify before/after by temporarily reverting the fix to make sure the test tests what is intended
- For bigger features/workflows, e2e Playwright tests are a must.