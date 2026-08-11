# AI Handoff Document

> **First file any new AI/model/task should read.**

---

## Project Name

**MIS_PROJECT**

## Workspace Boundary

- **Workspace root:** `C:/dev/MIS_PROJECT`
- **All work MUST stay inside this directory.**

### Explicitly Forbidden Paths

Do NOT read, search, or request access to:

- `C:/dev`
- `C:/dev/a8_oa`
- `C:/dev/bible_reading_v2`
- Parent directories
- Sibling directories
- Any path outside `C:/dev/MIS_PROJECT`

---

## Project Goal

Rebuild the legacy PHP MIS request system (in `legacy_php/`) as an enterprise internal project request / project management system in Django.

The legacy PHP code is **read-only reference material**. Do not modify files in `legacy_php/`.

---

## Current Django Apps

| App | Purpose |
|-----|---------|
| `accounts` | Custom user model, department, and department-scoped role helpers |
| `project_requests` | Project request lifecycle (draft → submit → approve → assign → complete) |
| `external_auth` | FoxPro/external auth bridge — **implemented** (Phase 4F complete; pilot readiness pending) |

---

## Completed Phases

| Phase | Description |
|-------|-------------|
| **Phase 0** | Django foundation and accounts foundation |
| **Phase 1** | `project_requests` foundation — models, admin, tests |
| **Phase 2A** | Service layer, permissions, selectors, request number generation, submit workflow, attachment upload |
| **Phase 2B** | Forms, views, templates — list, detail, create, attachment download view |
| **Phase 3A** | Approve/Reject services, approval permission helpers, pending approval selector hardening, tests (implemented by minimax-m2.7) |
| **Phase 3B** | Assignment/Claim services, permission helpers, tests (implemented by minimax-m2.7) |
| **Phase 3C** | Execution workflow services (Start/Hold/Resume/Complete), permission helpers, action context enrichment, tests (implemented by minimax-m2.7) |
| **Phase 3D-1** | Approve/Reject UI integration — forms, views, URLs, template controls, tests (implemented by minimax-m2.7) |
| **Phase 3D-2** | Assign/Claim UI integration — AssignmentForm with dynamic queryset, assign/claim POST views, assign/claim URL routes, template controls, tests |
| **Phase 3D-3** | Start/Hold/Resume/Complete UI — HoldActionForm, GenericCommentActionForm, start/hold/resume/complete POST views, URL routes, detail template controls, tests |
| **Phase 3D-4** | Detail template integration and end-to-end workflow tests — AssignmentForm in detail context, attachment upload error re-render context, ProjectRequestWorkflowEndToEndTest, ProjectRequestDetailWorkflowIntegrationTest |
| **Phase 3D-5A** | Final hardening review — targeted tests passed (116 OK), views are thin wrappers, no business logic duplication, CSRF and POST-only enforced, no blockers |
| **Phase 3D** | **Complete** — all 3D-1 through 3D-5A subphases done |
| **Phase 3** | **Complete** — 3A, 3B, 3C, 3D all complete |
| **Phase 4B** | Dashboard implementation — dashboard selectors, ProjectRequestDashboardView, project_requests:dashboard URL, dashboard.html template, dashboard navbar link, dashboard tests |

---

## Pending Phase

| Phase | Description |
|-------|-------------|
| **Phase 4C** | UI polish and usability hardening — deferred |
| **Phase 4D** | Legacy migration assessment — deferred |
| **Phase 4E** | FoxPro/external auth architecture planning — documentation sync in progress, not yet approved |
| **Phase 4F** | FoxPro/external auth implementation — **complete; pilot readiness pending** |

---

## Current Status

- **Phase 3 is complete.** All subphases (3A, 3B, 3C, 3D) are done.
- **Phase 3D-5A final hardening review: PASS.** 116 targeted tests OK. Views are thin wrappers. No business logic duplication. CSRF and POST-only enforced. No blockers.
- **Phase 4B Dashboard implementation: COMPLETE.** User manually ran full test suite and confirmed it passed.
- **Current active task: Final Phase 4E documentation synchronization cleanup only.** This is the only work being done. No code/templates/URLs/migrations are being modified.
- **Phase 4E architecture draft exists** in `documents/FOXPRO_AUTH_PLAN.md` using the Signed Launch URL pattern, but is not approved until this sync cleanup review passes.
- **Phase 4F implementation is complete; pilot readiness pending.** external_auth app exists with V2 signature validation. Pilot/go-live is NOT approved until verification steps are completed.
- Phase 4C and Phase 4D remain deferred.
- Independent minimax-m2.7 Phase 2B review returned **PASS**.
- minimax-m2.7 Phase 3A, 3B, 3C, 3D-1 implementations were **successful**.
- No blockers for the current documentation sync task.

