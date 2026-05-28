"""Foundation models for the project_requests app."""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


# ---------------------------------------------------------------------------
# TextChoices
# ---------------------------------------------------------------------------

class ProjectRequestStatus(models.TextChoices):
    DRAFT = "DRAFT", _("Draft")
    SUBMITTED = "SUBMITTED", _("Submitted")
    REVIEWING = "REVIEWING", _("Reviewing")
    APPROVED = "APPROVED", _("Approved")
    REJECTED = "REJECTED", _("Rejected")
    ASSIGNED = "ASSIGNED", _("Assigned")
    IN_PROGRESS = "IN_PROGRESS", _("In Progress")
    ON_HOLD = "ON_HOLD", _("On Hold")
    COMPLETED = "COMPLETED", _("Completed")
    CANCELLED = "CANCELLED", _("Cancelled")


class ProjectRequestPriority(models.IntegerChoices):
    P1 = 1, _("P1 - Critical")
    P2 = 2, _("P2 - High")
    P3 = 3, _("P3 - Medium")
    P4 = 4, _("P4 - Low")
    P5 = 5, _("P5 - Minimal")


class ProjectApprovalTaskStatus(models.TextChoices):
    PENDING = "PENDING", _("Pending")
    APPROVED = "APPROVED", _("Approved")
    REJECTED = "REJECTED", _("Rejected")


class ProjectApprovalRole(models.TextChoices):
    REQUEST_DEPT_MANAGER = "REQUEST_DEPT_MANAGER", _("Request Department Manager")
    PROJECT_DEPT_MANAGER = "PROJECT_DEPT_MANAGER", _("Project Department Manager")
    PROJECT_DEPT_VP = "PROJECT_DEPT_VP", _("Project Department VP")


class ProjectRequestActionType(models.TextChoices):
    DRAFT_CREATED = "DRAFT_CREATED", _("Draft Created")
    SUBMITTED = "SUBMITTED", _("Submitted")
    APPROVAL_CREATED = "APPROVAL_CREATED", _("Approval Task Created")
    APPROVED = "APPROVED", _("Approved")
    REJECTED = "REJECTED", _("Rejected")
    ADDITIONAL_APPROVAL_REQUESTED = "ADDITIONAL_APPROVAL_REQUESTED", _("Additional Approval Requested")
    ASSIGNED = "ASSIGNED", _("Assigned")
    CLAIMED = "CLAIMED", _("Claimed")
    STARTED = "STARTED", _("Started")
    PUT_ON_HOLD = "PUT_ON_HOLD", _("Put on Hold")
    RESUMED = "RESUMED", _("Resumed")
    COMPLETED = "COMPLETED", _("Completed")
    CANCELLED = "CANCELLED", _("Cancelled")
    COMMENTED = "COMMENTED", _("Commented")
    FILE_ATTACHED = "FILE_ATTACHED", _("File Attached")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class RequestNumberSequence(models.Model):
    """Year-based sequence for generating request numbers."""

    year = models.PositiveIntegerField(unique=True)
    sequence = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-year"]
        verbose_name = "request number sequence"
        verbose_name_plural = "request number sequences"

    def __str__(self):
        return f"{self.year} — sequence {self.sequence}"


class ProjectRequestType(models.Model):
    """Lookup for project request types."""

    code = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = "project request type"
        verbose_name_plural = "project request types"

    def __str__(self):
        return self.name


class ProjectRequestFileType(models.Model):
    """Lookup for allowed attachment file types."""

    code = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100, unique=True)
    allowed_extensions = models.CharField(
        max_length=200,
        help_text="Comma-separated extensions, e.g., pdf,docx,xlsx",
    )
    max_file_size_mb = models.PositiveIntegerField(default=25)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "name"]
        verbose_name = "project request file type"
        verbose_name_plural = "project request file types"

    def __str__(self):
        return self.name


class ProjectDepartmentProfile(models.Model):
    """Per-department configuration for project request workflow."""

    department = models.OneToOneField(
        "accounts.Department",
        on_delete=models.CASCADE,
        related_name="project_dept_profile",
    )
    is_active = models.BooleanField(default=True)
    can_receive_project_requests = models.BooleanField(default=True)
    allow_staff_claim = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "department__dept_code"]
        verbose_name = "project department profile"
        verbose_name_plural = "project department profiles"

    def __str__(self):
        return f"Profile for {self.department}"


