"""Queryset selectors for the project_requests app.

All selectors use department-scoped helpers from accounts.services.
Uses reduce(or_, conditions) for correct OR logic in visibility.
Uses Exists subquery for safe claimable filtering (no ~Q on reverse FK).
"""

from functools import reduce
from operator import or_

from django.db.models import Q, Exists, OuterRef

from accounts.services import (
    get_user_department_ids,
    get_user_managed_department_ids,
)

from .models import (
    ProjectRequest,
    ProjectRequestApprovalTask,
    ProjectRequestAssignment,
    ProjectRequestStatus,
    ProjectApprovalTaskStatus,
)


# ---------------------------------------------------------------------------
# Terminal / non-terminal statuses
# ---------------------------------------------------------------------------

TERMINAL_STATUSES = [
    ProjectRequestStatus.COMPLETED,
    ProjectRequestStatus.CANCELLED,
    ProjectRequestStatus.REJECTED,
]


# ---------------------------------------------------------------------------
# Selectors
# ---------------------------------------------------------------------------

def get_visible_project_requests(user):
    """Return project requests visible to the given user.

    Visibility is a UNION (OR) of:
    1. Own requests (requester == user)
    2. Requests from departments user manages (request_department in managed)
    3. Requests to project departments user manages (project_department in managed)
    4. Requests assigned to user
    5. Claimable requests (approved/unassigned, allow_staff_claim=True, user is member of proj_dept)

    Uses reduce(or_, conditions) for correct OR logic.
    Uses Exists subquery for claimable "no active assignment" check to avoid
    unsafe ~Q(assignments__is_active=True) across reverse FK joins.
    """
    if not user or not user.is_authenticated or not user.is_active:
        return ProjectRequest.objects.none()

    # Superuser sees everything
    if user.is_superuser:
        return ProjectRequest.objects.all()

    user_dept_ids = list(get_user_department_ids(user))
    managed_dept_ids = list(get_user_managed_department_ids(user))

    conditions = []

    # 1. Own requests
    conditions.append(Q(requester=user))

    # 2. Requests from managed request departments
    if managed_dept_ids:
        conditions.append(Q(request_department__id__in=managed_dept_ids))

    # 3. Requests to managed project departments
    if managed_dept_ids:
        conditions.append(Q(project_department__id__in=managed_dept_ids))

    # 4. Assigned to user
    conditions.append(Q(assignments__assigned_to=user, assignments__is_active=True))

    # 5. Claimable requests (approved/unassigned, allow_staff_claim, user is member of proj_dept)
    # Uses Exists subquery to safely check "no active assignment" without
    # relying on ~Q(assignments__is_active=True) which is unsafe when a
    # request has both active and inactive assignment rows.
    has_active_assignment = None
    if user_dept_ids:
        has_active_assignment = ProjectRequestAssignment.objects.filter(
            project_request=OuterRef("pk"),
            is_active=True,
        )
        claimable = Q(
            project_department__id__in=user_dept_ids,
            status__in=[ProjectRequestStatus.APPROVED, ProjectRequestStatus.ASSIGNED],
            project_department__project_dept_profile__is_active=True,
            project_department__project_dept_profile__allow_staff_claim=True,
        ) & ~Q(active_assignment_exists=True)
        conditions.append(claimable)

    if not conditions:
        return ProjectRequest.objects.none()

    combined = reduce(or_, conditions)

    # Build queryset with Exists annotation only when claimable condition is used
    if has_active_assignment is not None:
        qs = ProjectRequest.objects.annotate(
            active_assignment_exists=Exists(has_active_assignment),
        ).filter(combined).distinct()
    else:
        qs = ProjectRequest.objects.filter(combined).distinct()

    return qs


def get_my_project_requests(user):
    """Return project requests where user is the requester."""
    if not user or not user.is_authenticated:
        return ProjectRequest.objects.none()
    return ProjectRequest.objects.filter(requester=user)


