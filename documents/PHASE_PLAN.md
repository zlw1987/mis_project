# Phase Plan

---

## Phase 0 — Django Foundation and Accounts Foundation

**Status:** Complete

### Allowed Work
- Django project scaffolding
- `accounts` app: custom User model, Department, UserDepartment, AccessLevel
- `accounts/services.py`: department-scoped role helpers
- `accounts` admin, tests, migrations

### Forbidden Work
- `project_requests` models or logic
- Views, templates, forms

### Exit Criteria
- Custom user model works with `AUTH_USER_MODEL`
- Department and UserDepartment models functional
- Role helpers return correct values
- Tests pass

---

## Phase 1 — project_requests Foundation (Models, Admin, Tests)

**Status:** Complete

### Allowed Work
- `project_requests` models: ProjectRequest, ApprovalTask, Assignment, Attachment, ActivityLog, RequestNumberSequence, ProjectRequestType, ProjectRequestFileType, ProjectDepartmentProfile
- TextChoices: status, priority, approval role, approval status, action type
- Admin configuration
- Model-level tests

### Forbidden Work
- Service layer, permissions, selectors
- Views, templates, forms

### Exit Criteria
- All models migrate cleanly
- Admin pages functional
- Model tests pass

---

## Phase 2A — Service Layer, Permissions, Selectors

**Status:** Complete and reviewed (minimax-m2.7 PASS)

### Allowed Work
- `project_requests/services.py`: request number generation, draft creation, submit workflow, approval generation, attachment upload, activity logging, duplicate prevention, required-on-submit validation
- `project_requests/permissions.py`: permission helpers (can_view, can_submit, can_assign, can_claim, can_attach_file)
- `project_requests/selectors.py`: queryset selectors (visible, my, assigned, pending approvals, overdue)
- Service/permission/selector tests

### Forbidden Work
- Views, templates, forms
- Approve/reject/assign/claim/complete workflows

### Exit Criteria
- All service functions tested
- Permission checks use department-scoped helpers
- Selectors use correct OR logic and safe Exists subqueries
- Independent minimax review PASS
- Full test suite passes

---

## Phase 2B — Forms, Views, Templates

**Status:** Complete and reviewed (minimax-m2.7 PASS)

### Allowed Work
- `project_requests/forms.py`
- `project_requests/views.py`
- `project_requests/urls.py`
- Templates for create, list, detail views
- Permission-checked attachment download view
- Navigation links if needed

### Forbidden Work
- Approve/reject/assign/claim/start/complete workflows
- Rewriting Phase 2A services (unless fixing a discovered bug)
- Modifying `legacy_php/`

### Exit Criteria
- Views use service layer (no duplicated business logic)
- Download view enforces `can_view_project_request()` or a dedicated `can_download_attachment()`; templates must not expose `attachment.file.url` directly
- Tests cover: create draft, submit, list visibility, detail permissions, attachment upload/download permissions
- Independent minimax review PASS

---

## Phase 3 — Approve/Reject/Assign/Claim/Start/Hold/Resume/Complete Workflows

### Phase 3A — Approve/Reject Services & Permission Helpers

**Status:** Complete (implemented by minimax-m2.7)

### Allowed Work (Completed)
- `approve_project_request()` service: transitions to APPROVED only when all approval tasks are APPROVED
- `reject_project_request()` service: immediately transitions to REJECTED
- Approval permission helpers in `permissions.py`
- Pending approval selector hardening (`selectors.py`): PENDING tasks actionable only when parent status == REVIEWING
- Superuser pending selector and action context fixes
- Service/selector/permission tests

### Hardening Patch
- Superuser pending approval selector fix
- Superuser action context fix
- Stale DB status tests for approve/reject
- `approve_project_request` now requires all approval tasks APPROVED (not just no PENDING tasks)

### Exit Criteria (Met)
- All approve/reject transitions tested
- Status transitions follow defined rules
- Activity logs record all transitions
- Full test suite: 267 tests OK

---

### Phase 3B — Assignment/Claim Services & Permission Helpers

**Status:** Complete (implemented by minimax-m2.7)

### Allowed Work (Completed)
- `assign_project_request()` service: assigns APPROVED requests to a user in the project department
- `claim_project_request()` service: allows APPROVED -> ASSIGNED self-claim
- `can_assign_project_request()` permission helper hardening
- Assignment blocks inactive `project_department`
- Assignment blocks inactive or missing `ProjectDepartmentProfile`
- Claim only allows APPROVED -> ASSIGNED transition
- Reassignment deactivates old active assignment
- `get_assigned_to_me` regression tests

### Changed Code Areas
- `project_requests/permissions.py`
- `project_requests/services.py`
- `project_requests/tests.py`

### Not Implemented (Deferred to Phase 3D)
- Views
- Forms
- Templates
- URLs
- Buttons
- UI workflow actions

