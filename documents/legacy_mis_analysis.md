# Legacy MIS Project Analysis & Django Rebuild Plan

> This document analyzes the legacy PHP-based MIS (Management Information System) request/project management application and proposes a Django rebuild plan. The legacy PHP code under `legacy_php/` is treated as read-only reference material.

---

## 1. Legacy File Map

| File | Purpose | Tables Touched | Contains Business Logic? |
|------|---------|----------------|--------------------------|
| [`connection.php`](legacy_php/connection.php) | Database connection setup with hard-coded credentials. | None (connection only) | No |
| [`validate.php`](legacy_php/validate.php) | Authentication via external login parameters (`?ln=...&n=...&d=...&s=...&o=...&dp=...&t=...`). Validates encrypted timestamp, auto-registers unknown employees, manages session with 30-min timeout. | `employee` | **Yes** — login, encryption, auto-registration, session management |
| [`index.php`](legacy_php/index.php) | Landing page. Shows "New Request" and "Projects" links. Handles multi-department user department selection via POST. | `multi_department_user`, `department` | Partial — multi-department switching |
| [`request.php`](legacy_php/request.php) | Renders the request submission form. Loads project types, file types, and project-eligible departments from DB. | `options`, `department` | No (presentation only) |
| [`submit_request.php`](legacy_php/submit_request.php) | Processes request submission: duplicate check, inserts into `projects`, generates required approvals in `approval`, handles file upload to `project_file`, creates initial `project_log` entry. Auto-approves if no approvals needed. | `projects`, `approval`, `project_file`, `project_log` | **Yes** — core submission + approval generation logic |
| [`show_projects.php`](legacy_php/show_projects.php) | Main project list view with inline actions: approve, reject, request additional approval, assign, claim. Handles all POST actions for approvals, rejections, assignments, and additional approval requests. | `projects`, `approval`, `project_assignment`, `project_log`, `general_comment`, `employee`, `department`, `options` | **Yes** — approval/rejection/assignment/request-approval logic |
| [`project_detail.php`](legacy_php/project_detail.php) | Read-only detail view for a single project. | `projects` | No |
| [`project_log.php`](legacy_php/project_log.php) | Displays activity log for a project in a popup window. Joins `project_log`, `options`, `employee`, `general_comment`. | `project_log`, `options`, `projects`, `employee`, `general_comment` | No |
| [`logout.php`](legacy_php/logout.php) | Destroys session. | None | No |
| [`timeout.php`](legacy_php/timeout.php) | Displays timeout message when session expires (30 min inactivity). | None | No |
| [`error.php`](legacy_php/error.php) | Generic error page. Destroys session. | None | No |

---

## 2. Inferred Legacy Database Model

### `employee`

| Column | Inferred Type | Purpose |
|--------|--------------|---------|
| `id` | INT PK | Employee unique identifier |
| `name` | VARCHAR | Employee display name |
| `short_name` | VARCHAR | Short/alias name (used for assignment display) |
| `department` | INT FK → `department.id` | Employee's primary department |
| `title` | VARCHAR | Job title (e.g., "V.P.", "President") |
| `access_level` | INT | Authorization level: 1=VP/President, 2=Manager, 3+=Staff |
| `status` | INT | Account status (1=active) |

### `department`

| Column | Inferred Type | Purpose |
|--------|--------------|---------|
| `id` | INT PK | Department unique identifier |
| `name` | VARCHAR | Department display name |
| `project` | CHAR(1) | 'Y' if this department can receive project requests (project-eligible) |

**Known department codes from [`validate.php`](legacy_php/validate.php:25-77):**

| Code | Department | DP Param |
|------|-----------|----------|
| 1 | MIS | 88 |
| 2 | Sales | 01 |
| 3 | PM | 02 |
| 4 | Marketing | 03 |
| 5 | Credit | 10 |
| 6 | Production | 31 |
| 7 | Planning | 32 |
| 8 | Customer Service | 55 |
| 9 | Purchasing | 65 |
| 10 | Accounting | 85 |
| 11 | Engineering | 86 |
| 12 | IT | 90 |
| 13 | Other | (default) |

### `multi_department_user`

| Column | Inferred Type | Purpose |
|--------|--------------|---------|
| `employee` | INT FK → `employee.id` | Employee who belongs to multiple departments |
| `department` | INT FK → `department.id` | One of the departments the employee belongs to |
| `access_level` | INT | Access level in this specific department |

### `projects`

| Column | Inferred Type | Purpose |
|--------|--------------|---------|
| `id` | INT PK | Project/Request unique identifier |
| `project_name` | VARCHAR | Name of the request/project |
| `date` | DATETIME | Submission date (set to today) |
| `requestor` | INT FK → `employee.id` | Who submitted the request |
| `requestor_department` | INT FK → `department.id` | Department of the requestor |
| `system` | VARCHAR | System the request relates to (optional) |
| `scope` | TEXT | Scope/Region description (optional) |
| `description` | TEXT | Detailed description of the request |
| `need_by_date` | DATE | Deadline for the request |
| `customer` | VARCHAR | Customer name (optional) |
| `status` | INT FK → `options.id` | Current status (see Section 5) |
| `Priority` | INT | Priority 1-5 (1=highest) |
| `type` | INT FK → `options.id` | Request type (from options where subject='project_type') |
| `project_department` | INT FK → `department.id` | Target department for the request |
| `last_act_date` | DATETIME | Last activity timestamp |
| `etd` | DATE | Estimated time of delivery (set by assignee) |
| `hours` | VARCHAR | Hours estimate |
| `assign_to` | VARCHAR | Assigned employee(s) — likely denormalized |
| `dept_manager` | VARCHAR | Department manager name — likely denormalized |
| `mis_manager` | VARCHAR | MIS manager name — likely denormalized |
| `mis_vp` | VARCHAR | MIS VP name — likely denormalized |
| `approved_by` | VARCHAR | Who approved — likely denormalized |
| `approved_date` | DATE | Approval date — likely denormalized |
| `complete_date` | DATE | Completion date — likely denormalized |
| `file_path` | VARCHAR | File attachment path — likely denormalized (only first file?) |

### `approval`

| Column | Inferred Type | Purpose |
|--------|--------------|---------|
| `id` | INT PK (inferred) | Approval record ID |
| `department` | INT FK → `department.id` | Department whose approval is required |
| `access_level` | INT | Required role: 1=VP, 2=Manager |
| `status` | VARCHAR | 'N' = pending, 'Y' = approved, 'R' = rejected |
| `project` | INT FK → `projects.id` | Related project |
| `user` | INT FK → `employee.id` (nullable) | Who performed the approval (NULL = pending) |
| `date` | DATETIME (nullable) | When approval was performed |

