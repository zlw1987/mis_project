"""Views for the project_requests app.

Includes Phase 2B request CRUD/detail/attachment views, Phase 3D workflow
action views, and Phase 4B dashboard view. Business logic delegates to
services/permissions/selectors.
"""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from .forms import (
    ApprovalActionForm,
    AssignmentForm,
    GenericCommentActionForm,
    HoldActionForm,
    ProjectRequestAttachmentForm,
    ProjectRequestDraftForm,
    RejectActionForm,
)
from .models import (
    ProjectRequest,
    ProjectRequestApprovalTask,
    ProjectRequestAttachment,
    ProjectRequestPriority,
    ProjectRequestStatus,
    ProjectRequestType,
)
from .permissions import (
    can_view_project_request,
    get_project_request_action_context,
)
from .selectors import (
    get_visible_project_requests,
    get_dashboard_my_drafts,
    get_dashboard_my_open_requests,
    get_dashboard_pending_approval_tasks,
    get_dashboard_assigned_to_me,
    get_dashboard_claimable_requests,
    get_dashboard_project_department_queue,
    get_dashboard_in_progress_or_on_hold,
    get_dashboard_recently_completed,
    get_dashboard_status_counts,
    get_dashboard_overdue_count,
    get_overdue_project_requests,
)
from .services import (
    approve_project_request,
    assign_project_request,
    claim_project_request,
    complete_project_request,
    create_project_request_draft,
    hold_project_request,
    reject_project_request,
    resume_project_request,
    start_project_request,
    submit_project_request,
    upload_project_request_attachment,
)


# ---------------------------------------------------------------------------
# Helper: consistent detail context for upload error re-renders
# ---------------------------------------------------------------------------

def _build_detail_context(project_request, user, attachment_form=None, attachment_upload_error=None):
    """Build a consistent detail context dict for the projectrequest_detail.html template.

    Used by both ProjectRequestDetailView and ProjectRequestAttachmentUploadView
    to avoid copy-paste drift between detail view and upload error paths.
    """
    if attachment_form is None:
        attachment_form = ProjectRequestAttachmentForm()
    action_context = get_project_request_action_context(user, project_request)
    context = {
        "project_request": project_request,
        "action_context": action_context,
        "attachments": project_request.attachments.all(),
        "approval_tasks": project_request.approval_tasks.all(),
        "assignments": project_request.assignments.filter(is_active=True),
        "activity_logs": project_request.activity_log.all()[:50],
        "attachment_form": attachment_form,
        "attachment_upload_error": attachment_upload_error,
        "can_edit_draft": (
            project_request.status == ProjectRequestStatus.DRAFT
            and (
                project_request.requester == user
                or user.is_superuser
            )
        ),
        "can_submit_draft": (
            project_request.status == ProjectRequestStatus.DRAFT
            and (
                project_request.requester == user
                or user.is_superuser
            )
        ),
    }
    # Phase 3D-4: Include assignment_form when user can assign (matches ProjectRequestDetailView)
    if action_context.get("can_assign"):
        context["assignment_form"] = AssignmentForm(project_request=project_request)
    return context


# ---------------------------------------------------------------------------
# Phase 4B: Dashboard View
# ---------------------------------------------------------------------------

