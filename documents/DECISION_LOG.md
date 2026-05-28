# Decision Log

> ADR-style entries for key architectural and design decisions.

---

## Custom User Model

- **Decision:** Use `accounts.User` extending `AbstractUser`
- **Reason:** Fresh project; changing `AUTH_USER_MODEL` later is painful. Supports `employee_id`, `display_name`, and future identity sync.
- **Rejected alternatives:** Default Django User, separate UserProfile model
- **Phase:** Phase 0

---

## Department-Scoped Access Level via UserDepartment

- **Decision:** Use `UserDepartment` model for department-specific access level
- **Reason:** Users may belong to multiple departments with different roles (e.g., Staff in Accounting, Manager in MIS). Legacy system supports multi-department users.
- **Rejected alternatives:** Global `user.access_level` field
- **Phase:** Phase 0

---

## No Global access_level on User

- **Decision:** Do NOT use a global `user.access_level` field
- **Reason:** Access level is department-specific. A single global value cannot represent multi-department roles.
- **Rejected alternatives:** Single `access_level` on User model
- **Phase:** Phase 0

---

## Department Model Fields

- **Decision:** Department model fields are `dept_code` and `dept_name`
- **Reason:** Matches legacy department structure; `dept_code` provides short identifier, `dept_name` provides display name.
- **Rejected alternatives:** Single `name` field, numeric codes only
- **Phase:** Phase 0

---

## Project Department = Delivery/Completion Department

- **Decision:** "Project Department" means the delivery/completion department (the department receiving and fulfilling the request)
- **Reason:** Clarifies terminology. The requestor submits TO a project department.
- **Rejected alternatives:** Calling it "target department" or "receiving department"
- **Phase:** Phase 1

---

## Configurable Project Departments

- **Decision:** Project Departments are configurable via `ProjectDepartmentProfile`, not hard-coded to MIS/IT
- **Reason:** Enterprise system should support any department as a project department. Keeps `accounts.Department` clean.
- **Rejected alternatives:** Hard-coded MIS/IT departments, boolean flag on Department model
- **Phase:** Phase 1

---

## Request Number Format

- **Decision:** Format is `PRJ-{YYYY}-{6-digit sequence}` (e.g., `PRJ-2026-000001`)
- **Reason:** Human-readable, year-scoped sequence, sortable, matches enterprise conventions.
- **Rejected alternatives:** UUID, auto-increment integer, global sequence without year
- **Phase:** Phase 1

---

## Request Number Generated on Draft Creation

- **Decision:** `request_no` is generated when draft is created (not on submission)
- **Reason:** Avoids multiple drafts sharing empty string under unique constraint. Drafts may be abandoned, leaving acceptable gaps.
- **Rejected alternatives:** Generate on submission, use signals
- **Phase:** Phase 1

---

## create_project_request_draft Always Forces DRAFT

- **Decision:** `create_project_request_draft()` always sets `status=DRAFT` regardless of caller-provided status
- **Reason:** Prevents accidental creation of requests in wrong status. Draft is the safe initial state.
- **Rejected alternatives:** Accept caller-provided status
- **Phase:** Phase 2A

---

## Draft May Be Incomplete; Submit Validation Enforces Required Fields

- **Decision:** Draft allows incomplete/null fields. `submit_project_request()` validates required fields at submit time.
- **Reason:** Users need to save partial work. Required validation only matters when the request enters the workflow.
- **Rejected alternatives:** Require all fields at draft creation
- **Phase:** Phase 2A

---

## Status Values Use TextChoices

- **Decision:** Use `models.TextChoices` for all status/role/type enums
- **Reason:** Readable string codes in DB, type-safe in Python, no magic numbers.
- **Rejected alternatives:** Integer choices, separate lookup tables
- **Phase:** Phase 1

---

## Approval Tasks Are Project-Specific

- **Decision:** Use `ProjectRequestApprovalTask` in `project_requests` app (no generic approvals app)
- **Reason:** Fresh project with no existing approvals app. Project-specific approval rules (department + access level scoped) don't justify a generic engine at this stage.
- **Rejected alternatives:** Generic approvals app with ApprovalRule/ApprovalTask
- **Phase:** Phase 1

---

## Approval Generation Uses Department-Scoped Helpers

- **Decision:** Approval generation uses `accounts.services` helpers (`is_staff_in_department`, `is_manager_or_above`, `is_vp_or_above`)
- **Reason:** Access level is department-specific. All role checks must be scoped to the relevant department.
- **Rejected alternatives:** Global user role checks, hard-coded access level comparisons
- **Phase:** Phase 2A

---

## Activity Logs Are Append-Only / Immutable