### `project_assignment`

| Column | Inferred Type | Purpose |
|--------|--------------|---------|
| `id` | INT PK (inferred) | Assignment record ID |
| `assigned_by` | INT FK → `employee.id` | Who made the assignment |
| `assigned_to` | INT FK → `employee.id` | Who was assigned |
| `project` | INT FK → `projects.id` | Related project |

### `project_log`

| Column | Inferred Type | Purpose |
|--------|--------------|---------|
| `id` | INT PK | Log entry ID |
| `project` | INT FK → `projects.id` | Related project |
| `type` | INT FK → `options.id` | Log type (18=Request Submission, 19=Approval action, 21=Assignment) |
| `description` | VARCHAR | Description of the action |
| `add_by` | INT FK → `employee.id` | Who performed the action |
| `add_date` | DATETIME | When the action occurred (auto-generated) |

### `general_comment`

| Column | Inferred Type | Purpose |
|--------|--------------|---------|
| `id` | INT PK (inferred) | Comment ID |
| `user` | INT FK → `employee.id` | Who wrote the comment |
| `subject_id` | INT | ID of the related entity (e.g., `project_log.id`) |
| `comment` | TEXT | Comment text |
| `subject` | INT FK → `options.id` | Subject type (23 = project log comment) |

### `project_file`

| Column | Inferred Type | Purpose |
|--------|--------------|---------|
| `id` | INT PK (inferred) | File record ID |
| `project` | INT FK → `projects.id` | Related project |
| `file_path` | VARCHAR | Server path to uploaded file |
| `description` | TEXT | File description |
| `type` | INT FK → `options.id` | File type (from options where subject='file_type') |
| `upload_by` | INT FK → `employee.id` | Who uploaded the file |

### `options`

| Column | Inferred Type | Purpose |
|--------|--------------|---------|
| `id` | INT PK | Option ID (used as FK target for status, type, log type, file type, subject) |
| `name` | VARCHAR | Display name of the option |
| `subject` | VARCHAR | Category: 'project_type', 'file_type', status names, log type names, etc. |

This table serves as a generic lookup/dictionary for:
- Project types (`subject = 'project_type'`)
- File types (`subject = 'file_type'`)
- Project statuses (joined by `projects.status = options.id`)
- Log entry types (joined by `project_log.type = options.id`)
- Comment subjects (e.g., `subject = 23` means project log comment)

---

## 3. Legacy Business Workflow

### 3.1 Login / Session Flow

1. User arrives via external system with URL parameters: `?ln=<name>&n=<short_name>&d=<datetime>&s=<encrypted_string>&o=<authorization>&dp=<dept_code>&t=<title>`
2. [`validate.php`](legacy_php/validate.php) checks if session already exists:
   - If session exists but `last_activity` > 30 minutes ago → destroy session, redirect to [`timeout.php`](legacy_php/timeout.php)
   - If session exists and valid → refresh `last_activity`, show welcome message
3. If no session:
   - Validate all required parameters are present
   - Check that the external datetime is within 1 minute of current time
   - Verify the encrypted string matches `encrypt(datetime, title)` using custom XOR encryption
   - Look up employee in `employee` table by `name`, `department`, `short_name`
   - If found → load `access_level` from DB
   - If not found → auto-create employee record with calculated `access_level`:
     - V.P. or President → access_level = 1
     - Otherwise → access_level = `o` parameter + 1
   - Set session variables: `name`, `id`, `short_name`, `department`, `department_code`, `authorization`, `last_activity`
4. On [`index.php`](legacy_php/index.php), if user is in `multi_department_user`, show department selection buttons

### 3.2 Request Submission Flow

1. User fills form on [`request.php`](legacy_php/request.php) with: project name, date (auto-today), requestor (auto), requestor department (auto), request type, customer, target department, system, scope, description, priority (1-5), need-by-date, optional file upload
2. Form POSTs to [`submit_request.php`](legacy_php/submit_request.php)
3. Duplicate check: query `projects` for same `project_name` + `type` + `requestor` + `status=9` (Submitted)
4. If no duplicate:
   - Insert into `projects` with `status=9` (Submitted)
   - Generate required approvals (see Section 4)
   - If any approvals required → status stays 9
   - If NO approvals required → change status to 4 (Approved)
   - Process file upload if provided (move to `uploads/<project_id>/`)
   - Insert file record into `project_file`
   - Insert initial log entry: type=18, description='Request Submission'
5. Show confirmation page with submitted data

### 3.3 Approval Generation Flow

From [`submit_request.php`](legacy_php/submit_request.php:43-81):

Three potential approval requirements are evaluated:

| # | Approval | Department | Access Level | Label |
|---|----------|-----------|--------------|-------|
| 0 | Requestor's Department Manager | `requestor_department` | 2 (Manager) | "Department Manager" |
| 1 | Project (Target) Department Manager | `project_department` | 2 (Manager) | "Project Department Manager" |
| 2 | Project (Target) Department VP | `project_department` | 1 (VP) | "Project Department VP" |

Rules:
- **Project Dept Manager approval (row 1):** Required if `requestor_department != project_department` OR (`same department` AND `requestor access_level > 2` i.e., not manager)
- **Requestor Dept Manager approval (row 0):** Required if `requestor access_level > 2` (not manager) AND `requestor_department != project_department`
- **Project Dept VP approval (row 2):** Required if `priority == 1` (top priority) AND (`requestor_department != project_department` OR `requestor access_level > 1` i.e., not VP)

Each required approval is inserted into `approval` table with `status='N'` (pending).

If no approvals are required at all, the request is auto-approved (`status=4`).

### 3.4 Approval / Rejection Flow

From [`show_projects.php`](legacy_php/show_projects.php:26-112):

1. User clicks "Approve" or "Reject" button on a project row
2. Modal opens, hidden fields set with `action1` (modal title) and `action2` (Approve/Reject)
3. On POST:
   - `action = "Y"` for Approve, `"R"` for Reject
   - `level` determined from `action1` title: contains "VP" → level=1, otherwise level=2
   - Access level check: if `user.authorization > level` → redirect to error (user not authorized enough)
   - UPDATE `approval` set `user=current_user`, `date=now()`, `status=action` WHERE `project=X`, `user IS NULL`, `department=current_dept`, `access_level=level`
   - Check if any pending approvals remain (`user IS NULL`):
     - If approving and no pending remain → `status=4` (Approved)
     - If approving and pending remain → `status=3` (Reviewing)
     - If rejecting → `status=10` (Rejected)
   - UPDATE `projects` SET `status=X`, `last_act_date=now()`
   - INSERT `project_log` with type=19, description=action title