def get_assigned_to_me(user):
    """Return project requests actively assigned to the user."""
    if not user or not user.is_authenticated:
        return ProjectRequest.objects.none()
    return ProjectRequest.objects.filter(
        assignments__assigned_to=user,
        assignments__is_active=True,
    ).distinct()


def get_my_pending_approval_tasks(user):
    """Return pending approval tasks the user is eligible to approve.

    Uses department-scoped can_approve checks via UserDepartment records.
    A user is eligible for:
    - MANAGER/REQUEST_DEPT_MANAGER tasks: can_approve=True + access_level in MANAGER/DIRECTOR/VP
    - PROJECT_DEPT_VP tasks: can_approve=True + access_level == VP
    - Superusers: all pending tasks for REVIEWING requests

    Uses Q-based filtering instead of Python loops to avoid full table scans.
    """
    from accounts.models import AccessLevel, Department
    from .models import ProjectApprovalRole

    if not user or not user.is_authenticated or not user.is_active:
        return ProjectRequestApprovalTask.objects.none()

    # Superuser sees all pending tasks for REVIEWING requests
    if user.is_superuser:
        return ProjectRequestApprovalTask.objects.filter(
            status=ProjectApprovalTaskStatus.PENDING,
            project_request__status=ProjectRequestStatus.REVIEWING,
        ).distinct()

    # Departments where user can approve as manager or above
    manager_dept_ids = Department.objects.filter(
        user_departments__user=user,
        user_departments__is_active=True,
        user_departments__can_approve=True,
        user_departments__access_level__in=[
            AccessLevel.MANAGER, AccessLevel.DIRECTOR, AccessLevel.VP,
        ],
    ).values_list("id", flat=True)

    # Departments where user can approve as VP
    vp_dept_ids = Department.objects.filter(
        user_departments__user=user,
        user_departments__is_active=True,
        user_departments__can_approve=True,
        user_departments__access_level=AccessLevel.VP,
    ).values_list("id", flat=True)

    # If user has no eligible departments at all, return empty immediately
    if not manager_dept_ids.exists() and not vp_dept_ids.exists():
        return ProjectRequestApprovalTask.objects.none()

    # Build conditions only for departments the user actually has access to
    conditions = Q()

    if manager_dept_ids.exists():
        conditions |= Q(
            status=ProjectApprovalTaskStatus.PENDING,
            project_request__status=ProjectRequestStatus.REVIEWING,
            department__in=manager_dept_ids,
            role__in=[
                ProjectApprovalRole.PROJECT_DEPT_MANAGER,
                ProjectApprovalRole.REQUEST_DEPT_MANAGER,
            ],
        )

    if vp_dept_ids.exists():
        conditions |= Q(
            status=ProjectApprovalTaskStatus.PENDING,
            project_request__status=ProjectRequestStatus.REVIEWING,
            department__in=vp_dept_ids,
            role=ProjectApprovalRole.PROJECT_DEPT_VP,
        )

    return ProjectRequestApprovalTask.objects.filter(conditions).distinct()


def get_overdue_project_requests(user):
    """Return non-terminal project requests assigned to user that are past needed_by_date.

    Excludes terminal statuses (COMPLETED, CANCELLED, REJECTED).
    """
    from django.utils import timezone

    if not user or not user.is_authenticated:
        return ProjectRequest.objects.none()

    now = timezone.now().date()
    return ProjectRequest.objects.filter(
        assignments__assigned_to=user,
        assignments__is_active=True,
        needed_by_date__lt=now,
    ).exclude(
        status__in=TERMINAL_STATUSES,
    ).distinct()


# ---------------------------------------------------------------------------
# Phase 4B: Dashboard Selectors
# ---------------------------------------------------------------------------

def get_dashboard_my_drafts(user):
    """Return user's own DRAFT requests, ordered by -created_at.

    Base: get_my_project_requests(user)
    """
    if not user or not user.is_authenticated:
        return ProjectRequest.objects.none()

    return get_my_project_requests(user).filter(
        status=ProjectRequestStatus.DRAFT
    ).order_by("-created_at")