- **Decision:** `ProjectRequestActivityLog` entries are immutable by convention (no update/delete methods)
- **Reason:** Audit trail must be trustworthy. Any new information is added as a new log entry.
- **Rejected alternatives:** Allow editing log entries, soft-delete logs
- **Phase:** Phase 2A

---

## Permission-Checked Attachment Access

- **Decision:** Attachments require permission-checked access; no direct `file.url` access for protected downloads
- **Reason:** Prevents unauthorized access to uploaded files. Upload permission uses `can_attach_file()`. Download permission must use `can_view_project_request()` or a dedicated `can_download_attachment()`. Upload and download permissions are not the same. Protected downloads must never use direct `attachment.file.url` in templates.
- **Rejected alternatives:** Direct URL access via `attachment.file.url` in templates
- **Phase:** Phase 2A

---

## Duplicate Prevention Rules

- **Decision:** Duplicate = same requester + same request_type + normalized project_name (trim + lowercase) + status in OPEN_STATUSES
- **Reason:** Prevents users from accidentally submitting the same request multiple times while allowing re-submission after completion/rejection.
- **Rejected alternatives:** Exact string match only, check all statuses
- **Phase:** Phase 2A

---

## Claimable Definition

- **Decision:** Claimable means:
  - `ProjectRequest.status` == APPROVED only
  - no active assignments exist
  - `project_department` exists and is active
  - active `ProjectDepartmentProfile` exists for `project_department`
  - `ProjectDepartmentProfile.allow_staff_claim` == True
  - user has active `UserDepartment` membership in `project_department`
- **Reason:** Allows project department staff to pick up approved work. The `allow_staff_claim` flag lets admins control this per-department. Additional guards (active department, active profile, active membership) prevent claims against non-functional or misconfigured departments.
- **Rejected alternatives:** Auto-assign only, allow claim on any open status
- **Phase:** Phase 2A
- **Amended by Phase 3B:**
  - ASSIGNED requests are NOT claimable.
  - Reassignment for ASSIGNED requests must go through `assign_project_request()`.
  - Claim is strictly APPROVED -> ASSIGNED only.

---

## Phase 3A Approval/Reject Workflow Rules

- **Decision:** Phase 3A approval/reject workflow uses `ProjectRequestApprovalTask` as the source of approval action. Pending approval tasks are actionable only when parent `ProjectRequest.status == REVIEWING`. Rejection immediately transitions `ProjectRequest` to `REJECTED`. Approval transitions `ProjectRequest` to `APPROVED` only when all approval tasks are `APPROVED`.
- **Reason:** Prevents stale pending approvals from rejected requests. Keeps workflow state deterministic. Avoids false approval if any approval task is rejected or otherwise non-approved.
- **Rejected alternatives:** Treat no PENDING tasks as equivalent to all approved. Leave rejected requests' pending tasks actionable.
- **Phase:** Phase 3A

---

## Phase 3B/3C Service-Layer Only; Phase 3D Owns UI Integration

- **Decision:** Phase 3B and Phase 3C are service-layer workflow phases only. Phase 3D owns workflow UI integration.
- **Reason:** Keeps workflow business logic testable before exposing actions in views/templates.
- **Rejected alternatives:** Implementing assignment/claim UI before services are independently stable.
- **Phase:** Phase 3 planning

---

## Phase 3B Assignment/Claim Service Rules

- **Decision:** Phase 3B assignment and claim services enforce the following rules:
  - `assign_project_request()` allows APPROVED or ASSIGNED status:
    - APPROVED -> ASSIGNED is initial assignment.
    - ASSIGNED -> ASSIGNED is reassignment.
  - Reassignment deactivates existing active assignments before creating the new active assignment.
  - `claim_project_request()` allows APPROVED -> ASSIGNED only.
  - `claim_project_request()` does NOT allow ASSIGNED (already-assigned requests cannot be claimed).
  - Assignment blocks inactive `project_department` and inactive/missing `ProjectDepartmentProfile`.
- **Reason:** Prevents assigning to non-functional departments. Ensures clean assignment history by deactivating old assignments on reassignment. Claim is restricted to APPROVED state to prevent staff from hijacking already-assigned work. Reassignment requires explicit `assign_project_request()` call, not claim.
- **Rejected alternatives:** Allow assignment to inactive departments. Allow claim from any status. Keep old active assignments alongside new ones. Allow claim on ASSIGNED requests.
- **Phase:** Phase 3B (implemented by minimax-m2.7)

---

## Phase 3C Execution Workflow — Service-Layer Only