class ProjectRequest(models.Model):
    """Core project request entity."""

    request_no = models.CharField(
        max_length=30, unique=True, null=True, blank=True,
        help_text="Auto-generated request number, e.g. PRJ-2026-000001",
    )
    project_name = models.CharField(max_length=255, blank=True, default="")
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="project_requests",
    )
    request_department = models.ForeignKey(
        "accounts.Department",
        on_delete=models.PROTECT,
        related_name="submitted_project_requests",
    )
    project_department = models.ForeignKey(
        "accounts.Department",
        on_delete=models.PROTECT,
        related_name="received_project_requests",
        null=True, blank=True,
    )
    request_type = models.ForeignKey(
        "project_requests.ProjectRequestType",
        on_delete=models.PROTECT,
        null=True, blank=True,
    )
    priority = models.PositiveSmallIntegerField(
        choices=ProjectRequestPriority.choices,
        null=True, blank=True,
    )
    status = models.CharField(
        max_length=20,
        choices=ProjectRequestStatus.choices,
        default=ProjectRequestStatus.DRAFT,
    )

    # Date tracking fields
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    assigned_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    needed_by_date = models.DateField(null=True, blank=True)
    last_activity_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Structured scope fields
    scope_summary = models.TextField(blank=True, default="")
    business_problem = models.TextField(blank=True, default="")
    business_scope = models.TextField(blank=True, default="")
    technical_scope = models.TextField(blank=True, default="")
    in_scope = models.TextField(blank=True, default="")
    out_of_scope = models.TextField(blank=True, default="")
    expected_deliverables = models.TextField(blank=True, default="")
    acceptance_criteria = models.TextField(blank=True, default="")
    affected_systems = models.TextField(blank=True, default="")
    customer = models.CharField(max_length=255, blank=True, default="")

    # Project execution fields
    etd = models.DateField(null=True, blank=True)
    hours_estimate = models.CharField(max_length=50, blank=True, default="")

    class Meta:
        ordering = ["-last_activity_at", "-created_at"]
        verbose_name = "project request"
        verbose_name_plural = "project requests"
        indexes = [
            models.Index(fields=["status"], name="pr_idx_status"),
            models.Index(fields=["requester"], name="pr_idx_requester"),
            models.Index(fields=["request_department"], name="pr_idx_req_dept"),
            models.Index(fields=["project_department"], name="pr_idx_proj_dept"),
            models.Index(fields=["request_no"], name="pr_idx_request_no"),
            models.Index(fields=["needed_by_date"], name="pr_idx_needed_by"),
        ]

    def __str__(self):
        if self.request_no:
            return f"{self.request_no} - {self.project_name or '(Draft)'}"
        return "Draft Project Request"


class ProjectRequestApprovalTask(models.Model):
    """Approval task generated for a project request."""

    project_request = models.ForeignKey(
        "project_requests.ProjectRequest",
        on_delete=models.CASCADE,
        related_name="approval_tasks",
    )
    department = models.ForeignKey(
        "accounts.Department",
        on_delete=models.PROTECT,
        related_name="project_approval_tasks",
    )
    role = models.CharField(
        max_length=30,
        choices=ProjectApprovalRole.choices,
    )
    status = models.CharField(
        max_length=10,
        choices=ProjectApprovalTaskStatus.choices,
        default=ProjectApprovalTaskStatus.PENDING,
    )
    acted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="acted_project_approval_tasks",
    )
    acted_at = models.DateTimeField(null=True, blank=True)
    decision_comment = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = "project approval task"
        verbose_name_plural = "project approval tasks"
        constraints = [
            models.UniqueConstraint(
                fields=["project_request", "department", "role"],
                name="unique_project_approval_task_per_role_dept",
            ),
        ]

    def __str__(self):
        return f"Approval: {self.project_request} — {self.get_role_display()} ({self.get_status_display()})"


class ProjectRequestAssignment(models.Model):
    """Assigns a user to work on a project request."""

    project_request = models.ForeignKey(
        "project_requests.ProjectRequest",
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assigned_project_requests",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="project_requests_assigned",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    role = models.CharField(max_length=50, blank=True, default="")

    class Meta:
        ordering = ["-assigned_at"]
        verbose_name = "project request assignment"
        verbose_name_plural = "project request assignments"
        constraints = [
            models.UniqueConstraint(
                fields=["project_request", "assigned_to"],
                condition=models.Q(is_active=True),
                name="unique_active_assignment_per_user",
            ),
        ]

    def __str__(self):
        return f"Assignment: {self.project_request} → {self.assigned_to}"


class ProjectRequestAttachment(models.Model):
    """File attachment for a project request."""

    project_request = models.ForeignKey(
        "project_requests.ProjectRequest",
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField(upload_to="project_requests/%Y/%m/")
    original_filename = models.CharField(max_length=255)
    file_type = models.ForeignKey(
        "project_requests.ProjectRequestFileType",
        on_delete=models.PROTECT,
    )
    description = models.TextField(blank=True, default="")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uploaded_project_request_files",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    file_size = models.PositiveIntegerField(help_text="File size in bytes")

    class Meta:
        ordering = ["-uploaded_at"]
        verbose_name = "project request attachment"
        verbose_name_plural = "project request attachments"

    def __str__(self):
        return f"{self.original_filename} ({self.project_request})"


class ProjectRequestActivityLog(models.Model):
    """Immutable activity log for project request lifecycle events."""

    project_request = models.ForeignKey(
        "project_requests.ProjectRequest",
        on_delete=models.CASCADE,
        related_name="activity_log",
    )
    action_type = models.CharField(
        max_length=40,
        choices=ProjectRequestActionType.choices,
    )
    from_status = models.CharField(max_length=20, blank=True, default="")
    to_status = models.CharField(max_length=20, blank=True, default="")
    description = models.CharField(max_length=500)
    comment = models.TextField(blank=True, default="")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="project_request_actions",
        null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "project request activity log"
        verbose_name_plural = "project request activity logs"
        indexes = [
            models.Index(
                fields=["project_request", "-created_at"],
                name="pr_log_idx_pr_created",
            ),
            models.Index(fields=["action_type"], name="pr_log_idx_action"),
            models.Index(fields=["actor"], name="pr_log_idx_actor"),
        ]

    def __str__(self):
        return f"[{self.get_action_type_display()}] {self.project_request}: {self.description}"
