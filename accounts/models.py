from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class AccessLevel(models.TextChoices):
    """Access levels for users within departments.

    A user may have different access levels in different departments
    (legacy supports multi-department users).
    """
    STAFF = "STAFF", _("Staff")
    MANAGER = "MANAGER", _("Manager")
    DIRECTOR = "DIRECTOR", _("Director")
    VP = "VP", _("VP")


class User(AbstractUser):
    """Custom user model for MIS project.

    Extends AbstractUser to add employee_id and display_name while
    keeping username/email from AbstractUser.
    """
    employee_id = models.CharField(
        max_length=50, blank=True, default='',
        help_text='Legacy employee identifier'
    )
    display_name = models.CharField(
        max_length=150, blank=True, default='',
        help_text='Display name for UI (falls back to username)'
    )

    class Meta:
        verbose_name = 'user'
        verbose_name_plural = 'users'
        constraints = [
            # Fix 2: Prevent duplicate non-blank employee_id values.
            models.UniqueConstraint(
                fields=['employee_id'],
                condition=~models.Q(employee_id=''),
                name='unique_non_blank_employee_id',
            ),
        ]

    def __str__(self):
        return self.display_name or self.username


class Department(models.Model):
    """Organizational department."""
    dept_code = models.CharField(
        max_length=20, unique=True,
        help_text='Short code, e.g., MIS, IT, ACCT'
    )
    dept_name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['dept_code']
        verbose_name = 'department'
        verbose_name_plural = 'departments'

    def __str__(self):
        return f"{self.dept_code} - {self.dept_name}"


class UserDepartment(models.Model):
    """Links a user to a department with access level and properties.

    A user can belong to multiple departments with different access levels.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='user_departments'
    )
    department = models.ForeignKey(
        'accounts.Department', on_delete=models.PROTECT,
        related_name='user_departments'
    )
    access_level = models.CharField(
        max_length=20, choices=AccessLevel.choices,
        default=AccessLevel.STAFF
    )
    is_primary = models.BooleanField(
        default=False,
        help_text='Primary department for this user'
    )
    is_active = models.BooleanField(default=True)
    can_approve = models.BooleanField(
        default=False,
        help_text='User can act as approver in this department'
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'department'],
                name='unique_user_department'
            ),
            # Fix 1: Only one ACTIVE primary department per user.
            # An inactive primary membership does NOT block a new active primary.
            models.UniqueConstraint(
                fields=['user'],
                condition=models.Q(is_primary=True, is_active=True),
                name='one_active_primary_department_per_user',
            ),
        ]
        verbose_name = 'user department'
        verbose_name_plural = 'user departments'

    def __str__(self):
        return f"{self.user} → {self.department} ({self.access_level})"
