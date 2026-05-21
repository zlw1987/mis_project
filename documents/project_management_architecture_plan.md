# Project Management Architecture Plan

> Enterprise Internal Project Request / Project Management System
> Rebuild of legacy PHP MIS request system as a generic, multi-department-capable Django module.

**Based on:** [`documents/legacy_mis_analysis.md`](legacy_mis_analysis.md)
**Status:** Architecture design only — no implementation yet.
**Last Updated:** Repository reality check completed. All corrections A-H applied.

---

## Repository Reality Check Summary

| Item | Finding |
|------|---------|
| Workspace root | `c:/dev/mis_project` |
| Django project present? | **No** — no `manage.py`, no `settings.py`, no app directories |
| Existing approvals app? | **No** — fresh project |
| Existing accounts app? | **No** — fresh project |
| Existing common/purchase/travel/dashboard? | **No** — fresh project |
| `ProjectRequestApprovalTask` needed? | **Yes — REQUIRED** (no existing engine to reuse) |
| User model reference | `settings.AUTH_USER_MODEL` (not hard-coded `'accounts.UserProfile'`) |

### Corrections Applied

| Correction | Section | Change |
|------------|---------|--------|
| A — request_no | 2.1 | Generate on creation (not submission); `null=True, blank=True, unique=True`; `RequestNumberSequence` model with `select_for_update()` |
| B — requester field | 2.2, 6.3, 8.1, 9.2, 10.1 | All FK references use `settings.AUTH_USER_MODEL`, not `'accounts.UserProfile'` |
| C — project_department filtering | 3.3 | Correct `related_name='project_dept_profile'`; service-layer validation required |
| D — scope requiredness | 4.2 | Draft allows incomplete fields; submit requires 10 specific fields |
| E — duplicate prevention | 7.4 | Check all open statuses (DRAFT through ON_HOLD), not just SUBMITTED |
| F — permissions | 11.2, 11.3, 11.4 | Project dept staff see only assigned + claimable (not all dept requests) |
| G — activity log TextChoices | 9.1 | Top-level `class ProjectRequestActionType(models.TextChoices)`, not dynamic inside model |
| H — attachment download | 10.3, 10.4 | Never use `attachment.file.url` in templates; permission-checked download view required |

---

## Revision Summary (Round 2)

| Revision | Section | Change |
|----------|---------|--------|
| 1 — Phase 0 | 13 | Added Phase 0: Django Foundation and accounts app |
| 2 — Accounts models | 1.5 | Added Department, UserDepartment, AccessLevel TextChoices |
| 3 — Draft support | 2.2, 2.3 | Made draft-incomplete fields nullable/blankable; submit enforces required |
| 4 — request_no placement | 2.1 | Replaced signals with `ProjectRequestManager.create_with_number()` |
| 5 — Sequence concurrency | 2.1 | Added `IntegrityError` retry logic for year row creation |
| 6 — Approval TextChoices | 6.3 | Top-level `ProjectApprovalTaskStatus` and `ProjectApprovalRole` classes |
| 7 — Approval action fields | 6.3 | Replaced `approved_by`/`approved_at` with `acted_by`/`acted_at`/`decision_comment` |
| 8 — Claim workflow config | 3.1 | Added `allow_staff_claim` field to `ProjectDepartmentProfile` |
| 9 — Claimable queryset | 11.3 | Use `exclude(assignments__is_active=True)` instead of `assignments__is_active=False` |
| 10 — Attachment download | 10.4 | Replaced `serve()` with `FileResponse` |
| 11 — Seed data | 13 | Removed claim about seeding from legacy options table; use management command |
| 12 — Phase structure | 13 | Updated to Phase 0 through Phase 4 |

---

## 1. App Name Recommendation

**Recommended: `project_requests`**

Rationale:
- The system is an enterprise-wide project request / project management module, not MIS-only.
- `project_requests` clearly communicates the domain: requests that become internal projects.
- `internal_projects` is acceptable but less precise (the core object is a *request* that may become a project).
- `mis_requests` is rejected — the legacy system was MIS-centric, but the new system must support any project department.

**App label:** `project_requests`
**Verbose name:** "Project Requests"

### 1.5 Revision 2 — Accounts Foundation Models

Since this is a fresh project with no existing accounts app, the following models must be created in Phase 0 before `project_requests` can reference them.

#### AccessLevel TextChoices

```python
class AccessLevel(models.TextChoices):
    """Access levels for users within departments.

    A user may have different access levels in different departments
    (legacy supports multi-department users).
    """
    STAFF = "STAFF", "Staff"
    MANAGER = "MANAGER", "Manager"
    DIRECTOR = "DIRECTOR", "Director"
    VP = "VP", "VP"
```

**Important:** Do NOT put one global `access_level` directly on `User` as the only source of truth. A user may have different roles in different departments (e.g., Staff in Accounting, Manager in MIS).

#### Department Model

```python
class Department(models.Model):
    """Organizational department."""
    dept_code = models.CharField(max_length=20, unique=True,
                                 help_text='Short code, e.g., MIS, IT, ACCT')
    dept_name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['dept_code']
        verbose_name = 'department'
        verbose_name_plural = 'departments'

    def __str__(self):
        return f"{self.dept_code} - {self.dept_name}"
```

#### UserDepartment Model (multi-department membership)

```python
class UserDepartment(models.Model):
    """Links a user to a department with access level and properties.

    A user can belong to multiple departments with different access levels.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                             related_name='user_departments')
    department = models.ForeignKey('accounts.Department', on_delete=models.PROTECT,
                                   related_name='user_departments')
    access_level = models.CharField(max_length=20, choices=AccessLevel.choices,
                                    default=AccessLevel.STAFF)
    is_primary = models.BooleanField(default=False,
                                     help_text='Primary department for this user')
    is_active = models.BooleanField(default=True)
    can_approve = models.BooleanField(default=False,
                                      help_text='User can act as approver in this department')

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'department'],
                name='unique_user_department'
            ),
            # Only one primary department per user
            models.UniqueConstraint(
                fields=['user'],
                condition=Q(is_primary=True),
                name='one_primary_department_per_user'
            ),
        ]
        verbose_name = 'user department'
        verbose_name_plural = 'user departments'

    def __str__(self):
        return f"{self.user} → {self.department} ({self.access_level})"
```

#### Department-Based Role Helpers (Fix 2)

**CRITICAL:** Do NOT use `requester.access_level` as a global property. Access level is department-specific through `UserDepartment`. All role checks must be department-scoped.

```python
from django.contrib.auth.models import AbstractUser

def get_user_department_membership(user, department):
    """Return the UserDepartment record for user in department, or None."""
    return getattr(user, 'user_departments').filter(
        department=department, is_active=True
    ).first()


def get_user_access_level(user, department):
    """Return the access level string for user in department, or AccessLevel.STAFF."""
    membership = get_user_department_membership(user, department)
    return membership.access_level if membership else AccessLevel.STAFF


def is_staff_in_department(user, department):
    """User is STAFF level (below manager) in this department."""
    return get_user_access_level(user, department) == AccessLevel.STAFF


def is_manager_or_above(user, department):
    """User is MANAGER, DIRECTOR, or VP in this department."""
    level = get_user_access_level(user, department)
    return level in (AccessLevel.MANAGER, AccessLevel.DIRECTOR, AccessLevel.VP)


def is_vp_or_above(user, department):
    """User is VP in this department."""
    return get_user_access_level(user, department) == AccessLevel.VP


def get_user_departments(user):
    """Return all active departments for a user."""
    return getattr(user, 'user_departments').filter(is_active=True).values_list('department', flat=True)


def get_user_managed_departments(user):
    """Return departments where user is MANAGER or above."""
    return getattr(user, 'user_departments').filter(
        is_active=True,
        access_level__in=[AccessLevel.MANAGER, AccessLevel.DIRECTOR, AccessLevel.VP]
    ).values_list('department', flat=True)


def get_user_project_departments(user):
    """Return project departments where user is a member."""
    from django.db.models import Exists, OuterRef
    return getattr(user, 'user_departments').filter(
        is_active=True,
        department__project_dept_profile__is_active=True
    ).values_list('department', flat=True)
```

