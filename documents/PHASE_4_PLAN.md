# Phase 4 — Dashboard, Polish, Legacy Migration Assessment, FoxPro/External Auth Planning

> **Status:** Phase 4B complete. Phase 4F implementation complete; MIS-8 pilot-readiness verification in progress. Phase 4C, 4D deferred.
> **Model:** minimax-m2.7
> **Date:** 2026-05-27
> **Last Updated:** 2026-08-11 (MIS-8 pilot-readiness documentation/deployment-verification)
> **Prerequisite:** Phase 3 complete. Phase 3D-5A final hardening review PASS.

---

## READY / CONDITIONAL READY / NOT READY

**Phase 4B: COMPLETE**

Phase 4B implementation is complete. Implemented: dashboard selectors in selectors.py, ProjectRequestDashboardView, project_requests:dashboard URL, dashboard.html template, dashboard navbar link in base.html, ProjectRequestDashboardSelectorTest, ProjectRequestDashboardViewTest.

**Phase 4C: DEFERRED**

Phase 4C (UI polish) remains deferred. Not started.

**Phase 4F (FoxPro auth): Implementation complete; pilot readiness pending.**

Phase 4F code implementation is complete, but pilot/go-live is NOT approved until:
1. `python manage.py check` passes
2. `python manage.py makemigrations --check --dry-run` passes
3. `python manage.py test external_auth -v 2` passes
4. User manually runs full test suite

### Repository state — not proof of runtime deployment

Django source currently expects/configures:
- `FOXPRO_SIGNATURE_MODE='legacy_v2'`
- `FOXPRO_LAUNCH_MAX_AGE_SECONDS=15`
- `FOXPRO_V2_SECRET` in source is a placeholder and does not prove runtime secret
- `FOXPRO_ALLOWED_IPS` in source contains localhost testing defaults and does not prove runtime IP configuration
- `FOXPRO_TRUST_X_FORWARDED_FOR=False` is the repository default and must be verified against actual proxy topology

### Runtime / deployment verification required before pilot

1. Actual runtime `FOXPRO_V2_SECRET` is strong and non-placeholder.
2. FoxPro signing secret exactly matches Django runtime secret.
3. FoxPro canonicalization/signature generation matches MIS2|n|ln|dp|t|o|d|nonce|return and external_auth/signature.py.
4. Actual runtime `FOXPRO_SIGNATURE_MODE='legacy_v2'` confirmed.
5. Actual runtime `FOXPRO_LAUNCH_MAX_AGE_SECONDS=15` confirmed.
6. `FOXPRO_LAUNCH_TIMEZONE` matches deployed workstation behavior.
7. Actual `FOXPRO_ALLOWED_IPS` matches deployment topology.
8. `FOXPRO_TRUST_X_FORWARDED_FOR` matches trusted proxy topology.
9. Migration 0002_add_unsupported_signature_mode is applied to the actual pilot database.
10. Transport protection is confirmed for the signed-launch path.
11. Valid FoxPro → Django E2E launch succeeds.
12. Invalid signature is rejected.
13. Expired timestamp is rejected.
14. Previously used nonce is rejected.
15. Audit behavior is reviewed.

**Transport note:** Nonce uniqueness prevents second use of a nonce, but an unused valid signed URL remains a short-lived single-use credential until first redemption. An observer who obtains and submits it first can race the legitimate browser.

**Current active work:** MIS-8 pilot-readiness verification. No code implementation.

**Hard scope reminders:**
- Documentation only — no Python code, templates, URLs, migrations, or legacy_php modifications
- Phase 4C must NOT start until planned and approved
- Phase 4D remains deferred unless explicitly un-deferred
- Phase 4E architecture: **Signed Launch URL, NOT token exchange**
- Phase 4F implementation is complete; pilot readiness is pending verification steps above

---

## 0. Phase 4B Completion Notes

**Phase 4B is complete.** User manually ran full test suite and confirmed it passed.

### Implemented

- Dashboard selectors in `project_requests/selectors.py`
- `ProjectRequestDashboardView`
- `project_requests:dashboard` URL
- `templates/project_requests/dashboard.html`
- Dashboard navbar link in `base.html`
- `ProjectRequestDashboardSelectorTest`
- `ProjectRequestDashboardViewTest`

### Properties

- Dashboard is read-only GET-only
- Dashboard has no POST forms and no workflow action buttons
- Dashboard reuses existing selectors/visibility logic
- No model/migration changes
- No FoxPro/external auth implementation
- No legacy migration implementation

### Non-Blocking Notes

- `views.py` module docstring still says Phase 2B (stale, from earlier phases)
- Admin Overview overdue count may be semantically "assigned overdue" rather than true global/admin overdue — consider Phase 4C/cleanup clarification

---

## 1. Dashboard Planning

> **Important:** Dashboard must not bypass existing selectors/permissions. Dashboard must reuse existing service/selector/permission logic. Dashboard must not introduce new workflow actions.

### 1.1 Dashboard Scope Principles

- Dashboard is a read-only view that surfaces existing data through existing selectors.
- No new workflow actions, service functions, or permission helpers should be introduced by the dashboard.
- Dashboard view must call existing selectors (`get_visible_project_requests`, `get_my_project_requests`, `get_assigned_to_me`, `get_my_pending_approval_tasks`, `get_overdue_project_requests`, etc.).
- Dashboard counts and lists must be permission-gated based on the same rules as existing views.
- Superuser dashboard may show aggregate statistics but must not expose data outside the superuser's existing visibility scope.

### 1.2 Proposed Dashboard Sections

#### For All Authenticated Users