### 3.5 Additional Approval Request Flow

From [`show_projects.php`](legacy_php/show_projects.php:59-82):

1. User clicks "Request Approval" button (available when approval row shows 'N' = Not Required)
2. Modal title contains "Request" (e.g., "Request Department Approval" or "Request MIS VP Approval")
3. On POST:
   - Determines `approval_dept`: if VP request → current department; otherwise → `requestor_department` from projects table
   - Checks if approval record already exists for this `project` + `department` + `access_level`
   - If not → INSERT new approval with `status='N'`
   - Set project `status=3` (Reviewing)
   - INSERT `project_log` with type=19
   - Optional comment stored in `general_comment` with `subject=23`, `subject_id=log_id`

### 3.6 Assignment / Claim Flow

From [`show_projects.php`](legacy_php/show_projects.php:39-53):

1. **Assign** (by manager, `authorization <= 2`): Select one or more employees from department, POST with `action2='Assign'`
   - For each selected employee: INSERT into `project_assignment`
   - Set project `status=5` (Assigned)
   - INSERT `project_log` with type=21, description='Assign to: <names>'
2. **Claim** (by staff, `authorization > 2`): Available when user is in project department and all approvals are done
   - The claim button exists in UI but the backend handling for claim appears to use the same assignment POST flow (the modal shows employee selection for assign, but claim likely auto-selects the claimant — this may be a legacy bug or incomplete feature)

### 3.7 Log / Comment Flow

- Every significant action inserts a row into `project_log`
- Comments on log entries are stored in `general_comment` with `subject=23` and `subject_id=project_log.id`
- [`project_log.php`](legacy_php/project_log.php) displays all log entries for a project with optional comments

### 3.8 File Upload Flow

1. Single file upload on request submission
2. File moved to `uploads/<project_id>/<original_filename>`
3. Record inserted into `project_file`
4. **No server-side validation** of file type beyond the HTML `accept` attribute
5. **No size limit** enforced server-side

---

## 4. Approval Rule Extraction

### 4.1 Legacy Code Behavior (as-is)

The legacy approval logic from [`submit_request.php`](legacy_php/submit_request.php:43-81) implements the following rules. **Note: The legacy code contains inconsistencies and likely bugs. Section 4.2 below presents the corrected rules for the Django rebuild.**

**Legacy Rule 1 — Requestor Department Manager Approval:**
- Required when the requestor is NOT a manager (`access_level > 2`) AND the request crosses department boundaries (`requestor_department != project_department`).

**Legacy Rule 2 — Project (Target) Department Manager Approval:**
- Required if `requestor_department != project_department` OR (`same department` AND `requestor access_level > 2`).

**Legacy Rule 3 — Project (Target) Department VP Approval:**
- Required if `priority == 1` AND (`requestor_department != project_department` OR `requestor access_level > 1`).

**Legacy Rule 4 — Auto-Approval:**
- If no approvals are generated, status changes to 4 (Approved).

### 4.2 Corrected Business Rules (for Django Rebuild)

The following rules supersede the legacy code and should be implemented in the Django rebuild:

**Rule 1 — Target (Project) Department Manager Approval:**
- Required when the request crosses department boundaries (`requestor_department != project_department`).
- Also required for same-department requests if the requestor is NOT a manager (`access_level > MANAGER`).
- NOT required when a manager (`access_level <= MANAGER`) submits a request to their own department (unless top priority triggers VP approval).

**Rule 2 — Requestor Department Manager Approval:**
- NOT required for cross-department requests submitted by a manager. Managers are trusted to approve their own department's outgoing requests.
- Required only when the requestor is NOT a manager (`access_level > MANAGER`) AND the request crosses department boundaries.

**Rule 3 — Target (Project) Department VP Approval:**
- Required when the request is **top priority** (`priority == 1`).
- Applies to both cross-department and same-department requests.
- NOT required if the requestor is already a VP-level user (`access_level <= VP`) in the **target** department.

**Rule 4 — Auto-Approval:**
- If none of the above rules trigger (no approvals required), the request is automatically set to status `APPROVED`.
- This occurs when a manager submits a non-top-priority request to their own department.

### 4.3 Corrected Approval Matrix

| Scenario | Requestor Dept Mgr | Target Dept Mgr | Target Dept VP | Auto-Approve? |
|----------|-------------------|----------------|----------------|---------------|
| Staff → same dept | No | **Yes** | No (unless P1) | No |
| Staff → cross dept | Yes | Yes | Yes (if P1) | No |
| Manager → same dept, non-P1 | No | No | No | **Yes** |
| Manager → same dept, P1 | No | No | **Yes** | No |
| Manager → cross dept | **No** | Yes | Yes (if P1) | No |
| VP (target dept) → same dept, P1 | No | No | No | **Yes** |
| VP → cross dept, P1 | No | Yes | Yes | No |

### 4.4 Likely Legacy Bugs and Ambiguities

1. **Bug — `if ($user == 2)` in [`validate.php:101`](legacy_php/validate.php:101):** Compares an associative array to integer `2`. This condition is always false. Likely intended to check `$user['access_level'] == 2` or similar.

2. **Bug — Same-department staff requests auto-approved in legacy code:** The legacy code at [`submit_request.php:51`](legacy_php/submit_request.php:51) checks `$department_code != $project_department or ($department_code == $project_department && $authorization > 2)`. For a staff user (`authorization=3`) submitting to the same department, this evaluates to `false or true = true`, so target dept manager approval IS generated. However, the summary table in the original analysis incorrectly stated same-department staff requests would be auto-approved. The corrected rules in Section 4.2 clarify this.

3. **Bug — Claim flow incomplete:** The "Claim" button in [`show_projects.php`](legacy_php/show_projects.php:520) opens the same modal as "Assign" but the backend does not distinguish claim from assign. The claimant's ID is not auto-populated.

4. **Ambiguity — Multiple approvals with same department/access_level:** The UPDATE in approval flow uses `user IS NULL` which could match multiple rows if duplicates exist. No UNIQUE constraint appears to prevent duplicate approval records.