**All approval generation, permission checks, and selectors must use these helpers instead of any global `user.access_level`.**

#### User Model Decision (Fix 1 — Custom User Model)

**Decision:** Use a custom user model `accounts.User` extending `AbstractUser` from the first migration. Changing `AUTH_USER_MODEL` later is painful. This project may need `employee_id`, `display_name`, and identity sync for legacy external login.

```python
class User(AbstractUser):
    """Custom user model for MIS project."""
    employee_id = models.CharField(max_length=50, blank=True, default='',
                                   help_text='Legacy employee identifier')
    display_name = models.CharField(max_length=150, blank=True, default='',
                                    help_text='Display name for UI (falls back to username)')

    class Meta:
        verbose_name = 'user'
        verbose_name_plural = 'users'

    def __str__(self):
        return self.display_name or self.username
```

```python
# settings.py
AUTH_USER_MODEL = 'accounts.User'
```

**Important:** Department membership and role/access level are managed through `UserDepartment`, NOT on `User` as the only source of truth. A user may have different access levels in different departments (e.g., Staff in Accounting, Manager in MIS). All foreign keys in other apps must use `settings.AUTH_USER_MODEL`.

---

## 2. Core Domain Concept

The main object is **`ProjectRequest`** — a request submitted by any department to a project department for delivery of an internal project.

### 2.1 Business Number (Corrections A, 4, 5)

Each request gets a stable business number **when the request is first created** (not on submission). This avoids the problem of multiple drafts sharing an empty string under a unique constraint.

```
PRJ-2026-000001
```

Format: `PRJ-{YEAR}-{SEQUENCE}`

- **Generated via `ProjectRequestManager.create_with_number()`** (Revision 4 — NOT via signals)
- Immutable after generation
- Stored as `request_no` (CharField, `null=True, blank=True, unique=True`)
- Sequence resets yearly; prefix is configurable via settings
- **Abandoned drafts may leave gaps in PRJ numbers.** This is acceptable and expected for auditability.

#### RequestNumberSequence Model

```python
class RequestNumberSequence(models.Model):
    """Yearly sequence tracker for request_no generation."""
    year = models.PositiveIntegerField(unique=True)
    sequence = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'request number sequence'
        verbose_name_plural = 'request number sequences'
```

#### Concurrency-Safe Generation (Revision 5, Fix 7)

**Design decisions (unchanged):**
- Format: `PRJ-{YEAR}-{SEQUENCE}`
- Generated on creation (not submission) via `ProjectRequestManager.create_with_number()`
- NOT via signals (signals hide business behavior)
- Abandoned drafts may leave gaps — acceptable for auditability

**Concurrency approach (Fix 7):**
- Use `transaction.atomic()` with `select_for_update()` on existing yearly sequence row.
- If row does not exist, create it inside a retry loop.
- If `IntegrityError` occurs during concurrent year-row creation, retry in a **new** transaction (the current transaction may be in a broken state after IntegrityError).
- Tests should cover sequential generation; concurrency test can be added if feasible.

```python
class ProjectRequestManager(models.Manager):
    def create_with_number(self, **kwargs) -> 'ProjectRequest':
        """Create a ProjectRequest with a transaction-safe request_no.

        Uses retry loop to handle concurrent year-row creation safely.
        On IntegrityError, the current transaction is abandoned and retried
        in a new transaction to avoid operating on a broken transaction state.
        """
        from django.db import transaction, IntegrityError
        now = timezone.now()
        max_retries = 3
        for attempt in range(max_retries):
            try:
                return transaction.atomic(self._create_with_number_inner(now, **kwargs))
            except IntegrityError:
                if attempt < max_retries - 1:
                    continue
                raise RuntimeError("Failed to generate request_no after retries")

    @staticmethod
    def _create_with_number_inner(now, **kwargs):
        """Inner logic runs inside transaction.atomic()."""
        seq = RequestNumberSequence.objects.select_for_update().filter(year=now.year).first()
        if seq is None:
            # Race: another transaction may be creating this row.
            seq = RequestNumberSequence.objects.create(year=now.year)
        seq.sequence += 1
        seq.save(update_fields=['sequence'])
        request_no = f"PRJ-{now.year}-{seq.sequence:06d}"
        kwargs['request_no'] = request_no
        return ProjectRequest.objects.create(**kwargs)
```

**Why not signals?** (Revision 4) Signals hide business behavior, are harder to test, and make the creation flow non-obvious. Using `ProjectRequestManager.create_with_number()` makes the number generation explicit and testable.

**Alternative considered:** `blank=True, default=''` with generation on submission. **Rejected** because multiple drafts would share `''` violating the unique constraint.

### 2.2 Core Model Fields

```python
class ProjectRequest(models.Model):
    """Enterprise internal project request."""

    # Identity
    # Correction A: null=True allows generation before first save; unique=True enforced after populated
    request_no = models.CharField(max_length=20, unique=True, null=True, blank=True)
    # Revision 3: Draft support — project_name can be blank in drafts
    project_name = models.CharField(max_length=255, blank=True, default='')

    # Parties
    # Correction B: Use settings.AUTH_USER_MODEL
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    request_department = models.ForeignKey('accounts.Department', on_delete=models.PROTECT)
    # Correction C + Revision 3: project_department nullable for drafts
    project_department = models.ForeignKey('accounts.Department', on_delete=models.PROTECT,
                                           null=True, blank=True,
                                           limit_choices_to={'project_dept_profile__is_active': True})

    # Classification
    # Revision 3: request_type and priority nullable for drafts
    request_type = models.ForeignKey('project_requests.ProjectRequestType', on_delete=models.PROTECT,
                                     null=True, blank=True)
    priority = models.SmallIntegerField(choices=PRIORITY_CHOICES, null=True, blank=True, default=5,
                                        validators=[MinValueValidator(1), MaxValueValidator(5)])

    # Lifecycle status
    status = models.CharField(max_length=20, choices=ProjectRequestStatus.choices,
                              default=ProjectRequestStatus.DRAFT)

    # Dates
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    assigned_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    # Revision 3: needed_by_date nullable for drafts
    needed_by_date = models.DateField(null=True, blank=True)
    last_activity_at = models.DateTimeField(auto_now=True)

    # Scope (structured — see Section 4)
    scope_summary = models.TextField(blank=True, default='',
                                     help_text='Short summary shown in list/detail headers')
    business_problem = models.TextField(blank=True, default='',
                                        help_text='Why this project is needed')
    business_scope = models.TextField(blank=True, default='',
                                      help_text='Affected business process, department, customer, region, or operation')
    technical_scope = models.TextField(blank=True, default='',
                                       help_text='Affected system, report, interface, automation, data, or infrastructure')
    in_scope = models.TextField(blank=True, default='', help_text='What is explicitly included')
    out_of_scope = models.TextField(blank=True, default='', help_text='What is explicitly excluded')
    expected_deliverables = models.TextField(blank=True, default='',
                                             help_text='What must be delivered')
    acceptance_criteria = models.TextField(blank=True, default='',
                                           help_text='How requester and project department decide it is complete')
    affected_systems = models.TextField(blank=True, default='',
                                        help_text='Systems affected (free text for Phase 1; may become M2M later)')
    customer = models.CharField(max_length=255, blank=True, default='',
                                help_text='Customer name if applicable')

    # Project execution (set by project department)
    etd = models.DateField(null=True, blank=True, help_text='Estimated delivery date')
    hours_estimate = models.CharField(max_length=50, blank=True, default='')

    class Meta:
        ordering = ['-last_activity_at']
        verbose_name = 'project request'
        verbose_name_plural = 'project requests'
```

### 2.3 Design Decisions

