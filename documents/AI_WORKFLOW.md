# MIS_PROJECT AI Workflow

## Purpose

This document defines the controlled AI-assisted development workflow for MIS_PROJECT.

The goal is not to let AI freely change the project. The goal is to use AI with strict task boundaries, review gates, and human-controlled merging.

## Current Tooling

ChatGPT:
- planning
- architecture review
- scope control
- prompt writing
- code review support
- project handoff guidance

Roo Code + minimax-m2.7:
- primary implementation model
- targeted Django changes
- targeted bug fixes
- targeted tests
- controlled refactoring only when explicitly requested

qwen3.6-27b:
- lightweight review
- checklist generation
- documentation summary
- simple search and consistency checks
- not the primary model for complex Django implementation

GitHub Issues:
- task boundary
- acceptance criteria
- non-goals
- risk notes

GitHub Pull Requests:
- code review boundary
- verification record
- merge gate

Human owner:
- final scope decision
- final review
- final merge approval

## Hard Rules

1. One GitHub issue equals one AI task.
2. One AI task equals one feature branch.
3. No direct push to `main`.
4. No automatic merge.
5. No AI self-approval.
6. No full Django test suite unless explicitly requested.
7. Run targeted checks only.
8. Do not modify unrelated files.
9. Do not implement future-phase features.
10. Preserve legacy behavior unless the issue explicitly requires a behavior change.
11. If scope expansion is required, stop and report instead of implementing.
12. If a migration is needed, explain why before creating it.
13. If authentication, FoxPro launch behavior, or legacy PHP behavior may be affected, stop and ask for confirmation.

## Branch Naming

Use:

```text
ai/mis-<issue-number>-short-title
```

Example:

```text
ai/mis-12-foxpro-launch-validator-cleanup
```

## Commit Message Format

Use:

```text
MIS-<issue-number>: <short description>
```

Example:

```text
MIS-12: tighten FoxPro launch validation
```

## Default Verification

For normal Django changes, run targeted checks:

```bash
python manage.py check
python manage.py makemigrations --check
python manage.py migrate
python manage.py test <changed_app_or_targeted_tests>
```

Do not run the full Django test suite unless explicitly requested.

For documentation-only changes:

```text
Docs/process only. No Django tests required.
```

## Implementation Report Required

Every AI implementation must report:

1. Changed files
2. Behavior changed
3. Behavior intentionally not changed
4. Commands run
5. Test results
6. Known risks
7. Suggested reviewer focus

## Model Selection

Use minimax-m2.7 when:
- implementing Django code
- changing models, views, forms, templates, URLs, or tests
- fixing bugs
- modifying authentication or legacy integration logic

Use qwen3.6-27b only when:
- summarizing documentation
- creating checklists
- reviewing for scope creep
- scanning for consistency
- doing low-risk text cleanup

Do not use qwen3.6-27b as the primary implementation model for complex MIS_PROJECT coding tasks.

## Scope Control

Every issue must include:

- Goal
- Current context
- Scope
- Non-goals
- Acceptance criteria
- Required verification
- Risk level
- AI instructions

If any of these are unclear, the AI should ask for clarification before editing.

## Protected Areas

Extra caution is required for:

- FoxPro launch and external authentication
- legacy PHP compatibility
- database migrations
- PeopleSoft-style table naming
- permission and access-control logic
- production deployment behavior
- existing documents under `documents/`

Changes in these areas require explicit issue scope and human review.

## Merge Policy

AI may create code changes on a feature branch.

AI may not:
- merge to main
- bypass branch protection
- approve its own work
- silently expand scope
- convert planning documents into implementation without approval

Human review is required before merge.