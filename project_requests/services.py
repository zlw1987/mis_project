"""Business services for the project_requests app.

All business logic lives here, not in views.
"""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.services import (
    get_user_department_membership,
    is_manager_or_above,
    is_staff_in_department,
    is_vp_or_above,
)

from .models import (
    ProjectApprovalRole,
    ProjectApprovalTaskStatus,
    ProjectRequest,
    ProjectRequestActivityLog,
    ProjectRequestApprovalTask,
    ProjectRequestAssignment,
    ProjectRequestAttachment,
    ProjectRequestStatus,
    ProjectRequestActionType,
    RequestNumberSequence,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OPEN_STATUSES = [
    ProjectRequestStatus.DRAFT,
    ProjectRequestStatus.SUBMITTED,
    ProjectRequestStatus.REVIEWING,
    ProjectRequestStatus.APPROVED,
    ProjectRequestStatus.ASSIGNED,
    ProjectRequestStatus.IN_PROGRESS,
    ProjectRequestStatus.ON_HOLD,
]


# ---------------------------------------------------------------------------
# 1. Request Number Generation
# ---------------------------------------------------------------------------

def generate_request_no():
    """Generate a transaction-safe request number: PRJ-{YEAR}-{6-digit sequence}.

    Uses select_for_update() on the yearly sequence row.
    Retries up to 3 times if concurrent year-row creation causes IntegrityError.
    """
    now = timezone.now()
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return _generate_request_no_inner(now)
        except IntegrityError:
            if attempt < max_retries - 1:
                continue
            raise RuntimeError("Failed to generate request_no after retries")


@transaction.atomic
def _generate_request_no_inner(now):
    """Inner logic for request number generation (runs inside transaction.atomic)."""
    seq = RequestNumberSequence.objects.select_for_update().filter(year=now.year).first()
    if seq is None:
        seq = RequestNumberSequence.objects.create(year=now.year, sequence=0)
    seq.sequence += 1
    seq.save(update_fields=["sequence"])
    return f"PRJ-{now.year}-{seq.sequence:06d}"


def create_project_request_draft(**kwargs):
    """Create a ProjectRequest in DRAFT status with an auto-generated request_no.

    Expects kwargs suitable for ProjectRequest creation (requester, request_department, etc.).
    Always forces status=DRAFT regardless of caller-provided status.
    """
    request_no = generate_request_no()
    kwargs["status"] = ProjectRequestStatus.DRAFT
    kwargs["request_no"] = request_no
    return ProjectRequest.objects.create(**kwargs)


# ---------------------------------------------------------------------------
# 2. Required-on-submit Validation
# ---------------------------------------------------------------------------

def validate_required_for_submit(project_request):
    """Validate that all required fields are populated before submission.

    Checks:
    - requester must exist and be active.
    - request_department must exist and be active.
    - requester must have an active UserDepartment membership in request_department.
    - request_type must exist and be active.
    - project_department must have active ProjectDepartmentProfile with
      is_active=True and can_receive_project_requests=True.
    - Required string fields must be non-empty after strip():
      project_name, scope_summary, business_problem, in_scope,
      expected_deliverables, acceptance_criteria.
    - needed_by_date and priority must still be required.
    - project_department and request_type must still be required.

    Raises ValidationError with a dict of errors if validation fails.
    """
    errors = {}

    # --- Requester checks ---
    requester = getattr(project_request, "requester", None)
    if not requester or not getattr(requester, "is_active", False):
        errors["requester"] = "Requester must be an active user."

    # --- Request department checks ---
    req_dept = getattr(project_request, "request_department", None)
    if not req_dept:
        errors["request_department"] = "Request department is required."
    elif not getattr(req_dept, "is_active", False):
        errors["request_department"] = "Request department must be active."

    # --- Requester membership in request department ---
    if requester and req_dept:
        membership = get_user_department_membership(requester, req_dept)
        if membership is None:
            errors["request_department"] = (
                "Requester must be a member of the request department."
            )

    # --- Request type checks ---
    req_type = getattr(project_request, "request_type", None)
    if not req_type:
        errors["request_type"] = "Request type is required."
    elif not getattr(req_type, "is_active", False):
        errors["request_type"] = "Request type must be active."

    # --- Project department checks ---
    proj_dept = getattr(project_request, "project_department", None)
    if not proj_dept:
        errors["project_department"] = "Project department is required."
    elif not getattr(proj_dept, "is_active", False):
        errors["project_department"] = "Project department must be active."
    else:
        profile = getattr(proj_dept, "project_dept_profile", None)
        if profile is None or not profile.is_active or not profile.can_receive_project_requests:
            errors["project_department"] = (
                "Selected project department is not accepting requests."
            )

    # --- String fields: non-empty after strip ---
    string_fields = [
        "project_name",
        "scope_summary",
        "business_problem",
        "in_scope",
        "expected_deliverables",
        "acceptance_criteria",
    ]
    for field in string_fields:
        value = getattr(project_request, field, None)
        if not value or not str(value).strip():
            errors[field] = f"{field} is required before submission."

    # --- needed_by_date and priority ---
    if not getattr(project_request, "needed_by_date", None):
        errors["needed_by_date"] = "needed_by_date is required before submission."
    if not getattr(project_request, "priority", None):
        errors["priority"] = "priority is required before submission."

    if errors:
        raise ValidationError(errors)


# ---------------------------------------------------------------------------
# 2b. Normalization Helper
# ---------------------------------------------------------------------------

NORMALIZE_FIELDS = [
    "project_name",
    "scope_summary",
    "business_problem",
    "in_scope",
    "expected_deliverables",
    "acceptance_criteria",
    "business_scope",
    "technical_scope",
    "out_of_scope",
    "affected_systems",
    "customer",
    "hours_estimate",
]


def normalize_project_request_for_submit(project_request):
    """Strip whitespace on text fields before duplicate prevention.

    Returns True if any field was changed.
    """
    changed = False
    for field in NORMALIZE_FIELDS:
        value = getattr(project_request, field, None)
        if value:
            stripped = str(value).strip()
            if stripped != str(value):
                setattr(project_request, field, stripped)
                changed = True
    return changed


# ---------------------------------------------------------------------------
# 3. Duplicate Prevention
# ---------------------------------------------------------------------------

def check_duplicate_open_request(project_request):
    """Check for duplicate open requests.

    Duplicate definition:
    - same requester
    - same request_type
    - normalized project_name comparison (trim + lowercase)
    - status in OPEN_STATUSES
    - exclude current project_request pk

    Uses database functions (Lower/Trim) for normalized comparison so that
    existing requests with leading/trailing whitespace are also caught.

    Raises ValidationError if a duplicate is found.
    """
    from django.db.models.functions import Lower, Trim

    normalized_name = (project_request.project_name or "").strip().lower()

    duplicates = (
        ProjectRequest.objects
        .filter(
            requester=project_request.requester,
            request_type=project_request.request_type,
            status__in=OPEN_STATUSES,
        )
        .exclude(pk=project_request.pk)
        .annotate(normalized_project_name=Lower(Trim("project_name")))
        .filter(normalized_project_name=normalized_name)
    )

    if duplicates.exists():
        existing = duplicates.first()
        raise ValidationError(
            f"A duplicate open request already exists: {existing.request_no}"
        )


# ---------------------------------------------------------------------------
# 4. Activity Logging Service
# ---------------------------------------------------------------------------

def create_activity_log(
    project_request,
    action_type,
    actor=None,
    description="",
    comment="",
    from_status="",
    to_status="",
):
    """Create an immutable activity log entry for a project request.

    Updates project_request.last_activity_at to timezone.now() after log creation.
    Returns the created log entry.
    """
    log = ProjectRequestActivityLog.objects.create(
        project_request=project_request,
        action_type=action_type,
        actor=actor,
        description=description,
        comment=comment,
        from_status=from_status,
        to_status=to_status,
    )
    # Update last_activity_at without triggering recursive side effects
    ProjectRequest.objects.filter(pk=project_request.pk).update(
        last_activity_at=timezone.now()
    )
    return log


# ---------------------------------------------------------------------------
# 5. Approval Generation
# ---------------------------------------------------------------------------

def generate_required_approvals(project_request):
    """Generate approval tasks based on department-scoped rules.

    Returns a list of (department, role) tuples that need approval tasks.
    """
    requester = project_request.requester
    req_dept = project_request.request_department
    proj_dept = project_request.project_department
    priority = project_request.priority

    is_same_dept = (req_dept == proj_dept)
    requester_is_staff = is_staff_in_department(requester, req_dept)
    requester_is_vp_in_proj = is_vp_or_above(requester, proj_dept)
    is_p1 = (priority == 1)

    approvals = []

    # Rule 1 — Project Department Manager Approval
    # Required when:
    #   - cross-department (req_dept != proj_dept), OR
    #   - same department AND requester is below manager level
    # Not required when manager submits non-P1 to own department
    if not is_same_dept:
        approvals.append((proj_dept, ProjectApprovalRole.PROJECT_DEPT_MANAGER))
    elif requester_is_staff:
        approvals.append((proj_dept, ProjectApprovalRole.PROJECT_DEPT_MANAGER))

    # Rule 2 — Request Department Manager Approval
    # Required only when:
    #   - requester is below manager level in request_department AND
    #   - request_department != project_department
    if not is_same_dept and requester_is_staff:
        approvals.append((req_dept, ProjectApprovalRole.REQUEST_DEPT_MANAGER))

    # Rule 3 — Project Department VP Approval
    # Required when priority is P1 AND requester is not VP in project_department
    if is_p1 and not requester_is_vp_in_proj:
        approvals.append((proj_dept, ProjectApprovalRole.PROJECT_DEPT_VP))

    return approvals


def _create_approval_tasks(project_request, approvals):
    """Create ProjectRequestApprovalTask records for the given approvals list.

    Avoids duplicates. Creates activity logs for each approval task.
    """
    created_tasks = []
    for dept, role in approvals:
        task, created = ProjectRequestApprovalTask.objects.get_or_create(
            project_request=project_request,
            department=dept,
            role=role,
            defaults={
                "status": ProjectApprovalTaskStatus.PENDING,
                "decision_comment": "",
            },
        )
        if created:
            created_tasks.append(task)
            create_activity_log(
                project_request=project_request,
                action_type=ProjectRequestActionType.APPROVAL_CREATED,
                description=f"Approval task created: {task.get_role_display()} for {dept}",
            )
    return created_tasks


# ---------------------------------------------------------------------------
# 6. Submit Workflow Service
# ---------------------------------------------------------------------------

@transaction.atomic
def submit_project_request(project_request, actor):
    """Submit a DRAFT project request.

    Steps:
    1. Lock the ProjectRequest row with select_for_update()
    2. Validate actor (authenticated, active, requester or superuser)
    3. Verify DB status is DRAFT (not stale in-memory object)
    4. Validate required fields
    5. Check duplicate prevention
    6. Transition DRAFT -> SUBMITTED
    7. Generate approval tasks
    8. If required_approvals non-empty: SUBMITTED -> REVIEWING
    9. If no approvals required: SUBMITTED -> APPROVED (auto-approve)

    Returns the updated project_request (locked_request from DB).
    """
    # Step 1: Lock the row to prevent concurrent submissions
    locked_request = ProjectRequest.objects.select_for_update().get(
        pk=project_request.pk
    )

    # Step 2: Validate actor
    if not actor or not getattr(actor, "is_authenticated", False):
        raise PermissionDenied("Actor must be an authenticated user.")
    if not actor.is_active:
        raise PermissionDenied("Actor must be an active user.")
    if actor != locked_request.requester and not actor.is_superuser:
        raise PermissionDenied(
            "Only the requester or a superuser can submit this request."
        )

    # Step 3: Must be DRAFT (use DB state, not stale in-memory object)
    if locked_request.status != ProjectRequestStatus.DRAFT:
        raise ValidationError(
            f"Cannot submit request with status '{locked_request.status}'. "
            "Only DRAFT can be submitted."
        )

    # Step 4: Validate required fields
    validate_required_for_submit(locked_request)

    # Step 4b: Normalize text fields before duplicate check
    normalize_project_request_for_submit(locked_request)
    locked_request.save(update_fields=NORMALIZE_FIELDS)

    # Step 5: Check duplicates
    check_duplicate_open_request(locked_request)

    # Step 6: Transition to SUBMITTED
    old_status = locked_request.status
    locked_request.status = ProjectRequestStatus.SUBMITTED
    locked_request.submitted_at = timezone.now()
    locked_request.save(update_fields=["status", "submitted_at", "last_activity_at"])

    create_activity_log(
        project_request=locked_request,
        action_type=ProjectRequestActionType.SUBMITTED,
        actor=actor,
        description="Request submitted for approval",
        from_status=old_status,
        to_status=ProjectRequestStatus.SUBMITTED,
    )

    # Step 7: Generate approval tasks
    required_approvals = generate_required_approvals(locked_request)
    _create_approval_tasks(locked_request, required_approvals)

    # Step 8/9: Decision based on required_approvals (not created_tasks)
    if required_approvals:
        # Has approvals required -> REVIEWING
        locked_request.status = ProjectRequestStatus.REVIEWING
        locked_request.save(update_fields=["status", "last_activity_at"])
        create_activity_log(
            project_request=locked_request,
            action_type=ProjectRequestActionType.APPROVAL_CREATED,
            description="Approval tasks created; request under review",
            from_status=ProjectRequestStatus.SUBMITTED,
            to_status=ProjectRequestStatus.REVIEWING,
        )
    else:
        # No approvals required -> auto-approve
        locked_request.status = ProjectRequestStatus.APPROVED
        locked_request.approved_at = timezone.now()
        locked_request.save(update_fields=["status", "approved_at", "last_activity_at"])
        create_activity_log(
            project_request=locked_request,
            action_type=ProjectRequestActionType.APPROVED,
            description="Auto-approved (no approval tasks required)",
            from_status=ProjectRequestStatus.SUBMITTED,
            to_status=ProjectRequestStatus.APPROVED,
        )

    return locked_request


# ---------------------------------------------------------------------------
# 9. Attachment Upload Service
# ---------------------------------------------------------------------------

@transaction.atomic
def upload_project_request_attachment(
    project_request, uploaded_file, file_type, uploaded_by, description=""
):
    """Upload and attach a file to a project request.

    Validates:
    - uploaded_by has permission to attach (via can_attach_file)
    - file_type is active
    - extension matches allowed_extensions (case-insensitive)
    - file has an extension (no-extension files rejected)
    - allowed_extensions is non-empty
    - file size <= max_file_size_mb

    Creates ProjectRequestAttachment and FILE_ATTACHED activity log
    within an atomic transaction.

    Returns the created ProjectRequestAttachment.
    Raises PermissionDenied if uploaded_by lacks permission.
    Raises ValidationError for file validation failures.
    """
    # Validate permission first
    from .permissions import can_attach_file
    if not can_attach_file(uploaded_by, project_request):
        raise PermissionDenied(
            "You do not have permission to attach files to this request."
        )

    # Validate file_type is active
    if not file_type.is_active:
        raise ValidationError("Selected file type is not active.")

    # Parse allowed extensions (strip whitespace, lowercase, remove leading dot)
    allowed = [
        e.strip().lower().lstrip(".")
        for e in file_type.allowed_extensions.split(",")
        if e.strip()
    ]
    if not allowed:
        raise ValidationError(
            "No file extensions are configured for this file type."
        )

    # Validate extension
    import os
    filename = uploaded_file.name if hasattr(uploaded_file, "name") else str(uploaded_file)
    _, ext = os.path.splitext(filename)
    ext_stripped = ext.lstrip(".")
    if not ext_stripped:
        raise ValidationError("File must have a valid extension.")
    ext_lower = ext_stripped.lower()
    if ext_lower not in allowed:
        raise ValidationError(
            f"Extension '.{ext_lower}' is not allowed. "
            f"Allowed: {file_type.allowed_extensions}"
        )

    # Validate file size — prefer uploaded_file.size when available
    max_bytes = file_type.max_file_size_mb * 1024 * 1024
    if hasattr(uploaded_file, "size") and uploaded_file.size is not None:
        file_size = uploaded_file.size
    else:
        content = uploaded_file.read()
        file_size = len(content)
        uploaded_file.seek(0)
    if file_size > max_bytes:
        raise ValidationError(
            f"File size ({file_size} bytes) exceeds maximum "
            f"({file_type.max_file_size_mb} MB)."
        )

    # Reset file pointer for saving
    uploaded_file.seek(0)

    # Determine original filename
    original_filename = (
        filename
        if filename
        else f"attachment.{ext_lower}"
    )

    # Create attachment and activity log atomically
    attachment = ProjectRequestAttachment.objects.create(
        project_request=project_request,
        file=uploaded_file,
        original_filename=original_filename,
        file_type=file_type,
        uploaded_by=uploaded_by,
        file_size=file_size,
        description=description,
    )

    # Create activity log
    create_activity_log(
        project_request=project_request,
        action_type=ProjectRequestActionType.FILE_ATTACHED,
        actor=uploaded_by,
        description=f"File attached: {original_filename}",
    )

    return attachment


# ---------------------------------------------------------------------------
# 10. Approve/Reject Workflow Services (Phase 3A)
# ---------------------------------------------------------------------------

@transaction.atomic
def approve_project_request(project_request, approval_task, actor, comment=""):
    """Approve a project request by acting on an approval task.

    Rules:
    - Uses transaction.atomic().
    - Locks ProjectRequest row with select_for_update().
    - Locks ProjectRequestApprovalTask row with select_for_update().
    - Uses DB-fresh locked objects, not stale in-memory objects.
    - The locked approval task must belong to the locked project_request.
    - ProjectRequest.status must be REVIEWING.
    - approval_task.status must be PENDING.
    - actor must pass can_approve_project_request_task(actor, locked_task).
    - Approval comment is optional.
    - Sets approval_task.status = APPROVED, acted_by, acted_at, decision_comment.
    - If all approval tasks for the project_request are APPROVED:
      - ProjectRequest.status -> APPROVED
      - approved_at = now()
      - create activity log with action_type APPROVED
    - If not all tasks are approved:
      - ProjectRequest remains REVIEWING
      - No separate activity log for individual task approval (no compatible action_type)
    - Non-PENDING task raises ValidationError.
    - Returns locked ProjectRequest.
    """
    from .permissions import can_approve_project_request_task

    # Lock the ProjectRequest row
    locked_request = ProjectRequest.objects.select_for_update().get(
        pk=project_request.pk
    )

    # Lock the ApprovalTask row
    locked_task = ProjectRequestApprovalTask.objects.select_for_update().get(
        pk=approval_task.pk
    )

    # Verify the task belongs to this project request
    if locked_task.project_request_id != locked_request.pk:
        raise ValidationError(
            "The approval task does not belong to this project request."
        )

    # ProjectRequest must be REVIEWING
    if locked_request.status != ProjectRequestStatus.REVIEWING:
        raise ValidationError(
            f"Cannot approve request with status '{locked_request.status}'. "
            "Request must be under review."
        )

    # Task must be PENDING
    if locked_task.status != ProjectApprovalTaskStatus.PENDING:
        raise ValidationError(
            f"Cannot approve task with status '{locked_task.status}'. "
            "Task must be pending."
        )

    # Actor must have permission
    if not can_approve_project_request_task(actor, locked_task):
        raise PermissionDenied(
            "You do not have permission to approve this task."
        )

    # Set task fields
    locked_task.status = ProjectApprovalTaskStatus.APPROVED
    locked_task.acted_by = actor
    locked_task.acted_at = timezone.now()
    locked_task.decision_comment = comment.strip() if comment else ""
    locked_task.save(update_fields=[
        "status", "acted_by", "acted_at", "decision_comment", "updated_at"
    ])

    # Check if ALL tasks are APPROVED (not just no PENDING tasks)
    # This handles edge cases where tasks might be in other non-PENDING states
    non_approved_tasks = ProjectRequestApprovalTask.objects.filter(
        project_request=locked_request,
    ).exclude(status=ProjectApprovalTaskStatus.APPROVED)

    if not non_approved_tasks.exists():
        # All tasks are APPROVED - transition to APPROVED
        old_status = locked_request.status
        locked_request.status = ProjectRequestStatus.APPROVED
        locked_request.approved_at = timezone.now()
        locked_request.save(update_fields=["status", "approved_at", "last_activity_at"])

        create_activity_log(
            project_request=locked_request,
            action_type=ProjectRequestActionType.APPROVED,
            actor=actor,
            description="Request approved by all approvers",
            from_status=old_status,
            to_status=ProjectRequestStatus.APPROVED,
        )
    else:
        # Not all tasks approved yet - just update last_activity_at
        locked_request.save(update_fields=["last_activity_at"])

    return locked_request


@transaction.atomic
def reject_project_request(project_request, approval_task, actor, comment):
    """Reject a project request by acting on an approval task.

    Rules:
    - Uses transaction.atomic().
    - Locks ProjectRequest row with select_for_update().
    - Locks ProjectRequestApprovalTask row with select_for_update().
    - Uses DB-fresh locked objects.
    - locked approval task must belong to locked project_request.
    - ProjectRequest.status must be REVIEWING.
    - approval_task.status must be PENDING.
    - actor must pass can_reject_project_request_task(actor, locked_task).
    - Rejection comment is required (non-empty, non-whitespace).
    - Sets approval_task.status = REJECTED, acted_by, acted_at, decision_comment.
    - ProjectRequest.status -> REJECTED immediately.
    - Creates activity log with action_type REJECTED.
    - Other pending approval tasks may remain PENDING but are not actionable.
    - Returns locked ProjectRequest.
    """
    from .permissions import can_reject_project_request_task

    # Validate comment is provided and non-empty
    if not comment or not str(comment).strip():
        raise ValidationError("Rejection comment is required.")

    # Lock the ProjectRequest row
    locked_request = ProjectRequest.objects.select_for_update().get(
        pk=project_request.pk
    )

    # Lock the ApprovalTask row
    locked_task = ProjectRequestApprovalTask.objects.select_for_update().get(
        pk=approval_task.pk
    )

    # Verify the task belongs to this project request
    if locked_task.project_request_id != locked_request.pk:
        raise ValidationError(
            "The approval task does not belong to this project request."
        )

    # ProjectRequest must be REVIEWING
    if locked_request.status != ProjectRequestStatus.REVIEWING:
        raise ValidationError(
            f"Cannot reject request with status '{locked_request.status}'. "
            "Request must be under review."
        )

    # Task must be PENDING
    if locked_task.status != ProjectApprovalTaskStatus.PENDING:
        raise ValidationError(
            f"Cannot reject task with status '{locked_task.status}'. "
            "Task must be pending."
        )

    # Actor must have permission
    if not can_reject_project_request_task(actor, locked_task):
        raise PermissionDenied(
            "You do not have permission to reject this task."
        )

    # Set task fields
    locked_task.status = ProjectApprovalTaskStatus.REJECTED
    locked_task.acted_by = actor
    locked_task.acted_at = timezone.now()
    locked_task.decision_comment = str(comment).strip()
    locked_task.save(update_fields=[
        "status", "acted_by", "acted_at", "decision_comment", "updated_at"
    ])

    # Transition project request to REJECTED immediately
    old_status = locked_request.status
    locked_request.status = ProjectRequestStatus.REJECTED
    locked_request.save(update_fields=["status", "last_activity_at"])

    create_activity_log(
        project_request=locked_request,
        action_type=ProjectRequestActionType.REJECTED,
        actor=actor,
        description=f"Request rejected: {locked_task.decision_comment}",
        from_status=old_status,
        to_status=ProjectRequestStatus.REJECTED,
    )

    return locked_request


# ---------------------------------------------------------------------------
# 11. Assignment/Claim Workflow Services (Phase 3B)
# ---------------------------------------------------------------------------

@transaction.atomic
def assign_project_request(project_request, assigned_to, assigned_by, role="", comment=""):
    """Assign a project request to a user.

    Rules:
    - Uses transaction.atomic().
    - Locks ProjectRequest row with select_for_update().
    - Uses DB-fresh locked ProjectRequest, not stale in-memory object.
    - assigned_by must pass can_assign_project_request(assigned_by, locked_request).
    - assigned_to must be authenticated and active.
    - assigned_to must have active UserDepartment membership in locked_request.project_department.
    - request status must be APPROVED or ASSIGNED.
    - If request status is APPROVED: transition ProjectRequest to ASSIGNED.
    - If request status is already ASSIGNED: keep ASSIGNED (reassignment).
    - Reassignment rule: deactivate all existing active assignments for this project_request,
      then create a new active ProjectRequestAssignment for assigned_to.
    - If assigning the same user who is already active assignee: raise ValidationError.
    - Set assignment.assigned_by = assigned_by.
    - Save role/comment only if matching model fields already exist.
    - Create activity log using ProjectRequestActionType.ASSIGNED.
    - Returns locked ProjectRequest.
    """
    from .permissions import can_assign_project_request

    # Step 1: Lock the ProjectRequest row
    locked_request = ProjectRequest.objects.select_for_update().get(
        pk=project_request.pk
    )

    # Step 2: Validate request status is APPROVED or ASSIGNED (use DB-fresh locked row)
    if locked_request.status not in (ProjectRequestStatus.APPROVED, ProjectRequestStatus.ASSIGNED):
        raise ValidationError(
            f"Cannot assign request with status '{locked_request.status}'. "
            "Request must be APPROVED or ASSIGNED."
        )

    # Step 3: Validate assigned_by has permission
    if not can_assign_project_request(assigned_by, locked_request):
        raise PermissionDenied(
            "You do not have permission to assign this request."
        )

    # Step 4: Validate assigned_to is authenticated and active
    if not assigned_to or not getattr(assigned_to, "is_authenticated", False):
        raise PermissionDenied("Assigned-to user must be authenticated.")
    if not assigned_to.is_active:
        raise PermissionDenied("Assigned-to user must be active.")

    # Step 5: Validate assigned_to has active membership in project_department
    proj_dept = locked_request.project_department
    if not proj_dept:
        raise ValidationError("Project department is not set on this request.")

    membership = get_user_department_membership(assigned_to, proj_dept)
    if membership is None:
        raise ValidationError(
            "Assigned-to user must be a member of the project department."
        )

    # Step 6: Check if this user is already actively assigned
    existing_active = ProjectRequestAssignment.objects.filter(
        project_request=locked_request,
        assigned_to=assigned_to,
        is_active=True,
    ).exists()
    if existing_active:
        raise ValidationError("User is already actively assigned.")

    # Step 7: Deactivate all existing active assignments (for reassignment)
    ProjectRequestAssignment.objects.filter(
        project_request=locked_request,
        is_active=True,
    ).update(is_active=False)

    # Step 8: Create new assignment
    assignment = ProjectRequestAssignment.objects.create(
        project_request=locked_request,
        assigned_to=assigned_to,
        assigned_by=assigned_by,
        is_active=True,
        role=role if role else "",
    )

    # Step 9: Transition status if APPROVED -> ASSIGNED
    old_status = locked_request.status
    status_changed = False
    if locked_request.status == ProjectRequestStatus.APPROVED:
        locked_request.status = ProjectRequestStatus.ASSIGNED
        locked_request.assigned_at = timezone.now()
        locked_request.save(update_fields=["status", "assigned_at", "last_activity_at"])
        status_changed = True
    else:
        # Already ASSIGNED (reassignment), just update last_activity_at
        locked_request.save(update_fields=["last_activity_at"])

    # Step 10: Create activity log
    if status_changed:
        create_activity_log(
            project_request=locked_request,
            action_type=ProjectRequestActionType.ASSIGNED,
            actor=assigned_by,
            description=f"Request assigned to {assigned_to}",
            comment=comment if comment else "",
            from_status=old_status,
            to_status=ProjectRequestStatus.ASSIGNED,
        )
    else:
        create_activity_log(
            project_request=locked_request,
            action_type=ProjectRequestActionType.ASSIGNED,
            actor=assigned_by,
            description=f"Request reassigned to {assigned_to}",
            comment=comment if comment else "",
            from_status=ProjectRequestStatus.ASSIGNED,
            to_status=ProjectRequestStatus.ASSIGNED,
        )

    return locked_request


@transaction.atomic
def claim_project_request(project_request, actor):
    """Claim an approved project request for oneself.

    Rules:
    - Uses transaction.atomic().
    - Locks ProjectRequest row with select_for_update().
    - Uses DB-fresh locked ProjectRequest.
    - actor must be authenticated and active.
    - actor must pass can_claim_project_request(actor, locked_request).
    - Service-level claim only allows APPROVED -> ASSIGNED.
    - Do not allow claim on ASSIGNED status.
    - There must be no active assignments at lock time.
    - ProjectDepartmentProfile.allow_staff_claim must be True.
    - actor must have active UserDepartment membership in project_department.
    - Creates ProjectRequestAssignment: assigned_to=actor, assigned_by=actor, is_active=True.
    - Transitions ProjectRequest APPROVED -> ASSIGNED.
    - Creates activity log using ProjectRequestActionType.CLAIMED.
    - Returns locked ProjectRequest.
    """
    from .permissions import can_claim_project_request

    # Step 1: Lock the ProjectRequest row
    locked_request = ProjectRequest.objects.select_for_update().get(
        pk=project_request.pk
    )

    # Step 2: Validate actor is authenticated and active
    if not actor or not getattr(actor, "is_authenticated", False):
        raise PermissionDenied("Actor must be an authenticated user.")
    if not actor.is_active:
        raise PermissionDenied("Actor must be an active user.")

    # Step 3: Service-level claim only allows APPROVED -> ASSIGNED
    # (can_claim_project_request only allows APPROVED status, not ASSIGNED.
    # Service-level claim is only for initial claim from APPROVED.)
    if locked_request.status != ProjectRequestStatus.APPROVED:
        raise ValidationError(
            f"Cannot claim request with status '{locked_request.status}'. "
            "Only APPROVED requests can be claimed."
        )

    # Step 4: Validate actor has permission to claim
    if not can_claim_project_request(actor, locked_request):
        raise PermissionDenied(
            "You do not have permission to claim this request."
        )

    # Step 5: Verify no active assignments at lock time
    if ProjectRequestAssignment.objects.filter(
        project_request=locked_request,
        is_active=True,
    ).exists():
        raise ValidationError(
            "This request already has an active assignment and cannot be claimed."
        )

    # Step 6: Verify actor has active membership in project_department
    proj_dept = locked_request.project_department
    if not proj_dept:
        raise ValidationError("Project department is not set on this request.")

    membership = get_user_department_membership(actor, proj_dept)
    if membership is None:
        raise ValidationError(
            "Actor must be a member of the project department."
        )

    # Step 7: Create assignment (actor claims for themselves)
    assignment = ProjectRequestAssignment.objects.create(
        project_request=locked_request,
        assigned_to=actor,
        assigned_by=actor,
        is_active=True,
    )

    # Step 8: Transition APPROVED -> ASSIGNED
    old_status = locked_request.status
    locked_request.status = ProjectRequestStatus.ASSIGNED
    locked_request.assigned_at = timezone.now()
    locked_request.save(update_fields=["status", "assigned_at", "last_activity_at"])

    # Step 9: Create activity log
    create_activity_log(
        project_request=locked_request,
        action_type=ProjectRequestActionType.CLAIMED,
        actor=actor,
        description=f"Request claimed by {actor}",
        from_status=old_status,
        to_status=ProjectRequestStatus.ASSIGNED,
    )

    return locked_request


# ---------------------------------------------------------------------------
# Execution Workflow Services (Phase 3C)
# ---------------------------------------------------------------------------

@transaction.atomic
def start_project_request(project_request, actor, comment=""):
    """Start execution: ASSIGNED -> IN_PROGRESS.

    Rules:
    - project_request.status must be ASSIGNED (validated from DB).
    - Must have at least one active assignment at lock time.
    - actor must have permission (via can_start_project_request).
    - Sets started_at timestamp.
    - Creates activity log with action STARTED.

    Args:
        project_request: The ProjectRequest to start.
        actor: The user starting the request.
        comment: Optional comment.

    Returns:
        The updated ProjectRequest (status=IN_PROGRESS).

    Raises:
        PermissionDenied: If actor cannot start this request.
        ValidationError: If status is not ASSIGNED or no active assignment.
    """
    from .permissions import can_start_project_request

    # Re-fetch from DB first to validate against current state
    locked_request = ProjectRequest.objects.select_for_update().get(pk=project_request.pk)

    # Validate status first
    if locked_request.status != ProjectRequestStatus.ASSIGNED:
        raise ValidationError(
            f"Request must be ASSIGNED to start (current: {locked_request.status})."
        )

    # Validate at least one active assignment at lock time
    if not locked_request.assignments.filter(is_active=True).exists():
        raise ValidationError("Request has no active assignment.")

    if not can_start_project_request(actor, locked_request):
        raise PermissionDenied("You do not have permission to start this request.")

    old_status = locked_request.status
    locked_request.status = ProjectRequestStatus.IN_PROGRESS
    locked_request.started_at = timezone.now()
    locked_request.save(update_fields=["status", "started_at", "updated_at"])

    create_activity_log(
        project_request=locked_request,
        action_type=ProjectRequestActionType.STARTED,
        actor=actor,
        description="Request started",
        comment=comment.strip() if comment else "",
        from_status=old_status,
        to_status=ProjectRequestStatus.IN_PROGRESS,
    )

    return locked_request


@transaction.atomic
def hold_project_request(project_request, actor, comment):
    """Put on hold: IN_PROGRESS -> ON_HOLD.

    Rules:
    - project_request.status must be IN_PROGRESS (validated from DB).
    - Must have at least one active assignment at lock time.
    - actor must have permission (via can_hold_project_request).
    - comment is required (non-empty, non-whitespace).
    - Creates activity log with action PUT_ON_HOLD.

    Args:
        project_request: The ProjectRequest to hold.
        actor: The user putting the request on hold.
        comment: Required hold reason.

    Returns:
        The updated ProjectRequest (status=ON_HOLD).

    Raises:
        PermissionDenied: If actor cannot hold this request.
        ValidationError: If status is not IN_PROGRESS, no active assignment, or comment empty.
    """
    from .permissions import can_hold_project_request

    # Validate comment is required
    if not comment or not comment.strip():
        raise ValidationError("Hold comment is required.")

    # Re-fetch from DB first to validate against current state
    locked_request = ProjectRequest.objects.select_for_update().get(pk=project_request.pk)

    # Validate status first
    if locked_request.status != ProjectRequestStatus.IN_PROGRESS:
        raise ValidationError(
            f"Request must be IN_PROGRESS to hold (current: {locked_request.status})."
        )

    # Validate at least one active assignment at lock time
    if not locked_request.assignments.filter(is_active=True).exists():
        raise ValidationError("Request has no active assignment.")

    if not can_hold_project_request(actor, locked_request):
        raise PermissionDenied("You do not have permission to hold this request.")

    old_status = locked_request.status
    locked_request.status = ProjectRequestStatus.ON_HOLD
    locked_request.save(update_fields=["status", "updated_at"])

    create_activity_log(
        project_request=locked_request,
        action_type=ProjectRequestActionType.PUT_ON_HOLD,
        actor=actor,
        description="Request put on hold",
        comment=comment.strip(),
        from_status=old_status,
        to_status=ProjectRequestStatus.ON_HOLD,
    )

    return locked_request


@transaction.atomic
def resume_project_request(project_request, actor, comment=""):
    """Resume from hold: ON_HOLD -> IN_PROGRESS.

    Rules:
    - project_request.status must be ON_HOLD (validated from DB).
    - Must have at least one active assignment at lock time.
    - actor must have permission (via can_resume_project_request).
    - Creates activity log with action RESUMED.

    Args:
        project_request: The ProjectRequest to resume.
        actor: The user resuming the request.
        comment: Optional comment.

    Returns:
        The updated ProjectRequest (status=IN_PROGRESS).

    Raises:
        PermissionDenied: If actor cannot resume this request.
        ValidationError: If status is not ON_HOLD or no active assignment.
    """
    from .permissions import can_resume_project_request

    # Re-fetch from DB first to validate against current state
    locked_request = ProjectRequest.objects.select_for_update().get(pk=project_request.pk)

    # Validate status first
    if locked_request.status != ProjectRequestStatus.ON_HOLD:
        raise ValidationError(
            f"Request must be ON_HOLD to resume (current: {locked_request.status})."
        )

    # Validate at least one active assignment at lock time
    if not locked_request.assignments.filter(is_active=True).exists():
        raise ValidationError("Request has no active assignment.")

    if not can_resume_project_request(actor, locked_request):
        raise PermissionDenied("You do not have permission to resume this request.")

    old_status = locked_request.status
    locked_request.status = ProjectRequestStatus.IN_PROGRESS
    locked_request.save(update_fields=["status", "updated_at"])

    create_activity_log(
        project_request=locked_request,
        action_type=ProjectRequestActionType.RESUMED,
        actor=actor,
        description="Request resumed",
        comment=comment.strip() if comment else "",
        from_status=old_status,
        to_status=ProjectRequestStatus.IN_PROGRESS,
    )

    return locked_request


@transaction.atomic
def complete_project_request(project_request, actor, comment=""):
    """Complete execution: IN_PROGRESS -> COMPLETED.

    Rules:
    - project_request.status must be IN_PROGRESS (validated from DB).
    - Must have at least one active assignment at lock time.
    - actor must have permission (via can_complete_project_request).
    - Sets completed_at timestamp.
    - Creates activity log with action COMPLETED.

    Args:
        project_request: The ProjectRequest to complete.
        actor: The user completing the request.
        comment: Optional comment.

    Returns:
        The updated ProjectRequest (status=COMPLETED).

    Raises:
        PermissionDenied: If actor cannot complete this request.
        ValidationError: If status is not IN_PROGRESS or no active assignment.
    """
    from .permissions import can_complete_project_request

    # Re-fetch from DB first to validate against current state
    locked_request = ProjectRequest.objects.select_for_update().get(pk=project_request.pk)

    # Validate status first
    if locked_request.status != ProjectRequestStatus.IN_PROGRESS:
        raise ValidationError(
            f"Request must be IN_PROGRESS to complete (current: {locked_request.status})."
        )

    # Validate at least one active assignment at lock time
    if not locked_request.assignments.filter(is_active=True).exists():
        raise ValidationError("Request has no active assignment.")

    if not can_complete_project_request(actor, locked_request):
        raise PermissionDenied("You do not have permission to complete this request.")

    old_status = locked_request.status
    locked_request.status = ProjectRequestStatus.COMPLETED
    locked_request.completed_at = timezone.now()
    locked_request.save(update_fields=["status", "completed_at", "updated_at"])

    create_activity_log(
        project_request=locked_request,
        action_type=ProjectRequestActionType.COMPLETED,
        actor=actor,
        description="Request completed",
        comment=comment.strip() if comment else "",
        from_status=old_status,
        to_status=ProjectRequestStatus.COMPLETED,
    )

    return locked_request