- **`project_name`** is kept (not renamed to `title`) as requested.
- **No denormalized legacy fields:** `dept_manager`, `mis_manager`, `mis_vp`, `approved_by`, `assign_to`, `file_path` are NOT included. These are derived from approval tasks, assignments, and attachments.
- **`request_no`** is generated on creation via `ProjectRequestManager.create_with_number()` (not signals). DRAFT requests have a number.
- **`requester`** uses `settings.AUTH_USER_MODEL`, not hard-coded `'accounts.UserProfile'`.
- **Scope fields** are structured (see Section 4) rather than a single vague text field.
- **Draft support (Revision 3):** `project_name`, `request_type`, `project_department`, `needed_by_date`, `priority` all allow `blank=True`/`null=True` at the database level. `submit_project_request()` enforces required-on-submit validation in the service layer.

---

## 3. Project Department Design

### 3.1 Recommendation: Option B — `ProjectDepartmentProfile`

**Rationale:**
- Keeps `accounts.Department` clean and generic.
- Allows project-department-specific configuration without polluting the core department model.
- Supports future extensions (SLA settings, default teams, escalation rules) without modifying `accounts`.
- Fits the pattern of "profile" models used in enterprise Django apps.

```python
class ProjectDepartmentProfile(models.Model):
    """Configurable profile for departments that can receive project requests."""
    department = models.OneToOneField('accounts.Department', on_delete=models.CASCADE,
                                      related_name='project_dept_profile')
    is_active = models.BooleanField(default=True)
    can_receive_project_requests = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0, help_text='Lower = higher priority in dropdowns')
    # Revision 8: Claim workflow configuration
    allow_staff_claim = models.BooleanField(default=True,
                                            help_text='Allow project dept staff to claim approved/unassigned requests')
    # Future: default_manager_group, default_vp_group, sla_settings, etc.

    class Meta:
        ordering = ['display_order']
        verbose_name = 'project department profile'
        verbose_name_plural = 'project department profiles'
```

### 3.2 Admin Configuration

- `ProjectDepartmentProfile` is admin-editable.
- Departments without an active profile cannot be selected as `project_department`.
- Seed data includes MIS and IT (from legacy), but no hard-coded references in code.

### 3.3 Correction C — project_department filtering

The `related_name` is `'project_dept_profile'`, so all filters and queries must use:

```python
# Correct filter syntax:
project_dept_profile__is_active=True
project_dept_profile__can_receive_project_requests=True
```

**Form filtering is NOT enough.** `submit_project_request()` must also validate:

```python
def submit_project_request(request: HttpRequest, form: ProjectRequestCreationForm) -> ProjectRequest:
    # ...
    proj_dept = form.cleaned_data['project_department']
    profile = getattr(proj_dept, 'project_dept_profile', None)
    if profile is None or not profile.is_active or not profile.can_receive_project_requests:
        raise ValidationError("Selected project department is not accepting requests.")
    # ...
```

This dual validation (form `limit_choices_to` + service-layer check) prevents bypassing the filter via direct API calls or admin manipulation.

### 3.3 Legacy Mapping

| Legacy Department | Legacy Code | Seed Data |
|-------------------|-------------|-----------|
| MIS | 1 | Active project department |
| IT | 12 | Active project department |
| Engineering | 11 | Inactive by default (admin can enable) |
| Planning | 7 | Inactive by default |
| Accounting | 10 | Inactive by default |

---

## 4. Scope Design

The legacy system had a single `scope` text field plus a `description` field. This is insufficient for enterprise project management.

### 4.1 Structured Scope Fields (Phase 1)

All scope fields are on the `ProjectRequest` model as `TextField(blank=True, default='')`:

| Field | Purpose | Required? |
|-------|---------|-----------|
| `scope_summary` | Short summary (1-2 sentences) shown in list/detail headers | No |
| `business_problem` | Why this project is needed; the pain point or opportunity | No |
| `business_scope` | Affected business process, department, customer, region, or operation | No |
| `technical_scope` | Affected system, report, interface, automation, data, or infrastructure | No |
| `in_scope` | What is explicitly included in this project | No |
| `out_of_scope` | What is explicitly excluded (prevents scope creep) | No |
| `expected_deliverables` | Concrete deliverables (reports, interfaces, tools, etc.) | No |
| `acceptance_criteria` | How the requester and project department agree the project is complete | No |
| `affected_systems` | Systems affected (free text for Phase 1) | No |
| `customer` | Customer name if applicable | No |

### 4.2 Correction D — Scope Requiredness

**Draft mode:** All scope fields are optional. The requester can save a draft with incomplete scope.

**Submit validation:** The following fields are required before submission:

| Required on Submit | Field |
|--------------------|-------|
| Yes | `project_name` |
| Yes | `request_type` |
| Yes | `project_department` |
| Yes | `needed_by_date` |
| Yes | `priority` |
| Yes | `scope_summary` |
| Yes | `business_problem` |
| Yes | `in_scope` |
| Yes | `expected_deliverables` |
| Yes | `acceptance_criteria` |

**Optional on submit** (may become required by business decision later):

| Optional | Field |
|----------|-------|
| Optional | `technical_scope` |
| Optional | `out_of_scope` |
| Optional | `affected_systems` |
| Optional | `customer` |
| Optional | `business_scope` |

Enforced in `submit_project_request()` service:

```python
REQUIRED_ON_SUBMIT = [
    'project_name', 'request_type', 'project_department', 'needed_by_date', 'priority',
    'scope_summary', 'business_problem', 'in_scope', 'expected_deliverables', 'acceptance_criteria',
]

def submit_project_request(request: HttpRequest, form: ProjectRequestCreationForm) -> ProjectRequest:
    pr = form.save(commit=False)
    for field in REQUIRED_ON_SUBMIT:
        if not getattr(pr, field, None):
            raise ValidationError(f"{field} is required before submission.")
    # ... continue with request_no generation, status transition, approval generation
```

### 4.3 Phase 2 Enhancement (Optional)

- `affected_systems` could become M2M to a `BusinessSystem` model if the project already has one.
- `affected_departments` could become M2M to `Department` if cross-department impact tracking is needed.
- These are deferred to avoid over-engineering in Phase 1.

### 4.3 Form Design

The request submission form will have a "Scope" section with these fields organized in a logical layout:
1. `scope_summary` (prominent, at top)
2. `business_problem` + `business_scope` (side by side)
3. `technical_scope` + `affected_systems` (side by side)
4. `in_scope` + `out_of_scope` (side by side)
5. `expected_deliverables` + `acceptance_criteria` (side by side)

---

## 5. Status Design

### 5.1 TextChoices Definition

```python
class ProjectRequestStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    SUBMITTED = 'SUBMITTED', 'Submitted'
    REVIEWING = 'REVIEWING', 'Reviewing'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'
    ASSIGNED = 'ASSIGNED', 'Assigned'
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    ON_HOLD = 'ON_HOLD', 'On Hold'
    COMPLETED = 'COMPLETED', 'Completed'
    CANCELLED = 'CANCELLED', 'Cancelled'
```

### 5.2 Legal Status Transitions

| From | To | Trigger |
|------|----|---------|
| DRAFT | SUBMITTED | Requester submits the form |
| SUBMITTED | APPROVED | Auto-approval (no approvals required) |
| SUBMITTED | REVIEWING | Approval tasks created |
| REVIEWING | APPROVED | All approval tasks completed |
| REVIEWING | REJECTED | Any approval task rejected |
| APPROVED | ASSIGNED | Project department assigns or staff claims |
| ASSIGNED | IN_PROGRESS | Assignee starts work |
| IN_PROGRESS | ON_HOLD | Assignee or manager pauses work |
| ON_HOLD | IN_PROGRESS | Work resumes |
| IN_PROGRESS | COMPLETED | Assignee marks complete |
| DRAFT | CANCELLED | Requester cancels draft |
| SUBMITTED | CANCELLED | Requester cancels (if allowed by policy) |
| REVIEWING | CANCELLED | Requester cancels (if allowed by policy) |
| APPROVED | CANCELLED | Requester or project dept manager cancels |
| ASSIGNED | CANCELLED | Project dept manager cancels |
| IN_PROGRESS | CANCELLED | Project dept manager cancels |
| ON_HOLD | CANCELLED | Project dept manager cancels |

**Terminal states:** REJECTED, COMPLETED, CANCELLED (no transitions out)

### 5.3 Enforcement

Transitions are enforced in `project_requests/services.py`:

