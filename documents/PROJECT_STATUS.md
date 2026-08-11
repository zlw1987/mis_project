# Project Status

---

## Current Status

- **Phase 3 is complete.** All subphases (3A, 3B, 3C, 3D) are done.
- **Phase 3D-5A final hardening review: PASS.** 116 targeted tests OK. Views are thin wrappers. No business logic duplication. CSRF and POST-only enforced. No blockers.
- **Phase 4B Dashboard implementation: COMPLETE.** User manually ran full test suite and confirmed it passed.
- **Final Phase 4E documentation synchronization cleanup is in progress (this task).** external_auth app implementation complete; migration 0002_add_unsupported_signature_mode.py added.
- **Phase 4C (UI polish) is paused/deferred.** Implementation has not started.
- **Phase 4F implementation complete; pilot readiness pending.** external_auth app exists with V2 signature validation. Pilot/go-live is NOT approved until verification steps are completed.
- **Current blockers:** Pilot readiness — see Phase 4F verification steps below.

---

## Completed Work

- Phase 0 — Django foundation and accounts foundation
- Phase 0 hardening
- Phase 1 — `project_requests` foundation (models, admin, tests)
- Phase 1 hardening
- Phase 2A — Service layer, permissions, selectors, request number, submit workflow, attachment upload
- Phase 2A hardening / correctness patches
- Final Phase 2A correctness patch
- Phase 2B — Forms, views, templates (list, detail, create, attachment download)
- Phase 2B hardening
- Phase 3A — Approve/Reject services, approval permission helpers, pending approval selector hardening, tests
- Phase 3A hardening patch (superuser pending selector, superuser action context, stale DB status tests, approve_project_request all-task-check)
- Phase 3B — Assignment/Claim services, permission helpers, tests (implemented by minimax-m2.7)
- Phase 3C — Execution workflow services (Start/Hold/Resume/Complete), permission helpers, action context enrichment, tests (implemented by minimax-m2.7)
- Phase 3D-1 — Approve/Reject UI integration: ApprovalActionForm, RejectActionForm, approve/reject POST views, approve/reject URLs, approve/reject template controls, nullable task.acted_by and log.actor safe rendering, stale future action HTML comments removed (implemented by minimax-m2.7)
- Phase 3D-2 — Assign/Claim UI integration: AssignmentForm with dynamic assigned_to queryset, project_request_assign POST view, project_request_claim POST view, assign/claim URL routes, assign form gated by action_context.can_assign, claim button gated by action_context.can_claim, ProjectRequestAssignClaimViewTest with assign/claim view coverage
- Phase 3D-3 — Start/Hold/Resume/Complete UI: HoldActionForm, GenericCommentActionForm, project_request_start/hold/resume/complete POST views, start/hold/resume/complete URL routes, execution controls on detail page gated by action_context.can_start/can_hold/can_resume/can_complete, hold requires comment, start/resume/complete support optional comments, views call service-layer functions without duplicating business logic
- Phase 3D-4 — Detail template integration and end-to-end workflow tests: _build_detail_context() includes assignment_form when action_context.can_assign is True, attachment upload error re-render context consistency, ProjectRequestWorkflowEndToEndTest, ProjectRequestDetailWorkflowIntegrationTest, end-to-end and detail workflow integration coverage
- Phase 3D-5A — Final hardening review: read-only review passed. Targeted review checks passed (manage.py check, makemigrations --check --dry-run, 116 targeted tests OK). Views confirmed thin wrappers. No business logic duplication. CSRF and POST-only enforced. No blockers.
- Phase 4B — Dashboard implementation: dashboard selectors in selectors.py, ProjectRequestDashboardView, project_requests:dashboard URL, dashboard.html template, dashboard navbar link in base.html, ProjectRequestDashboardSelectorTest, ProjectRequestDashboardViewTest. Dashboard is read-only GET-only with no POST forms or workflow action buttons. Reuses existing selectors/visibility logic. No model/migration changes.

---

## Technical Debt / Future Cleanup (Non-Blocking, Not Required)

These items were identified during Phase 3D-5A review but are NOT blockers:

- `views.py` module docstring says Phase 2B (stale) — identified Phase 3D-5A, carried forward
- Some test names/comments are historically stale after later Phase 3D subphases
- Light test helper refactor could reduce duplication but is optional
- Extra black-box create-to-complete UI flow is not needed now
- Final review confirmed no business logic was duplicated in views
- Admin Overview overdue count may be semantically "assigned overdue" rather than true global/admin overdue — consider Phase 4C/cleanup clarification

---

## Latest Known Test Status

- **User-observed full test suite: 267 tests OK (after Phase 3A).**
- Phase 3B: Full test suite manually verified by user after implementation.
- Phase 3C: Full test suite manually verified by user after implementation.
- Phase 3D-1: **Roo ran targeted tests only**. **User manually runs full test suite.**
- Phase 3D-2: **Roo ran targeted tests only**. **User manually runs full test suite.**
- Phase 3D-3: **Roo ran targeted tests only**. **User manually ran full test suite and confirmed it passed.**
- Phase 3D-4: **Roo ran targeted tests only**. **User manually ran full test suite and confirmed it passed.**
- Phase 3D-5A: **Read-only final hardening review. No code modified. No new full-test run required. Phase 3D-5A targeted review checks passed: manage.py check, makemigrations --check --dry-run, 116 targeted tests OK.**
- Phase 4B: **Roo ran targeted tests only**. **User manually ran full test suite and confirmed it passed.**

---

## Current Next Step

**Final Phase 4E documentation synchronization cleanup.** Phase 4B is complete.

Phase 4F implementation is complete; pilot readiness is pending verification:

**Pilot/go-live is NOT approved until:**
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

Phase 4C and Phase 4D remain deferred.

---

## Current Blockers

Phase 4F code implementation is complete. Current blockers are pilot readiness verification steps listed above — not implementation blockers.

---

## Warnings

A previous AI response incorrectly claimed tests passed before full terminal output was verified. Always verify final test output before claiming tests pass.

**Roo should run targeted tests only. User manually runs full test suite.**
