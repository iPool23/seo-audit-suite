---
name: python-refactor
description: 'Refactor Python code for readability, smaller functions, type hints, clearer boundaries, and less duplication. Use when improving MCP server code, crawl logic, parsing helpers, or any src/seo_mcp/*.py module without changing behavior.'
---

# Python Refactor Skill

## When to Use
- Improve existing Python code without changing user-facing behavior.
- Split large functions into smaller helpers.
- Add or tighten type hints, docstrings, and naming.
- Reduce duplication in parsing, crawling, formatting, or validation code.

## Procedure
1. Find the controlling function or module before editing.
2. Preserve behavior first; refactor structure second.
3. Extract pure helpers for normalization, parsing, formatting, and aggregation.
4. Keep public tool signatures and JSON keys stable unless the user asked for a change.
5. Validate the result with syntax checks, targeted errors, and tests when available.

## Refactor Rules
- Do not mix a refactor with unrelated feature work.
- Prefer standard library tools before adding new dependencies.
- Keep functions small, explicit, and easy to test.
- Make error handling consistent and actionable.
- Remove dead code only when its replacement is already in place.

## Validation
- Run a syntax check on touched Python files.
- Check the editor diagnostics for new errors.
- If behavior changed, add or update regression tests.
- If the change touches crawling or HTTP parsing, test at least one happy path and one failure path.