```python
LEGAL_TRANSITIONS = {
    ProjectRequestStatus.DRAFT: [ProjectRequestStatus.SUBMITTED, ProjectRequestStatus.CANCELLED],
    ProjectRequestStatus.SUBMITTED: [ProjectRequestStatus.APPROVED, ProjectRequestStatus.REVIEWING,
                                      ProjectRequestStatus.REJECTED, ProjectRequestStatus.CANCELLED],
    ProjectRequestStatus.REVIEWING: [ProjectRequestStatus.APPROVED, ProjectRequestStatus.REJECTED,
                                      ProjectRequestStatus.CANCELLED],
    ProjectRequestStatus.APPROVED: [ProjectRequestStatus.ASSIGNED, ProjectRequestStatus.CANCELLED],
    ProjectRequestStatus.ASSIGNED: [ProjectRequestStatus.IN_PROGRESS, ProjectRequestStatus.CANCELLED],
    ProjectRequestStatus.IN_PROGRESS: [ProjectRequestStatus.COMPLETED, ProjectRequestStatus.ON_HOLD,
                                        ProjectRequestStatus.CANCELLED],
    ProjectRequestStatus.ON_HOLD: [ProjectRequestStatus.IN_PROGRESS, ProjectRequestStatus.CANCELLED],
    ProjectRequestStatus.COMPLETED: [],
    ProjectRequestStatus.REJECTED: [],
    ProjectRequestStatus.CANCELLED: [],
}

def transition_status(request: ProjectRequest, new_status: str, actor: UserProfile) -> ProjectRequest:
    """Enforce legal status transitions and log the change."""
    if new_status not in LEGAL_TRANSITIONS.get(request.status, []):
        raise InvalidStatusTransitionError(...)
    old_status = request.status
    request.status = new_status
    # Set appropriate timestamp
    if new_status == ProjectRequestStatus.APPROVED:
        request.approved_at = now()
    elif new_status == ProjectRequestStatus.ASSIGNED:
        request.assigned_at = now()
    # ... etc
    request.save(update_fields=['status', 'last_activity_at', ...])
    # Log activity
    log_activity(request, action_type=..., from_status=old_status, to_status=new_status, actor=actor)
    return request
```

---

## 6. Approval Engine Integration

### 6.1 Fresh Project Decision

**Finding:** The workspace currently has no Django project structure (no `manage.py`, no `accounts/`, no `approvals/`, etc.). This is a fresh project.

**Decision:** Since there is no existing `approvals` app to reuse, the `project_requests` app must include its own approval models. The approval design below is self-contained but structured to be extractable into a shared `approvals` app later if other modules (purchase, travel, etc.) need it.

### 6.2 Future Extraction Path

When the project grows and other modules need approval functionality, the approval models can be extracted:
1. Move `ProjectRequestApprovalTask` → `approvals/ApprovalTask`
2. Add `ContentType` + `ObjectID` generic relation for cross-module support
3. Keep `ProjectRequest`-specific approval generation logic in `project_requests/services.py`

### 6.3 Approval Task Model (Revisions 6, 7)

Since this is a fresh project with no existing approvals app, the following model is included directly in `project_requests`. It is designed for future extraction into a shared `approvals` app.

#### Revision 6 — Top-Level TextChoices

**Do NOT define TextChoices dynamically inside the model.** Use top-level classes:

```python
class ProjectApprovalTaskStatus(models.TextChoices):
    """Status values for approval tasks."""
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"


class ProjectApprovalRole(models.TextChoices):
    """Role types for approval tasks."""
    REQUEST_DEPT_MANAGER = "REQUEST_DEPT_MANAGER", "Request Department Manager"
    PROJECT_DEPT_MANAGER = "PROJECT_DEPT_MANAGER", "Project Department Manager"
    PROJECT_DEPT_VP = "PROJECT_DEPT_VP", "Project Department VP"
```

#### Model (with Revision 7 — action fields)

```python
class ProjectRequestApprovalTask(models.Model):
    """Approval tasks for project requests. Designed for future extraction into a shared approvals app."""
    project_request = models.ForeignKey('project_requests.ProjectRequest', on_delete=models.CASCADE,
                                        related_name='approval_tasks')
    department = models.ForeignKey('accounts.Department', on_delete=models.PROTECT)
    role = models.CharField(max_length=30, choices=ProjectApprovalRole.choices)
    status = models.CharField(max_length=10, choices=ProjectApprovalTaskStatus.choices,
                              default=ProjectApprovalTaskStatus.PENDING)
    # Revision 7: Use acted_by/acted_at/decision_comment (not approved_by/approved_at)
    # The task may be approved OR rejected — "approved_by" is semantically wrong for rejection
    acted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                 null=True, blank=True,
                                 help_text='User who acted on this task (approve or reject)')
    acted_at = models.DateTimeField(null=True, blank=True,
                                    help_text='When the action was taken')
    decision_comment = models.TextField(blank=True, default='',
                                        help_text='Required when rejecting; optional when approving')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['project_request', 'department', 'role'],
                name='unique_approval_task_per_role_dept'
            )
        ]
```

**Revision 7 note:** Rejection MUST require `decision_comment`. Enforce in the service layer:

```python
def reject_approval_task(task: ProjectRequestApprovalTask, actor, comment: str) -> ProjectRequestApprovalTask:
    if not comment or not comment.strip():
        raise ValidationError("A comment is required when rejecting an approval task.")
    task.status = ProjectApprovalTaskStatus.REJECTED
    task.acted_by = actor
    task.acted_at = now()
    task.decision_comment = comment.strip()
    task.save(update_fields=['status', 'acted_by', 'acted_at', 'decision_comment'])
    # ... cascade to request status
```

**Answer: `ProjectRequestApprovalTask` is REQUIRED** (not forbidden, not optional). There is no existing approval engine to reuse.

---

## 7. Corrected Approval Rules

These rules supersede the legacy code and the original analysis document.

### 7.1 Rule Definitions

**Rule 1 — Project Department Manager Approval:**
- Required when `request_department != project_department` (cross-department).
- Also required when `request_department == project_department` AND requester is below manager level.
- NOT required when a manager submits a non-P1 request to their own project department.

**Rule 2 — Request Department Manager Approval:**
- Required ONLY when requester is below manager level AND `request_department != project_department`.
- NOT required for cross-department requests submitted by a manager (managers are trusted for outgoing requests).

**Rule 3 — Project Department VP Approval:**
- Required when priority is P1 (top priority).
- Applies to both cross-department and same-department requests.
- NOT required if the requester is already VP-level in the **project department**.

**Rule 4 — Auto-Approval:**
- If no approval rule triggers, the request is automatically set to `APPROVED`.
- This occurs when a manager submits a non-P1 request to their own project department.

### 7.2 Corrected Approval Matrix

| Scenario | Request Dept Mgr | Project Dept Mgr | Project Dept VP | Auto-Approve? |
|----------|-----------------|-----------------|-----------------|---------------|
| Staff → same project dept | No | **Yes** | No (unless P1) | No |
| Staff → cross dept | Yes | Yes | Yes (if P1) | No |
| Manager → same project dept, non-P1 | No | No | No | **Yes** |
| Manager → same project dept, P1 | No | No | **Yes** | No |
| Manager → cross dept | **No** | Yes | Yes (if P1) | No |
| VP (project dept) → same dept, P1 | No | No | No | **Yes** |
| VP → cross dept, P1 | No | Yes | Yes | No |

### 7.3 Approval Generation Service