def get_dashboard_my_open_requests(user):
    """Return user's non-terminal, non-draft requests.

    Includes: SUBMITTED, REVIEWING, APPROVED, ASSIGNED, IN_PROGRESS, ON_HOLD
    Excludes: DRAFT, COMPLETED, REJECTED, CANCELLED
    """
    if not user or not user.is_authenticated:
        return ProjectRequest.objects.none()

    open_statuses = [
        ProjectRequestStatus.SUBMITTED,
        ProjectRequestStatus.REVIEWING,
        ProjectRequestStatus.APPROVED,
        ProjectRequestStatus.ASSIGNED,
        ProjectRequestStatus.IN_PROGRESS,
        ProjectRequestStatus.ON_HOLD,
    ]
    return get_my_project_requests(user).filter(
        status__in=open_statuses
    ).order_by("-last_activity_at")


def get_dashboard_pending_approval_tasks(user):
    """Return approval tasks user can act on, ordered by project request submitted_at.

    Base: get_my_pending_approval_tasks(user)
    """
    if not user or not user.is_authenticated:
        return ProjectRequestApprovalTask.objects.none()

    qs = get_my_pending_approval_tasks(user)
    return qs.select_related("project_request", "department").order_by(
        "project_request__submitted_at", "project_request__id"
    )


def get_dashboard_assigned_to_me(user):
    """Return requests actively assigned to user, ordered by needed_by_date.

    Base: get_assigned_to_me(user)
    """
    if not user or not user.is_authenticated:
        return ProjectRequest.objects.none()

    return get_assigned_to_me(user).order_by(
        "-needed_by_date", "-last_activity_at"
    )


def get_dashboard_claimable_requests(user):
    """Return APPROVED requests with no active assignment that user can claim.

    - status=APPROVED
    - no active assignment (Exists subquery)
    - active project_department with active ProjectDepartmentProfile
    - allow_staff_claim=True on profile
    - user's active department memberships include the project_department
    - superuser sees ALL claimable requests (no user_department_ids restriction)

    Base: get_visible_project_requests(user).filter(status=APPROVED)
    """
    if not user or not user.is_authenticated:
        return ProjectRequest.objects.none()

    qs = get_visible_project_requests(user).filter(status=ProjectRequestStatus.APPROVED)

    # Filter to active project departments with allow_staff_claim=True
    qs = qs.filter(
        project_department__is_active=True,
        project_department__project_dept_profile__is_active=True,
        project_department__project_dept_profile__allow_staff_claim=True,
    )

    # Superuser: see all claimable (no department membership restriction)
    if user.is_superuser:
        # Annotate active_assignment_exists and filter
        has_active_assignment = ProjectRequestAssignment.objects.filter(
            project_request=OuterRef("pk"),
            is_active=True,
        )
        qs = qs.annotate(
            active_assignment_exists=Exists(has_active_assignment),
        ).filter(
            active_assignment_exists=False,
        )
        return qs.distinct()

    # Normal users: restrict to their department memberships
    user_dept_ids = list(get_user_department_ids(user))
    if not user_dept_ids:
        return ProjectRequest.objects.none()

    qs = qs.filter(project_department__id__in=user_dept_ids)

    # Exclude requests with active assignment using Exists subquery
    has_active_assignment = ProjectRequestAssignment.objects.filter(
        project_request=OuterRef("pk"),
        is_active=True,
    )
    qs = qs.annotate(
        active_assignment_exists=Exists(has_active_assignment),
    ).filter(
        active_assignment_exists=False,
    )

    return qs.order_by("-needed_by_date").distinct()


