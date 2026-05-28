# Roo Code Prompts for MIS_PROJECT

## Implementation Prompt

```text
We are working on MIS_PROJECT.

Use minimax-m2.7.

Implement GitHub issue #<ISSUE_NUMBER>: <ISSUE_TITLE>.

Follow documents/AI_WORKFLOW.md.

Rules:
- Work only on this ticket.
- Do not implement adjacent or future-phase features.
- Do not modify unrelated files.
- Preserve legacy behavior unless the issue explicitly says otherwise.
- If scope expansion is required, stop and report it instead of implementing.
- Do not run the full Django test suite unless explicitly requested.
- Run targeted checks only.
- Do not commit until I approve the diff.

Required workflow:
1. Inspect the current code.
2. Summarize the implementation plan before editing.
3. Make minimal changes.
4. Run targeted checks:
   - python manage.py check
   - python manage.py makemigrations --check
   - python manage.py migrate if migrations are involved
   - targeted tests for changed apps
5. Give an implementation report:
   - changed files
   - behavior changed
   - behavior intentionally not changed
   - commands run
   - test results
   - risks
   - suggested reviewer focus

Do not commit until I approve the diff.
```

## Docs-Only Implementation Prompt

```text
We are working on MIS_PROJECT.

Use minimax-m2.7.

This is a documentation/process-only task.

Scope:
- <list allowed files>

Non-goals:
- Do not modify Django app code.
- Do not modify models, views, forms, templates, migrations, settings, or tests.
- Do not configure GitHub MCP.
- Do not configure GitHub Actions.
- Do not install or configure VS Code extensions.
- Do not change branch protection settings.

Before editing, inspect the repo structure and give me a short implementation plan.

Do not commit until I approve the diff.
```

## Commit Prompt

```text
The diff is approved for commit.

Create a commit on the current feature branch with this message:

MIS-<ISSUE_NUMBER>: <short description>

Do not merge.
Do not push to main.
```

## Review Prompt

```text
Review this MIS_PROJECT diff as a strict code reviewer.

Focus on:
1. Scope creep
2. Legacy behavior changes
3. Django model/migration risks
4. Query correctness
5. Permission/auth risks
6. Missing tests
7. Unrelated file changes
8. Whether implementation matches the issue acceptance criteria

Do not rewrite the code.
Do not suggest unrelated improvements.

Return:
- Blockers
- Warnings
- Nice-to-have
- Required verification commands
```

## Fix Review Comments Prompt

```text
Address only the blocker review comments below.

Rules:
- Do not refactor unrelated code.
- Do not expand scope.
- Do not change behavior not mentioned in the review.
- Rerun targeted checks.
- Report changed files and test results.
```

## Handoff Prompt for New ChatGPT Chat

```text
We are continuing MIS_PROJECT.

Current workflow:
- ChatGPT is used for planning, review, prompt writing, and scope control.
- Roo Code in VS Code uses company LiteLLM models.
- minimax-m2.7 is the primary implementation model.
- qwen3.6-27b is only for lightweight review/checklist/documentation summary.
- GitHub Issues define task scope.
- GitHub PRs define change review.
- No automatic merge.
- No direct push to main.
- No full Django test suite unless explicitly requested.
- Use targeted checks.

Current branch:
<BRANCH_NAME>

Current issue:
<ISSUE_NUMBER_AND_TITLE>

Current status:
<WHAT_HAS_BEEN_DONE>

Changed files:
<FILES>

Verification:
<COMMANDS_AND_RESULTS>

Next step needed:
<NEXT_ACTION>
```