```python
def generate_required_approvals(project_request: ProjectRequest) -> List[ProjectRequestApprovalTask]:
    """Generate approval tasks based on corrected rules.

    Fix 3: Uses department-specific role helpers (not global user.access_level)
    and ProjectApprovalRole enum values.
    """
    from .helpers import (
        is_staff_in_department,
        is_manager_or_above,
        is_vp_or_above,
    )
    approvals = []
    requester = project_request.requester
    req_dept = project_request.request_department
    proj_dept = project_request.project_department
    is_cross_dept = req_dept != proj_dept
    is_p1 = project_request.priority == 1

    # Fix 2: Department-specific role checks (NOT global user.access_level)
    requester_is_staff_in_request_dept = is_staff_in_department(requester, req_dept)
    requester_is_manager_or_above_in_request_dept = is_manager_or_above(requester, req_dept)
    requester_is_vp_or_above_in_project_dept = is_vp_or_above(requester, proj_dept)

    # Rule 1: Project Department Manager
    # Required when cross-department, or same-department from staff (below manager)
    if is_cross_dept or (not is_cross_dept and requester_is_staff_in_request_dept):
        approvals.append((ProjectApprovalRole.PROJECT_DEPT_MANAGER, proj_dept))

    # Rule 2: Request Department Manager
    # Required ONLY when staff (below manager) submits cross-department
    if requester_is_staff_in_request_dept and is_cross_dept:
        approvals.append((ProjectApprovalRole.REQUEST_DEPT_MANAGER, req_dept))

    # Rule 3: Project Department VP (P1 only)
    # NOT required if requester is already VP-level in the project department
    if is_p1 and not requester_is_vp_or_above_in_project_dept:
        approvals.append((ProjectApprovalRole.PROJECT_DEPT_VP, proj_dept))

    # Create approval tasks
    return [_create_approval_task(project_request, role, dept) for role, dept in approvals]
```

---

## 7.4 Correction E — Duplicate Prevention

**Do NOT check only `SUBMITTED` status.** The original design checked for duplicates only among requests with `status=SUBMITTED`, which is too narrow.

**Corrected behavior:** Duplicate prevention checks all **open** statuses:

| Open Statuses (duplicate check applies) | Terminal Statuses (no duplicate check) |
|----------------------------------------|----------------------------------------|
| DRAFT | REJECTED |
| SUBMITTED | CANCELLED |
| REVIEWING | COMPLETED |
| APPROVED | |
| ASSIGNED | |
| IN_PROGRESS | |
| ON_HOLD | |

**Rationale:** A requester should not be able to create multiple drafts or submissions for the same project while an earlier request is still open. Rejected, Cancelled, and Completed requests should NOT block a new request (the business may want to resubmit after addressing the rejection or completing the prior request).

**Implementation in `submit_project_request()`:**

```python
OPEN_STATUSES = [
    ProjectRequestStatus.DRAFT,
    ProjectRequestStatus.SUBMITTED,
    ProjectRequestStatus.REVIEWING,
    ProjectRequestStatus.APPROVED,
    ProjectRequestStatus.ASSIGNED,
    ProjectRequestStatus.IN_PROGRESS,
    ProjectRequestStatus.ON_HOLD,
]

def check_duplicate(project_name, request_type, requester, exclude_pk=None):
    """Check for duplicate open requests."""
    qs = ProjectRequest.objects.filter(
        project_name__iexact=project_name,
        request_type=request_type,
        requester=requester,
        status__in=OPEN_STATUSES,
    )
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    if qs.exists():
        existing = qs.first()
        raise ValidationError(
            f"A request '{existing.project_name}' of type '{existing.request_type}' "
            f"already exists (status: {existing.status}, request_no: {existing.request_no})."
        )
```

---

## 8. Assignment and Project Execution

### 8.1 Model

```python
class ProjectRequestAssignment(models.Model):
    """Tracks which employees are assigned to deliver a project request."""
    project_request = models.ForeignKey('project_requests.ProjectRequest', on_delete=models.CASCADE,
                                        related_name='assignments')
    # Correction B: Use settings.AUTH_USER_MODEL
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                    related_name='assigned_project_requests')
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                    related_name='project_requests_assigned')
    assigned_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True, help_text='False if replaced by a newer assignment')
    role = models.CharField(max_length=50, blank=True, default='',
                            help_text='e.g., Lead Developer, Analyst, Tester')

    class Meta:
        constraints = [
            # Fix 6: Conditional unique constraint — only block active duplicate assignments.
            # A user may be deactivated from an assignment and later assigned again.
            models.UniqueConstraint(
                fields=['project_request', 'assigned_to'],
                condition=Q(is_active=True),
                name='unique_active_assignment_per_user'
            )
        ]
```

### 8.2 Assignment Rules

| Rule | Enforcement |
|------|-------------|
| Only project department manager/VP can assign | Permission check in `assign_project_request()` |
| Project department staff may claim if no active assignment exists | Permission check in `claim_project_request()` |
| Assignment blocked before approval (status must be APPROVED or ASSIGNED) | Status check in service |
| Claim blocked if status is COMPLETED, REJECTED, or CANCELLED | Status check in service |
| Claim blocked if active assignment already exists | Query check in service |

### 8.3 Service Functions

```python
def assign_project_request(project_request: ProjectRequest, assignees: List[UserProfile],
                           assigned_by: UserProfile, role: str = '') -> List[ProjectRequestAssignment]:
    """Assign project to specific staff. Only project dept manager/VP can do this."""
    # Validate: assigned_by is manager/VP in project_department
    # Validate: status is APPROVED or ASSIGNED
    # Create assignment records
    # If status == APPROVED, transition to ASSIGNED
    # Log activity

def claim_project_request(project_request: ProjectRequest, claimant: UserProfile) -> ProjectRequestAssignment:
    """Self-assign. Only project dept staff can claim, and only if no active assignment exists."""
    # Validate: claimant is in project_department
    # Validate: status is APPROVED or ASSIGNED
    # Validate: no active assignment exists
    # Create assignment with assigned_by=claimant, assigned_to=claimant
    # If status == APPROVED, transition to ASSIGNED
    # Log activity
```

---

## 9. Activity Log and Audit Trail

### 9.1 Correction G — Action Types as Top-Level TextChoices

**Do NOT define TextChoices dynamically inside the model** (e.g., `ACTION_TYPES = TextChoices([...])`). Use a normal class-level TextChoices definition at module level:

```python
class ProjectRequestActionType(models.TextChoices):
    """Action types for project request activity log entries."""
    SUBMITTED = 'SUBMITTED', 'Submitted'
    APPROVAL_CREATED = 'APPROVAL_CREATED', 'Approval Task Created'
    APPROVED = 'APPROVED', 'Approved'
    REJECTED = 'REJECTED', 'Rejected'
    ADDITIONAL_APPROVAL_REQUESTED = 'ADDITIONAL_APPROVAL_REQUESTED', 'Additional Approval Requested'
    ASSIGNED = 'ASSIGNED', 'Assigned'
    CLAIMED = 'CLAIMED', 'Claimed'
    STARTED = 'STARTED', 'Started'
    PUT_ON_HOLD = 'PUT_ON_HOLD', 'Put on Hold'
    RESUMED = 'RESUMED', 'Resumed'
    COMPLETED = 'COMPLETED', 'Completed'
    CANCELLED = 'CANCELLED', 'Cancelled'
    COMMENTED = 'COMMENTED', 'Commented'
    FILE_ATTACHED = 'FILE_ATTACHED', 'File Attached'
```

### 9.2 Model

```python
class ProjectRequestActivityLog(models.Model):
    """Immutable audit log for all actions on a project request."""
    project_request = models.ForeignKey('project_requests.ProjectRequest', on_delete=models.CASCADE,
                                        related_name='activity_log')
    action_type = models.CharField(max_length=40, choices=ProjectRequestActionType.choices)
    from_status = models.CharField(max_length=20, blank=True, default='')
    to_status = models.CharField(max_length=20, blank=True, default='')
    description = models.CharField(max_length=500)
    comment = models.TextField(blank=True, default='')
    # Correction B: Use settings.AUTH_USER_MODEL
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                              related_name='project_request_actions')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['project_request', '-created_at'])]
```

### 9.2 Immutability

- No `update` or `delete` allowed after creation (enforced via admin and service layer)
- `created_at` is auto-generated and not editable
- If the project uses `django-simple-history`, consider using it for `ProjectRequest` model changes in addition to this action log

---

## 10. Attachments

### 10.1 Model