| Section | Purpose | Selector/Queryset | Notes |
|---------|---------|-------------------|-------|
| **My Drafts** | User's own DRAFT requests | `get_dashboard_my_drafts(user)` | New dashboard selector |
| **My Open Requests** | User's non-terminal requests (excludes DRAFT and terminal) | `get_dashboard_my_open_requests(user)` | New dashboard selector |
| **My Pending Approval Tasks** | Approval tasks user can act on | `get_dashboard_pending_approval_tasks(user)` | Existing selector |
| **My Assigned Requests** | Requests actively assigned to user | `get_dashboard_assigned_to_me(user)` | Existing selector |
| **My Overdue Requests** | Assigned requests past needed_by_date | `get_overdue_project_requests(user)` | Existing selector |

#### For Project Department Staff (allow_staff_claim=True)

| Section | Purpose | Selector | Notes |
|---------|---------|----------|-------|
| **Claimable Requests** | APPROVED, no active assignment, allow_staff_claim=True | `get_dashboard_claimable_requests(user)` | New selector; uses Exists subquery; no Python loop |

#### For Project Department Manager/Director/VP

| Section | Purpose | Selector | Notes |
|---------|---------|----------|-------|
| **Project Dept Queue** | Non-terminal requests in managed project dept | `get_dashboard_project_department_queue(user)` | New selector |
| **In Progress / On Hold** | Active work in managed project dept | `get_dashboard_in_progress_or_on_hold(user)` | New selector |
| **Recently Completed** | Completed in managed dept (last 30 days) | `get_dashboard_recently_completed(user, days=30)` | New selector |

#### For Superuser Only

| Section | Purpose | Notes |
|---------|---------|-------|
| **Admin Overview** | Aggregate counts by status | `get_dashboard_status_counts(user)` |
| **All Pending Approvals** | All REVIEWING requests with pending tasks | Uses existing superuser-elevated `get_my_pending_approval_tasks` |

### 1.3 Who Sees What Dashboard

| User Type | Dashboard Sections |
|-----------|-------------------|
| **Regular staff** (no approval authority, not in project dept) | My Drafts, My Open Requests, My Assigned Requests, My Overdue |
| **Request dept manager** | My Drafts, My Open Requests, My Assigned Requests, My Overdue, My Pending Approval Tasks |
| **Project dept staff** (allow_staff_claim=True) | Above + Claimable Requests |
| **Project dept manager/director/VP** | Above + Claimable, Project Dept Queue, In Progress/On Hold, Recently Completed |
| **Superuser** | All sections including Admin Overview |

---

### 1.4 Phase 4A — Detailed Selector Design

Phase 4A produces this selector design. No implementation code is written in Phase 4A. The design below must be approved before Phase 4B begins.

#### Selector Naming Convention

All new dashboard selectors are prefixed `get_dashboard_` to distinguish them from existing selectors. Dashboard selectors live in `project_requests/selectors.py` alongside existing selectors.

#### Permission Boundary Rule

Every dashboard selector must use one of these as its permission foundation:
- `get_visible_project_requests(user)` — for queries where user can see any request
- `get_my_project_requests(user)` — for queries where user is the requester
- `get_assigned_to_me(user)` — for queries where user is the assignee
- `get_my_pending_approval_tasks(user)` — for queries where user has approval tasks

Dashboard selectors must NOT call `ProjectRequest.objects.all()` directly. Superuser always gets the full scope through `get_visible_project_requests(user)` (which already returns all for superuser).

#### `get_dashboard_my_drafts(user)`

| Property | Value |
|----------|-------|
| **Purpose** | User's own DRAFT requests for the dashboard |
| **Base queryset** | `get_my_project_requests(user)` |
| **Filter** | `status=DRAFT` |
| **Ordering** | `-created_at` |
| **Default limit** | 10 |
| **Used for** | List + count |
| **Tests in Phase 4B** | Regular user sees only own drafts. Superuser sees own drafts only (not all drafts). Staff with no requests returns empty. |

#### `get_dashboard_my_open_requests(user)`

| Property | Value |
|----------|-------|
| **Purpose** | User's submitted/in-progress requests (excludes DRAFT and terminal statuses) |
| **Base queryset** | `get_my_project_requests(user)` |
| **Filter** | `status__in=[SUBMITTED, REVIEWING, APPROVED, ASSIGNED, IN_PROGRESS, ON_HOLD]` |
| **Ordering** | `-last_activity_at` |
| **Default limit** | 10 |
| **Used for** | List + count |
| **Tests in Phase 4B** | DRAFT excluded. COMPLETED/REJECTED/CANCELLED excluded. Superuser sees own only. |
| **Note** | Excludes DRAFT to avoid showing the user's own work-in-progress drafts alongside submitted requests. Excludes terminal statuses since those are completed or cancelled and not "open." |

#### `get_dashboard_pending_approval_tasks(user)`

| Property | Value |
|----------|-------|
| **Purpose** | Approval tasks the user can act on |
| **Base queryset** | `get_my_pending_approval_tasks(user)` |
| **Filter** | None (already filtered by existing selector) |
| **Ordering** | `project_request__submitted_at` |
| **Default limit** | 20 |
| **Used for** | List + count |
| **Tests in Phase 4B** | Manager sees only tasks in their managed departments. Superuser sees all. Staff with no approval authority sees none. |

#### `get_dashboard_assigned_to_me(user)`

| Property | Value |
|----------|-------|
| **Purpose** | Requests actively assigned to the user |
| **Base queryset** | `get_assigned_to_me(user)` |
| **Filter** | None (existing selector already filters `assignments__is_active=True`) |
| **Ordering** | `-needed_by_date` then `-last_activity_at` |
| **Default limit** | 10 |
| **Used for** | List + count |
| **Tests in Phase 4B** | Returns only active assignments. User with no assignments returns empty. |

#### `get_dashboard_claimable_requests(user)`

