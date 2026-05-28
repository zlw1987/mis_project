# AI Change Log

> Phase-level log of AI-assisted work on MIS_PROJECT.

---

## Phase 0

- Phase 0 completed: Django foundation and accounts app
- Phase 0 hardening completed

## Phase 1

- Phase 1 completed: `project_requests` foundation (models, admin, tests)
- Phase 1 hardening completed

## Phase 2A

- Phase 2A completed: service layer, permissions, selectors, request number, submit workflow, attachment upload
- Phase 2A hardening patches completed
- Final Phase 2A correctness patch completed
- Minimax-m2.7 independent review: **PASS**

## Phase 2B

- Phase 2B completed: forms, views, templates (list, detail, create, attachment download)
- Phase 2B hardening completed
- Minimax-m2.7 independent review: **PASS**
- User-observed full test suite: 218 tests OK

## Phase 3A

- Phase 3A completed: Approve/Reject services, approval permission helpers, pending approval selector hardening, tests
- Implemented by minimax-m2.7
- Phase 3A hardening patch applied:
  - Superuser pending approval selector fix
  - Superuser action context fix
  - Stale DB status tests for approve/reject
  - `approve_project_request` now transitions to APPROVED only when all approval tasks are APPROVED
- User-observed full test suite: **267 tests OK**
- minimax-m2.7 developer test was successful

## Phase 3B

- Phase 3B completed: Assignment/Claim services, permission helpers, tests
- Implemented by minimax-m2.7
- Changed code areas:
  - `project_requests/permissions.py`
  - `project_requests/services.py`
  - `project_requests/tests.py`
- Implemented:
  - `can_assign_project_request` hardening
  - `assign_project_request()` service
  - `claim_project_request()` service
  - Assignment blocks inactive `project_department`
  - Assignment blocks inactive or missing `ProjectDepartmentProfile`
  - Claim only allows APPROVED -> ASSIGNED
  - Reassignment deactivates old active assignment
  - `get_assigned_to_me` regression tests
- No views, forms, templates, or URLs were implemented
- Full test suite manually verified by user after implementation

## Phase 3C

- Phase 3C completed: Execution workflow services (Start/Hold/Resume/Complete), permission helpers, action context enrichment, tests
- Implemented by minimax-m2.7
- Changed code areas:
  - `project_requests/permissions.py`
  - `project_requests/services.py`
  - `project_requests/tests.py`
- Implemented:
  - `can_start_project_request()` permission helper
  - `can_hold_project_request()` permission helper
  - `can_resume_project_request()` permission helper
  - `can_complete_project_request()` permission helper
  - `start_project_request()` service — ASSIGNED -> IN_PROGRESS
  - `hold_project_request()` service — IN_PROGRESS -> ON_HOLD (requires comment)
  - `resume_project_request()` service — ON_HOLD -> IN_PROGRESS
  - `complete_project_request()` service — IN_PROGRESS -> COMPLETED
  - `get_project_request_action_context()` enriched with can_start/can_hold/can_resume/can_complete
  - All execution actions require at least one active assignment
  - ON_HOLD cannot complete directly; must resume first
  - Start requires active project_department and active ProjectDepartmentProfile
  - Hold requires a comment
  - ActivityLog.description stores short action description; ActivityLog.comment stores user-provided comment
- No views, forms, templates, or URLs were implemented
- Full test suite manually verified by user after implementation

## Phase 3D-1

- Phase 3D-1 completed: Approve/Reject UI integration
- Implemented by minimax-m2.7
- Changed code areas:
  - `project_requests/forms.py` — added `ApprovalActionForm`, `RejectActionForm`
  - `project_requests/views.py` — added `project_request_approve`, `project_request_reject`
  - `project_requests/urls.py` — added approve/reject URL routes
  - `project_requests/tests_views.py` — added approve/reject view tests
  - `templates/project_requests/projectrequest_detail.html` — added approval task controls