@method_decorator(login_required, name="dispatch")
class ProjectRequestDashboardView(TemplateView):
    """Read-only dashboard showing user's project request sections.

    GET-only. No POST forms. No workflow actions.
    All data sourced from existing selectors.
    """

    template_name = "project_requests/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # My Drafts
        drafts_qs = get_dashboard_my_drafts(user)
        context["my_drafts"] = {
            "title": "My Drafts",
            "count": drafts_qs.count(),
            "items": list(drafts_qs[:10]),
            "empty_state": "No drafts",
            "view_all_url": None,
        }

        # My Open Requests
        open_qs = get_dashboard_my_open_requests(user)
        context["my_open_requests"] = {
            "title": "My Open Requests",
            "count": open_qs.count(),
            "items": list(open_qs[:10]),
            "empty_state": "No open requests",
            "view_all_url": reverse("project_requests:list"),
        }

        # My Pending Approval Tasks
        tasks_qs = get_dashboard_pending_approval_tasks(user)
        context["my_pending_approval_tasks"] = {
            "title": "My Pending Approval Tasks",
            "count": tasks_qs.count(),
            "items": list(tasks_qs[:20]),
            "empty_state": "No pending approvals",
            "view_all_url": None,
        }

        # My Assigned Requests
        assigned_qs = get_dashboard_assigned_to_me(user)
        context["my_assigned_requests"] = {
            "title": "My Assigned Requests",
            "count": assigned_qs.count(),
            "items": list(assigned_qs[:10]),
            "empty_state": "No assigned requests",
            "view_all_url": None,
        }

        # My Overdue Requests
        overdue_qs = get_overdue_project_requests(user)
        context["my_overdue_requests"] = {
            "title": "My Overdue Requests",
            "count": overdue_qs.count(),
            "items": list(overdue_qs[:10]),
            "empty_state": "No overdue requests",
            "view_all_url": None,
        }

        # Claimable Requests (project department staff only)
        claimable_qs = get_dashboard_claimable_requests(user)
        context["claimable_requests"] = {
            "title": "Claimable Requests",
            "count": claimable_qs.count(),
            "items": list(claimable_qs[:10]),
            "empty_state": "No claimable requests",
            "view_all_url": None,
        }

        # Project Department Queue (manager/director/VP only)
        queue_qs = get_dashboard_project_department_queue(user)
        context["project_dept_queue"] = {
            "title": "Project Dept Queue",
            "count": queue_qs.count(),
            "items": list(queue_qs[:15]),
            "empty_state": "No requests in queue",
            "view_all_url": None,
        }

        # In Progress / On Hold (manager/director/VP only)
        in_progress_qs = get_dashboard_in_progress_or_on_hold(user)
        context["in_progress_or_on_hold"] = {
            "title": "In Progress / On Hold",
            "count": in_progress_qs.count(),
            "items": list(in_progress_qs[:10]),
            "empty_state": "No active requests",
            "view_all_url": None,
        }

        # Recently Completed (manager/director/VP only)
        completed_qs = get_dashboard_recently_completed(user, days=30)
        context["recently_completed"] = {
            "title": "Recently Completed (30 days)",
            "count": completed_qs.count(),
            "items": list(completed_qs[:10]),
            "empty_state": "No recently completed",
            "view_all_url": None,
        }

        # Admin Overview (superuser only)
        if user.is_superuser:
            context["admin_overview"] = {
                "title": "Admin Overview",
                "status_counts": get_dashboard_status_counts(user),
                "overdue_count": get_dashboard_overdue_count(user),
            }
            # All pending approvals for superuser
            all_pending_qs = get_dashboard_pending_approval_tasks(user)
            context["all_pending_approvals"] = {
                "title": "All Pending Approvals",
                "count": all_pending_qs.count(),
                "items": list(all_pending_qs[:20]),
                "empty_state": "No pending approvals",
                "view_all_url": None,
            }

        return context


# ---------------------------------------------------------------------------
# A. ProjectRequestListView
# ---------------------------------------------------------------------------

@method_decorator(login_required, name="dispatch")
class ProjectRequestListView(ListView):
    """List project requests visible to the current user."""

    model = ProjectRequest
    template_name = "project_requests/projectrequest_list.html"
    context_object_name = "project_requests"
    paginate_by = 25

    def get_queryset(self):
        qs = get_visible_project_requests(self.request.user)

        # Filters
        status = self.request.GET.get("status", "").strip()
        request_type = self.request.GET.get("request_type", "").strip()
        priority = self.request.GET.get("priority", "").strip()
        project_department = self.request.GET.get("project_department", "").strip()
        search = self.request.GET.get("search", "").strip()

        if status:
            qs = qs.filter(status=status)
        if request_type:
            qs = qs.filter(request_type_id=request_type)
        if priority:
            qs = qs.filter(priority=priority)
        if project_department:
            qs = qs.filter(project_department_id=project_department)
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(request_no__icontains=search)
                | Q(project_name__icontains=search)
            )

        return qs.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_choices"] = ProjectRequestStatus.choices
        context["request_type_choices"] = ProjectRequestType.objects.filter(
            is_active=True
        ).values_list("id", "name")
        context["priority_choices"] = ProjectRequestPriority.choices
        from accounts.models import Department
        context["project_department_choices"] = Department.objects.filter(
            is_active=True
        ).values_list("id", "dept_name")
        context["current_filters"] = self.request.GET.copy()
        return context