5. **Bug — No transaction handling:** If the approval INSERT succeeds but the project_log INSERT fails, the data is inconsistent. No ROLLBACK mechanism.

6. **Ambiguity — Rejection finality:** When a rejection sets `status=10`, the remaining pending approval records are left in `status='N'` state. They are never cleaned up.

---

## 5. Legacy Status Mapping

The `projects.status` field references the `options` table. From code analysis:

| Status Code | Inferred Meaning | Evidence |
|-------------|-----------------|----------|
| **3** | **Reviewing** | [`show_projects.php:82`](legacy_php/show_projects.php:82) — set after additional approval request; [`show_projects.php:105`](legacy_php/show_projects.php:105) — set when approval done but more pending; appears in UI checks as `'Reviewing'` at [`show_projects.php:343`](legacy_php/show_projects.php:343) |
| **4** | **Approved** | [`submit_request.php:80`](legacy_php/submit_request.php:80) — set when no approvals needed; [`show_projects.php:107`](legacy_php/show_projects.php:107) — set when all approvals completed |
| **5** | **Assigned** | [`show_projects.php:54`](legacy_php/show_projects.php:54) — set after assignment action |
| **8** | **Uncertain (likely In Progress / Development)** | Excluded from manager view filter at [`show_projects.php:248`](legacy_php/show_projects.php:248) alongside 10 and 11. Not set anywhere visible. Likely set by external process or removed code. |
| **9** | **Submitted** | [`submit_request.php:25`](legacy_php/submit_request.php:25) — initial status on new request; duplicate check at [`submit_request.php:29`](legacy_php/submit_request.php:29); appears in UI as `'Submitted'` at [`show_projects.php:343`](legacy_php/show_projects.php:343) |
| **10** | **Rejected** | [`show_projects.php:110`](legacy_php/show_projects.php:110) — set on rejection; excluded from manager view at [`show_projects.php:248`](legacy_php/show_projects.php:248) |
| **11** | **Uncertain (likely Cancelled / Closed / Completed)** | Excluded from manager view at [`show_projects.php:248`](legacy_php/show_projects.php:248). Not set in visible code. May represent a final terminal state. |

**Additional statuses likely in `options` table but not directly used as integers in visible code:**
- The `options` table likely contains human-readable names for all status codes, joined at [`show_projects.php:149`](legacy_php/show_projects.php:149).

---

## 6. Security and Design Problems in the Legacy PHP Project

### 6.1 Hard-Coded Database Credentials
[`connection.php`](legacy_php/connection.php:4-6) contains plain-text database credentials. These must never be copied to the Django project. Use environment variables / Django `settings.py` with `django-environ` or similar.

### 6.2 SQL Injection Risk
Nearly all queries use string concatenation with unsanitized user input:
- [`validate.php:97`](legacy_php/validate.php:97): `name`, `department`, `short_name` directly interpolated
- [`submit_request.php:29`](legacy_php/submit_request.php:29): `projectName`, `type`, `id` directly interpolated
- [`project_detail.php:20`](legacy_php/project_detail.php:20): `projectId` from `$_GET` directly interpolated
- [`show_projects.php`](legacy_php/show_projects.php): Multiple unsanitized interpolations

Only [`project_log.php:14`](legacy_php/project_log.php:14) uses `intval()` for sanitization.

### 6.3 Weak Custom Encryption
The `encrypt()` function in [`validate.php:136-154`](legacy_php/validate.php:136) uses simple XOR with the title as key. This provides no real security:
- XOR with repeating key is trivially breakable
- Non-alphabetic characters are replaced with sequential lowercase letters, losing information
- The "encrypted" timestamp can be reverse-engineered

### 6.4 Magic Numbers
- Status codes (3, 4, 5, 8, 9, 10, 11) used as raw integers
- Access levels (1, 2, 3+) used as raw integers
- Log types (18, 19, 21) used as raw integers
- Comment subject (23) used as raw integer
- Department codes (1-13) used as raw integers

### 6.5 Business Logic Mixed with Presentation
- Approval generation logic is embedded in [`submit_request.php`](legacy_php/submit_request.php:43-76) alongside HTML output
- Approval/rejection/assignment logic is embedded in [`show_projects.php`](legacy_php/show_projects.php:20-137) alongside table rendering
- Inline PHP in HTML makes testing and refactoring nearly impossible

### 6.6 File Upload Risks
- No server-side file type validation (relies on HTML `accept` attribute only)
- No file size limit
- Original filename preserved (path traversal risk)
- Upload directory `uploads/<project_id>/` has no access control
- No virus scanning

### 6.7 Lack of Transaction Handling
- Multi-step operations (insert project → insert approvals → insert file → insert log) have no transaction wrapping
- Partial failures leave inconsistent data

### 6.8 Authorization Risks
- No check that the user has access to a project before showing detail or performing actions
- [`project_detail.php`](legacy_php/project_detail.php:19) loads any project by ID without permission check
- [`project_log.php`](legacy_php/project_log.php:13) only validates `project_id` is an integer
- The visibility filter in [`show_projects.php:245-248`](legacy_php/show_projects.php:245) is query-level but individual actions lack re-verification

### 6.9 Duplicated / Fragile Approval Logic
- Approval generation in [`submit_request.php`](legacy_php/submit_request.php)
- Approval processing in [`show_projects.php`](legacy_php/show_projects.php)
- Additional approval request in [`show_projects.php`](legacy_php/show_projects.php)
- All use fragile string matching on modal titles (`strpos($action1, "VP")`) to determine approval level

### 6.10 Other Issues
- Session fixation risk: no `session_regenerate_id()`
- No CSRF protection
- No rate limiting on login or submission
- Error messages leak database errors (`$conn->error`)
- [`validate.php:101`](legacy_php/validate.php:101) dead code (`$user == 2` always false)

---

## 7. Proposed Django Domain Model

A new Django app named **`mis_requests`** is proposed. If the repository already has a `projects` app with overlapping models, the naming should be adjusted to avoid conflicts.

### 7.1 Existing OA Architecture Integration