```python
class ProjectRequestAttachment(models.Model):
    """Private file attachments for project requests."""
    project_request = models.ForeignKey('project_requests.ProjectRequest', on_delete=models.CASCADE,
                                        related_name='attachments')
    file = models.FileField(upload_to='project_requests/%Y/%m/')
    original_filename = models.CharField(max_length=255)
    file_type = models.ForeignKey('project_requests.ProjectRequestFileType', on_delete=models.PROTECT)
    description = models.TextField(blank=True, default='')
    # Correction B: Use settings.AUTH_USER_MODEL
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                    related_name='uploaded_project_files')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    file_size = models.PositiveIntegerField(help_text='File size in bytes')
```

### 10.2 Lookup Model

```python
class ProjectRequestFileType(models.Model):
    """Configurable file types for attachments."""
    name = models.CharField(max_length=100, unique=True)
    allowed_extensions = models.CharField(max_length=200,
                                          help_text='Comma-separated extensions, e.g., pdf,docx,xlsx')
    max_file_size_mb = models.PositiveIntegerField(default=25, help_text='Max file size in MB')

    class Meta:
        verbose_name_plural = 'project request file types'
```

### 10.3 Security Rules

| Rule | Implementation |
|------|---------------|
| Validate extension server-side | Check against `file_type.allowed_extensions` in service |
| Validate file size server-side | Check against `file_type.max_file_size_mb` in service |
| Do not rely on HTML `accept` attribute | Server-side validation is the only enforcement |
| **Do not use `attachment.file.url` in templates** (Correction H) | Raw file URLs bypass permission checks entirely |
| **Use a permission-checked download URL only** | Every download must pass through `download_attachment()` |
| Store `original_filename` separately | Prevents path traversal; stored file uses Django's safe name |

### 10.4 Correction H — Private Download View

**CRITICAL:** Never use `{{ attachment.file.url }}` in templates as the only access control. Anyone with the URL can download the file. Always use a permission-checked download view:

```python
@require_GET
@login_required
def download_attachment(request, attachment_id):
    """Private attachment download with permission check."""
    attachment = get_object_or_404(ProjectRequestAttachment, pk=attachment_id)
    if not can_view_project_request(request.user, attachment.project_request):
        raise PermissionDenied
    # Revision 10: Use FileResponse instead of serve()
    return FileResponse(
        attachment.file.open("rb"),
        as_attachment=True,
        filename=attachment.original_filename,
    )
```

**Template usage:**

```html
<!-- WRONG - bypasses permission checks -->
<a href="{{ attachment.file.url }}">Download</a>

<!-- CORRECT - permission-checked -->
<a href="{% url 'project_requests:download_attachment' attachment.pk %}">Download</a>
```

---

## 11. Permissions Architecture

### 11.1 Module Structure

```
project_requests/
    permissions.py    # Permission check functions
    selectors.py      # Queryset filtering functions
    services.py       # Business logic services
```

### 11.2 Correction F — Permissions Architecture

**Enterprise default permission model:**

| Role | Can View |
|------|----------|
| Project department manager/VP | All requests to their project department |
| Project department staff | Only assigned requests + approved/unassigned claimable requests (if claim workflow enabled) |
| Requester | Own requests |
| Request dept manager/VP | Requests submitted by their department |
| Assignee | Assigned requests |
| Superuser | All requests |
| Unrelated staff | Only their own requests |

**Key change from original design:** Project department staff can no longer see ALL requests to their department. They see only:
1. Requests assigned to them
2. Approved/unassigned requests (claimable) — only if claim workflow is enabled for that project department

```python
def can_view_project_request(user, project_request: ProjectRequest) -> bool:
    """Check if user can view a specific project request."""
    if user.is_superuser:
        return True
    if project_request.requester == user:
        return True  # Requester can view own requests
    if _is_in_department(user, project_request.request_department) and _is_manager_or_above(user):
        return True  # Request dept manager/VP can view
    if _is_in_department(user, project_request.project_department) and _is_manager_or_above(user):
        return True  # Project dept manager/VP can see all requests to their dept
    if _is_in_department(user, project_request.project_department):
        # Project dept staff: only assigned or claimable
        if project_request.assignments.filter(assigned_to=user, is_active=True).exists():
            return True  # Assigned to this staff
        if project_request.status == ProjectRequestStatus.APPROVED:
            if not project_request.assignments.filter(is_active=True).exists():
                return True  # Claimable (approved, unassigned)
        return False
    if project_request.assignments.filter(assigned_to=user, is_active=True).exists():
        return True  # Assignee can view
    return False


def can_submit_project_request(user: UserProfile) -> bool:
    """Any authenticated staff can submit."""
    return user.is_active


def can_approve_project_task(user: UserProfile, task) -> bool:
    """Check if user can approve a specific approval task."""
    # Must be in the task's department and have sufficient access level
    ...


def can_assign_project_request(user: UserProfile, project_request: ProjectRequest) -> bool:
    """Only project department manager/VP can assign."""
    return (_is_in_department(user, project_request.project_department)
            and _is_manager_or_above(user)
            and project_request.status in (ProjectRequestStatus.APPROVED, ProjectRequestStatus.ASSIGNED))


def can_claim_project_request(user: UserProfile, project_request: ProjectRequest) -> bool:
    """Project department staff can claim if no active assignment exists."""
    if not _is_in_department(user, project_request.project_department):
        return False
    if project_request.status not in (ProjectRequestStatus.APPROVED, ProjectRequestStatus.ASSIGNED):
        return False
    if project_request.assignments.filter(is_active=True).exists():
        return False
    return True


def can_start_project_request(user: UserProfile, project_request: ProjectRequest) -> bool:
    """Assigned user or project dept manager can start."""
    ...


def can_complete_project_request(user: UserProfile, project_request: ProjectRequest) -> bool:
    """Assigned user or project dept manager can complete."""
    ...


def get_project_request_action_context(user: UserProfile, project_request: ProjectRequest) -> dict:
    """Return all action permissions for a user on a request (for UI button rendering)."""
    return {
        'can_view': can_view_project_request(user, project_request),
        'can_approve': can_approve_project_task(user, ...),
        'can_reject': ...,
        'can_assign': can_assign_project_request(user, project_request),
        'can_claim': can_claim_project_request(user, project_request),
        'can_start': can_start_project_request(user, project_request),
        'can_complete': can_complete_project_request(user, project_request),
        'can_cancel': ...,
        'can_attach_file': ...,
    }
```

### 11.3 Correction F (continued) — `selectors.py`

Updated to match the corrected permission model where project department staff only see assigned/claimable requests:

```python
from functools import reduce
from operator import or_

def get_visible_project_requests(user) -> QuerySet:
    """Return all project requests visible to the user.

    Fix 4: Uses reduce(or_, ...) for correct OR logic.
    Multiple positional Q objects in filter() are ANDed, not ORed.
    """
    if user.is_superuser:
        return ProjectRequest.objects.all()

    user_depts = get_user_departments(user)
    # Fix 2: Use department-specific helper (not global is_manager)
    managed_depts = get_user_managed_departments(user)
    is_manager = managed_depts.exists()

    visibility_conditions = [
        Q(requester=user),  # Own requests
    ]

    # Request dept manager/VP: see requests from their managed departments
    if is_manager:
        visibility_conditions.append(Q(request_department__in=managed_depts))

    # Project dept manager/VP: see all requests to their managed project departments
    if is_manager:
        visibility_conditions.append(Q(project_department__in=managed_depts))

    # Project dept staff (non-manager): see assigned + approved/unassigned (claimable)
    visibility_conditions.append(Q(assignments__assigned_to=user, assignments__is_active=True))

    # Fix 5: Claimable — use direct Q expression (not evaluating queryset and looping)
    # Also check allow_staff_claim on ProjectDepartmentProfile
    claimable_condition = (
        Q(status=ProjectRequestStatus.APPROVED)
        & Q(project_department__in=user_depts)
        & Q(project_department__project_dept_profile__allow_staff_claim=True)
    )
    visibility_conditions.append(claimable_condition)

    # Fix 4: Combine with OR logic using reduce
    if not visibility_conditions:
        return ProjectRequest.objects.none()

    visibility_q = reduce(or_, visibility_conditions)
    return ProjectRequest.objects.filter(visibility_q).distinct()


def get_my_pending_approvals(user) -> QuerySet:
    """Return requests with pending approval tasks for this user."""
    ...


def get_assigned_to_me(user) -> QuerySet:
    """Return active assignments for this user."""
    return ProjectRequest.objects.filter(
        assignments__assigned_to=user,
        assignments__is_active=True
    ).distinct()


def get_overdue_requests(user) -> QuerySet:
    """Return non-terminal requests past their needed_by_date."""
    base_qs = get_visible_project_requests(user)
    return base_qs.filter(
        needed_by_date__lt=timezone.now().date(),
        status__in=[ProjectRequestStatus.SUBMITTED, ProjectRequestStatus.REVIEWING,
                    ProjectRequestStatus.APPROVED, ProjectRequestStatus.ASSIGNED,
                    ProjectRequestStatus.IN_PROGRESS, ProjectRequestStatus.ON_HOLD]
    )
```