# ---------------------------------------------------------------------------
# B. ProjectRequestDetailView
# ---------------------------------------------------------------------------

@method_decorator(login_required, name="dispatch")
class ProjectRequestDetailView(DetailView):
    """Detail view for a single project request."""

    model = ProjectRequest
    template_name = "project_requests/projectrequest_detail.html"
    context_object_name = "project_request"

    def get_queryset(self):
        return ProjectRequest.objects.all()

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not can_view_project_request(request.user, self.object):
            return self.handle_no_permission()
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def handle_no_permission(self):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("You do not have permission to view this request.")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pr = self.object
        action_context = get_project_request_action_context(
            self.request.user, pr
        )
        context["action_context"] = action_context
        context["attachments"] = pr.attachments.all()
        context["approval_tasks"] = pr.approval_tasks.all()
        context["assignments"] = pr.assignments.filter(is_active=True)
        context["activity_logs"] = pr.activity_log.all()[:50]
        context["attachment_form"] = ProjectRequestAttachmentForm()
        context["can_edit_draft"] = (
            pr.status == ProjectRequestStatus.DRAFT
            and (
                pr.requester == self.request.user
                or self.request.user.is_superuser
            )
        )
        context["can_submit_draft"] = (
            pr.status == ProjectRequestStatus.DRAFT
            and (
                pr.requester == self.request.user
                or self.request.user.is_superuser
            )
        )
        # Phase 3D-2: Assignment form when user can assign
        if action_context.get("can_assign"):
            context["assignment_form"] = AssignmentForm(project_request=pr)
        return context


# ---------------------------------------------------------------------------
# C. ProjectRequestCreateView
# ---------------------------------------------------------------------------

@method_decorator(login_required, name="dispatch")
class ProjectRequestCreateView(CreateView):
    """Create a new project request (draft or submit)."""

    model = ProjectRequest
    form_class = ProjectRequestDraftForm
    template_name = "project_requests/projectrequest_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        if not self.request.user.is_active:
            form.add_error(None, "Your account is inactive.")
            return self.form_invalid(form)

        # Build data for draft creation
        form_data = form.cleaned_data.copy()
        form_data["requester"] = self.request.user

        # Check for submit action — if submitting directly (not saving draft),
        # create draft then attempt submit, but delete orphan on failure.
        is_submit = self.request.POST.get("submit")

        # Create draft via service
        try:
            project_request = create_project_request_draft(**form_data)
        except Exception as e:
            form.add_error(None, str(e))
            return self.form_invalid(form)

        if is_submit:
            # Attempt submit via service
            try:
                submit_project_request(project_request, self.request.user)
            except (ValidationError, PermissionDenied) as e:
                # Submit validation failed — delete the orphan draft before returning.
                # Gaps in request_no sequence are acceptable.
                project_request_id = project_request.pk
                project_request.delete()
                # Refresh from DB to ensure deletion is committed before response.
                ProjectRequest.objects.filter(pk=project_request_id).delete()
                if isinstance(e, ValidationError) and hasattr(e, "message_dict"):
                    for field, messages in e.message_dict.items():
                        if field in form.fields:
                            for msg in messages:
                                form.add_error(field, msg)
                        else:
                            form.add_error(None, f"{field}: {', '.join(messages)}")
                else:
                    form.add_error(None, str(e))
                return self.form_invalid(form)
            except Exception as e:
                # Delete orphan draft on unexpected error too.
                project_request_id = project_request.pk
                project_request.delete()
                ProjectRequest.objects.filter(pk=project_request_id).delete()
                form.add_error(None, str(e))
                return self.form_invalid(form)

        return redirect("project_requests:detail", pk=project_request.pk)

    def get_success_url(self):
        return reverse("project_requests:list")


# ---------------------------------------------------------------------------
# D. ProjectRequestEditDraftView
# ---------------------------------------------------------------------------