> **Important:** Before implementing, inspect the existing Django project for these patterns:
> - `approvals` app with `ApprovalRule`, `ApprovalTask` models
> - `PurchaseRequest`, `TravelRequest` or similar request models for convention reference
> - `common` app with shared choices, mixins, or base models
> - History/audit patterns (e.g., `django-simple-history` or custom audit models)
> - Template base classes, navigation patterns, and permission conventions
>
> **Recommendation:** If the existing `approvals` app provides a generic approval engine with `ApprovalRule` (defines who must approve) and `ApprovalTask` (tracks individual approval instances), the MIS app should **reuse it** rather than creating separate approval models. This would mean:
> - `MISRequest` references the existing approval system via a generic relation or FK
> - Approval generation calls the existing `ApprovalRule` engine
> - Approval actions use existing `ApprovalTask` approve/reject methods
> - Activity logging uses any existing history/audit pattern
>
> The MIS-specific models below (`MISRequestApproval`, etc.) are only needed if the existing approval engine cannot support MIS requirements (e.g., department+access_level-based rules, additional approval requests mid-flow). If reuse is possible, replace `MISRequestApproval` with the existing `ApprovalTask` model and remove the MIS-specific approval service functions in favor of calling the existing approval engine.

### 7.2 Core Models

```python
# mis_requests/models.py
from django.db import models
from django.text import TextChoices


class MISRequestStatus(TextChoices):
    """Request lifecycle statuses — not a database lookup table."""
    DRAFT = 'DRAFT', 'Draft'
    SUBMITTED = 'SUBMITTED', 'Submitted'
    REVIEWING = 'REVIEWING', 'Reviewing'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'
    ASSIGNED = 'ASSIGNED', 'Assigned'
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    COMPLETED = 'COMPLETED', 'Completed'
    CANCELLED = 'CANCELLED', 'Cancelled'


class MISRequestActionType(TextChoices):
    """Activity log action types — not a database lookup table."""
    SUBMISSION = 'SUBMISSION', 'Request Submission'
    APPROVAL = 'APPROVAL', 'Approval Action'
    ASSIGNMENT = 'ASSIGNMENT', 'Assignment'
    REJECTION = 'REJECTION', 'Rejection'
    ADDITIONAL_APPROVAL_REQUEST = 'ADDITIONAL_APPROVAL_REQUEST', 'Additional Approval Request'
    CLAIM = 'CLAIM', 'Claim'


class MISRequest(models.Model):
    """Main request/project record."""
    PRIORITY_CHOICES = [(1, 'P1 - Critical'), (2, 'P2 - High'), (3, 'P3 - Medium'),
                        (4, 'P4 - Low'), (5, 'P5 - Minimal')]

    project_name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    requestor = models.ForeignKey('accounts.UserProfile', on_delete=models.PROTECT,
                                  related_name='mis_requests')
    requestor_department = models.ForeignKey('accounts.Department', on_delete=models.PROTECT,
                                             related_name='mis_requests_as_requestor_dept')
    request_type = models.ForeignKey('mis_requests.MISRequestType', on_delete=models.PROTECT)
    customer = models.CharField(max_length=255, blank=True, default='')
    project_department = models.ForeignKey('accounts.Department', on_delete=models.PROTECT,
                                           related_name='mis_requests_as_target_dept',
                                           limit_choices_to={'project_eligible': True})
    system = models.CharField(max_length=255, blank=True, default='')
    scope = models.TextField(blank=True, default='')
    description = models.TextField()
    need_by_date = models.DateField()
    priority = models.SmallIntegerField(choices=PRIORITY_CHOICES, default=5,
                                        validators=[MinValueValidator(1), MaxValueValidator(5)])
    status = models.CharField(max_length=20, choices=MISRequestStatus.choices,
                              default=MISRequestStatus.SUBMITTED)
    last_activity = models.DateTimeField(auto_now=True)
    etd = models.DateField(null=True, blank=True)
    hours_estimate = models.CharField(max_length=50, blank=True, default='')
    complete_date = models.DateField(null=True, blank=True)

    # NOTE: The following legacy denormalized fields are NOT included:
    # dept_manager, mis_manager, mis_vp, approved_by, approved_date, assign_to, file_path
    # These are derived from approval records, assignment records, and attachment records instead.

    class Meta:
        ordering = ['-created_at']
        # Duplicate prevention is handled in the service layer, not via UniqueConstraint,
        # to avoid complex cross-field conditions that are fragile at the DB level.


class MISRequestApproval(models.Model):
    """Tracks required and completed approvals for a request.

    NOTE: If the existing 'approvals' app can support MIS approval rules,
    replace this model with ApprovalTask and remove MIS-specific approval services.
    """
    STATUS_CHOICES = [('PENDING', 'Pending'), ('APPROVED', 'Approved'), ('REJECTED', 'Rejected')]
    ACCESS_LEVEL_CHOICES = [('VP', 'VP'), ('MANAGER', 'Manager')]

    request = models.ForeignKey('mis_requests.MISRequest', on_delete=models.CASCADE,
                                related_name='approvals')
    department = models.ForeignKey('accounts.Department', on_delete=models.PROTECT)
    access_level = models.CharField(max_length=10, choices=ACCESS_LEVEL_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    approved_by = models.ForeignKey('accounts.UserProfile', on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='mis_approvals_given')
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [('request', 'department', 'access_level')]
        ordering = ['access_level']


class MISRequestAssignment(models.Model):
    """Tracks which employees are assigned to a request."""
    request = models.ForeignKey('mis_requests.MISRequest', on_delete=models.CASCADE,
                                related_name='assignments')
    assigned_by = models.ForeignKey('accounts.UserProfile', on_delete=models.PROTECT,
                                    related_name='mis_assignments_made')
    assigned_to = models.ForeignKey('accounts.UserProfile', on_delete=models.PROTECT,
                                    related_name='mis_assigned_requests')
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('request', 'assigned_to')]


class MISRequestAttachment(models.Model):
    """File attachments for a request."""
    request = models.ForeignKey('mis_requests.MISRequest', on_delete=models.CASCADE,
                                related_name='attachments')
    file = models.FileField(upload_to='mis_uploads/%Y/%m/')
    file_type = models.ForeignKey('mis_requests.MISFileType', on_delete=models.PROTECT)
    description = models.TextField(blank=True, default='')
    uploaded_by = models.ForeignKey('accounts.UserProfile', on_delete=models.PROTECT,
                                    related_name='mis_uploaded_files')
    uploaded_at = models.DateTimeField(auto_now_add=True)


class MISRequestActivityLog(models.Model):
    """Audit log for all actions on a request.

    NOTE: If the project uses django-simple-history or a common audit pattern,
    consider using that instead of a custom log model.
    """
    request = models.ForeignKey('mis_requests.MISRequest', on_delete=models.CASCADE,
                                related_name='activity_log')
    action_type = models.CharField(max_length=40, choices=MISRequestActionType.choices)
    description = models.CharField(max_length=500)
    comment = models.TextField(blank=True, default='')
    performed_by = models.ForeignKey('accounts.UserProfile', on_delete=models.PROTECT,
                                     related_name='mis_performed_actions')
    created_at = models.DateTimeField(auto_now_add=True)


# Configurable lookup models (admin-managed)

class MISRequestType(models.Model):
    """Configurable request types, e.g., 'Report', 'Interface', 'Enhancement', 'Bug Fix'."""
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True)

    class Meta:
        verbose_name_plural = 'MIS request types'


class MISFileType(models.Model):
    """Configurable file types for attachments."""
    name = models.CharField(max_length=100, unique=True)
    extension = models.CharField(max_length=10)  # e.g., '.pdf', '.docx'

---

## 8. Proposed Services

Service layer in `mis_requests/services.py`:

### 8.1 `create_mis_request()`

```python
def create_mis_request(
    requestor: UserProfile,
    project_name: str,
    request_type: MISRequestType,
    project_department: Department,
    description: str,
    need_by_date: date,
    priority: int,
    customer: str = '',
    system: str = '',
    scope: str = '',
    file: Optional[UploadedFile] = None,
    file_type: Optional[MISFileType] = None,
    file_description: str = '',
) -> MISRequest:
```

- Validates requestor is authenticated
- Gets requestor department from session/profile
- Checks for duplicate in service layer (query for same name + type + requestor + status=`SUBMITTED`)
- Creates `MISRequest` with status=`MISRequestStatus.SUBMITTED`
- Calls `generate_required_approvals()`
- If no approvals generated → auto-set status=`MISRequestStatus.APPROVED`
- Handles file upload if provided (with type and size validation)
- Creates initial activity log entry (action_type=`SUBMISSION`)
- Wraps all operations in `transaction.atomic()`

### 8.2 `generate_required_approvals()`

```python
def generate_required_approvals(request_obj: MISRequest) -> List[MISRequestApproval]:
```

Implements the **corrected** approval rules from Section 4.2:

1. **Target (Project) Dept Manager:** Required if `requestor_department != project_department` OR (`same department` AND `requestor.access_level > MANAGER`)
2. **Requestor Dept Manager:** Required if `requestor.access_level > MANAGER` AND `requestor_department != project_department` (managers are trusted for cross-department requests)
3. **Target (Project) Dept VP:** Required if `priority == 1` AND requestor is NOT a VP-level user in the **target** department

Returns list of created `MISRequestApproval` objects (or creates `ApprovalTask` records if reusing the existing approvals app).

### 8.3 `approve_request()`

```python
def approve_request(
    request_obj: MISRequest,
    user: UserProfile,
    department: Department,
    access_level: str,  # 'VP' or 'MANAGER'
) -> dict:
```

- Validates user has sufficient access level for the target approval
- Finds the pending approval record for this `request` + `department` + `access_level`
- Updates approval: `status=APPROVED`, `approved_by=user`, `approved_at=now()`
- Checks if any pending approvals remain:
  - If none → set `request.status = MISRequestStatus.APPROVED`
  - If some remain → set `request.status = MISRequestStatus.REVIEWING`
- Creates activity log entry (action_type=`APPROVAL`)
- Returns dict with `new_status` and `remaining_approvals` count

### 8.4 `reject_request()`

```python
def reject_request(
    request_obj: MISRequest,
    user: UserProfile,
    department: Department,
    access_level: str,
    comment: str,
) -> dict:
```

- Validates user authorization
- Updates approval: `status=REJECTED`
- Sets `request.status = MISRequestStatus.REJECTED`
- Creates activity log entry (action_type=`REJECTION`) with comment
- Cleans up remaining pending approvals (marks them as not required)

### 8.5 `request_additional_approval()`

```python
def request_additional_approval(
    request_obj: MISRequest,
    user: UserProfile,
    department: Department,
    access_level: str,
    comment: str = '',
) -> MISRequestApproval:
```

- Checks if approval record already exists (prevent duplicates via get_or_create)
- Creates new `MISRequestApproval` with `status=PENDING`
- Sets `request.status = MISRequestStatus.REVIEWING`
- Creates activity log entry (action_type=`ADDITIONAL_APPROVAL_REQUEST`) with comment

### 8.6 `assign_request()`

```python
def assign_request(
    request_obj: MISRequest,
    assignee: UserProfile,
    assigned_by: UserProfile,
) -> MISRequestAssignment:
```

- Validates `assigned_by` is a manager in the project department
- Creates `MISRequestAssignment` record
- Sets `request.status = MISRequestStatus.ASSIGNED`
- Creates activity log entry (action_type=`ASSIGNMENT`)

### 8.7 `claim_request()`

```python
def claim_request(
    request_obj: MISRequest,
    claimant: UserProfile,
) -> MISRequestAssignment:
```

- Validates claimant is in the project department
- Validates all approvals are completed (no pending approvals)
- Creates `MISRequestAssignment` with `assigned_by=claimant` and `assigned_to=claimant`
- Sets `request.status = MISRequestStatus.ASSIGNED`
- Creates activity log entry (action_type=`CLAIM`)

---

## 9. Permissions Model

### 9.1 Role Definitions

| Role | Access Level | Description |
|------|-------------|-------------|
| Staff | 3+ | Regular employee, can submit requests, claim assignments |
| Manager | 2 | Department manager, can approve, assign, submit requests |
| VP | 1 | Vice President / President, can approve top-priority requests |
| Admin/Superuser | Django `is_superuser` | Full system access |
| Multi-Department User | Varies | User in `multi_department_user` with different roles per department |

### 9.2 Object-Level Permissions

| Action | Who Can Do It |
|--------|--------------|
| Submit request | Any authenticated user |
| View own requests | Requestor |
| View department projects | Manager/VP in `requestor_department` or `project_department` |
| View all projects | Admin/Superuser, staff in project-eligible department |
| Approve (Manager level) | Manager (`access_level <= 2`) in the relevant department |
| Approve (VP level) | VP (`access_level <= 1`) in the project department |
| Reject | Same roles as approve |
| Request additional approval | Manager in relevant department |
| Assign | Manager in project department |
| Claim | Staff in project department (when all approvals done) |
| Upload files | Requestor, assignees |
| View activity log | Anyone with view access to the request |
| Add comment | Anyone with view access to the request |

### 9.3 Django Permission Implementation

- Use Django's built-in `ModelPermissions` for CRUD operations
- Use object-level permissions in queryset filtering
- Custom permission decorators / mixins for role-based checks:
  - `@require_access_level('MANAGER')`
  - `@require_department_membership()`
- Use `django-guardian` for object-level permissions if granular per-request permissions are needed

### 9.4 Multi-Department Users

- Store department-specific access level in a `UserProfileDepartment` model (replacing legacy `multi_department_user`)
- On login, user selects active department (stored in session)
- All permission checks use the active department from session
- The `accounts` app should already handle this pattern if conventions exist

---

## 10. Implementation Phases

### Phase 1: Stable Models, Admin, Migrations, and Tests

**Scope:** Only stable data models, admin configuration, migrations, and model-level tests. No views, no forms, no business logic.

**Deliverables:**
- Create `mis_requests` app
- Implement all models from Section 7 (with `TextChoices` for status and action types)
- Configure Django admin for all models (list filters, search fields, inlines for approvals/assignments/attachments/logs)
- Create initial migration with seed data for configurable lookup tables (`MISRequestType`, `MISFileType`)
- Write model tests:
  - Test `MISRequestApproval` unique constraint (request + department + access_level)
  - Test `MISRequestAssignment` unique constraint (request + assigned_to)
  - Test model `__str__` methods
  - Test `TextChoices` enum values
  - Test model field validation (priority range, date constraints)

**Risk:** Low — no business logic yet, just data structure.

### Phase 2: Request Create/List/Detail, Attachments, Logs, Duplicate Prevention, Approval Task Generation

**Scope:** Full GET+POST for request creation, list/detail views, file attachments, activity logs, duplicate prevention, and automatic approval task generation on submission.

**Deliverables:**
- Forms: `MISRequestCreationForm` (with file upload validation)
- Service: `create_mis_request()` with duplicate prevention and `generate_required_approvals()`
- Views:
  - `MISRequestCreateView` (GET form + POST submission with approval generation)
  - `MISRequestListView` (filtered by user role/department)
  - `MISRequestDetailView` (read-only, shows approval status)
  - `MISRequestLogView` (activity log, supports popup/modal)
- Templates:
  - `mis_requests/request_form.html`
  - `mis_requests/request_list.html`
  - `mis_requests/request_detail.html`
  - `mis_requests/request_log.html`
- URL configuration
- Navigation integration with existing project dashboard
- Tests:
  - Test request creation (GET form, POST valid, POST invalid)
  - Test duplicate prevention (service layer rejects duplicate name+type+requestor+submitted)
  - Test approval generation for all corrected scenarios (Section 4.3 matrix)
  - Test auto-approval when no approvals needed
  - Test list filtering by role
  - Test detail view permission denial
  - Test file upload (valid file, invalid type, oversized file)
  - Test activity log display

**Risk:** Medium — file upload handling and approval generation logic need careful testing.

### Phase 3: Approve/Reject/Additional Approval/Assign/Claim Actions

**Scope:** All approval workflow actions and assignment operations.

**Deliverables:**
- Services: `approve_request()`, `reject_request()`, `request_additional_approval()`, `assign_request()`, `claim_request()`
- Views:
  - `ApproveRequestView` (POST via modal/AJAX)
  - `RejectRequestView` (POST via modal/AJAX, requires comment)
  - `RequestAdditionalApprovalView` (POST via modal/AJAX)
  - `AssignRequestView` (POST, multi-select employees)
  - `ClaimRequestView` (POST, self-assign)
- Update `MISRequestListView` to show action buttons based on permissions
- Tests:
  - Test approve flow (partial approval → full approval → status changes to APPROVED)
  - Test reject flow (status changes to REJECTED, remaining approvals handled)
  - Test additional approval request (new approval record created, status → REVIEWING)
  - Test assign flow (manager assigns staff, status → ASSIGNED)
  - Test claim flow (staff self-assigns, status → ASSIGNED)
  - Test permission denial for unauthorized users
  - Test VP/top-priority approval chain

**Risk:** High — complex business logic with many edge cases.

### Phase 4: Optional Legacy External Login Compatibility

**Deliverables:**
- Custom authentication backend or middleware to handle legacy external login parameters
- Replace XOR encryption with proper HMAC-based signature validation
- Session management with configurable timeout
- Graceful error pages (replacing `error.php`, `timeout.php`)
- Tests for authentication flow

**Risk:** Medium — depends on external system integration details.

---

## 11. Test Plan

### 11.1 Staff Submitting Cross-Department Request

**Setup:** Staff user (`access_level=3`) in Sales (dept 2), submitting to MIS (dept 1), priority 3.

**Expected (corrected rules):**
- Request created with status=`SUBMITTED`
- 2 approval records created:
  - Sales Department Manager (access_level=MANAGER) — requestor dept manager required for staff cross-dept
  - MIS Department Manager (access_level=MANAGER) — target dept manager required for cross-dept
- No VP approval (not P1)
- Activity log entry: "Request Submission"

### 11.2 Manager Submitting Cross-Department Request

**Setup:** Manager user (`access_level=2`) in Sales (dept 2), submitting to MIS (dept 1), priority 3.

**Expected (corrected rules):**
- Request created with status=`SUBMITTED`
- 1 approval record created:
  - MIS Department Manager (access_level=MANAGER) — target dept manager required
- **No** requestor dept manager approval (manager is trusted for outgoing requests)
- No VP approval (not P1)

### 11.3 Staff Submitting Same-Department Request

**Setup:** Staff user (`access_level=3`) in MIS (dept 1), submitting to MIS (dept 1), priority 3.

**Expected (corrected rules):**
- Request created with status=`SUBMITTED`
- 1 approval record created:
  - MIS Department Manager (access_level=MANAGER) — **target dept manager approval IS required for same-dept staff**
- **NOT auto-approved** (this corrects the original analysis error)
- Activity log entry: "Request Submission"

### 11.4 VP / Top Priority Approval

**Setup:** Staff user (`access_level=3`) in Sales (dept 2), submitting to MIS (dept 1), priority 1.

**Expected:**
- Request created with status=`SUBMITTED`
- 3 approval records created:
  - Sales Department Manager (access_level=MANAGER)
  - MIS Department Manager (access_level=MANAGER)
  - MIS Department VP (access_level=VP)

**Then:** MIS VP approves.

**Expected:**
- VP approval record updated: status=APPROVED, approved_by=VP_user
- Request status=`REVIEWING` (more approvals pending)

**Then:** Remaining approvals complete.

**Expected:**
- Request status=`APPROVED`

### 11.5 Auto-Approval When No Approvals Required

**Setup:** Manager (`access_level=2`) in MIS (dept 1), submitting to MIS (dept 1), priority 3 (non-P1).

**Expected:**
- Request created with status=`APPROVED` — auto-approved
- Zero approval records
- No VP approval needed (not P1, manager in own department)

### 11.6 Manager Same-Department Top Priority

**Setup:** Manager (`access_level=2`) in MIS (dept 1), submitting to MIS (dept 1), priority 1.

**Expected (corrected rules):**
- Request created with status=`SUBMITTED`
- 1 approval record created:
  - MIS Department VP (access_level=VP) — P1 triggers VP approval even for same-dept manager
- No manager-level approval needed (submitter is manager in own department)

### 11.7 Reject Flow

**Setup:** Request with 2 pending approvals. Manager in target department rejects.

**Expected:**
- Rejected approval record: status=REJECTED
- Request status=`REJECTED`
- Activity log entry with rejection comment
- Remaining pending approvals should be cleaned up (design decision: mark as not required)

### 11.8 Assign Flow

**Setup:** Approved request in MIS department. MIS manager assigns to 2 staff members.

**Expected:**
- 2 `MISRequestAssignment` records created
- Request status=`ASSIGNED`
- Activity log entry: "Assign to: <name1>, <name2>"

### 11.9 Duplicate Prevention

**Setup:** Staff submits request "Test Project" with type=X, status=SUBMITTED. Then tries to submit again with same name and type.

**Expected:**
- Second submission rejected with "Duplicate request" error
- Duplicate prevention enforced in service layer (query for same name+type+requestor+status=SUBMITTED)

### 11.10 File Upload

**Setup:** Submit request with valid PDF file.

**Expected:**
- File saved to structured upload directory (`mis_uploads/%Y/%m/`)
- `MISRequestAttachment` record created
- File accessible only to authorized users

**Setup:** Submit request with executable file (.exe).

**Expected:**
- File type rejected with validation error

**Setup:** Submit request with oversized file (e.g., 100MB).

**Expected:**
- File size rejected with validation error (configurable limit via `FILE_UPLOAD_MAX_MEMORY_SIZE`)

### 11.11 Permission Denial

**Setup:** Staff user in Sales tries to approve a request in MIS department.

**Expected:**
- 403 Forbidden or redirect to error page
- No database changes

**Setup:** Staff user tries to access project detail of a request in another department where they have no role.

**Expected:**
- 403 Forbidden or "Project not found" (depending on security policy)

**Setup:** Non-manager tries to assign a request.

**Expected:**
- Assign button not visible or 403 on POST

---

## Appendix A: Department Code Reference

| Code | Department | Project Eligible |
|------|-----------|-----------------|
| 1 | MIS | Likely Yes (handles assignments) |
| 2 | Sales | Unknown |
| 3 | PM | Unknown |
| 4 | Marketing | Unknown |
| 5 | Credit | Unknown |
| 6 | Production | Unknown |
| 7 | Planning | Unknown |
| 8 | Customer Service | Unknown |
| 9 | Purchasing | Unknown |
| 10 | Accounting | Unknown |
| 11 | Engineering | Unknown |
| 12 | IT | Unknown |
| 13 | Other | No (default/fallback) |

> Note: The `department.project = 'Y'` flag determines project eligibility. Only departments with this flag can be selected as `project_department`. From the code, MIS is confirmed as project-eligible (assignment logic at [`show_projects.php:398`](legacy_php/show_projects.php:398) checks `department_code == 1`).

## Appendix B: Log Type Reference

| Code | Name | Usage |
|------|------|-------|
| 18 | Request Submission | Initial log entry on request creation |
| 19 | Approval Action | Approve, Reject, Request Additional Approval |
| 21 | Assignment | Assign or Claim action |

## Appendix C: Comment Subject Reference

| Code | Subject | Usage |
|------|---------|-------|
| 23 | Project Log Comment | Comments attached to `project_log` entries |

## Appendix D: Major Uncertainties Requiring Human Review

1. **Existing `approvals` app compatibility (CRITICAL):** Before Phase 1 implementation, inspect the existing Django project for an `approvals` app with `ApprovalRule`/`ApprovalTask` models. If it exists and can support MIS approval rules (department + access_level-based routing, additional approval requests mid-flow), the MIS app should reuse it. This decision affects whether `MISRequestApproval` is needed at all, and whether the MIS-specific approval service functions should be replaced with calls to the existing approval engine. **Human decision required.**

2. **Status codes 8 and 11:** Cannot be confirmed from visible code. They are excluded from the manager view filter but their meaning and how they are set is unknown. May require checking the `options` table data or asking the legacy system owner.

3. **Claim flow implementation:** The "Claim" button exists in the UI but the backend does not clearly handle it differently from "Assign." The intended behavior may need clarification.

4. **Project-eligible departments:** Only MIS is confirmed as project-eligible from the code. The full list requires checking the `department` table's `project` column.

5. **External login system:** The legacy system relies on an external system (referred to as "SO") for authentication. The integration details, including the meaning of all URL parameters and the encryption key source, need to be confirmed with the external system team.

6. **Multi-department user data:** The `multi_department_user` table structure is inferred from a single query. The full schema may have additional columns.

7. **`employee.access_level` semantics:** The exact mapping of access levels to roles is inferred. The legacy code uses `> 2` for "not manager" and `> 1` for "not VP," but edge cases may exist.

8. **`project_detail.php` field sources:** Several fields displayed in the detail view (`assign_to`, `hours`, `etd`, `dept_manager`, `mis_manager`, `mis_vp`, `approved_by`, `approved_date`, `complete_date`, `file_path`) appear to come from the `projects` table directly, suggesting denormalized columns that may have been added by migrations not visible in the PHP code. These are NOT carried forward into the Django model.

9. **File upload directory permissions:** The legacy `uploads/` directory may have web-server-level access controls not visible in the PHP code.

10. **Whether the `projects` table has a `date` column or if `created_at` is auto-generated:** The legacy code shows `cast(p.date as date)` suggesting an explicit `date` column, but the INSERT in `submit_request.php` does not include a `date` value, suggesting it may be auto-generated by the database.

11. **Existing Django project conventions:** The current repository has minimal structure (only `README.md`, `.gitattributes`, and `legacy_php/`). If existing Django apps (`accounts`, `approvals`, `common`, `projects`, `dashboard`) exist elsewhere, their conventions should be reviewed before finalizing the proposed models. Template base classes, navigation patterns, and permission conventions should be reused.
