"""Department-scoped role helper functions for accounts app.

All role checks are department-specific through UserDepartment.
Do NOT use a global user.access_level field.
"""
from .models import AccessLevel


# ---------------------------------------------------------------------------
# Membership / Access-Level Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Department Queryset Helpers  (Fix 4 — explicit return types)
# ---------------------------------------------------------------------------

def get_user_departments(user):
    """Return Department queryset of all active departments for a user."""
    return getattr(user, 'user_departments').filter(
        is_active=True
    ).values_list('department', flat=True)


def get_user_department_ids(user):
    """Return active department IDs for a user (alias for clarity)."""
    return get_user_departments(user)


def get_user_managed_departments(user):
    """Return Department queryset where user is MANAGER or above."""
    return getattr(user, 'user_departments').filter(
        is_active=True,
        access_level__in=[AccessLevel.MANAGER, AccessLevel.DIRECTOR, AccessLevel.VP]
    ).values_list('department', flat=True)


def get_user_managed_department_ids(user):
    """Return active managed department IDs for a user (alias for clarity)."""
    return get_user_managed_departments(user)


# ---------------------------------------------------------------------------
# Approval Helpers  (Fix 5 — can_approve semantics)
# ---------------------------------------------------------------------------

def can_approve_in_department(user, department):
    """User has active membership AND can_approve=True in this department."""
    membership = get_user_department_membership(user, department)
    if membership is None:
        return False
    return membership.can_approve


def can_approve_as_manager_or_above(user, department):
    """User can approve AND is MANAGER/DIRECTOR/VP in this department."""
    membership = get_user_department_membership(user, department)
    if membership is None or not membership.can_approve:
        return False
    return membership.access_level in (AccessLevel.MANAGER, AccessLevel.DIRECTOR, AccessLevel.VP)


def can_approve_as_vp(user, department):
    """User can approve AND is VP in this department."""
    membership = get_user_department_membership(user, department)
    if membership is None or not membership.can_approve:
        return False
    return membership.access_level == AccessLevel.VP