---

## Technical Debt / Future Cleanup (Non-Blocking, Not Required)

These items were identified during Phase 3D-5A review but are NOT blockers. They may be addressed in Phase 4 or future work:

- `views.py` module docstring says Phase 2B (stale) — identified Phase 3D-5A, carried forward
- Some test names/comments are historically stale after later Phase 3D subphases
- Light test helper refactor could reduce duplication but is optional
- Extra black-box create-to-complete UI flow is not needed now
- Final review confirmed no business logic was duplicated in views — this is now verified.
- Admin Overview overdue count may be semantically "assigned overdue" rather than true global/admin overdue — consider Phase 4C/cleanup clarification

---

## Important Testing Note

- Phase 2B era: User-observed full test suite: **218 tests OK**.
- Phase 3A era: User-observed full test suite: **267 tests OK**.
- Phase 3B era: Full test suite manually verified by user after implementation.
- Phase 3C era: Full test suite manually verified by user after implementation.
- Phase 3D-1 era: **Roo ran targeted tests only**. **User manually runs full test suite.**
- Phase 3D-2 era: **Roo ran targeted tests only**. **User manually runs full test suite.**
- Phase 3D-3 era: **Roo ran targeted tests only**. **User manually ran full test suite and confirmed it passed.**
- Phase 3D-4 era: **Roo ran targeted tests only**. **User manually ran full test suite and confirmed it passed.**
- Phase 3D-5A era: **Read-only final hardening review. No code modified. No new full-test run required. Phase 3D-5A targeted review checks passed: manage.py check, makemigrations --check --dry-run, 116 targeted tests OK.**
- Phase 4B era: **Roo ran targeted tests only**. **User manually ran full test suite and confirmed it passed.**
- Phase 3 complete. All Phase 3 subphases done.
- Phase 4B complete.

---

## Phase 4 Warning

**Phase 4E documentation synchronization is in progress (this task).** Phase 4B is complete.

**Phase 4C and Phase 4D remain deferred.** Do not begin Phase 4C or Phase 4D implementation until explicitly approved.

**Phase 4F implementation is complete; pilot readiness pending.** Do not claim pilot/go-live is approved until:
1. `python manage.py check` passes
2. `python manage.py makemigrations --check --dry-run` passes
3. `python manage.py test external_auth -v 2` passes
4. User manually runs full test suite
5. Migration is reviewed/applied
6. `FOXPRO_V2_SECRET` is set to real secret and matches FoxPro `MisSecretV2()`
7. `FOXPRO_ALLOWED_IPS` is configured for actual workstation/NAT/proxy source IPs
8. `FOXPRO_LAUNCH_TIMEZONE` is configured
9. v=2 FoxPro-side URL generation is updated and tested
10. End-to-end FoxPro → Django dashboard launch succeeds

The approved Phase 4F architecture is Signed Launch URL (not token exchange), implemented in the `external_auth` app.

---

## Model Usage Rules

| Model | Role |
|-------|------|
| **minimax-m2.7** | Preferred for core workflow implementation and review |
| **qwen3.6-27b** | Documentation, small mechanical tasks, unless otherwise instructed |

---

## New Task Rules

**Start a New Task when:**

1. Switching models (e.g., qwen → minimax or minimax → qwen)
2. Switching from implementation to review (or review back to implementation)
3. Entering a new phase
4. After serious false assumptions, false test-pass claims, or outside-workspace access attempts

---

## Testing Rule

**Do NOT claim tests passed unless the final terminal output was actually observed.**

If the test command times out or output is truncated without full results, state: "Not verified by Roo due timeout."

**Roo should run targeted tests/checks only. User manually runs full test suite.**