@method_decorator(login_required, name="dispatch")
class ProjectRequestEditDraftView(UpdateView):
    """Edit a DRAFT project request. Only requester or superuser can edit."""

    model = ProjectRequest
    form_class = ProjectRequestDraftForm
    template_name = "project_requests/projectrequest_form.html"
    context_object_name = "project_request"

    def get_queryset(self):
        return ProjectRequest.objects.all()

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not self._can_edit():
            return self.handle_no_permission()
        # Only DRAFT status can be edited
        if self.object.status != ProjectRequestStatus.DRAFT:
            return self.handle_no_permission()
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not self._can_edit():
            return self.handle_no_permission()

        # Only DRAFT can be edited
        if self.object.status != ProjectRequestStatus.DRAFT:
            return self.handle_no_permission()

        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def _can_edit(self):
        pr = self.object
        return (
            pr.requester == self.request.user
            or self.request.user.is_superuser
        )

    def handle_no_permission(self):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("You do not have permission to edit this request.")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        # Save draft changes
        for field in form.Meta.fields:
            if field in form.cleaned_data:
                setattr(self.object, field, form.cleaned_data[field])
        self.object.save(update_fields=form.Meta.fields + ["updated_at"])

        # Check for submit action
        if self.request.POST.get("submit"):
            try:
                submit_project_request(self.object, self.request.user)
            except ValidationError as e:
                # Submit validation failed — remains DRAFT
                if hasattr(e, "message_dict"):
                    for field, messages in e.message_dict.items():
                        if field in form.fields:
                            for msg in messages:
                                form.add_error(field, msg)
                        else:
                            form.add_error(None, f"{field}: {', '.join(messages)}")
                else:
                    form.add_error(None, str(e))
                return self.form_invalid(form)
            except PermissionDenied as e:
                form.add_error(None, str(e))
                return self.form_invalid(form)
            except Exception as e:
                form.add_error(None, str(e))
                return self.form_invalid(form)

        return redirect("project_requests:detail", pk=self.object.pk)


# ---------------------------------------------------------------------------
# E. ProjectRequestAttachmentUploadView
# ---------------------------------------------------------------------------

@method_decorator(login_required, name="dispatch")
class ProjectRequestAttachmentUploadView(CreateView):
    """Upload an attachment to a project request.

    Uses upload_project_request_attachment() service for validation and permissions.
    """

    model = ProjectRequest
    form_class = ProjectRequestAttachmentForm
    template_name = "project_requests/projectrequest_detail.html"

    def get(self, request, *args, **kwargs):
        # GET not supported — redirect to detail
        project_request = get_object_or_404(ProjectRequest, pk=kwargs.get("pk"))
        return redirect("project_requests:detail", pk=project_request.pk)

    def post(self, request, *args, **kwargs):
        project_request = get_object_or_404(ProjectRequest, pk=kwargs.get("pk"))

        # Check view permission first
        if not can_view_project_request(request.user, project_request):
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden(
                "You do not have permission to view this request."
            )

        form = self.get_form()
        if not form.is_valid():
            # Re-render detail with form errors — always include attachment_form
            context = _build_detail_context(
                project_request, request.user, attachment_form=form
            )
            return render(
                request,
                "project_requests/projectrequest_detail.html",
                context,
            )

        uploaded_file = form.cleaned_data["file"]
        file_type = form.cleaned_data["file_type"]
        description = form.cleaned_data.get("description", "")

        try:
            upload_project_request_attachment(
                project_request=project_request,
                uploaded_file=uploaded_file,
                file_type=file_type,
                uploaded_by=request.user,
                description=description,
            )
        except PermissionDenied:
            context = _build_detail_context(
                project_request, request.user,
                attachment_upload_error=(
                    "You do not have permission to attach files to this request."
                ),
            )
            return render(
                request,
                "project_requests/projectrequest_detail.html",
                context,
            )
        except ValidationError as e:
            messages = []
            if hasattr(e, "message_dict"):
                for msgs in e.message_dict.values():
                    messages.extend(msgs)
            else:
                messages.append(str(e))
            context = _build_detail_context(
                project_request, request.user,
                attachment_upload_error=" ".join(messages),
            )
            return render(
                request,
                "project_requests/projectrequest_detail.html",
                context,
            )

        return redirect("project_requests:detail", pk=project_request.pk)


# ---------------------------------------------------------------------------
# F. ProjectRequestAttachmentDownloadView
# ---------------------------------------------------------------------------