### 11.4 Correction F — Permission Principles Summary

| Role | Can View | Can Submit | Can Approve | Can Assign | Can Claim | Can Start/Complete |
|------|----------|------------|-------------|------------|-----------|-------------------|
| Requester | Own requests | Yes | No | No | No | No |
| Request Dept Manager/VP | Requests from their dept | Yes | Own dept approvals | No | No | No |
| Project Dept Manager/VP | All requests to their dept | Yes | Dept approvals | Yes | Yes | Yes |
| Project Dept Staff | Assigned + claimable only | Yes | No | No | Yes (if unassigned) | Yes (if assigned) |
| Assignee | Assigned requests | Yes | No | No | No | Yes |
| Superuser | All | Yes | All | All | All | All |
| Unrelated Staff | Only own requests | Yes | No | No | No | No |

---

## 12. List / Detail / Dashboard Scope

### 12.1 Planned UI Sections

| Section | Query | Phase |
|---------|-------|-------|
| My Project Requests | `requester=user` | Phase 2 |
| Project Department Queue | `project_department=user_dept AND status in (SUBMITTED, REVIEWING, APPROVED)` | Phase 3 |
| My Pending Approvals | Approval tasks assigned to user | Phase 3 |
| Assigned to Me | `assignments__assigned_to=user AND is_active` | Phase 3 |
| In Progress Projects | `status=IN_PROGRESS` | Phase 3 |
| Completed Projects | `status=COMPLETED` | Phase 3 |
| Overdue / Aging | `needed_by_date < now AND status not terminal` | Phase 3 |

### 12.2 Search and Filters

All list views support filtering by:
- `project_department` (dropdown from active `ProjectDepartmentProfile`)
- `request_department` (dropdown from all departments)
- `priority` (1-5)
- `status` (all non-terminal or specific)
- `requester` (autocomplete)
- `assigned_to` (autocomplete)
- `needed_by_date` (date range)
- `request_no` (exact match)
- `project_name` (contains)

### 12.3 Detail View Sections

1. **Header:** Request number, project name, status badge, priority badge, project department
2. **Summary:** Scope summary, needed by date, requestor, request department
3. **Scope Details:** Full structured scope fields (collapsible)
4. **Approval Status:** Current approval tasks and their status
5. **Assignments:** Active and past assignments
6. **Attachments:** File list with download links
7. **Activity Log:** Chronological action history

---

## 13. Implementation Phases (Revision 12)

### Phase 0 — Django Foundation and Accounts Foundation (Revision 1)

**Scope:** Create the Django project structure and accounts app. `project_requests` depends on `accounts.Department` and `settings.AUTH_USER_MODEL`, so these must exist first.

**Deliverables:**
- Create Django project structure (`django-admin startproject`)
- Create `accounts` app
- Create `project_requests` app shell
- Configure `settings.py`: `INSTALLED_APPS`, `TEMPLATES`, `STATIC_URL`, `MEDIA_URL`, `DATABASES`, `AUTH_USER_MODEL`
- Accounts models:
  - `Department` (dept_code, dept_name, is_active)
  - `UserDepartment` (user, department, access_level, is_primary, is_active, can_approve)
  - `AccessLevel` TextChoices (STAFF, MANAGER, DIRECTOR, VP)
- Django admin for accounts models
- Basic tests:
  - Department creation and string representation
  - UserDepartment multi-department membership
  - One primary department per user constraint
  - AccessLevel enum values

**Risk:** Low — foundation only.

### Phase 1 — project_requests Foundation Models / Admin / Tests

**Scope:** Only stable data models, admin configuration, migrations, and model-level tests. No views, no forms, no business logic.

**Deliverables:**
- Models:
  - `RequestNumberSequence`
  - `ProjectRequestType` (configurable lookup)
  - `ProjectRequestFileType` (configurable lookup)
  - `ProjectDepartmentProfile` (OneToOne to Department, with `allow_staff_claim`)
  - `ProjectRequest` (with draft support — nullable fields)
  - `ProjectRequestApprovalTask` (with top-level TextChoices)
  - `ProjectRequestAssignment`
  - `ProjectRequestAttachment`
  - `ProjectRequestActivityLog`
  - `ProjectRequestActionType` (TextChoices, not a model)
  - `ProjectApprovalTaskStatus` (TextChoices)
  - `ProjectApprovalRole` (TextChoices)
- Django admin for all models (list filters, search fields, inlines)
- **Revision 11 — Seed data:** Do NOT claim seeding from legacy `options` table (data not present in this repository). For Phase 1, provide minimal default seed data only if explicitly defined. If legacy options data becomes available later, import via data migration or management command.
- Model tests:
  - TextChoices enum values
  - Unique constraints (assignment per user, project department profile per department, approval task per role/dept)
  - Model `__str__` methods
  - Field validation (priority range, date constraints)
  - `ProjectDepartmentProfile` admin configurability
  - Draft field nullability

**Risk:** Low — no business logic yet.

### Phase 2: Create/List/Detail, Attachments, Logs, Duplicate Prevention, Approval Generation

**Scope:** Full GET+POST for request creation, list/detail views, file attachments, activity logs, duplicate prevention, and automatic approval task generation on submission.

**Deliverables:**
- Forms: `ProjectRequestCreationForm` (with structured scope fields and file upload)
- Services:
  - `submit_project_request()` with duplicate prevention and `request_no` generation
  - `generate_required_approvals()` with corrected approval rules
  - `upload_attachment()` with server-side validation
- Views:
  - `ProjectRequestCreateView` (GET form + POST submission)
  - `ProjectRequestListView` (filtered by `get_visible_project_requests()`)
  - `ProjectRequestDetailView` (read-only, shows approval status and scope)
  - `ProjectRequestLogView` (activity log)
  - `AttachmentDownloadView` (permission-checked file serving)
- Templates (following existing project conventions)
- URL configuration
- Navigation integration
- Tests:
  - Request creation (GET form, POST valid, POST invalid)
  - Structured scope fields saved correctly
  - Duplicate prevention (service layer)
  - `request_no` generation format
  - Approval generation for all corrected scenarios (Section 7.2 matrix)
  - Auto-approval when no approvals needed
  - List filtering by role/department
  - Detail view permission denial
  - File upload (valid, invalid type, oversized)
  - Private attachment download (authorized vs unauthorized)
  - Activity log entries created on submission

**Risk:** Medium — approval generation and file upload need careful testing.

### Phase 3: Approve/Reject/Additional Approval/Assign/Claim/Execute

**Scope:** All approval workflow actions, assignment operations, and project execution status transitions.

**Deliverables:**
- Services:
  - `approve_project_task()`
  - `reject_project_task()`
  - `request_additional_approval()`
  - `assign_project_request()`
  - `claim_project_request()`
  - `start_project_request()`
  - `put_on_hold()`
  - `resume_project_request()`
  - `complete_project_request()`
  - `cancel_project_request()`
- Views for each action (POST via modal/AJAX)
- Update list/detail views with action buttons based on `get_project_request_action_context()`
- Dashboard sections:
  - Project Department Queue
  - My Pending Approvals
  - Assigned to Me
  - Overdue / Aging