- Implemented:
  - `ApprovalActionForm` — approve action form with optional comment
  - `RejectActionForm` — reject action form with required comment
  - `project_request_approve` view — POST-only, validates task belongs to request
  - `project_request_reject` view — POST-only, validates task belongs to request
  - Approve/reject URL routes (`/<int:pk>/approve/`, `/<int:pk>/reject/`)
  - Approve/reject template controls gated by `action_context.can_approve_any_task` / `can_reject_any_task`
  - Nullable `task.acted_by` and `log.actor` safe rendering in templates
  - Stale future action HTML comments removed from detail template
- Tests: Roo ran targeted tests only (ProjectRequestApproveRejectViewTest: 29/29, ProjectRequestDetailViewTest: 6/6). User manually runs full test suite.
- Phase 3D-2 (Assign/Claim UI) is next.

## Phase 3D-2

- Phase 3D-2 completed: Assign/Claim UI integration
- Changed code areas:
  - `project_requests/forms.py` — added `AssignmentForm` with dynamic assigned_to queryset
  - `project_requests/views.py` — added `project_request_assign`, `project_request_claim`
  - `project_requests/urls.py` — added assign/claim URL routes
  - `project_requests/tests_views.py` — added `ProjectRequestAssignClaimViewTest`
  - `templates/project_requests/projectrequest_detail.html` — added assignment form and claim button
- Implemented:
  - `AssignmentForm` — assignment form with dynamic assigned_to queryset filtering active users in project department
  - `project_request_assign` view — POST-only, creates/replaces assignment, transitions APPROVED->ASSIGNED or ASSIGNED->ASSIGNED
  - `project_request_claim` view — POST-only, allows staff to self-claim APPROVED requests
  - Assign/claim URL routes (`/<int:pk>/assign/`, `/<int:pk>/claim/`)
  - Assignment form gated by `action_context.can_assign`
  - Claim button gated by `action_context.can_claim`
- Non-blocking hardening note: `_build_detail_context()` does not include `assignment_form` when `action_context.can_assign` is True; can be addressed in Phase 3D-5 or earlier
- Tests: Roo ran targeted tests only (ProjectRequestAssignClaimViewTest). User manually runs full test suite.
- Phase 3D-3 (Start/Hold/Resume/Complete UI) is next.

## Phase 3D-3

- Phase 3D-3 completed: Start/Hold/Resume/Complete UI integration
- Changed code areas:
  - `project_requests/forms.py` — added `HoldActionForm`, `GenericCommentActionForm`
  - `project_requests/views.py` — added `project_request_start`, `project_request_hold`, `project_request_resume`, `project_request_complete`
  - `project_requests/urls.py` — added start/hold/resume/complete URL routes
  - `project_requests/tests_views.py` — added execution view tests
  - `templates/project_requests/projectrequest_detail.html` — added execution controls
- Implemented:
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
- Phase 3D-3 did NOT implement: dashboard, model changes, migration changes, service-layer business logic changes, FoxPro/external auth, legacy migration
- Tests: Roo ran targeted tests only. User manually ran full test suite and confirmed it passed.
- Phase 3D-4 (Detail template integration and end-to-end workflow tests) is next.

## Phase 3D-4

- Phase 3D-4 completed: Detail template integration and end-to-end workflow tests
- Implemented:
  - `_build_detail_context()` now includes `assignment_form` when `action_context.can_assign` is True
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
- Phase 3D-4 did NOT implement: dashboard, model changes, migration changes, service-layer business logic changes, new workflow routes/views, FoxPro/external auth, legacy migration
- Tests: Roo ran targeted tests only. User manually ran full test suite and confirmed it passed.

## Phase 3D-5A

- Phase 3D-5A completed: Final hardening review — PASS
- Phase 3D-5A was **read-only**. No code, templates, URLs, or migrations were modified.
- Review verdict: **PASS**
- Targeted review checks passed:
  - `manage.py check`: no issues
  - `makemigrations --check --dry-run`: no changes detected
  - ProjectRequestWorkflowEndToEndTest: 6 OK
  - ProjectRequestDetailWorkflowIntegrationTest: 10 OK
  - ProjectRequestApproveRejectViewTest: OK
  - ProjectRequestAssignClaimViewTest: 36 OK
  - ProjectRequestExecutionViewTest: 41 OK
  - Total targeted tests: 116 OK