@method_decorator(login_required, name="dispatch")
class ProjectRequestAttachmentDownloadView(TemplateView):
    """Permission-checked attachment download.

    Uses can_view_project_request() to authorize download.
    Returns FileResponse — does NOT expose attachment.file.url.
    """

    def get(self, request, *args, **kwargs):
        attachment_id = kwargs.get("attachment_id")
        attachment = get_object_or_404(ProjectRequestAttachment, pk=attachment_id)

        # Permission check via parent project_request
        if not can_view_project_request(request.user, attachment.project_request):
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden(
                "You do not have permission to download this attachment."
            )

        # Return file via FileResponse (permission-checked, no direct URL exposure)
        try:
            response = FileResponse(
                attachment.file.open("rb"),
                as_attachment=True,
                filename=attachment.original_filename,
            )
            return response
        except Exception:
            raise Http404("Attachment file not found.")


# ---------------------------------------------------------------------------
# Phase 3D-1: Approve/Reject Views
# ---------------------------------------------------------------------------

@login_required
@require_POST
def project_request_approve(request, pk):
    """Approve a project request by acting on an approval task.

    POST only. Delegates to approve_project_request() service.
    Validates approval_task_id belongs to the current project request.
    """
    from django.contrib import messages

    project_request = get_object_or_404(ProjectRequest, pk=pk)

    if not can_view_project_request(request.user, project_request):
        raise PermissionDenied

    form = ApprovalActionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Invalid approval form.")
        return redirect("project_requests:detail", pk=pk)

    approval_task_id = form.cleaned_data["approval_task_id"]
    comment = form.cleaned_data["comment"]

    # Validate task belongs to this request
    try:
        task = ProjectRequestApprovalTask.objects.get(pk=approval_task_id)
    except ProjectRequestApprovalTask.DoesNotExist:
        messages.error(request, "Approval task not found.")
        return redirect("project_requests:detail", pk=pk)

    if task.project_request_id != project_request.pk:
        messages.error(request, "Approval task does not belong to this request.")
        return redirect("project_requests:detail", pk=pk)

    try:
        approve_project_request(project_request, task, request.user, comment)
        messages.success(request, "Request approved.")
    except PermissionDenied as e:
        messages.error(request, str(e))
    except ValidationError as e:
        messages.error(request, str(e))

    return redirect("project_requests:detail", pk=pk)


@login_required
@require_POST
def project_request_reject(request, pk):
    """Reject a project request by acting on an approval task.

    POST only. Delegates to reject_project_request() service.
    Validates approval_task_id belongs to the current project request.
    """
    from django.contrib import messages

    project_request = get_object_or_404(ProjectRequest, pk=pk)

    if not can_view_project_request(request.user, project_request):
        raise PermissionDenied

    form = RejectActionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "A rejection comment is required.")
        return redirect("project_requests:detail", pk=pk)

    approval_task_id = form.cleaned_data["approval_task_id"]
    comment = form.cleaned_data["comment"]

    # Validate task belongs to this request
    try:
        task = ProjectRequestApprovalTask.objects.get(pk=approval_task_id)
    except ProjectRequestApprovalTask.DoesNotExist:
        messages.error(request, "Approval task not found.")
        return redirect("project_requests:detail", pk=pk)

    if task.project_request_id != project_request.pk:
        messages.error(request, "Approval task does not belong to this request.")
        return redirect("project_requests:detail", pk=pk)

    try:
        reject_project_request(project_request, task, request.user, comment)
        messages.success(request, "Request rejected.")
    except PermissionDenied as e:
        messages.error(request, str(e))
    except ValidationError as e:
        messages.error(request, str(e))

    return redirect("project_requests:detail", pk=pk)


# ---------------------------------------------------------------------------
# Phase 3D-2: Assign/Claim Views
# ---------------------------------------------------------------------------

@login_required
@require_POST
def project_request_assign(request, pk):
    """Assign a project request to a user.

    POST only. Delegates to assign_project_request() service.
    """
    from django.contrib import messages

    project_request = get_object_or_404(ProjectRequest, pk=pk)

    if not can_view_project_request(request.user, project_request):
        raise PermissionDenied

    form = AssignmentForm(request.POST, project_request=project_request)
    if not form.is_valid():
        messages.error(request, "Invalid assignment form.")
        return redirect("project_requests:detail", pk=pk)

    assigned_to = form.cleaned_data["assigned_to"]
    comment = form.cleaned_data.get("comment", "")

    try:
        assign_project_request(
            project_request, assigned_to, request.user, comment=comment
        )
        messages.success(request, "Request assigned.")
    except PermissionDenied as e:
        messages.error(request, str(e))
    except ValidationError as e:
        messages.error(request, str(e))

    return redirect("project_requests:detail", pk=pk)


