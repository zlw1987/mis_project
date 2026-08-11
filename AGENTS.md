# MIS Project Agent Instructions

## Environment

- This repository runs on Windows.
- The repository root is exactly:
  `C:\dev\mis_project`
- The directory name is exactly `mis_project`.
- There is NO space in `C:\dev\mis_project`.
- Company policy blocks PowerShell.
- Use Windows CMD-compatible commands only.
- Do not use PowerShell.
- Do not use Unix paths such as `/tmp` or `/dev/null`.
- Do not use bash-specific shell syntax.

## File Path Safety

Prefer repository-relative paths for all file tools.

Examples:

- `documents/FOXPRO_AUTH_PLAN.md`
- `documents/PHASE_4_PLAN.md`
- `documents/PROJECT_STATUS.md`
- `external_auth/signature.py`

Do NOT rewrite these as:

- `FOXPRO_AUTH_PLAN. md`
- `signature. py`
- `C:\dev\ mis_project`
- any other path containing invented spaces

Never insert whitespace before a file extension.

For example:

- `.md` is correct
- `. md` is incorrect
- `.py` is correct
- `. py` is incorrect

## Path Verification

If a Read/Edit/FileSystem tool reports `File not found` for a path that should exist:

1. Do NOT guess a different filename.
2. Do NOT insert or remove spaces based on the error.
3. Do NOT rename, move, copy, or recreate the file.
4. Verify the exact tracked path with CMD/Git first.

Use commands such as:

```cmd
git ls-files
git ls-files documents
git ls-files external_auth
dir /b documents
dir /b external_auth

```

Then use the exact path returned by Git.

If a native Read/Edit tool continues to corrupt a valid path, use CMD-compatible inspection as a fallback instead of inventing another path.

Examples:

```cmd
type documents\FOXPRO_AUTH_PLAN.md
git diff -- documents\FOXPRO_AUTH_PLAN.md
findstr /N /C:"text" documents\FOXPRO_AUTH_PLAN.md
```

## Tool Failure Rule

A native tool failure does NOT prove that the repository path or filename is wrong.

If a tool reports errors such as:

- `File not found`
- `FileSystem.access`
- `NotFound`

first verify the path independently with:

```cmd
git ls-files
dir /b
```

If Git confirms the path exists:

- Treat the native-tool failure as a tooling/integration problem.
- Do NOT recursively reason about alternate filenames.
- Do NOT rename, move, copy, or recreate the file.
- Prefer repository-relative paths.
- Fall back to Windows CMD inspection when safe.
- If editing cannot be performed safely, STOP and report.

## Exact Token Integrity

Never insert spaces inside filenames, paths, identifiers, setting names, migration names, or commands.

These are exact tokens:

- `C:\dev\mis_project`
- `documents/FOXPRO_AUTH_PLAN.md`
- `documents/PHASE_4_PLAN.md`
- `documents/PROJECT_STATUS.md`
- `external_auth/signature.py`
- `FOXPRO_SIGNATURE_MODE`
- `FOXPRO_V2_SECRET`
- `FOXPRO_LAUNCH_MAX_AGE_SECONDS`
- `FOXPRO_LAUNCH_TIMEZONE`
- `FOXPRO_ALLOWED_IPS`
- `FOXPRO_TRUST_X_FORWARDED_FOR`
- `foxpro_canonical_v2`
- `foxpro_sign_v2`
- `0002_add_unsupported_signature_mode`
- `manage.py`
- `external_auth`

Examples of invalid corruption:

- `C:\dev\ mis_project`
- `FOXPRO_AUTH_PLAN. md`
- `signature. py`
- `FOXPRO_ V2_SECRET`
- `external_ auth`
- `manage. py`

If a tool or model produces any of these corrupted forms, do not write them to repository files.

## Git Workflow

- Before editing, run `git status --short`.
- Preserve existing intentional working-tree changes unless instructed otherwise.
- Do not commit or push unless the user explicitly requests it.
- The user normally performs commit and push manually.
- Do not create branches unless explicitly requested.

## Scope Discipline

- Do not expand task scope in order to fix tooling problems.
- Do not create replacement files because a native file tool cannot access an existing tracked file.
- Do not rename files as a workaround for tool-call failures.
- If safe progress becomes impossible because of a tool failure, STOP and report the exact failure.