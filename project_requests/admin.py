"""Admin registration for project_requests models."""

from django.contrib import admin
from .models import (
    RequestNumberSequence,
    ProjectRequestType,
    ProjectRequestFileType,
    ProjectDepartmentProfile,
    ProjectRequest,
    ProjectRequestApprovalTask,
    ProjectRequestAssignment,
    ProjectRequestAttachment,
    ProjectRequestActivityLog,
)


class ProjectRequestApprovalTaskInline(admin.TabularInline):
    model = ProjectRequestApprovalTask
    extra = 0
    readonly_fields = ("department", "role", "status", "acted_by", "acted_at", "decision_comment", "created_at", "updated_at")
    can_delete = False


class ProjectRequestAssignmentInline(admin.TabularInline):
    model = ProjectRequestAssignment
    extra = 0
    readonly_fields = ("assigned_to", "assigned_by", "assigned_at", "is_active", "role")
    can_delete = False


class ProjectRequestAttachmentInline(admin.TabularInline):
    model = ProjectRequestAttachment
    extra = 0
    readonly_fields = ("file", "original_filename", "file_type", "description", "uploaded_by", "uploaded_at", "file_size")
    can_delete = False


class ProjectRequestActivityLogInline(admin.TabularInline):
    model = ProjectRequestActivityLog
    extra = 0
    readonly_fields = ("action_type", "from_status", "to_status", "description", "comment", "actor", "created_at")
    can_delete = False


@admin.register(ProjectRequest)
class ProjectRequestAdmin(admin.ModelAdmin):
    list_display = (
        "request_no", "project_name", "requester", "request_department",
        "project_department", "request_type", "priority", "status",
        "needed_by_date", "last_activity_at",
    )
    search_fields = (
        "request_no", "project_name",
        "requester__username", "requester__display_name",
        "request_department__dept_code", "request_department__dept_name",
        "project_department__dept_code", "project_department__dept_name",
    )
    list_filter = ("status", "priority", "request_department", "project_department", "request_type")
    readonly_fields = (
        "created_at", "updated_at", "last_activity_at",
        "submitted_at", "approved_at", "assigned_at",
        "started_at", "completed_at", "cancelled_at",
    )
    inlines = (
        ProjectRequestApprovalTaskInline,
        ProjectRequestAssignmentInline,
        ProjectRequestAttachmentInline,
        ProjectRequestActivityLogInline,
    )
    date_hierarchy = "created_at"


@admin.register(RequestNumberSequence)
class RequestNumberSequenceAdmin(admin.ModelAdmin):
    list_display = ("year", "sequence", "created_at", "updated_at")
    search_fields = ("year",)


@admin.register(ProjectRequestType)
class ProjectRequestTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active", "display_order")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(ProjectRequestFileType)
class ProjectRequestFileTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active", "display_order", "max_file_size_mb")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(ProjectDepartmentProfile)
class ProjectDepartmentProfileAdmin(admin.ModelAdmin):
    list_display = ("department", "is_active", "can_receive_project_requests", "allow_staff_claim", "display_order")
    list_filter = ("is_active", "can_receive_project_requests", "allow_staff_claim")
    search_fields = ("department__dept_code", "department__dept_name")


@admin.register(ProjectRequestApprovalTask)
class ProjectRequestApprovalTaskAdmin(admin.ModelAdmin):
    list_display = ("project_request", "department", "role", "status", "acted_by", "acted_at")
    list_filter = ("status", "role", "department")
    search_fields = ("project_request__request_no", "project_request__project_name")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ProjectRequestAssignment)
class ProjectRequestAssignmentAdmin(admin.ModelAdmin):
    list_display = ("project_request", "assigned_to", "assigned_by", "assigned_at", "is_active", "role")
    list_filter = ("is_active",)
    search_fields = ("project_request__request_no", "assigned_to__username")
    readonly_fields = ("assigned_at",)


@admin.register(ProjectRequestAttachment)
class ProjectRequestAttachmentAdmin(admin.ModelAdmin):
    list_display = ("project_request", "original_filename", "file_type", "uploaded_by", "uploaded_at", "file_size")
    list_filter = ("file_type",)
    search_fields = ("original_filename", "project_request__request_no")
    readonly_fields = ("uploaded_at", "file_size")


@admin.register(ProjectRequestActivityLog)
class ProjectRequestActivityLogAdmin(admin.ModelAdmin):
    list_display = ("project_request", "action_type", "from_status", "to_status", "actor", "created_at")
    list_filter = ("action_type",)
    search_fields = ("project_request__request_no", "description")
    readonly_fields = (
        "project_request", "action_type", "from_status", "to_status",
        "description", "comment", "actor", "created_at",
    )
    exclude = ()

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        # Prevent any modifications to existing records
        pass