@login_required
@require_POST
def project_request_claim(request, pk):
    """Claim an approved project request for oneself.

    POST only. Delegates to claim_project_request() service.
    """
    from django.contrib import messages

    project_request = get_object_or_404(ProjectRequest, pk=pk)

    if not can_view_project_request(request.user, project_request):
        raise PermissionDenied

    try:
        claim_project_request(project_request, request.user)
        messages.success(request, "Request claimed.")
    except PermissionDenied as e:
        messages.error(request, str(e))
    except ValidationError as e:
        messages.error(request, str(e))

    return redirect("project_requests:detail", pk=pk)


# ---------------------------------------------------------------------------
# Phase 3D-3: Execution Workflow Views (Start/Hold/Resume/Complete)
# ---------------------------------------------------------------------------

@login_required
@require_POST
def project_request_start(request, pk):
    """Start execution: ASSIGNED -> IN_PROGRESS.

    POST only. Delegates to start_project_request() service.
    Comment is optional.
    """
    from django.contrib import messages

    project_request = get_object_or_404(ProjectRequest, pk=pk)

    if not can_view_project_request(request.user, project_request):
        raise PermissionDenied

    form = GenericCommentActionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Invalid start form.")
        return redirect("project_requests:detail", pk=pk)

    comment = form.cleaned_data.get("comment", "")

    try:
        start_project_request(project_request, request.user, comment=comment)
        messages.success(request, "Request started.")
    except PermissionDenied as e:
        messages.error(request, str(e))
    except ValidationError as e:
        messages.error(request, str(e))

    return redirect("project_requests:detail", pk=pk)


@login_required
@require_POST
def project_request_hold(request, pk):
    """Put on hold: IN_PROGRESS -> ON_HOLD.

    POST only. Delegates to hold_project_request() service.
    Comment is required.
    """
    from django.contrib import messages

    project_request = get_object_or_404(ProjectRequest, pk=pk)

    if not can_view_project_request(request.user, project_request):
        raise PermissionDenied

    form = HoldActionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "A hold reason is required.")
        return redirect("project_requests:detail", pk=pk)

    comment = form.cleaned_data.get("comment", "")

    try:
        hold_project_request(project_request, request.user, comment=comment)
        messages.success(request, "Request put on hold.")
    except PermissionDenied as e:
        messages.error(request, str(e))
    except ValidationError as e:
        messages.error(request, str(e))

    return redirect("project_requests:detail", pk=pk)


@login_required
@require_POST
def project_request_resume(request, pk):
    """Resume from hold: ON_HOLD -> IN_PROGRESS.

    POST only. Delegates to resume_project_request() service.
    Comment is optional.
    """
    from django.contrib import messages

    project_request = get_object_or_404(ProjectRequest, pk=pk)

    if not can_view_project_request(request.user, project_request):
        raise PermissionDenied

    form = GenericCommentActionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Invalid resume form.")
        return redirect("project_requests:detail", pk=pk)

    comment = form.cleaned_data.get("comment", "")

    try:
        resume_project_request(project_request, request.user, comment=comment)
        messages.success(request, "Request resumed.")
    except PermissionDenied as e:
        messages.error(request, str(e))
    except ValidationError as e:
        messages.error(request, str(e))

    return redirect("project_requests:detail", pk=pk)


@login_required
@require_POST
def project_request_complete(request, pk):
    """Complete execution: IN_PROGRESS -> COMPLETED.

    POST only. Delegates to complete_project_request() service.
    Comment is optional.
    """
    from django.contrib import messages

    project_request = get_object_or_404(ProjectRequest, pk=pk)

    if not can_view_project_request(request.user, project_request):
        raise PermissionDenied

    form = GenericCommentActionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Invalid complete form.")
        return redirect("project_requests:detail", pk=pk)

    comment = form.cleaned_data.get("comment", "")

    try:
        complete_project_request(project_request, request.user, comment=comment)
        messages.success(request, "Request completed.")
    except PermissionDenied as e:
        messages.error(request, str(e))
    except ValidationError as e:
        messages.error(request, str(e))

    return redirect("project_requests:detail", pk=pk)