- Review confirmed:
  - Views are thin wrappers around services
  - No business logic duplication in views
  - Template workflow controls are gated by action_context
  - No direct attachment.file.url exposure
  - CSRF and POST-only pattern are enforced
  - URL scope is clean
  - Tests are meaningful and use real POST routes
  - No blockers
- Optional cleanup items identified (non-blocking, not required):
  - `views.py` module docstring says Phase 2B (stale)
  - Some test names/comments are historically stale after later Phase 3D subphases
  - Light test helper refactor could reduce duplication but is optional
  - Extra black-box create-to-complete UI flow is not needed now
- Phase 3D is now complete. Phase 3 is complete.

## Phase 3 Complete

- Phase 3 is complete. All subphases (3A, 3B, 3C, 3D) are done.
- Phase 3A: Approve/Reject services, approval permission helpers, pending approval selector hardening, tests
- Phase 3B: Assignment/Claim services, permission helpers, tests
- Phase 3C: Execution workflow services (Start/Hold/Resume/Complete), permission helpers, action context enrichment, tests
- Phase 3D: Workflow UI integration — all subphases 3D-1 through 3D-5A complete
- Phase 4 planning is next.

## Phase 4B

- Phase 4B completed: Dashboard implementation
- Implemented:
  - Dashboard selectors in `project_requests/selectors.py`
  - `ProjectRequestDashboardView`
  - `project_requests:dashboard` URL
  - `templates/project_requests/dashboard.html`
  - Dashboard navbar link in `base.html`
  - `ProjectRequestDashboardSelectorTest`
  - `ProjectRequestDashboardViewTest`
- Properties:
  - Dashboard is read-only GET-only
  - Dashboard has no POST forms and no workflow action buttons
  - Dashboard reuses existing selectors/visibility logic
  - No model/migration changes
- Non-blocking notes:
  - `views.py` module docstring still says Phase 2B (stale)
  - Admin Overview overdue count may be semantically "assigned overdue" rather than true global/admin overdue — consider Phase 4C/cleanup clarification
- Tests: **Roo ran targeted tests only**. **User manually ran full test suite and confirmed it passed.**

## Phase 4E

- Phase 4E FoxPro auth architecture planning was drafted in `documents/FOXPRO_AUTH_PLAN.md`
- **Final Phase 4E documentation synchronization cleanup in progress** (this task)
- No code/templates/URLs/migrations were modified in this task
- Architecture: Signed Launch URL with HMAC-SHA256 (NOT token exchange)
- App: New `external_auth` Django app (planned, not implemented)
- Models: `FoxproLaunchAttempt` + `FoxproLaunchNonce` (planned, not implemented)
- Endpoint: `GET /auth/foxpro-launch/` (planned, not implemented)
- FoxPro `o` is audit-only; Django permissions come from `accounts.User` / `Department` / `UserDepartment` only
- User mapping: `employee_id` first, fallback `username`; no auto-create users in pilot
- Return URL: named route allowlist + `reverse()`; `admin:index` NOT part of pilot
- **Phase 4F implementation has not started**
- **Phase 4F is blocked** until Phase 4E docs synchronized/approved and prerequisites explicit:
  1. Helper EXE/DLL secret protection choice finalized
  2. Shared secret generated and stored
  3. Terminal server static IP / allowlist value confirmed
  4. Timestamp convention selected (UTC or terminal-server-local)
  5. Helper I/O contract finalized
  6. Legacy fallback approval/sunset (if needed)

## Phase 3 Planning

- Phase 3B/3C/3D scope wording corrected so Phase 3B and 3C remain service-layer phases; UI actions deferred to Phase 3D.

### Optional Future Test Hardening

- List view tests for:
  - Superuser
  - Request department manager
  - Project department manager
  - Assigned user

## Incident Log

- **False test-pass incident:** AI claimed tests passed before full terminal output was verified. User manually ran tests and found 6 errors. Errors were fixed and full test suite later passed (164 tests OK).

## Environment Hardening

- `.venv` created
- `requirements.txt` added
- README local setup updated
