"""Forms for the project_requests app (Phase 2B)."""

from django import forms

from accounts.models import Department, User
from .models import (
    ProjectRequest,
    ProjectRequestFileType,
    ProjectRequestPriority,
    ProjectRequestType,
)


class ProjectRequestDraftForm(forms.ModelForm):
    """Form for creating or editing a ProjectRequest draft.

    Does not enforce submit-required fields so incomplete drafts can be saved.
    Querysets are filtered to active/receivable departments and types.
    """

    class Meta:
        model = ProjectRequest
        fields = [
            "project_name",
            "request_department",
            "project_department",
            "request_type",
            "priority",
            "needed_by_date",
            "scope_summary",
            "business_problem",
            "business_scope",
            "technical_scope",
            "in_scope",
            "out_of_scope",
            "expected_deliverables",
            "acceptance_criteria",
            "affected_systems",
            "customer",
            "etd",
            "hours_estimate",
        ]
        widgets = {
            "project_name": forms.TextInput(attrs={"class": "form-control"}),
            "request_department": forms.Select(attrs={"class": "form-control"}),
            "project_department": forms.Select(attrs={"class": "form-control"}),
            "request_type": forms.Select(attrs={"class": "form-control"}),
            "priority": forms.Select(attrs={"class": "form-control"}),
            "needed_by_date": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}
            ),
            "scope_summary": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "business_problem": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "business_scope": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "technical_scope": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "in_scope": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "out_of_scope": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "expected_deliverables": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "acceptance_criteria": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "affected_systems": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "customer": forms.TextInput(attrs={"class": "form-control"}),
            "etd": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "hours_estimate": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._user = user or None

        # Filter project_department to active departments with active ProjectDepartmentProfile
        # where is_active=True and can_receive_project_requests=True
        self.fields["project_department"].queryset = Department.objects.filter(
            is_active=True,
            project_dept_profile__is_active=True,
            project_dept_profile__can_receive_project_requests=True,
        ).distinct()

        # Filter request_type to active types only
        self.fields["request_type"].queryset = ProjectRequestType.objects.filter(
            is_active=True
        )

        # Filter request_department:
        # - Superuser sees all active departments
        # - Normal users see only departments where they have active UserDepartment membership
        if self._user and self._user.is_superuser:
            self.fields["request_department"].queryset = Department.objects.filter(
                is_active=True
            )
        elif self._user and self._user.is_authenticated:
            self.fields["request_department"].queryset = Department.objects.filter(
                is_active=True,
                user_departments__user=self._user,
                user_departments__is_active=True,
            ).distinct()
        else:
            self.fields["request_department"].queryset = Department.objects.none()

        # Make business fields optional for draft form, but keep request_department required
        for field_name in self.Meta.fields:
            if field_name != "request_department":
                self.fields[field_name].required = False


class ProjectRequestAttachmentForm(forms.ModelForm):
    """Form for uploading an attachment to a ProjectRequest.

    Does not duplicate full upload validation; the upload_project_request_attachment()
    service handles permission, extension, size, and activity log validation.
    """

    class Meta:
        model = ProjectRequest
        fields = []  # Not bound to ProjectRequest fields directly

    file = forms.FileField(required=True)
    file_type = forms.ModelChoiceField(
        queryset=ProjectRequestFileType.objects.filter(is_active=True),
        required=True,
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    )

    def clean_file_type(self):
        file_type = self.cleaned_data.get("file_type")
        if file_type and not file_type.is_active:
            raise forms.ValidationError("Selected file type is not active.")
        return file_type


# ---------------------------------------------------------------------------
# Phase 3D-1: Approval Action Forms
# ---------------------------------------------------------------------------

class ApprovalActionForm(forms.Form):
    """Form for approving a project request task. Comment is optional."""

    approval_task_id = forms.IntegerField(widget=forms.HiddenInput())
    comment = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    )


class RejectActionForm(forms.Form):
    """Form for rejecting a project request task. Comment is required."""

    approval_task_id = forms.IntegerField(widget=forms.HiddenInput())
    comment = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        error_messages={"required": "A rejection comment is required."},
    )


# ---------------------------------------------------------------------------
# Phase 3D-2: Assignment Form
# ---------------------------------------------------------------------------

class AssignmentForm(forms.Form):
    """Form for assigning a project request to a user.

    The queryset for assigned_to is dynamically filtered in __init__ to only
    include active users with active UserDepartment membership in the
    project_request's project_department.
    """

    assigned_to = forms.ModelChoiceField(
        queryset=None,  # Set dynamically in __init__
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    comment = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    )

    def __init__(self, *args, project_request=None, **kwargs):
        super().__init__(*args, **kwargs)
        if project_request and project_request.project_department:
            proj_dept = project_request.project_department
            self.fields["assigned_to"].queryset = (
                User.objects.filter(
                    is_active=True,
                    user_departments__department=proj_dept,
                    user_departments__is_active=True,
                )
                .order_by("display_name", "username")
                .distinct()
            )
        else:
            self.fields["assigned_to"].queryset = User.objects.none()


# ---------------------------------------------------------------------------
# Phase 3D-3: Execution Action Forms
# ---------------------------------------------------------------------------

class HoldActionForm(forms.Form):
    """Form for putting a project request on hold. Comment is required."""

    comment = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        error_messages={"required": "A hold reason is required."},
    )


class GenericCommentActionForm(forms.Form):
    """Optional comment form for start/resume/complete actions."""

    comment = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    )
