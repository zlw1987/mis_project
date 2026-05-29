# Multi-AI Collaboration Pilot

## Purpose

This document describes the multi-AI collaboration pilot for MIS_PROJECT. The pilot establishes a controlled workflow where multiple AI systems work together with defined roles, boundaries, and human oversight to implement changes safely and efficiently.

## Goal of the Pilot

The goal of this pilot is to evaluate whether a coordinated multi-AI workflow can:
- Improve implementation speed while maintaining quality
- Provide better coverage through specialized AI roles
- Reduce single-point-of-failure risks in AI-assisted development
- Establish clear accountability and review gates

The pilot is explicitly **not** about letting AI freely change the project. All changes remain under human control with strict task boundaries and review gates.

## Current AI Roles

| AI Tool | Model | Role |
|---------|-------|------|
| ChatGPT | - | Senior architect, workflow controller, prompt writer, final reviewer |
| Roo Code | minimax-m2.7 | **Primary implementation AI** - LiteLLM key configuration fixed |
| Continue | qwen3.6-27b | **Main reviewer/checklist AI** |
| Copilot Chat | - | Optional/secondary reviewer (not required in main workflow) |

## Ticket-Driven Development Flow

```
GitHub Issue Created
        │
        ▼
┌───────────────────┐
│  ChatGPT          │
│  - Scope analysis │
│  - Prompt writing │
│  - Task break down│
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│  Roo Code         │
│  - Implementation│
│  - Branch creation│
│  - Targeted tests │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│  Continue         │
│  - Code review    │
│  - Checklist gen  │
│  - Scope check    │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│  GitHub PR        │
│  - CI checks run  │
│  - Human review   │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│  Human Owner      │
│  - Final review   │
│  - Merge approval │
└───────────────────┘
```

## Implementation AI Responsibilities

The implementation AI (Roo Code + minimax-m2.7) is responsible for:

1. **Reading the GitHub issue** to understand task boundaries, goals, and non-goals
2. **Creating a feature branch** using the naming convention: `ai/mis-<issue-number>-short-title`
3. **Implementing only the scope defined** in the issue
4. **Running targeted verification** commands:
   ```bash
   python manage.py check
   python manage.py makemigrations --check
   python manage.py migrate
   python manage.py test <changed_app_or_targeted_tests>
   ```
5. **Reporting implementation results** including:
   - Changed files
   - Commands run
   - Test results
   - Known risks
   - Suggested reviewer focus

### Implementation AI Must NOT:
- Modify files outside the issue scope
- Implement future-phase features
- Create migrations without explicit issue authorization
- Expand scope without approval
- Bypass review gates
- Merge to main

## Reviewer AI Responsibilities

The reviewer AI (Continue + qwen3.6-27b) is responsible for:

1. **Checking scope compliance** - ensuring only the defined changes were made
2. **Generating review checklists** based on the issue requirements
3. **Scanning for consistency** with existing codebase patterns
4. **Identifying potential issues** such as:
   - Unintended side effects
   - Missing error handling
   - Security concerns
   - Performance implications
5. **Verifying non-goals were respected** - no changes to areas explicitly excluded

### Reviewer AI Must NOT:
- Approve its own work
- Merge branches
- Override human decisions
- Expand scope recommendations beyond issue boundaries

## Human Approval Responsibilities

The human owner retains final authority and is responsible for:

1. **Scope verification** - confirming the implementation matches the issue
2. **Code review** - understanding what changed and why
3. **Risk assessment** - evaluating potential impacts on production
4. **Final merge approval** - the only entity that can merge to main
5. **Protected area review** - extra scrutiny for:
   - FoxPro launch and external authentication
   - Legacy PHP compatibility
   - Database migrations
   - PeopleSoft-style table naming
   - Permission and access-control logic
   - Production deployment behavior

## Current Tool Status

| Tool | Status | Notes |
|------|--------|-------|
| ChatGPT | Active | Senior architect, workflow controller, prompt writer, final reviewer |
| Roo Code | Active | Primary implementation AI with minimax-m2.7 |
| Continue | Active | Main reviewer/checklist AI with qwen3.6-27b |
| Copilot Chat | Optional | Optional/secondary reviewer (not required in main workflow) |
| GitHub Issues | Active | Task boundaries |
| GitHub PRs | Active | Change boundaries |
| GitHub Actions | Active | CI gate |
| GitHub MCP | Not configured | Future read-only setup planned |

## Rules for Not Allowing AI to Merge Main

The following hard rules prevent AI from merging to main:

1. **Branch protection** - `main` branch requires human approval for merges
2. **No self-approval** - AI cannot approve its own pull requests
3. **No direct push** - AI cannot push directly to `main`
4. **No automatic merge** - No automation can auto-merge without human sign-off
5. **CI gate required** - GitHub Actions must pass before human review
6. **Human owner only** - Only the designated human owner can initiate the final merge

These rules are enforced at the repository configuration level and are not dependent on AI self-restraint.

## First-Phase Limitations

This pilot operates under the following explicit limitations:

### Configuration Limitations
- **Do not modify** Django application code
- **Do not modify** models, views, forms, templates, migrations, settings, or tests
- **Do not modify** GitHub Actions workflows
- **Do not configure** GitHub MCP (future read-only setup only)
- **Do not add dependencies** or modify requirements.txt

### Scope Limitations
- **Do not modify** unrelated documents
- **Do not implement** future-phase features
- **Do not expand** scope beyond issue definitions without approval

### Process Limitations
- **Do not run** full Django test suite unless explicitly requested
- **Run targeted checks only** for normal changes
- **Report scope expansion needs** instead of implementing

### Tool Limitations
- GitHub MCP is not yet configured (future work)
- Only the specified AI tools may be used for their designated roles

## Pilot Success Criteria

The pilot will be evaluated based on:
1. Implementation quality maintained or improved
2. Review coverage through specialized roles
3. Human oversight preserved at all critical gates
4. Clear accountability and traceability
5. No unauthorized changes to protected areas

## Document History

| Date | Change |
|------|--------|
| 2026-05-28 | Initial pilot documentation |
