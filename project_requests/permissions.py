"""Permission helpers for the project_requests app.

All permission checks use department-scoped helpers from accounts.services.
"""

from accounts.services import (
    can_approve_as_manager_or_above,
    can_approve_as_vp,
    get_user_department_ids,
    get_user_managed_department_ids,
    is_manager_or_above,
)

from .models import (
    ProjectApprovalRole,
    ProjectApprovalTaskStatus,
    ProjectRequest,
    ProjectRequestStatus,
)


# ---------------------------------------------------------------------------
# Terminal statuses
# ---------------------------------------------------------------------------

TERMINAL_STATUSES = [
    ProjectRequestStatus.COMPLETED,
    ProjectRequestStatus.CANCELLED,
    ProjectRequestStatus.REJECTED,
]


def _is_authenticated_active(user):
    """Check user is authenticated and active."""
    return user is not None and user.is_authenticated and user.is_active


# ---------------------------------------------------------------------------
# Core Permission Checks
# ---------------------------------------------------------------------------

def can_view_project_request(user, project_request):
    """Determine if a user can view a project request.

    Rules:
    - superuser can view all
    - requester can view own requests
    - request department manager/VP can view requests from their managed departments
    - project department manager/VP can view requests to their managed project departments
    - assigned users can view assigned requests
    - project department staff can view approved/unassigned claimable requests
      only when ProjectDepartmentProfile.allow_staff_claim=True
    - unrelated staff cannot view
    """
    if not _is_authenticated_active(user):
        return False

    # Superuser sees everything
    if user.is_superuser:
        return True

    # Requester can view own
    if project_request.requester == user:
        return True

    # Request department manager/VP can view requests from their managed departments
    managed_dept_ids = set(get_user_managed_department_ids(user))
    if project_request.request_department_id in managed_dept_ids:
        return True

    # Project department manager/VP can view requests to their managed project departments
    if project_request.project_department_id in managed_dept_ids:
        return True

    # Assigned users can view assigned requests
    if project_request.assignments.filter(assigned_to=user, is_active=True).exists():
        return True

    # Project department staff can view approved/unassigned claimable requests
    if _is_claimable_by_user(user, project_request):
        return True

    return False


def can_submit_project_request(user):
    """Determine if a user can submit a project request.

    Requires authenticated active user.
    """
    return _is_authenticated_active(user)


def can_assign_project_request(user, project_request):
    """Determine if a user can assign a project request.

    Rules:
    - user must be authenticated and active.
    - superuser may assign when request status allows assignment.
    - request status must be APPROVED or ASSIGNED.
    - project_request.project_department must exist and be active.
    - ProjectDepartmentProfile must exist and be active.
    - normal user must be manager/director/VP in project_department.
    - request department manager who is not also project department manager
      must not assign (cross-department assignment requires project dept authority).
    """
    if not _is_authenticated_active(user):
        return False

    if project_request.status not in (ProjectRequestStatus.APPROVED, ProjectRequestStatus.ASSIGNED):
        return False

    proj_dept = project_request.project_department
    if not proj_dept:
        return False

    # Check project department is active
    if not proj_dept.is_active:
        return False

    # Check ProjectDepartmentProfile exists and is active
    profile = getattr(proj_dept, "project_dept_profile", None)
    if not profile or not profile.is_active:
        return False

    # Superuser can assign regardless of department membership
    if user.is_superuser:
        return True

    # User must be manager or above in the project department
    if not is_manager_or_above(user, proj_dept):
        return False

    # If user is manager or above in request department but NOT in project department,
    # they cannot assign (cross-department assignment requires project dept authority)
    req_dept = project_request.request_department
    if req_dept and req_dept != proj_dept:
        if is_manager_or_above(user, req_dept) and not is_manager_or_above(user, proj_dept):
            return False

    return True


def can_claim_project_request(user, project_request):
    """Determine if a user can claim a project request.

    Claim is only allowed when ProjectRequest.status == APPROVED.
    ASSIGNED requests must not be claimable, even if there is no active assignment.
    Reassignment for ASSIGNED requests must go through assign_project_request().

    Requires:
    - user is authenticated and active
    - project department membership
    - ProjectDepartmentProfile.is_active=True
    - allow_staff_claim=True on ProjectDepartmentProfile
    - status == APPROVED
    - no active assignment for this user
    """
    if not _is_authenticated_active(user):
        return False

    # Claim is only allowed for APPROVED status
    if project_request.status != ProjectRequestStatus.APPROVED:
        return False

    return _is_claimable_by_user(user, project_request)