| Property | Value |
|----------|-------|
| **Purpose** | APPROVED requests with no active assignment that the user can claim |
| **Base queryset** | `get_visible_project_requests(user).filter(status=APPROVED)` |
| **Filter** | `project_department__in=user_department_ids`, `project_department__project_dept_profile__allow_staff_claim=True`, `project_department__project_dept_profile__is_active=True`, `project_department__is_active=True` |
| **Exclude** | Requests with active assignment (`active_assignment_exists=True` annotation via `Exists` subquery — same pattern as `get_visible_project_requests`) |
| **Ordering** | `-needed_by_date` |
| **Default limit** | 10 |
| **Used for** | List + count |
| **Tests in Phase 4B** | Staff in project dept with `allow_staff_claim=True` sees claimable. Staff in dept without claim flag sees none. Users already assigned to a request do not see it as claimable. Superuser sees all claimable. |
| **Important** | Must use `Exists` subquery pattern for `active_assignment_exists` — same safeguard as `get_visible_project_requests`. No Python loop over all requests. |

#### `get_dashboard_project_department_queue(user)`

| Property | Value |
|----------|-------|
| **Purpose** | Non-terminal requests in user's managed project departments |
| **Base queryset** | `get_visible_project_requests(user)` |
| **Filter** | `project_department__in=managed_department_ids`, `status__in=[SUBMITTED, REVIEWING, APPROVED, ASSIGNED, IN_PROGRESS, ON_HOLD]` |
| **Ordering** | `-priority`, `-needed_by_date` |
| **Default limit** | 15 |
| **Used for** | List + count |
| **Visible to** | MANAGER/DIRECTOR/VP in project department only |
| **Tests in Phase 4B** | Project dept manager sees queue. Staff (non-manager) in same dept sees none. Regular staff not in project dept sees none. |

#### `get_dashboard_in_progress_or_on_hold(user)`

| Property | Value |
|----------|-------|
| **Purpose** | IN_PROGRESS or ON_HOLD requests in user's managed project departments |
| **Base queryset** | `get_visible_project_requests(user)` |
| **Filter** | `project_department__in=managed_department_ids`, `status__in=[IN_PROGRESS, ON_HOLD]` |
| **Ordering** | `status`, `-needed_by_date` |
| **Default limit** | 10 |
| **Used for** | List + count |
| **Visible to** | MANAGER/DIRECTOR/VP in project department only |
| **Tests in Phase 4B** | Manager sees IN_PROGRESS and ON_HOLD in their dept. DRAFT/SUBMITTED/APPROVED not shown. Staff sees nothing. |

#### `get_dashboard_recently_completed(user, days=30)`

| Property | Value |
|----------|-------|
| **Purpose** | COMPLETED requests in user's managed project departments within a time window |
| **Base queryset** | `get_visible_project_requests(user)` |
| **Filter** | `project_department__in=managed_department_ids`, `status=COMPLETED`, `completed_at__gte=timezone.now() - timedelta(days=days)` |
| **Ordering** | `-completed_at` |
| **Default limit** | 10 |
| **Default days** | 30 |
| **Used for** | List + count |
| **Visible to** | MANAGER/DIRECTOR/VP in project department only |
| **Tests in Phase 4B** | Manager sees recently completed in their dept. Requests completed before the window excluded. |

#### `get_dashboard_status_counts(user)`

| Property | Value |
|----------|-------|
| **Purpose** | Aggregate counts by status for the user's visible requests |
| **Base queryset** | `get_visible_project_requests(user)` |
| **Aggregation** | `.values('status').annotate(count=Count('id'))` |
| **Used for** | Count only (not list) |
| **Superuser** | Uses `get_visible_project_requests(user)` which returns all for superuser — no `ProjectRequest.objects.all()` |
| **Tests in Phase 4B** | Counts match what would be returned by the full visible queryset. Superuser count is all requests. Staff count is only own + assigned + visible. |

#### `get_dashboard_overdue_count(user)`

| Property | Value |
|----------|-------|
| **Purpose** | Count of assigned requests past needed_by_date |
| **Base queryset** | `get_overdue_project_requests(user)` (existing selector) |
| **Used for** | Count only |
| **Tests in Phase 4B** | Count matches `get_overdue_project_requests(user).count()`. |

---

### 1.5 Dashboard Section Specification

Each dashboard section renders as a card with a header (title + count badge), a list of up to N items, and a "View all" link if applicable.

| Section | Visible to | Selector | Max items | Empty state | View all target |
|---------|-----------|----------|-----------|-------------|-----------------|
| My Drafts | All authenticated | `get_dashboard_my_drafts` | 10 | "No drafts" | Filtered list view |
| My Open Requests | All authenticated | `get_dashboard_my_open_requests` | 10 | "No open requests" | Filtered list view |
| My Pending Approval Tasks | Request dept manager, Project dept VP | `get_dashboard_pending_approval_tasks` | 20 | "No pending approvals" | Filtered approval list |
| My Assigned Requests | All authenticated | `get_dashboard_assigned_to_me` | 10 | "No assigned requests" | Filtered list (assigned) |
| My Overdue Requests | All authenticated | `get_overdue_project_requests` | 10 | "No overdue requests" | Filtered list (overdue) |
| Claimable Requests | Project dept staff (allow_staff_claim) | `get_dashboard_claimable_requests` | 10 | "No claimable requests" | Filtered list (claimable) |
| Project Dept Queue | Project dept manager/director/VP | `get_dashboard_project_department_queue` | 15 | "No requests in queue" | Filtered list (project dept) |
| In Progress / On Hold | Project dept manager/director/VP | `get_dashboard_in_progress_or_on_hold` | 10 | "No active requests" | Filtered list (in-progress) |
| Recently Completed | Project dept manager/director/VP | `get_dashboard_recently_completed` | 10 | "No recently completed" | Filtered list (completed) |
| Admin Overview | Superuser only | `get_dashboard_status_counts` | N/A | N/A | N/A |
| All Pending Approvals | Superuser only | `get_my_pending_approval_tasks` (superuser) | 20 | "No pending approvals" | Admin approval list |

**Dashboard is read-only.** No POST forms on the dashboard. All workflow actions remain on the detail page.

---

### 1.6 Dashboard Permissions

### 1.5 Dashboard Permissions