- **Decision:** Phase 3C execution workflow is service-layer only. Active assignee, project department manager/director/VP, and superuser may execute workflow actions when status allows and at least one active assignment exists. ON_HOLD cannot complete directly; must resume before completion. Hold requires a comment. User comments are stored in ActivityLog.comment; descriptions remain short system action labels.
- **Reason:** Keeps execution workflow deterministic and auditable. Prevents UI exposure before service-layer behavior is stable.
- **Rejected alternatives:**
  - Allowing only active assignee to execute actions.
  - Allowing ON_HOLD -> COMPLETED directly.
  - Mixing user comments into ActivityLog.description.
- **Phase:** Phase 3C (implemented by minimax-m2.7)

---

## Phase 3D-2 Assign/Claim UI Implementation

- **Decision:** Phase 3D-2 implements Assign/Claim UI as isolated POST action views without modifying the service layer.
- **Reason:** Keeps views as thin wrappers around existing Phase 3B services. AssignmentForm dynamically filters assigned_to queryset to active users in the project department.
- **Non-blocking hardening note:** `_build_detail_context()` used by attachment upload error re-render does not include `assignment_form` when `action_context.can_assign` is True. Can be addressed in Phase 3D-5 or earlier.
- **Phase:** Phase 3D-2

---

## Phase 3D-3 Start/Hold/Resume/Complete UI Implementation

- **Decision:** Phase 3D-3 implements Start/Hold/Resume/Complete UI as isolated POST action views without modifying the service layer.
- **Reason:** Keeps views as thin wrappers around existing Phase 3C services. HoldActionForm enforces required comment at form level. GenericCommentActionForm supports optional comments for start/resume/complete. Execution controls are gated by `action_context.can_start` / `can_hold` / `can_resume` / `can_complete`.
- **Implemented:**
  - `HoldActionForm` — hold action form with required comment
  - `GenericCommentActionForm` — optional comment form for start/resume/complete
  - `project_request_start` view — POST-only, transitions ASSIGNED -> IN_PROGRESS
  - `project_request_hold` view — POST-only, transitions IN_PROGRESS -> ON_HOLD (requires comment)
  - `project_request_resume` view — POST-only, transitions ON_HOLD -> IN_PROGRESS
  - `project_request_complete` view — POST-only, transitions IN_PROGRESS -> COMPLETED
  - Start/hold/resume/complete URL routes
  - Execution controls on detail page, gated by action_context flags
- **Did NOT implement:** dashboard, model changes, migration changes, service-layer business logic changes, FoxPro/external auth, legacy migration
- **Non-blocking hardening notes (deferred to Phase 3D-5):**
  - `_build_detail_context()` does not include `assignment_form` when `action_context.can_assign` is True.
  - `urls.py` module docstring may be stale and may not mention Phase 3D-3. Code-comment cleanup only.
- **Tests:** Roo ran targeted tests only. User manually ran full test suite and confirmed it passed.
- **Phase:** Phase 3D-3

---

## Phase 3D-4 Detail Template Integration and End-to-End Workflow Tests

- **Decision:** Phase 3D-4 completed detail template integration and end-to-end workflow tests.
- **Implemented:**
  - `_build_detail_context()` now includes `assignment_form` when `action_context.can_assign` is True
  - Attachment upload error re-render context consistency
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
- **Did NOT implement:** dashboard, model changes, migration changes, service-layer business logic changes, new workflow routes/views, FoxPro/external auth, legacy migration
- **Tests:** Roo ran targeted tests only. User manually ran full test suite and confirmed it passed.
- **Phase:** Phase 3D-4

---

## Phase 3D-5A Final Hardening Review — Complete

- **Decision:** Phase 3D-5A final hardening review is complete. VERDICT: PASS.
- Phase 3D-5A was **read-only**. No code, templates, URLs, or migrations were modified.
- **Targeted review checks passed:**
  - `manage.py check`: no issues
  - `makemigrations --check --dry-run`: no changes detected
  - ProjectRequestWorkflowEndToEndTest: 6 OK
  - ProjectRequestDetailWorkflowIntegrationTest: 10 OK
  - ProjectRequestApproveRejectViewTest: OK
  - ProjectRequestAssignClaimViewTest: 36 OK
  - ProjectRequestExecutionViewTest: 41 OK
  - Total: 116 targeted tests OK
- **Review confirmed:**
  - Views are thin wrappers around services
  - No business logic duplication in views
  - Template workflow controls are gated by action_context
  - No direct attachment.file.url exposure
  - CSRF and POST-only pattern are enforced
  - URL scope is clean
  - Tests are meaningful and use real POST routes
  - No blockers
- **Non-blocking cleanup items (moved to technical debt, not blockers):**
  - `views.py` module docstring says Phase 2B (stale)
  - Some test names/comments are historically stale after later Phase 3D subphases
  - Light test helper refactor could reduce duplication but is optional
  - Extra black-box create-to-complete UI flow is not needed now