### Exit Criteria (Met)
- All assign/claim transitions tested
- Status transitions follow defined rules
- Activity logs record all transitions
- Full test suite manually verified by user

---

### Phase 3C — Execution Workflow Services (Start/Hold/Resume/Complete)

**Status:** Complete (implemented by minimax-m2.7)

### Allowed Work (Completed)
- Service functions for start, hold, resume, complete
- Permission checks for execution actions (can_start, can_hold, can_resume, can_complete)
- `get_project_request_action_context()` enriched with can_start/can_hold/can_resume/can_complete
- Service/permission tests

### Implemented
- `can_start_project_request()` — active assignee, project dept manager/director/VP, superuser may start when ASSIGNED
- `can_hold_project_request()` — active assignee, project dept manager/director/VP, superuser may hold when IN_PROGRESS
- `can_resume_project_request()` — active assignee, project dept manager/director/VP, superuser may resume when ON_HOLD
- `can_complete_project_request()` — active assignee, project dept manager/director/VP, superuser may complete when IN_PROGRESS
- `start_project_request()` — ASSIGNED -> IN_PROGRESS, requires active project_department and active ProjectDepartmentProfile
- `hold_project_request()` — IN_PROGRESS -> ON_HOLD, requires comment
- `resume_project_request()` — ON_HOLD -> IN_PROGRESS
- `complete_project_request()` — IN_PROGRESS -> COMPLETED
- All execution actions require at least one active assignment
- ON_HOLD cannot complete directly; must resume first
- Hold requires a comment
- ActivityLog.description stores short action description; ActivityLog.comment stores user-provided comment

### Changed Code Areas
- `project_requests/permissions.py`
- `project_requests/services.py`
- `project_requests/tests.py`

### Not Implemented (Deferred to Phase 3D)
- Views
- Forms
- Templates
- URLs
- Buttons
- UI workflow actions

### Exit Criteria (Met)
- All execution transitions tested
- Status transitions follow defined rules
- Activity logs record all transitions
- Full test suite manually verified by user

---

### Phase 3D — Workflow UI Integration

**Status:** Complete (Phase 3D-1, 3D-2, 3D-3, 3D-4, 3D-5A all complete)

### Phase 3D-1 — Approve/Reject UI

**Status:** Complete (implemented by minimax-m2.7)

### Allowed Work (Completed)
- `ApprovalActionForm` — approve action form with optional comment
- `RejectActionForm` — reject action form with required comment
- `project_request_approve` view — POST-only, validates task ownership
- `project_request_reject` view — POST-only, validates task ownership
- Approve/reject URL routes
- Approve/reject template controls on detail page
- Nullable `task.acted_by` and `log.actor` safe rendering
- Stale future action HTML comments removed

### Changed Code Areas
- `project_requests/forms.py`
- `project_requests/views.py`
- `project_requests/urls.py`
- `templates/project_requests/projectrequest_detail.html`
- `project_requests/tests_views.py`

### Not Implemented (Deferred to Phase 3D-2)
- Assignment/claim UI
- Start/hold/resume/complete UI

### Exit Criteria (Met)
- Approver sees approve/reject controls for own pending tasks
- Non-approver does not see controls
- Approve POST transitions to APPROVED when final approval
- Approve POST keeps REVIEWING when more approvals remain
- Reject POST requires comment and transitions to REJECTED
- Wrong `approval_task_id` from another request is rejected
- CSRF-bearing forms exist in template
- All Phase 3D-1 tests pass (Roo: 29/29 + 6/6 targeted; user runs full suite)

---

### Phase 3D-2 — Assign/Claim UI

**Status:** Complete

### Allowed Work (Completed)
- AssignmentForm with dynamic assigned_to queryset
- project_request_assign POST view
- project_request_claim POST view
- Assign/claim URL routes
- Assignment form gated by action_context.can_assign on detail template
- Claim button gated by action_context.can_claim on detail template
- ProjectRequestAssignClaimViewTest with assign/claim view coverage

### Changed Code Areas
- `project_requests/forms.py` — added AssignmentForm
- `project_requests/views.py` — added project_request_assign, project_request_claim
- `project_requests/urls.py` — added assign/claim URL routes
- `project_requests/tests_views.py` — added ProjectRequestAssignClaimViewTest
- `templates/project_requests/projectrequest_detail.html` — added assignment form and claim button

### Not Implemented (Deferred to Phase 3D-3)
- Start/hold/resume/complete UI

### Non-Blocking Hardening Note
- `_build_detail_context()` used by attachment upload error re-render does not currently include `assignment_form` when `action_context.can_assign` is True. This can be addressed in Phase 3D-5 hardening or earlier if convenient.