- All dashboard sections must be gated by existing permission logic.
- `get_visible_project_requests` is the authoritative source of what a user can see.
- No new permission helpers should be created unless existing selectors cannot express the visibility rule.
- Superuser aggregate counts must not exceed what superuser could already see via existing selectors.

### 1.6 Dashboard Design Notes

- Dashboard should be a single view at `/dashboard/` (URL: `project_requests:dashboard`).
- Dashboard should be a GET-only view; no POST actions.
- Dashboard should use Bootstrap card/grid layout matching existing `base.html`.
- Status badges should use existing styling from `projectrequest_list.html`.
- Empty states should be handled gracefully (empty queryset → show "No requests" message, not error).
- Counts should be displayed as badge numbers on section headers.

### 1.7 Dashboard Implementation Risks

| Risk | Mitigation |
|------|------------|
| Dashboard bypassing permissions by introducing new querysets that don't apply existing visibility rules | All dashboard querysets must be built on top of existing selectors or apply the same visibility conditions |
| Overloading dashboard with too much data | Phase 4A selector design should include pagination or limits per section; consider deferring large lists to filtered list views |
| Superuser aggregate counts exposing data superuser couldn't otherwise access | Superuser dashboard uses `get_visible_project_requests(user)` queryset, not `ProjectRequest.objects.all()` |
| Dashboard view introducing workflow actions | Dashboard is GET-only. No POST forms on dashboard. All actions remain on detail page. |

---

## 2. UI Polish / Usability Planning

> **Principle:** Non-risky polish only. No large redesigns unless clearly deferred.

### 2.1 Navigation

- Add a "Dashboard" link to the navbar in `base.html` next to "Requests" or "New Request".
- The link should only appear for authenticated users.
- No other navigation changes.

### 2.2 Status Badges

- Status display is already implemented in `projectrequest_list.html` with badge styling.
- Ensure all status values have distinct, readable badge colors.
- Review that DRAFT, SUBMITTED, REVIEWING, APPROVED, REJECTED, ASSIGNED, IN_PROGRESS, ON_HOLD, COMPLETED, CANCELLED all render with appropriate badges.
- If colors are missing for any status, add minimal CSS; do not overhaul the color system.

### 2.3 Action Section Organization (Detail Page)

- The detail page (`projectrequest_detail.html`) has workflow action buttons.
- Ensure action buttons are grouped logically: Approve/Reject (Reviewing) → Assign/Claim (Approved) → Start (Assigned) → Hold/Resume/Complete (In Progress/On Hold).
- Use fieldset or section grouping with clear labels.
- No new actions; only reorganisation of existing button rendering.

### 2.4 Message Display

- Messages (`messages.success`, `messages.error`) are already used in views.
- Ensure all workflow action views return appropriate success/error messages.
- No changes needed unless a workflow action is missing a message.

### 2.5 Table Readability (List Page)

- The list page (`projectrequest_list.html`) should show request_no, project_name, requester, request_department, project_department, status, priority, needed_by_date.
- Columns should be sortable if feasible without complex query changes.
- Priority should display as readable label (P1-Critical, P2-High, etc.) not raw integer.
- Date fields should be formatted consistently.
- No new columns; only ensure existing columns render clearly.

### 2.6 Form Layout (Create/Edit)

- Create/edit form (`projectrequest_form.html`) uses Bootstrap form layout.
- Ensure required field indicators (`*`) are consistent.
- Ensure error messages render inline below their fields.
- No layout overhaul; minor alignment fixes only.

### 2.7 Empty States

- List views with empty querysets should display a friendly message: "No requests found."
- Detail page empty sections (e.g., no attachments, no approval tasks) should show "None" or skip the section rather than an empty table.
- Do not add placeholder content or illustrations; plain text empty states suffice.

### 2.8 Accessibility Basics

- Ensure all form inputs have associated `<label>` elements.
- Ensure color is not the only means of conveying status (status badges use text + color).
- Ensure action buttons have descriptive text (not just icons).
- No extensive accessibility audit; basic checks only.

### 2.9 Mobile/Responsive Basics

- The existing templates use Bootstrap-like CSS.
- Ensure the navbar collapses on small screens.
- Ensure tables have `table-responsive` wrapper.
- No mobile-first redesign; ensure basic responsiveness works.

---

## 3. Legacy Data Migration Assessment

> **Important:** This is an assessment/planning document only. No migration scripts will be implemented in Phase 4.

### 3.1 Legacy PHP Database Tables → Django Model Mapping