- Tests:
  - Approve flow (partial → full → APPROVED)
  - Reject flow (→ REJECTED, cleanup)
  - Additional approval request (new task, → REVIEWING)
  - Assign flow (manager assigns, → ASSIGNED)
  - Claim flow (staff self-assigns, → ASSIGNED)
  - Start/complete flow (ASSIGNED → IN_PROGRESS → COMPLETED)
  - On-hold/resume flow
  - Cancel from various states
  - Assignment blocked before approval
  - Claim blocked if already assigned
  - Illegal state transitions rejected
  - Permission denial for all actions
  - Activity log immutability

**Risk:** High — complex business logic with many edge cases.

### Phase 4: Legacy Compatibility and Data Migration

**Scope:** Optional legacy external login compatibility and data migration from PHP system.

**Deliverables:**
- Custom authentication backend for legacy external login parameters
- Replace XOR encryption with HMAC-based signature validation
- Session management with configurable timeout
- Data migration script (if needed):
  - Import legacy `projects` → `ProjectRequest`
  - Import legacy `approval` → approval tasks
  - Import legacy `project_assignment` → `ProjectRequestAssignment`
  - Import legacy `project_file` → `ProjectRequestAttachment`
  - Import legacy `project_log` → `ProjectRequestActivityLog`

**Risk:** Medium — depends on external system and legacy data quality.

---

## 14. Testing Strategy (Fix 8 — Updated)

### 14.1 Model Tests (Phase 0-1)

- `accounts.User` exists and `AUTH_USER_MODEL` is `'accounts.User'`
- `User` has `employee_id` and `display_name` fields
- `ProjectRequestStatus` TextChoices has all expected values
- `ProjectDepartmentProfile` is admin-configurable (not hard-coded)
- `ProjectRequestAssignment` conditional unique constraint:
  - Active duplicate assignment is blocked
  - Inactive assignment does NOT block re-assigning same user
- `ProjectRequest` field validation (priority 1-5, dates)
- `UserDepartment` supports same user in multiple departments with different access levels
- One primary department per user constraint

### 14.2 Service Tests (Phase 2-3)

| Test Case | Expected Result |
|-----------|----------------|
| Staff submits cross-department request | Request dept mgr + project dept mgr approvals created |
| Manager submits cross-department request | Project dept mgr approval only (no request dept mgr) |
| Staff submits same project dept request | Project dept mgr approval required |
| Manager submits same project dept, non-P1 | Auto-approved (no approvals) |
| Manager submits same project dept, P1 | Project dept VP approval required |
| VP (project dept) submits same dept, P1 | Auto-approved |
| Staff submits cross-dept, P1 | Request dept mgr + project dept mgr + project dept VP |
| P1 cross-dept from non-project-dept VP | Project dept mgr + project dept VP (no request dept mgr) |
| **Approval uses department-specific roles** | `is_staff_in_department(requester, req_dept)` used, not `requester.access_level` |
| Assignment attempted before approval | Blocked with error |
| Claim attempted with active assignment | Blocked with error |
| Claim attempted on COMPLETED request | Blocked with error |
| Illegal status transition (e.g., DRAFT → COMPLETED) | Rejected with InvalidStatusTransitionError |
| Auto-approval when no rules trigger | Status set to APPROVED, approved_at set |

### 14.3 Permission Tests (Phase 2-3)

| Test Case | Expected Result |
|-----------|----------------|
| Requester views own request | Allowed |
| Request dept manager views dept's requests | Allowed |
| Project dept staff views assigned + claimable only | Allowed (not all dept requests) |
| **Claim visibility respects `allow_staff_claim`** | Staff cannot see claimable when `allow_staff_claim=False` |
| Unrelated staff views another dept's request | Denied |
| Assignee views assigned request | Allowed |
| Superuser views all requests | Allowed |
| Non-manager tries to assign | Denied |
| Non-project-dept user tries to claim | Denied |
| Unauthorized user downloads attachment | Denied |
| **`get_visible_project_requests` uses OR logic** | User sees union of own/managed/assigned/claimable (not intersection) |

### 14.4 Integration Tests (Phase 2-3)

- Full submission flow: DRAFT → SUBMITTED → approval tasks created → all approved → APPROVED
- Full rejection flow: SUBMITTED → one rejection → REJECTED
- Full assignment flow: APPROVED → assigned → IN_PROGRESS → COMPLETED
- Full claim flow: APPROVED → claimed → IN_PROGRESS → COMPLETED
- File upload and download with permission checks
- Activity log entries created for every action

### 14.5 Configuration Tests (Phase 0-1)

- Project department can be added/removed via admin without code changes
- Adding a new project department makes it available in the request form
- Removing a project department's active profile prevents new requests to it
- MIS and IT are not hard-coded in any model, service, or view
- `AUTH_USER_MODEL` is `'accounts.User'` from first migration

---

## Appendix A: Complete Model List (Updated)

| Model | Purpose | Phase |
|-------|---------|-------|
| `RequestNumberSequence` | Yearly sequence tracker for request_no generation (Correction A) | 1 |
| `ProjectRequest` | Core request entity | 1 |
| `ProjectRequestType` | Configurable request types | 1 |
| `ProjectRequestFileType` | Configurable file types | 1 |
| `ProjectDepartmentProfile` | Configurable project departments | 1 |
| `ProjectRequestApprovalTask` | Approval tasks (REQUIRED — no existing approvals app) | 1 |
| `ProjectRequestAttachment` | File attachments | 1 |
| `ProjectRequestAssignment` | Staff assignments | 1 |
| `ProjectRequestActivityLog` | Immutable audit log | 1 |
| `ProjectRequestActionType` | TextChoices for activity log action types (not a model) | — |

---

## Appendix B: Final Status Transition Diagram

```
                    DRAFT
                      |
                      v
                  SUBMITTED -----> APPROVED (auto, if no approvals)
                      |                 |
                      v                 v
                  REVIEWING <----------+
                      |
          +-----------+-----------+
          |           |           |
          v           v           v
      APPROVED    REJECTED    CANCELLED
          |
          v
      ASSIGNED
          |
          v
     IN_PROGRESS <--> ON_HOLD
          |
          v
      COMPLETED

Any non-terminal state --> CANCELLED (with permission check)
```

---

## Appendix C: Blockers Requiring Human Decision (Updated)

### Resolved Items

1. **~~Existing `approvals` app compatibility~~ — RESOLVED:** The workspace has no Django project structure. This is a fresh project. `ProjectRequestApprovalTask` is **REQUIRED** (not conditional). See Section 6.3.

2. **~~Existing `accounts` app structure~~ — PARTIALLY RESOLVED:** All FK references to user models now use `settings.AUTH_USER_MODEL` (Correction B). The `accounts.Department` model still needs to be confirmed when the accounts app is created.

3. **~~`request_no` format~~ — RESOLVED:** Changed from `PRJREQ-{YEAR}-{SEQUENCE}` to `PRJ-{YEAR}-{SEQUENCE}` (Correction A). Generated on creation using `RequestNumberSequence` model with `select_for_update()`.

### Remaining Blockers

4. **`request_no` format confirmation:** The format `PRJ-{YEAR}-{SEQUENCE}` (e.g., `PRJ-2026-000001`) should be confirmed with stakeholders. The prefix and sequence length may need adjustment.

5. **User model and access level:** When the `accounts` app is created, confirm:
   - What is `settings.AUTH_USER_MODEL`? (Django's built-in `auth.User` or a custom model?)
   - How is user access level (Staff/Manager/VP) represented? (`access_level` field? Group membership? Custom roles?)
   - How is department membership tracked? (Single FK? M2M multi-department?)

6. **Scope field requirements:** The proposed structured scope fields are comprehensive but may be more than needed for Phase 1. Stakeholders should confirm which fields are essential vs. nice-to-have. See Correction D for the required-on-submit list.

7. **Legacy data migration:** If importing data from the legacy PHP system is needed, the quality and completeness of the legacy data must be assessed first.

8. **External login system:** The legacy system uses an external authentication source ("SO"). The integration approach (custom backend vs. SSO vs. Django auth) needs to be decided.

9. **Common choices and navigation:** When `common/choices.py` and `common/navigation.py` exist, reuse their patterns for priority choices, status patterns, and navigation integration.