- **Phase 3D is complete. Phase 3 is complete.**
- **Phase:** Phase 3D-5A / Phase 3D / Phase 3

---

## Phase 3 Complete

- **Decision:** Phase 3 is complete. All subphases (3A, 3B, 3C, 3D) are done.
- Phase 3A: Approve/Reject services, approval permission helpers, pending approval selector hardening, tests
- Phase 3B: Assignment/Claim services, permission helpers, tests
- Phase 3C: Execution workflow services (Start/Hold/Resume/Complete), permission helpers, action context enrichment, tests
- Phase 3D: Workflow UI integration — all subphases 3D-1 through 3D-5A complete
- **Next step:** Phase 4 planning. Implementation has NOT started.
- **Phase:** Phase 3

---

## Phase 4B Dashboard Implementation — Complete

- **Decision:** Phase 4B Dashboard implementation is complete and accepted.
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
  - No FoxPro/external auth implementation
  - No legacy migration implementation
- Non-blocking notes:
  - `views.py` module docstring still says Phase 2B (stale)
  - Admin Overview overdue count may be semantically "assigned overdue" rather than true global/admin overdue — consider Phase 4C/cleanup clarification
- Tests: **Roo ran targeted tests only**. **User manually ran full test suite and confirmed it passed.**
- **Next step:** Phase 4E documentation sync (documentation-only). Phase 4C, 4D, 4F are deferred.
- **Phase:** Phase 4B / Phase 4

---

## Phase 4E — FoxPro External Auth Architecture

- **Decision:** Phase 4E uses Signed Launch URL pattern (not token exchange) for FoxPro 5 compatibility
- **Architecture:** Signed Launch URL with HMAC-SHA256
  - FoxPro 5 builds normalized launch parameters
  - FoxPro 5 calls helper EXE/DLL for HMAC computation (shared secret never passed via command-line)
  - FoxPro 5 uses SHELLEXEC to open HMAC-signed URL
  - Django validates at `GET /auth/foxpro-launch/` in one request
  - Django creates session and redirects via `reverse()` to named route
- **App boundary:** New `external_auth` Django app (separate from `accounts` and `project_requests`)
- **Primary models:** `FoxproLaunchAttempt` + `FoxproLaunchNonce` only (NOT `LaunchSession`)
  - `FoxproLaunchAttempt` — all launch attempts logged (success and failure)
  - `FoxproLaunchNonce` — nonce reservation for replay prevention (atomically reserved after HMAC passes)
- **FoxPro `o` is audit-only:** Never used for Django authorization. Django permissions come from `accounts.User` / `Department` / `UserDepartment` only.
- **User mapping:** `employee_id` first, fallback `username`; case-insensitive, whitespace trimmed; no auto-create users in pilot
- **Return URL:** Named route allowlist + `reverse()`. `admin:index` NOT part of pilot. Do not hard-code external paths.
- **Validation order:**
  1. IP allowlist
  2. Required params
  3. Timestamp format / age
  4. HMAC over raw normalized values including return
  5. Invalid HMAC must NOT reserve nonce
  6. After HMAC passes, atomically reserve nonce_hash in FoxproLaunchNonce
  7. Reused nonce must still create failed FoxproLaunchAttempt
  8. Validate return named route allowlist
  9. Map user
  10. Validate active Department
  11. Validate active UserDepartment
  12. login()
  13. Audit log
  14. Redirect via reverse()
- **Pilot prerequisites (required before Phase 4F):**
  1. Helper EXE/DLL secret protection choice finalized (config file / env / embedded)
  2. Shared secret generated and stored
  3. Terminal server static IP / allowlist value confirmed
  4. Timestamp convention selected (UTC or terminal-server-local)
  5. Helper I/O contract finalized
  6. Legacy fallback approval/sunset (if needed)
- **Deployment topology:** Central terminal/server with helper EXE/DLL (Option B). FoxPro runs on shared server, not each workstation.
- **User-facing errors:** Must be generic ("Unable to launch. Please contact IT support."). Internal audit `failure_reason` keeps detailed codes.
- **Legacy fallback:** Only if explicitly approved with sunset. NOT approved for pilot.
- **Rejected alternatives:**
  - Token exchange (`LaunchSession`, `/auth/launch-token/`, `/auth/launch/`) — requires JSON parsing in FoxPro 5
  - Direct HMAC in FoxPro 5 — FoxPro 5 unlikely to support native HMAC
  - Broad IP allowlist for pilot — terminal server static IP only
- **Phase:** Phase 4E (documentation sync in progress, not yet approved)