def can_attach_file(user, project_request):
    """Determine if a user can attach a file to a project request.

    Allows: requester, project dept manager/VP, request dept manager/VP, and assignee
    while request is non-terminal.
    """
    if not _is_authenticated_active(user):
        return False

    if project_request.status in TERMINAL_STATUSES:
        return False

    # Requester
    if project_request.requester == user:
        return True

    # Assignee
    if project_request.assignments.filter(assigned_to=user, is_active=True).exists():
        return True

    # Project department manager/VP
    proj_dept = project_request.project_department
    if proj_dept and is_manager_or_above(user, proj_dept):
        return True

    # Request department manager/VP
    req_dept = project_request.request_department
    if req_dept and is_manager_or_above(user, req_dept):
        return True

    return False


def can_approve_project_request_task(user, approval_task):
    """Determine if a user can approve a specific approval task.

    Rules:
    - user must be authenticated and active.
    - superuser can approve/reject pending tasks only when parent ProjectRequest is REVIEWING.
    - approval_task.status must be PENDING.
    - approval_task.project_request.status must be REVIEWING.
    - task role PROJECT_DEPT_MANAGER:
      user must have can_approve=True and manager/director/VP level in approval_task.department.
    - task role REQUEST_DEPT_MANAGER:
      user must have can_approve=True and manager/director/VP level in approval_task.department.
    - task role PROJECT_DEPT_VP:
      user must have can_approve=True and VP level in approval_task.department.
    """
    if not _is_authenticated_active(user):
        return False

    # Task must be PENDING
    if approval_task.status != ProjectApprovalTaskStatus.PENDING:
        return False

    # Parent project request must be REVIEWING
    project_request = approval_task.project_request
    if project_request.status != ProjectRequestStatus.REVIEWING:
        return False

    # Superuser can approve any pending task when parent is REVIEWING
    if user.is_superuser:
        return True

    # Check based on role
    role = approval_task.role
    department = approval_task.department

    if role == ProjectApprovalRole.PROJECT_DEPT_VP:
        return can_approve_as_vp(user, department)
    elif role in (ProjectApprovalRole.PROJECT_DEPT_MANAGER, ProjectApprovalRole.REQUEST_DEPT_MANAGER):
        return can_approve_as_manager_or_above(user, department)

    return False


def can_reject_project_request_task(user, approval_task):
    """Determine if a user can reject a specific approval task.

    Uses the same eligibility rules as can_approve_project_request_task.
    """
    return can_approve_project_request_task(user, approval_task)


# ---------------------------------------------------------------------------
# Execution Workflow Permissions (Phase 3C)
# ---------------------------------------------------------------------------

def _has_active_assignment(project_request):
    """Check if project_request has at least one active assignment."""
    return project_request.assignments.filter(is_active=True).exists()


def _is_active_assignee(user, project_request):
    """Check if user is an active assignee on this request."""
    return project_request.assignments.filter(
        assigned_to=user, is_active=True
    ).exists()


def _is_project_dept_manager_or_above(user, project_request):
    """Check if user is manager/director/VP in the project department."""
    proj_dept = project_request.project_department
    if not proj_dept:
        return False
    return is_manager_or_above(user, proj_dept)


def _can_execute_project_request(user, project_request):
    """Core execution permission: active assignee OR project dept manager/VP OR superuser."""
    if not _is_authenticated_active(user):
        return False

    # Superuser can always execute
    if user.is_superuser:
        return True

    # Active assignee can execute
    if _is_active_assignee(user, project_request):
        return True

    # Project department manager/director/VP can execute
    if _is_project_dept_manager_or_above(user, project_request):
        return True

    return False


def can_start_project_request(user, project_request):
    """Determine if a user can start (ASSIGNED -> IN_PROGRESS) a project request.

    Rules:
    - user must be authenticated and active.
    - project_request.status must be ASSIGNED.
    - request must have at least one active assignment.
    - actor may be active assignee OR project dept manager/director/VP OR superuser.
    - project_request.project_department must exist and be active.
    - ProjectDepartmentProfile must exist and be active.
    """
    if not _is_authenticated_active(user):
        return False

    if project_request.status != ProjectRequestStatus.ASSIGNED:
        return False

    # Must have at least one active assignment
    if not _has_active_assignment(project_request):
        return False

    # Check execution permission
    if not _can_execute_project_request(user, project_request):
        return False

    proj_dept = project_request.project_department
    if not proj_dept:
        return False

    # Check project department is active
    if not proj_dept.is_active:
        return False

    # Check ProjectDepartmentProfile exists and is active
    profile = getattr(proj_dept, "project_dept_profile", None)
    if not profile or not profile.is_active:
        return False

    return True