def get_dashboard_project_department_queue(user):
    """Return non-terminal requests in user's managed project departments.

    Visible to: MANAGER/DIRECTOR/VP in project department only.
    Normal staff returns empty queryset.

    Statuses: SUBMITTED, REVIEWING, APPROVED, ASSIGNED, IN_PROGRESS, ON_HOLD
    """
    if not user or not user.is_authenticated:
        return ProjectRequest.objects.none()

    # Superuser: use visible requests without department restriction
    if user.is_superuser:
        queue_statuses = [
            ProjectRequestStatus.SUBMITTED,
            ProjectRequestStatus.REVIEWING,
            ProjectRequestStatus.APPROVED,
            ProjectRequestStatus.ASSIGNED,
            ProjectRequestStatus.IN_PROGRESS,
            ProjectRequestStatus.ON_HOLD,
        ]
        return get_visible_project_requests(user).filter(
            status__in=queue_statuses,
        ).order_by("-priority", "-needed_by_date")

    managed_dept_ids = list(get_user_managed_department_ids(user))
    if not managed_dept_ids:
        return ProjectRequest.objects.none()

    queue_statuses = [
        ProjectRequestStatus.SUBMITTED,
        ProjectRequestStatus.REVIEWING,
        ProjectRequestStatus.APPROVED,
        ProjectRequestStatus.ASSIGNED,
        ProjectRequestStatus.IN_PROGRESS,
        ProjectRequestStatus.ON_HOLD,
    ]
    return get_visible_project_requests(user).filter(
        project_department__id__in=managed_dept_ids,
        status__in=queue_statuses,
    ).order_by("-priority", "-needed_by_date")


def get_dashboard_in_progress_or_on_hold(user):
    """Return IN_PROGRESS or ON_HOLD requests in user's managed project departments.

    Visible to: MANAGER/DIRECTOR/VP in project department only.
    """
    if not user or not user.is_authenticated:
        return ProjectRequest.objects.none()

    # Superuser: use visible requests
    if user.is_superuser:
        return get_visible_project_requests(user).filter(
            status__in=[ProjectRequestStatus.IN_PROGRESS, ProjectRequestStatus.ON_HOLD],
        ).order_by("status", "-needed_by_date")

    managed_dept_ids = list(get_user_managed_department_ids(user))
    if not managed_dept_ids:
        return ProjectRequest.objects.none()

    return get_visible_project_requests(user).filter(
        project_department__id__in=managed_dept_ids,
        status__in=[ProjectRequestStatus.IN_PROGRESS, ProjectRequestStatus.ON_HOLD],
    ).order_by("status", "-needed_by_date")


def get_dashboard_recently_completed(user, days=30):
    """Return COMPLETED requests in managed departments within the time window.

    Visible to: MANAGER/DIRECTOR/VP in project department only.
    """
    from django.utils import timezone

    if not user or not user.is_authenticated:
        return ProjectRequest.objects.none()

    cutoff = timezone.now() - timezone.timedelta(days=days)

    # Superuser: use visible requests
    if user.is_superuser:
        return get_visible_project_requests(user).filter(
            status=ProjectRequestStatus.COMPLETED,
            completed_at__gte=cutoff,
        ).order_by("-completed_at")

    managed_dept_ids = list(get_user_managed_department_ids(user))
    if not managed_dept_ids:
        return ProjectRequest.objects.none()

    return get_visible_project_requests(user).filter(
        project_department__id__in=managed_dept_ids,
        status=ProjectRequestStatus.COMPLETED,
        completed_at__gte=cutoff,
    ).order_by("-completed_at")


def get_dashboard_status_counts(user):
    """Return aggregate counts by status for user's visible requests.

    Base: get_visible_project_requests(user)
    Returns list of dicts: [{'status': 'SUBMITTED', 'count': 5}, ...]
    """
    from django.db.models import Count

    if not user or not user.is_authenticated:
        return []

    qs = get_visible_project_requests(user)
    return list(
        qs.values("status")
        .annotate(count=Count("id"))
        .order_by("status")
    )


def get_dashboard_overdue_count(user):
    """Return count of overdue requests (non-terminal, past needed_by_date, assigned to user).

    Base: get_overdue_project_requests(user)
    Returns integer count.
    """
    if not user or not user.is_authenticated:
        return 0

    return get_overdue_project_requests(user).count()