### Exit Criteria (Met)
- Project dept manager sees assignment form when `can_assign` is True
- Assign POST creates assignment and transitions APPROVED -> ASSIGNED
- Reassign POST deactivates old assignment
- `assigned_to` queryset excludes inactive users and users outside project department
- Staff sees claim button when `can_claim` is True
- Claim POST transitions APPROVED -> ASSIGNED
- Staff does not see claim button for ASSIGNED
- All Phase 3D-2 tests pass (Roo: targeted tests only; user runs full suite)

---

### Phase 3D-3 — Start/Hold/Resume/Complete UI

**Status:** Complete

### Implemented
- `HoldActionForm` — hold action form with required comment
- `GenericCommentActionForm` — optional comment form for start/resume/complete
- `project_request_start` view — POST-only, transitions ASSIGNED -> IN_PROGRESS
- `project_request_hold` view — POST-only, transitions IN_PROGRESS -> ON_HOLD (requires comment)
- `project_request_resume` view — POST-only, transitions ON_HOLD -> IN_PROGRESS
- `project_request_complete` view — POST-only, transitions IN_PROGRESS -> COMPLETED
- Start/hold/resume/complete URL routes (`/<int:pk>/start/`, `/<int:pk>/hold/`, `/<int:pk>/resume/`, `/<int:pk>/complete/`)
- Execution controls on detail page gated by `action_context.can_start` / `can_hold` / `can_resume` / `can_complete`
- Hold requires comment; start/resume/complete support optional comments
- Views call service-layer functions and do not duplicate business logic

### Changed Code Areas
- `project_requests/forms.py` — added `HoldActionForm`, `GenericCommentActionForm`
- `project_requests/views.py` — added `project_request_start`, `project_request_hold`, `project_request_resume`, `project_request_complete`
- `project_requests/urls.py` — added start/hold/resume/complete URL routes
- `templates/project_requests/projectrequest_detail.html` — added execution controls
- `project_requests/tests_views.py` — added execution view tests

### Allowed Work (Completed)
- Hold/comment forms
- Start/hold/resume/complete POST views
- URL routes for execution actions
- Execution controls to detail template
- View-level tests for execution actions

### Forbidden Work
- Modifying service layer
- Modifying Phase 2B, 3D-1, or 3D-2 views

### Exit Criteria (Met)
- Active assignee sees start/hold/resume/complete buttons/forms when status allows
- Start POST ASSIGNED -> IN_PROGRESS
- Hold POST requires comment and transitions IN_PROGRESS -> ON_HOLD
- Resume POST ON_HOLD -> IN_PROGRESS
- Complete POST IN_PROGRESS -> COMPLETED
- All Phase 3D-3 tests pass (Roo: targeted tests only; user manually ran full test suite and confirmed it passed)

---

### Phase 3D-4 — Detail Template Integration and End-to-End Tests

**Status:** Complete

### Implemented
- `_build_detail_context()` includes `assignment_form` when `action_context.can_assign` is True
- Attachment upload error re-render context consistency tests
- `ProjectRequestWorkflowEndToEndTest` — end-to-end workflow coverage:
  - submit -> approve -> assign -> start -> complete
  - submit -> approve -> claim -> start -> hold -> resume -> complete
  - submit -> reject
  - reassign workflow
  - ON_HOLD cannot complete from UI
- `ProjectRequestDetailWorkflowIntegrationTest` — detail workflow integration coverage:
  - DRAFT shows no workflow controls
  - REVIEWING shows approve/reject only to valid approver
  - APPROVED shows assign/claim according to permissions
  - ASSIGNED shows start according to permissions
  - IN_PROGRESS shows hold/complete
  - ON_HOLD shows resume and not complete
  - COMPLETED shows no workflow controls
  - attachment.file.url is not exposed
  - POST forms include CSRF

### Phase 3D-4 Did NOT Implement
- dashboard
- model changes
- migration changes
- service-layer business logic changes
- new workflow routes/views
- FoxPro/external auth
- legacy migration

### Exit Criteria (Met)
- All workflow controls render correctly based on `action_context`
- End-to-end workflow test passes
- All Phase 3D-4 tests pass (Roo: targeted tests only; user manually ran full test suite and confirmed it passed)

---

### Phase 3D-5 — Hardening and Review

**Status:** Complete — PASS

### Summary
- Phase 3D-5A was a read-only final hardening review. No code or files were modified.
- Review verdict: PASS.
- Targeted review checks passed:
  - `manage.py check`: no issues
  - `makemigrations --check --dry-run`: no changes detected
  - ProjectRequestWorkflowEndToEndTest: 6 OK
  - ProjectRequestDetailWorkflowIntegrationTest: 10 OK
  - ProjectRequestApproveRejectViewTest: OK
  - ProjectRequestAssignClaimViewTest: 36 OK
  - ProjectRequestExecutionViewTest: 41 OK
  - Total targeted tests: 116 OK
