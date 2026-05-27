# Copilot Instructions -- COMBOT (Carrier Operation Manager Bot)

## Project Identity

COMBOT is a chatbot for **Carrier Operation Managers** (NOT property managers).
It shares the same core architecture as PM Chatbot v2 but has different tools, UI colors, and no card rendering.

## No Implicit Fallback Rule

- **NEVER** add fallback logic that silently uses an alternative API endpoint or data source when the primary one fails or returns empty.
- If the correct endpoint returns no data, return empty -- do not scrape data from unrelated endpoints.
- Any fallback strategy requires explicit user approval before implementation.

## System Prompt & Tool Consistency Rules

- Every tool registered in `agent.py` must have a corresponding **tool selection hint** in the system prompt.
- When adding a field to a tool's text output, verify the system prompt still matches.
- Never add heuristic logic in tools to guess user intent. The LLM resolves intent; tools expose explicit parameters.
- When the PMD API supports server-side filtering, expose it as an optional tool parameter rather than post-filtering in Python code.

## E2E Test Coverage Rule

- **Every new tool** registered in `agent.py` **must** have a corresponding E2E Playwright test file in `tests/e2e/`.
- **Every modification to an existing tool** must pass existing E2E tests.
- E2E tests verify: **LLM response coherence** (text assertions) and **response time** (wall time thresholds).
- Test questions must be in **English** and target **real data** from the INT environment.
- Shared helpers in `tests/e2e/helpers.py`; auth fixtures in `tests/e2e/conftest.py`.

## UI: No Cards

- COMBOT displays **raw LLM text** only. Do NOT implement card rendering.
- The UI accent color is **cyan/teal (#06b6d4)** to distinguish from PM Chatbot's amber.

## Playwright Authentication Guardrails

- Always handle header auth first (`#header-login`, `#header-password`, `#header-auth-btn`).
- Never assume login fields are enabled.
- Before sending a chat message, verify `#msg-input` is visible and enabled.

## PowerShell 5.1 Script Compatibility Rules

- **ASCII only** in `.ps1` files.
- **No `??` operator** -- use `if/else` instead.
- **Wrap `$var` near `:` in `${var}`**.
- **Validate syntax** after editing `.ps1` files.