def can_hold_project_request(user, project_request):
    """Determine if a user can hold (IN_PROGRESS -> ON_HOLD) a project request.

    Rules:
    - user must be authenticated and active.
    - project_request.status must be IN_PROGRESS.
    - request must have at least one active assignment.
    - actor may be active assignee OR project dept manager/director/VP OR superuser.
    - Do NOT block solely because ProjectDepartmentProfile was later deactivated.
    """
    if not _is_authenticated_active(user):
        return False

    if project_request.status != ProjectRequestStatus.IN_PROGRESS:
        return False

    # Must have at least one active assignment
    if not _has_active_assignment(project_request):
        return False

    # Check execution permission
    if not _can_execute_project_request(user, project_request):
        return False

    return True


def can_resume_project_request(user, project_request):
    """Determine if a user can resume (ON_HOLD -> IN_PROGRESS) a project request.

    Rules:
    - user must be authenticated and active.
    - project_request.status must be ON_HOLD.
    - request must have at least one active assignment.
    - actor may be active assignee OR project dept manager/director/VP OR superuser.
    - Do NOT block solely because ProjectDepartmentProfile was later deactivated.
    """
    if not _is_authenticated_active(user):
        return False

    if project_request.status != ProjectRequestStatus.ON_HOLD:
        return False

    # Must have at least one active assignment
    if not _has_active_assignment(project_request):
        return False

    # Check execution permission
    if not _can_execute_project_request(user, project_request):
        return False

    return True


def can_complete_project_request(user, project_request):
    """Determine if a user can complete (IN_PROGRESS -> COMPLETED) a project request.

    Rules:
    - user must be authenticated and active.
    - project_request.status must be IN_PROGRESS.
    - request must have at least one active assignment.
    - actor may be active assignee OR project dept manager/director/VP OR superuser.
    - Do NOT allow ON_HOLD -> COMPLETED.
    - Do NOT block solely because ProjectDepartmentProfile was later deactivated.
    """
    if not _is_authenticated_active(user):
        return False

    if project_request.status != ProjectRequestStatus.IN_PROGRESS:
        return False

    # Must have at least one active assignment
    if not _has_active_assignment(project_request):
        return False

    # Check execution permission
    if not _can_execute_project_request(user, project_request):
        return False

    return True


def get_project_request_action_context(user, project_request):
    """Return a dict of all action permissions for a user on a project request.

    Useful for passing to templates or API responses.
    Includes Phase 3A approval/reject context and Phase 3C execution workflow context.
    """
    from .selectors import get_my_pending_approval_tasks

    # Get pending tasks user can act on for this project request
    pending_tasks = get_my_pending_approval_tasks(user).filter(
        project_request=project_request
    )

    return {
        "can_view": can_view_project_request(user, project_request),
        "can_submit": can_submit_project_request(user),
        "can_assign": can_assign_project_request(user, project_request),
        "can_claim": can_claim_project_request(user, project_request),
        "can_attach_file": can_attach_file(user, project_request),
        # Phase 3A: Approval/reject context
        "pending_approval_tasks_user_can_act_on": list(pending_tasks),
        "can_approve_any_task": pending_tasks.exists(),
        "can_reject_any_task": pending_tasks.exists(),
        # Phase 3C: Execution workflow context
        "can_start": can_start_project_request(user, project_request),
        "can_hold": can_hold_project_request(user, project_request),
        "can_resume": can_resume_project_request(user, project_request),
        "can_complete": can_complete_project_request(user, project_request),
    }


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _is_claimable_by_user(user, project_request):
    """Check if a request is claimable by the given user.

    Claimable requires:
    - status == APPROVED
    - project_department exists and is active
    - ProjectDepartmentProfile exists, is_active=True, and allow_staff_claim=True
    - user has active UserDepartment membership in project_department
    - no active assignment exists

    Note: ASSIGNED requests are NOT claimable. Reassignment must go through
    assign_project_request().
    """
    if not _is_authenticated_active(user):
        return False

    # Claim is only allowed for APPROVED status
    if project_request.status != ProjectRequestStatus.APPROVED:
        return False

    proj_dept = project_request.project_department
    if not proj_dept:
        return False

    # Check project department is active
    if not proj_dept.is_active:
        return False

    # Check user is member of project department
    user_dept_ids = set(get_user_department_ids(user))
    if proj_dept.id not in user_dept_ids:
        return False

    # Check ProjectDepartmentProfile exists, is_active, and allow_staff_claim
    profile = getattr(proj_dept, "project_dept_profile", None)
    if not profile or not profile.is_active or not profile.allow_staff_claim:
        return False

    # Check no active assignments at all (not just for this user)
    if project_request.assignments.filter(is_active=True).exists():
        return False

    return True