- User manually ran full test suite after Phase 3D-4 and confirmed it passed.
- Review confirmed:
  - Views are thin wrappers around services
  - No business logic duplication in views
  - Template workflow controls are gated by action_context
  - No direct attachment.file.url exposure
  - CSRF and POST-only pattern are enforced
  - URL scope is clean
  - Tests are meaningful and use real POST routes
  - No blockers

### Non-Blocking Cleanup Items (Moved to Technical Debt)
- `views.py` module docstring says Phase 2B (stale)
- Some test names/comments are historically stale after later Phase 3D subphases
- Light test helper refactor could reduce duplication but is optional
- Extra black-box create-to-complete UI flow is not needed now

### Exit Criteria (Met)
- Targeted review checks passed
- Views confirmed as thin wrappers
- No business logic duplication in views
- No blockers

---

## Phase 3D Summary

| Subphase | Description | Status |
|----------|-------------|--------|
| **Phase 3D-1** | Approve/Reject UI | **Complete** |
| **Phase 3D-2** | Assign/Claim UI | **Complete** |
| **Phase 3D-3** | Start/Hold/Resume/Complete UI | **Complete** |
| **Phase 3D-4** | Detail template integration and end-to-end tests | **Complete** |
| **Phase 3D-5** | Hardening and review | **Complete — PASS** |

**Phase 3D is complete.**

---

## Phase 3 — Complete

**Status:** Complete (3A, 3B, 3C, 3D all complete)

- Phase 3A: Approve/Reject services and permission helpers
- Phase 3B: Assignment/Claim services and permission helpers
- Phase 3C: Execution workflow services (Start/Hold/Resume/Complete)
- Phase 3D: Workflow UI integration (3D-1 through 3D-5A)

---

## Phase 4 — Dashboard, Polish, Legacy Migration, External Auth

**Status:** Phase 4B complete. Phase 4E documentation sync in progress. Phase 4C, 4D, 4F deferred/blocked.

### Scope
- Dashboard views and summaries
- External authentication integration (FoxPro/external auth)
- Legacy data migration assessment
- UI polish and accessibility improvements

### Phase 4 Subphases

| Subphase | Type | Status |
|----------|------|--------|
| **Phase 4A** | Dashboard selector design | **Complete** |
| **Phase 4B** | Dashboard implementation | **Complete** |
| **Phase 4C** | UI polish and usability hardening | **Deferred** |
| **Phase 4D** | Legacy migration assessment | **Deferred** |
| **Phase 4E** | FoxPro/external auth architecture planning | **Documentation sync in progress — not yet approved** |
| **Phase 4F** | FoxPro/external auth implementation | **BLOCKED — requires Phase 4E approved + prerequisites explicit** |

### Phase 4B — Complete

**Status:** Complete. Implemented dashboard selectors, ProjectRequestDashboardView, dashboard URL, dashboard template, dashboard navbar link, dashboard tests.

### Phase 4C — Deferred

Phase 4C is deferred. Not started.

### Phase 4D — Deferred

Phase 4D is deferred. Not started.

### Phase 4E — Documentation Sync In Progress

**Status:** Documentation synchronization cleanup in progress (this task). Not yet approved.

Phase 4E architecture in `documents/FOXPRO_AUTH_PLAN.md`:
- **Pattern:** Signed Launch URL with HMAC-SHA256 (NOT token exchange)
- **Endpoint:** `GET /auth/foxpro-launch/`
- **App:** New `external_auth` Django app
- **Models:** `FoxproLaunchAttempt` + `FoxproLaunchNonce` only
- **FoxPro `o`:** Audit-only, NOT used for Django authorization
- **User mapping:** `employee_id` first, fallback `username`; no auto-create
- **Return URL:** Named route allowlist + `reverse()`; `admin:index` NOT in pilot

### Phase 4F — BLOCKED

**Phase 4F is blocked** until Phase 4E docs are synchronized/approved AND prerequisites are explicit.

**Prerequisites required before Phase 4F:**
1. Helper EXE/DLL secret protection choice finalized
2. Shared secret generated and stored
3. Terminal server static IP / allowlist value confirmed
4. Timestamp convention selected (UTC or terminal-server-local)
5. Helper I/O contract finalized
6. Legacy fallback approval/sunset (if needed)

**Phase 4F subphases (when unblocked):**
- Phase 4F-1: external_auth app + models + settings
- Phase 4F-2: Signed launch validation view + tests
- Phase 4F-3: FoxPro 5/helper integration test
- Phase 4F-4: Legacy fallback (ONLY if explicitly approved)

### Exit Criteria (not yet applicable for Phase 4C+)
- Dashboard displays correct data
- External auth integration functional
- Legacy data migrated
- Full regression test suite passes