| Legacy Table | Django Model | Fields Safe to Migrate | Uncertain Fields |
|-------------|--------------|------------------------|------------------|
| `projects` | `ProjectRequest` | `project_name`, `scope_summary`, `description`, `needed_by_date`, `customer`, `system_name`, `priority`, `status`, `request_no` (legacy ID), `submitted_at`, `completed_at`, `cancelled_at` | `etd`, `hours` (estimate fields — may not map cleanly), `assign_to`, `dept_manager`, `mis_manager`, `mis_vp`, `approved_by`, `approved_date` (denormalized, possibly redundant), `file_path` (denormalized, may be first attachment only) |
| `approval` | `ProjectRequestApprovalTask` | `department`, `access_level`, `status`, `acted_by`, `acted_at` | `user` (who performed — nullable; may not map cleanly if legacy user IDs don't correspond to Django User IDs) |
| `project_assignment` | `ProjectRequestAssignment` | `assigned_by`, `assigned_to`, `is_active` (inferred from date fields), `created_at` | `assigned_to` may not map if legacy employee IDs don't correspond to Django User IDs |
| `project_log` | `ProjectRequestActivityLog` | `description`, `add_date`, `action_type` (derived from legacy log type) | `add_by` (legacy employee ID may not map), `type` (legacy log type may not map 1:1 to action types) |
| `project_file` | `ProjectRequestAttachment` | `file_path`, `description`, `uploaded_at` | `upload_by` (legacy employee ID), `type` (file type ID from legacy options) |
| `employee` | `accounts.User` + `accounts.UserDepartment` | `name` → `display_name`, `short_name`, `department`, `access_level`, `status` (active) | `title` (job title — no direct mapping to User model), `id` (legacy ID — needed for mapping but not used in Django) |
| `department` | `accounts.Department` | `dept_code`, `dept_name`, `is_active` (derived from `project` column) | Legacy `id` needed for mapping; `project` char(1) maps to `ProjectDepartmentProfile.can_receive_project_requests` |
| `multi_department_user` | `accounts.UserDepartment` | `employee`, `department`, `access_level` | Legacy employee ID to Django User ID mapping required |
| `options` | `ProjectRequestType`, `ProjectRequestFileType` | `name`, `code` | Legacy `id` used as FK; may need mapping table |

### 3.2 Field Mapping Details

#### Status Mapping

Legacy statuses (from `projects.status` = `options.id` where `subject` = status name):

| Legacy Status ID | Legacy Status Name | Django `ProjectRequest.status` |
|-----------------|-------------------|--------------------------------|
| (inferred: 9) | Submitted | `SUBMITTED` or `REVIEWING` |
| (inferred) | Approved | `APPROVED` |
| (inferred) | Rejected | `REJECTED` |
| (inferred) | Assigned | `ASSIGNED` |
| (inferred) | In Progress | `IN_PROGRESS` |
| (inferred) | On Hold | `ON_HOLD` |
| (inferred) | Completed | `COMPLETED` |
| (inferred) | Cancelled | `CANCELLED` |

**Risk:** Legacy status IDs are numeric and may not map 1:1. The actual legacy status values need to be verified against the `options` table data.

#### User/Department Mapping

- Legacy `employee.id` does NOT map to Django `User.id`. A mapping table (legacy_employee_id → django_user_id) is required.
- Auto-registration in legacy (`validate.php`) created new `employee` records for unknown users. These may need to be created as Django users.
- Legacy `multi_department_user` maps to `UserDepartment` entries with the same access level.
- Legacy `access_level` in `employee` table (1=VP, 2=Manager, 3+=Staff) maps inversely: `access_level - 1` maps to Django `AccessLevel` enum.

#### Request Number

- Legacy `projects.id` (integer) does NOT map to Django `ProjectRequest.request_no` (format `PRJ-YYYY-NNNNNN`).
- A mapping approach is needed: either preserve legacy ID as a separate field, or generate new request numbers and track the mapping.
- **Recommended:** Preserve legacy `projects.id` as `legacy_request_id` field (new nullable field on `ProjectRequest`) if migration is pursued. This avoids number collision while preserving reference ability.

#### Attachments

- Legacy `project_file.file_path` points to uploaded files in `legacy_php/uploads/`.
- Files may need to be copied to Django's media storage.
- File references may be stale or orphaned.

#### Audit/Activity History

- `project_log` entries can be migrated to `ProjectRequestActivityLog` with action types mapped from legacy `options.type` values.
- `add_by` (legacy employee ID) may not be mappable if the employee wasn't migrated.

### 3.3 Migration Deferral Recommendation

**Recommend deferring legacy migration to a phase after Phase 4 (Phase 5 or later) for the following reasons:**

1. **Data mapping ambiguity:** Legacy status IDs and user IDs need to be verified against actual DB data before a reliable migration script can be written.
2. **Risk of data corruption:** Migrating wrong status values or wrong user associations could corrupt the new system's integrity.
3. **Not required for pilot:** The pilot can proceed with new requests created in Django. Legacy data remains accessible in read-only mode via legacy PHP during the transition period.
4. **Staff capacity:** Migration planning and execution is time-consuming and should be a separate focused effort.
5. **FoxPro/external auth takes priority:** Getting users into the Django app from FoxPro is a prerequisite for useful pilot testing.

**However, a migration assessment phase (Phase 4D) should still be completed to:**
- Produce an exact field mapping document
- Identify gaps and ambiguities
- Produce a legacy DB schema export for reference
- Recommend whether to migrate before pilot or after initial pilot

### 3.4 Migration Validation Plan (Assessment Only)

If migration is pursued in the future:

1. Run migration in a staging environment with a copy of production data.
2. Validate record counts match per table.
3. Spot-check status values, user mappings, and date fields.
4. Verify attachment files exist at the referenced paths.
5. Run Django's `get_visible_project_requests` selector against migrated data to verify visibility rules don't break.
6. Keep legacy DB accessible for rollback.

---

## 4. FoxPro / External Auth Planning

### 4.1 Architecture Status

> **⚠️ The token-exchange design (LaunchSession, /auth/launch-token/, /auth/launch/) is SUPERSEDED.**
>
> The authoritative architecture for Phase 4F is documented in `documents/FOXPRO_AUTH_PLAN.md`. It uses a **Signed Launch URL** pattern, NOT token exchange.
>
> - **Primary endpoint:** `GET /auth/foxpro-launch/`
> - **Primary models:** `FoxproLaunchAttempt` + `FoxproLaunchNonce` (NOT `LaunchSession`)
> - **App location:** New `external_auth` app (NOT `accounts/authentication`)
>
> The old token-exchange design in this document (Option C/E with `LaunchSession`) is retained in Section 4.3 as a **rejected historical alternative** and is NOT approved for implementation.

### 4.2 Current Phase 4E Architecture (Approved Direction)

The Signed Launch URL architecture from `documents/FOXPRO_AUTH_PLAN.md` is the current approved direction:

| Aspect | Value |
|--------|-------|
| Pattern | Signed Launch URL with **custom FoxPro-compatible V2 signature** (NOT HMAC-SHA256) |
| Endpoint | `GET /auth/foxpro-launch/` |
| Signature format | `V2-{h1:010d}-{h2:010d}-{h3:010d}` |
| Canonical string | `MIS2\|n\|ln\|dp\|t\|o\|d\|nonce\|return` |
| Secret setting | `FOXPRO_V2_SECRET` (NOT `FOXPRO_HMAC_SECRET`) |
| FoxPro side | FoxPro 5 computes V2 signature directly, SHELLEXEC opens signed URL |
| Deployment | **Network-share EXE on local workstations** (current pilot) |
| Central terminal/server | **Future alternative only** — NOT current pilot |
| Helper EXE/DLL | Future alternative only — NOT current pilot |
| Models | `FoxproLaunchAttempt` + `FoxproLaunchNonce` only |
| App | New `external_auth` Django app |
| Authorization | Django permissions from `accounts.User` / `Department` / `UserDepartment` only |
| FoxPro `o` | Audit-only, NOT used for Django authorization |
| User mapping | `employee_id` first, fallback `username`; no auto-create |
| Return URL | Named route allowlist + `reverse()` |
| v=2 only | No v1 fallback in pilot |
| No token exchange | No LaunchSession, no /auth/launch-token/, no /auth/launch/ |

**Phase 4F prerequisites (must be explicit before Phase 4F begins):**
1. Shared secret generated and stored (for `FOXPRO_V2_SECRET`)
2. IP allowlist range confirmed (internal subnet or empty for internal network)
3. Timestamp convention selected (UTC or local workstation time)
4. Legacy fallback NOT approved for pilot

### 4.3 Rejected Historical Token-Exchange Alternative — DO NOT IMPLEMENT

> **SUPERSEDED.** The following token-exchange design is NOT approved. It is retained for historical reference only. Implementation of this design is forbidden.

**Old token-exchange design (NOT implemented in Phase 4F):**
- FoxPro calls `POST /auth/launch-token/` to get a short-lived random token
- FoxPro launches Django with `?token=...`
- Django validates token against `LaunchSession` table (exists, not expired, not used)
- `LaunchSession` model stores: token hash, user FK, expires_at, used_at, source_ip

**Why rejected:**
- Requires JSON parsing and two-step workflow in FoxPro 5 (SHELLEXEC only, no native JSON)
- Complex for FoxPro 5 — two network calls instead of one
- The old Option A/B/C/D/E implementation details in this superseded section are DO NOT USE

**Approved design for Phase 4F:**
- **Signed Launch URL** pattern with **custom V2 signature** (NOT HMAC-SHA256)
- Single SHELLEXEC call from FoxPro 5
- `FoxproLaunchAttempt` + `FoxproLaunchNonce` models (NOT `LaunchSession`)
- New `external_auth` Django app
- `GET /auth/foxpro-launch/`
- `FOXPRO_V2_SECRET` setting
- v=2 only (no v1 fallback)
- Network-share EXE on local workstations (NOT central terminal/server)

---

## 5. Phase 4 Subphase Breakdown

### Phase 4A — Dashboard Planning and Selector Design

**Allowed work:**
- Design dashboard view and URL (`/dashboard/`)
- Design dashboard sections and their querysets
- Design new selectors in `selectors.py`
- Write selector function signatures and docstrings
- Review selector design for permission-bypass risks
- Update `documents/PHASE_4_PLAN.md` with approved selector design

**Forbidden work:**
- Implementing dashboard view code
- Implementing dashboard template
- Modifying existing selectors/services/permissions
- Adding new workflow actions
- Modifying URLs, views, templates

**Files likely changed:**
- `documents/PHASE_4_PLAN.md` (updated with selector design)

**Tests to run:**
- None (planning only)

**Exit criteria:**
- Selector design is documented
- Permission safety review passed
- Selector names and signatures are approved

---

### Phase 4B — Dashboard Implementation

**Allowed work:**
- New selectors in `selectors.py`
- Dashboard view in `views.py`
- Dashboard URL in `urls.py`
- Dashboard template `dashboard.html`
- Dashboard tests in `tests_views.py`
- Add "Dashboard" navbar link in `base.html`

**Forbidden work:**
- New workflow actions
- New permission helpers
- Changes to existing selectors/services/permissions
- Modifying legacy_php
- Modifying migrations
- Modifying Phase 3 workflow code

**Files likely changed:**
- `project_requests/selectors.py` (new selectors)
- `project_requests/views.py` (dashboard view)
- `project_requests/urls.py` (dashboard URL)
- `templates/project_requests/dashboard.html` (new template)
- `templates/base.html` (navbar link)
- `project_requests/tests_views.py` (dashboard tests)

**Tests to run:**
- Dashboard view tests (targeted)
- Selector unit tests (targeted)

**Exit criteria:**
- Dashboard renders without errors
- All sections show correct data for each user role
- Existing selectors are reused
- Permissions are not bypassed
- User manually runs full test suite

---

### Phase 4C — UI Polish and Usability Hardening

**Allowed work:**
- Status badge CSS improvements in `base.html` or `projectrequest_list.html`
- Form layout adjustments in `projectrequest_form.html`
- Empty state handling in list/detail templates
- Accessibility label fixes on forms
- Navbar responsive improvements in `base.html`
- Priority display formatting in `projectrequest_list.html`

**Forbidden work:**
- Large redesign or layout overhaul
- New workflow functionality
- Changes to selector/permission logic
- Modifying Phase 3 workflow code
- Modifying models or migrations

**Files likely changed:**
- `templates/base.html`
- `templates/project_requests/projectrequest_list.html`
- `templates/project_requests/projectrequest_detail.html`
- `templates/project_requests/projectrequest_form.html`

**Tests to run:**
- Manual UI inspection
- Basic smoke tests (no new test files needed)

**Exit criteria:**
- UI is clean and usable
- Status badges consistent
- Forms render correctly
- Empty states handled gracefully
- Basic accessibility checks pass

---

### Phase 4D — Legacy Migration Assessment

**Allowed work:**
- Read `legacy_php/` as read-only reference (reference only; no modification)
- Read uploaded legacy DB schema/export if user provides it (user provides file path; AI reads it)
- Write `documents/LEGACY_MIGRATION_ASSESSMENT.md` with exact field mapping table
- Document legacy DB schema findings
- Document status code mapping
- Document user/department mapping approach
- Document attachment migration approach
- Document validation plan
- Document deferral recommendation

**Forbidden work:**
- Writing migration scripts
- Modifying Django models
- Creating migrations
- Importing data into the database
- Modifying `legacy_php/` files
- Modifying Phase 3 code

**Files likely changed:**
- `documents/LEGACY_MIGRATION_ASSESSMENT.md` (new file)

**Tests to run:**
- None (documentation only)

**Exit criteria:**
- Assessment document is complete
- Field mapping table is accurate
- Deferral recommendation is approved or migration is green-lit with clear scope

---

### Phase 4E — FoxPro/External Auth Architecture Plan

**Status:** Documentation synchronized and approved; Phase 4F implementation complete.

**Allowed work:**
- Write/update `documents/FOXPRO_AUTH_PLAN.md` with Signed Launch URL design (NOT token exchange)
- Design `FoxproLaunchAttempt` model schema
- Design `FoxproLaunchNonce` model schema
- Design validation flow (IP → params → timestamp → V2 signature → nonce → return → user → department → login → redirect)
- Design helper EXE/DLL requirements (Option B: central terminal/server)
- Design FoxPro change requirements
- Design audit logging approach
- Document prerequisites before Phase 4F can begin

**Forbidden work:**
- Implementing any code, URLs, migrations
- Modifying existing auth configuration
- Modifying Phase 3 code
- Modifying legacy_php
- Implementing `LaunchSession` or token exchange

**Files likely changed:**
- `documents/FOXPRO_AUTH_PLAN.md` (updated with signed launch URL architecture)

**Tests to run:**
- None (documentation only)

**Exit criteria:**
- FoxPro auth plan is approved by user after sync cleanup review
- `FoxproLaunchAttempt` and `FoxproLaunchNonce` model designs are documented
- Phase 4F prerequisites are explicit and documented
- helper EXE/DLL approach confirmed by user

---

### Phase 4F — FoxPro/External Auth Implementation

> **Important:** Phase 4F implementation must NOT begin until Phase 4E plan is approved AND Phase 4F prerequisites are explicit.

**Phase 4F-1: external_auth App Foundation (blocked until prerequisites met)**
- Create `external_auth/` Django app
- Create `FoxproLaunchAttempt` model
- Create `FoxproLaunchNonce` model (for nonce reservation/replay prevention)
- Add settings (`FOXPRO_V2_SECRET`, `FOXPRO_ALLOWED_IPS`, `FOXPRO_LAUNCH_MAX_AGE_SECONDS`, `FOXPRO_ALLOWED_RETURN_PATHS`)
- Create migration
- Forbidden: modifying `accounts`/`project_requests` workflow code, implementing views yet

**Phase 4F-2: Signed Launch Validation View + Tests (blocked until 4F-1 complete)**
- Implement `foxpro_launch` view at `GET /auth/foxpro-launch/`
- Implement validation flow (IP → params → timestamp → V2 signature → nonce → return → user → department → login → redirect)
- Implement audit logging
- Write tests
- Forbidden: modifying Phase 3 workflow code, creating new URLs outside `external_auth`

**Phase 4F-3: FoxPro 5 Integration Test (blocked until 4F-2 complete)**
- Coordinate end-to-end test with user (who implements FoxPro 5 side)
- Test V2 signature generation from FoxPro 5
- Test full launch flow: FoxPro 5 → Django → Dashboard

**Phase 4F-4: Legacy Fallback (ONLY if explicitly approved)**
- Implement `GET /auth/foxpro-legacy-launch/` view
- Implement XOR signature validation
- Implement stricter IP allowlist
- Add sunset date to settings
- NOT approved for pilot — only if explicitly approved with sunset

**Superseded design (DO NOT IMPLEMENT):**
- `LaunchSession` model
- `/auth/launch-token/` endpoint
- `/auth/launch/` endpoint
- Token exchange flow
- `accounts/authentication` app as implementation location

**Current approved architecture:**
- App: `external_auth`
- Primary endpoint: `GET /auth/foxpro-launch/`
- Models: `FoxproLaunchAttempt` + `FoxproLaunchNonce` only
- Authorization: `accounts.User` / `Department` / `UserDepartment` only
- FoxPro `o`: audit-only

**Phase 4F prerequisites (must be explicit before Phase 4F begins):**
1. Shared secret generated and stored (for `FOXPRO_V2_SECRET`)
2. IP allowlist range confirmed (internal subnet or empty for internal network)
3. Timestamp convention selected (UTC or local workstation time)
4. Legacy fallback NOT approved for pilot

**Exit criteria:**
- FoxPro can successfully launch Django with V2-signed URL
- V2 signature validation is secure (nonce replay prevented, timestamp enforced)
- Launch audit log is created (success and failure)
- Normal Django login still works
- User manually runs full test suite after Phase 4F-2

---

## 6. Risks

### 6.1 Dashboard Bypassing Permissions

**Risk:** New dashboard querysets inadvertently expose requests users should not see.

**Likelihood:** Medium
**Impact:** High

**Mitigation:**
- All dashboard querysets must be built on top of existing selectors.
- Selector design review (Phase 4A) must explicitly check for permission bypass.
- Dashboard tests must cover visibility for different user roles.

### 6.2 Overloading Dashboard with Too Much Data

**Risk:** Dashboard renders slowly or displays overwhelming amounts of data.

**Likelihood:** Medium
**Impact:** Low

**Mitigation:**
- Dashboard sections should have sensible limits (e.g., top 10 per section, "View all" link).
- No full-table scans; use existing selectors with `.distinct()`.
- Large lists deferred to filtered list views.

### 6.3 Legacy Status Mapping Errors

**Risk:** Status values in legacy data don't map correctly to Django statuses, causing migration failures or data corruption.

**Likelihood:** High (ambiguous legacy schema)
**Impact:** High

**Mitigation:**
- Phase 4D assessment must verify actual legacy status values from DB data.
- Migration deferred until mapping is verified.
- Staging validation before any production migration.

### 6.4 User/Department Mapping Ambiguity

**Risk:** Legacy employee IDs and department IDs don't map cleanly to Django User/Department IDs.

**Likelihood:** High
**Impact:** Medium

**Mitigation:**
- Phase 4D assessment documents the mapping approach.
- Auto-registration (as in legacy) may be needed for unmatched users.
- Mapping table (legacy_id → django_id) tracks unresolved mappings.

### 6.5 Treating Weak FoxPro Encryption as Real Auth

**Risk:** FoxPro XOR signature is used as strong authentication, exposing the system to forged URLs.

**Likelihood:** Low (the risk is known and documented)
**Impact:** High

**Mitigation:**
- Phase 4F uses custom V2 signature (NOT HMAC-SHA256, NOT XOR signature)
- Legacy params kept only as audit hints during transition (legacy fallback only, with sunset)
- Documentation explicitly states XOR is not secure and is not used for authorization

### 6.6 Replay Attacks

**Risk:** Launch URL or nonce is reused to gain unauthorized access.

**Likelihood:** Low (mitigated by design)
**Impact:** Medium

**Mitigation:**
- Nonce uniqueness enforced via `FoxproLaunchNonce` unique constraint on `nonce_hash`
- Reused nonce creates failed `FoxproLaunchAttempt` (for audit) but request is rejected
- Invalid V2 signature does NOT reserve nonce — nonce reservation happens only after V2 signature passes
- Timestamp max age (15 seconds) limits replay window
- Audit log tracks all launch attempts

### 6.7 Accidental Implementation Before Planning

**Risk:** Phase 4 implementation begins before planning is complete, leading to misaligned code.

**Likelihood:** Low (this document exists)
**Impact:** Medium

**Mitigation:**
- This plan must be approved before Phase 4B begins.
- Subphases must be completed in order.
- Hard scope rules enforced.

### 6.8 Scope Creep

**Risk:** Phase 4 absorbs work that should be separate phases (e.g., new workflow features, model changes).

**Likelihood:** Medium
**Impact:** Low

**Mitigation:**
- Phase 4 subphases have explicit allowed/forbidden lists.
- New workflow actions are explicitly forbidden in Phase 4.
- Model changes are forbidden except for `FoxproLaunchAttempt` + `FoxproLaunchNonce` in Phase 4F.

---

## 7. Final Recommendation

### Status

**Phase 4B is complete.** Dashboard implementation is done and accepted by user.

**Phase 4E documentation synchronization is complete. Phase 4F implementation is complete; MIS-8 pilot-readiness verification is in progress.**

**Phase 4C and Phase 4D remain deferred.**

**Phase 4F implementation is complete; pilot readiness pending.** external_auth app exists with V2 signature validation.

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

### Next Step

MIS-8 pilot-readiness verification. Complete the required runtime/deployment checks before pilot/go-live.

### Confirmation Statements

- [x] **Documentation only** — No Python code, templates, URLs, migrations, or legacy_php modifications
- [x] **Phase 4B complete** — Dashboard implementation is done and accepted by user
- [x] **Phase 4E docs synchronized** — FOXPRO_AUTH_PLAN.md updated with Signed Launch URL architecture; old token-exchange design compressed into rejected historical section
- [x] **Phase 4F implementation complete** — external_auth app exists with V2 signature validation; pilot readiness pending
- [x] **Phase 4C, 4D remain deferred** — No implementation started
- [x] **No outside workspace files were read** — All files are within `c:/dev/MIS_PROJECT`
- [x] **Hard scope respected** — Did not modify workflow services, selectors, permissions, models, URLs, or legacy_php
- [x] **Testing rule preserved** — Roo runs targeted tests only; user manually runs full test suite

---

## Appendix A: Existing Selectors Reference

These selectors exist and should be reused by the dashboard:

```
get_visible_project_requests(user)              # All requests user can see
get_my_project_requests(user)                    # Requests user created
get_assigned_to_me(user)                         # Requests actively assigned to user
get_my_pending_approval_tasks(user)             # Approval tasks user can act on
get_overdue_project_requests(user)               # Assigned requests past needed_by_date
```

---

## Appendix B: Existing Permission Helpers Reference

These permission helpers exist and should be reused by the dashboard:

```
can_view_project_request(user, project_request)
can_submit_project_request(user)
can_assign_project_request(user, project_request)
can_claim_project_request(user, project_request)
can_attach_file(user, project_request)
can_approve_project_request(user, project_request, task)   # Phase 3A
can_reject_project_request(user, project_request, task)   # Phase 3A
can_start_project_request(user, project_request)          # Phase 3C
can_hold_project_request(user, project_request)            # Phase 3C
can_resume_project_request(user, project_request)          # Phase 3C
can_complete_project_request(user, project_request)        # Phase 3C
```

---

## Appendix C: Phase 4 Work Summary

| Subphase | Type | Output | Implementation? |
|----------|------|--------|-----------------|
| 4A | Planning | Selector design document | No |
| 4B | Implementation | Dashboard view, template, selectors, tests | Yes |
| 4C | Polish | Template/CSS improvements | Yes (deferred) |
| 4D | Assessment | Legacy migration assessment document | No (deferred) |
| 4E | Planning | FoxPro auth architecture document | No (complete) |
| 4F | Implementation | FoxproLaunchAttempt + FoxproLaunchNonce models, signed launch view, tests | Yes (complete; pilot readiness pending) |

Phase 4 produces: `documents/PHASE_4_PLAN.md` (this document), `documents/LEGACY_MIGRATION_ASSESSMENT.md`, `documents/FOXPRO_AUTH_PLAN.md`, and Phase 4B implementation code. Phase 4C/4D deferred. Phase 4F implementation complete; pilot readiness pending.