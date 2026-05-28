# Phase 3D — Workflow UI Integration Plan

> **Status:** Phase 3D COMPLETE — Phase 3D-5A PASS — Phase 4 PLANNING NEXT
> **Model:** minimax-m2.7
> **Date:** 2026-05-22
> **Last Updated:** 2026-05-27 (Phase 3D-5A acceptance, Phase 3D complete, Phase 3 complete)

---

## READY / CONDITIONAL READY / NOT READY

**READY**

All prerequisites are complete:
- Phase 0, 1, 2A, 2B: complete and reviewed
- Phase 3A (approve/reject services): complete
- Phase 3B (assign/claim services): complete
- Phase 3C (execution workflow services): complete
- `get_project_request_action_context()` enriched with all Phase 3C flags
- Full test suite verified by user after Phase 3C (267+ tests OK)
- Phase 3D-1: complete (implemented by minimax-m2.7)
- No blockers identified before Phase 3D-2

---

## 1. Current UI Foundation (Phase 2B)

### Existing Views
| View | URL | Method | Purpose |
|------|-----|--------|---------|
| `ProjectRequestListView` | `/` | GET | List visible requests with filters |
| `ProjectRequestDetailView` | `/<pk>/` | GET | Detail page with attachments, approvals, assignments, activity log |
| `ProjectRequestCreateView` | `/new/` | GET/POST | Create draft or submit |
| `ProjectRequestEditDraftView` | `/<pk>/edit/` | GET/POST | Edit draft, save or submit |
| `ProjectRequestAttachmentUploadView` | `/<pk>/attachments/upload/` | POST | Upload attachment |
| `ProjectRequestAttachmentDownloadView` | `/attachments/<id>/download/` | GET | Permission-checked download |

### Existing URL Structure
```
project_requests:list                    /
project_requests:create                 /new/
project_requests:detail                  /<int:pk>/
project_requests:edit                    /<int:pk>/edit/
project_requests:attachment_upload       /<int:pk>/attachments/upload/
project_requests:attachment_download     /attachments/<int:attachment_id>/download/
```

### Existing Template Structure
- `base.html`: Bootstrap-like CSS, navbar with user greeting, messages block
- `projectrequest_list.html`: Filter bar, paginated table, status badges
- `projectrequest_detail.html`: Main info card, approval tasks table, assignments table, attachments section, activity log, actions card
- `projectrequest_form.html`: Draft create/edit form

### Existing action_context Usage
The detail view already calls `get_project_request_action_context(user, project_request)` and passes it to the template. Currently used for `can_attach_file` only. The context already contains all Phase 3A/3C flags:
- `can_assign`, `can_claim`
- `pending_approval_tasks_user_can_act_on`, `can_approve_any_task`, `can_reject_any_task`
- `can_start`, `can_hold`, `can_resume`, `can_complete`

### Existing Error Handling Pattern
- Attachment upload re-renders detail with `attachment_upload_error` in context
- Views use `messages` framework for success/error feedback
- PermissionDenied returns 403 on detail/edit views
- ValidationError from services caught and re-rendered with error context

---

## 2. Proposed Phase 3D Forms

All forms go in `project_requests/forms.py`. Forms validate input shape only — business rules live in services.

### 2.1 ApprovalActionForm
```python
class ApprovalActionForm(forms.Form):
    """Form for approving a project request task. Comment is optional."""
    approval_task_id = forms.IntegerField(widget=forms.HiddenInput())
    comment = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    )
```

### 2.2 RejectActionForm
```python
class RejectActionForm(forms.Form):
    """Form for rejecting a project request task. Comment is required."""
    approval_task_id = forms.IntegerField(widget=forms.HiddenInput())
    comment = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        error_messages={"required": "A rejection comment is required."},
    )
```

### 2.3 AssignmentForm
```python
class AssignmentForm(forms.Form):
    """Form for assigning a project request to a user."""
    assigned_to = forms.ModelChoiceField(
        queryset=User.objects.none(),  # Set dynamically in __init__
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
            self.fields["assigned_to"].queryset = User.objects.filter(
                is_active=True,
                user_departments__department=proj_dept,
                user_departments__is_active=True,
            ).distinct()
        else:
            self.fields["assigned_to"].queryset = User.objects.none()
```

### 2.4 HoldActionForm
```python
class HoldActionForm(forms.Form):
    """Form for putting a project request on hold. Comment is required."""
    comment = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        error_messages={"required": "A hold reason is required."},
    )
```

### 2.5 GenericCommentActionForm (optional, for start/resume/complete)
```python
class GenericCommentActionForm(forms.Form):
    """Optional comment form for start/resume/complete actions."""
    comment = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    )
```

### Form Design Rules
- Forms validate input shape only (required fields, field types, max lengths)
- Forms do NOT duplicate service-layer business rules
- `AssignmentForm.__init__` receives `project_request` to build the dynamic queryset
- `RejectActionForm` and `HoldActionForm` enforce required comment at form level
- All forms use Bootstrap-compatible widget classes matching existing templates

---

## 3. Proposed Views and URL Routes

All action views are POST-only, require login, and delegate to existing services.

### 3.1 URL Routes

```
project_requests:approve    /<int:pk>/approve/
project_requests:reject     /<int:pk>/reject/
project_requests:assign     /<int:pk>/assign/
project_requests:claim      /<int:pk>/claim/
project_requests:start       /<int:pk>/start/
project_requests:hold        /<int:pk>/hold/
project_requests:resume      /<int:pk>/resume/
project_requests:complete   /<int:pk>/complete/
```

### 3.2 View Patterns

#### Pattern A: Approve View
```python
@login_required
@require_http_methods(["POST"])
def project_request_approve(request, pk):
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
```

#### Pattern B: Reject View
Same as approve, but uses `RejectActionForm` and `reject_project_request()`. Reject form validation ensures comment is non-empty before calling service.

#### Pattern C: Assign View
```python
@login_required
@require_http_methods(["POST"])
def project_request_assign(request, pk):
    project_request = get_object_or_404(ProjectRequest, pk=pk)
    if not can_view_project_request(request.user, project_request):
        raise PermissionDenied
    
    form = AssignmentForm(request.POST, project_request=project_request)
    if not form.is_valid():
        messages.error(request, "Invalid assignment form.")
        return redirect("project_requests:detail", pk=pk)
    
    assigned_to = form.cleaned_data["assigned_to"]
    comment = form.cleaned_data["comment"]
    
    try:
        assign_project_request(project_request, assigned_to, request.user, comment=comment)
        messages.success(request, f"Request assigned to {assigned_to}.")
    except PermissionDenied as e:
        messages.error(request, str(e))
    except ValidationError as e:
        messages.error(request, str(e))
    
    return redirect("project_requests:detail", pk=pk)
```

#### Pattern D: Claim View
```python
@login_required
@require_http_methods(["POST"])
def project_request_claim(request, pk):
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
```

#### Pattern E: Start View
```python
@login_required
@require_http_methods(["POST"])
def project_request_start(request, pk):
    project_request = get_object_or_404(ProjectRequest, pk=pk)
    if not can_view_project_request(request.user, project_request):
        raise PermissionDenied
    
    form = GenericCommentActionForm(request.POST)
    comment = form.cleaned_data.get("comment", "") if form.is_valid() else ""
    
    try:
        start_project_request(project_request, request.user, comment)
        messages.success(request, "Request started.")
    except PermissionDenied as e:
        messages.error(request, str(e))
    except ValidationError as e:
        messages.error(request, str(e))
    
    return redirect("project_requests:detail", pk=pk)
```

#### Pattern F: Hold View
```python
@login_required
@require_http_methods(["POST"])
def project_request_hold(request, pk):
    project_request = get_object_or_404(ProjectRequest, pk=pk)
    if not can_view_project_request(request.user, project_request):
        raise PermissionDenied
    
    form = HoldActionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Hold reason is required.")
        return redirect("project_requests:detail", pk=pk)
    
    comment = form.cleaned_data["comment"]
    
    try:
        hold_project_request(project_request, request.user, comment)
        messages.success(request, "Request put on hold.")
    except PermissionDenied as e:
        messages.error(request, str(e))
    except ValidationError as e:
        messages.error(request, str(e))
    
    return redirect("project_requests:detail", pk=pk)
```

#### Pattern G: Resume View
Same as start, but uses `resume_project_request()`.

#### Pattern H: Complete View
Same as start, but uses `complete_project_request()`.

### 3.3 View Design Rules
- All views use `@login_required` and `@require_http_methods(["POST"])`
- All views retrieve the `ProjectRequest` via `get_object_or_404`
- All views check `can_view_project_request` before any action
- All views call the appropriate service function
- All views catch `PermissionDenied` and `ValidationError` from services
- All views use `messages` framework for feedback
- All views redirect to the detail page
- No business logic duplication — views are thin wrappers
- For approve/reject: validate `approval_task_id` belongs to the current `ProjectRequest` before calling service

---

## 4. Detail Template UI Plan

Update `templates/project_requests/projectrequest_detail.html` to add workflow action controls in the Actions card section.

### 4.1 Approval Controls
```html
<!-- Approval Actions (Phase 3D) -->
{% if action_context.can_approve_any_task or action_context.can_reject_any_task %}
<div class="card" style="margin-bottom: 15px;">
    <p class="section-title">Your Approval Tasks</p>
    {% for task in action_context.pending_approval_tasks_user_can_act_on %}
    <div style="margin-bottom: 15px; padding: 10px; border: 1px solid #ddd; border-radius: 4px;">
        <p><strong>{{ task.get_role_display }}</strong> — {{ task.department.dept_name }}</p>
        
        <!-- Approve Form -->
        <form method="post" action="{% url 'project_requests:approve' project_request.pk %}" style="display: inline-block; margin-right: 10px;">
            {% csrf_token %}
            <input type="hidden" name="approval_task_id" value="{{ task.pk }}">
            <textarea name="comment" class="form-control" rows="2" placeholder="Optional comment" style="margin-bottom: 5px;"></textarea>
            <button type="submit" class="btn btn-success btn-sm">Approve</button>
        </form>
        
        <!-- Reject Form -->
        <form method="post" action="{% url 'project_requests:reject' project_request.pk %}" style="display: inline-block;">
            {% csrf_token %}
            <input type="hidden" name="approval_task_id" value="{{ task.pk }}">
            <textarea name="comment" class="form-control" rows="2" placeholder="Required rejection reason" style="margin-bottom: 5px;" required></textarea>
            <button type="submit" class="btn btn-danger btn-sm">Reject</button>
        </form>
    </div>
    {% endfor %}
</div>
{% endif %}
```

### 4.2 Assignment Controls
```html
<!-- Assignment Form (Phase 3D) -->
{% if action_context.can_assign %}
<div class="card" style="margin-bottom: 15px;">
    <p class="section-title">Assign Request</p>
    <form method="post" action="{% url 'project_requests:assign' project_request.pk %}">
        {% csrf_token %}
        <div class="form-group">
            <label for="id_assigned_to">Assign To</label>
            <select name="assigned_to" id="id_assigned_to" class="form-control" required>
                <option value="">-- Select User --</option>
                {% for user in assignment_form.fields.assigned_to.queryset %}
                    <option value="{{ user.pk }}">{{ user.display_name|default:user.username }}</option>
                {% endfor %}
            </select>
        </div>
        <div class="form-group">
            <label for="id_comment">Comment (optional)</label>
            <textarea name="comment" id="id_comment" class="form-control" rows="2"></textarea>
        </div>
        <button type="submit" class="btn btn-warning">Assign</button>
    </form>
</div>
{% endif %}
```

### 4.3 Claim Control
```html
<!-- Claim Button (Phase 3D) -->
{% if action_context.can_claim %}
<form method="post" action="{% url 'project_requests:claim' project_request.pk %}" style="display: inline-block;">
    {% csrf_token %}
    <button type="submit" class="btn btn-info">Claim This Request</button>
</form>
{% endif %}
```

### 4.4 Execution Controls
```html
<!-- Start Button (Phase 3D) -->
{% if action_context.can_start %}
<form method="post" action="{% url 'project_requests:start' project_request.pk %}" style="display: inline-block;">
    {% csrf_token %}
    <button type="submit" class="btn btn-primary">Start</button>
</form>
{% endif %}

<!-- Hold Form (Phase 3D) -->
{% if action_context.can_hold %}
<div style="margin-top: 10px;">
    <form method="post" action="{% url 'project_requests:hold' project_request.pk %}">
        {% csrf_token %}
        <div class="form-group" style="margin-bottom: 5px;">
            <textarea name="comment" class="form-control" rows="2" placeholder="Hold reason (required)" required></textarea>
        </div>
        <button type="submit" class="btn btn-warning">Put on Hold</button>
    </form>
</div>
{% endif %}

<!-- Resume Button (Phase 3D) -->
{% if action_context.can_resume %}
<form method="post" action="{% url 'project_requests:resume' project_request.pk %}" style="display: inline-block;">
    {% csrf_token %}
    <button type="submit" class="btn btn-success">Resume</button>
</form>
{% endif %}

<!-- Complete Button (Phase 3D) -->
{% if action_context.can_complete %}
<form method="post" action="{% url 'project_requests:complete' project_request.pk %}" style="display: inline-block;">
    {% csrf_token %}
    <button type="submit" class="btn btn-success">Mark Complete</button>
</form>
{% endif %}
```

### 4.5 Template Design Rules
- All forms include `{% csrf_token %}`
- All forms use `method="post"`
- All forms POST to the appropriate action URL
- Controls are gated by `action_context` flags, NOT by raw status checks
- `action_context.can_approve_any_task` / `can_reject_any_task` gate the approval section
- `action_context.can_assign` gates the assignment form
- `action_context.can_claim` gates the claim button
- `action_context.can_start/hold/resume/complete` gate execution controls
- Error messages displayed via `{% if messages %}` block in base template
- English UI text only
- No status-based button exposure — permission-based only

### 4.6 Context Changes for Template
The detail view's `get_context_data` needs to include the `AssignmentForm` for the assignment dropdown:
```python
def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    # ... existing context ...
    if action_context["can_assign"]:
        context["assignment_form"] = AssignmentForm(project_request=self.object)
    return context
```

---

## 5. Implementation Subphases

### Phase 3D-1: Approve/Reject UI

**Status:** COMPLETE (implemented by minimax-m2.7)

**Files changed:**
- `project_requests/forms.py` — added `ApprovalActionForm`, `RejectActionForm`
- `project_requests/views.py` — added `project_request_approve`, `project_request_reject`
- `project_requests/urls.py` — added approve/reject URL routes
- `project_requests/tests_views.py` — added approve/reject view tests
- `templates/project_requests/projectrequest_detail.html` — added approval task controls

**Implemented:**
- `ApprovalActionForm` — approve action form with optional comment
- `RejectActionForm` — reject action form with required comment
- `project_request_approve` view — POST-only via `@require_POST`, validates task belongs to request
- `project_request_reject` view — POST-only via `@require_POST`, validates task belongs to request
- Approve/reject URL routes (`/<int:pk>/approve/`, `/<int:pk>/reject/`)
- Approve/reject template controls gated by `action_context.can_approve_any_task` / `can_reject_any_task`
- Nullable `task.acted_by` and `log.actor` safe rendering in templates
- Stale future action HTML comments removed from detail template

**Tests to run:**
```bash
python manage.py test project_requests.tests_views.ProjectRequestApproveRejectViewTest
python manage.py test project_requests.tests.ProjectRequestApprovalServiceTest
```
Plus targeted regression: attachment upload/download, list/detail permissions.

**Exit criteria (MET):**
- Approver sees approve/reject controls for own pending tasks
- Non-approver does not see controls
- Approve POST transitions to APPROVED when final approval
- Approve POST keeps REVIEWING when more approvals remain
- Reject POST requires comment and transitions to REJECTED
- Wrong `approval_task_id` from another request is rejected
- CSRF-bearing forms exist in template
- All Phase 3D-1 tests pass (Roo: 29/29 + 6/6 targeted; user runs full suite)

---

### Phase 3D-2: Assign/Claim UI

**Status:** COMPLETE

**Files changed:**
- `project_requests/forms.py` — add `AssignmentForm`
- `project_requests/views.py` — add `project_request_assign`, `project_request_claim`
- `project_requests/urls.py` — add assign/claim URL routes
- `project_requests/tests_views.py` — add `ProjectRequestAssignClaimViewTest`
- `templates/project_requests/projectrequest_detail.html` — add assignment form and claim button

**Implemented:**
- `AssignmentForm` — assignment form with dynamic `assigned_to` queryset filtering active users in project department
- `project_request_assign` view — POST-only, creates/replaces assignment, transitions APPROVED->ASSIGNED or ASSIGNED->ASSIGNED
- `project_request_claim` view — POST-only, allows staff to self-claim APPROVED requests
- Assign/claim URL routes (`/<int:pk>/assign/`, `/<int:pk>/claim/`)
- Assignment form gated by `action_context.can_assign`
- Claim button gated by `action_context.can_claim`

**Non-blocking hardening note:**
- `_build_detail_context()` used by attachment upload error re-render does not currently include `assignment_form` when `action_context.can_assign` is True. This can be addressed in Phase 3D-5 hardening or earlier if convenient.

**Tests to run:**
```bash
python manage.py test project_requests.tests_views.ProjectRequestAssignClaimViewTest
```
Plus targeted regression: approve/reject still works, attachment upload/download.

**Exit criteria (MET):**
- Project dept manager sees assignment form when `can_assign` is True
- Request dept manager alone does not see assignment form
- Assign POST creates assignment and transitions APPROVED -> ASSIGNED
- Reassign POST deactivates old assignment
- `assigned_to` queryset excludes inactive users and users outside project department
- Staff sees claim button when `can_claim` is True
- Claim POST transitions APPROVED -> ASSIGNED
- Staff does not see claim button for ASSIGNED
- Unauthorized POST fails
- All Phase 3D-2 tests pass (Roo: targeted tests only; user runs full suite)

---

### Phase 3D-3: Start/Hold/Resume/Complete UI

**Status:** COMPLETE (accepted)

---

### Phase 3D-4: Detail Template Integration and End-to-End Tests

**Status:** COMPLETE (accepted)

**Implemented:**
- `_build_detail_context()` includes `assignment_form` when `action_context.can_assign` is True
- Attachment upload error re-render context consistency
- `ProjectRequestWorkflowEndToEndTest` — end-to-end workflow coverage:
  - submit -> approve -> assign -> start -> complete
  - submit -> approve -> claim -> start -> hold -> resume -> complete
  - submit -> reject
  - reassign workflow
  - ON_HOLD cannot complete from UI
- `ProjectRequestDetailWorkflowIntegrationTest` — detail workflow integration coverage:
  - DRAFT shows no workflow controls
  - REVIEWING shows approve/reject only to valid approver
  - APPROVED shows assign/claim according to permissions
  - ASSIGNED shows start according to permissions
  - IN_PROGRESS shows hold/complete
  - ON_HOLD shows resume and not complete
  - COMPLETED shows no workflow controls
  - attachment.file.url is not exposed
  - POST forms include CSRF

**Phase 3D-4 Did NOT Implement:**
- dashboard
- model changes
- migration changes
- service-layer business logic changes
- new workflow routes/views
- FoxPro/external auth
- legacy migration

**Tests to run:**
```bash
python manage.py test project_requests.tests_views.ProjectRequestWorkflowEndToEndTest
python manage.py test project_requests.tests_views.ProjectRequestDetailWorkflowIntegrationTest
```
Plus targeted regression: all existing tests.

**Exit criteria (MET):**
- All workflow controls render correctly based on `action_context`
- End-to-end workflow test passes
- Error messages display correctly after failed actions
- All Phase 3D-4 tests pass (Roo: targeted tests only; user manually ran full test suite and confirmed it passed)

---

### Phase 3D-5: Hardening and Review

**Status:** COMPLETE — PASS

**Phase 3D-5A was read-only final hardening review. No code, templates, URLs, or migrations were modified.**

**Review verdict:** PASS

**Targeted review checks passed:**
- `manage.py check`: no issues
- `makemigrations --check --dry-run`: no changes detected
- ProjectRequestWorkflowEndToEndTest: 6 OK
- ProjectRequestDetailWorkflowIntegrationTest: 10 OK
- ProjectRequestApproveRejectViewTest: OK
- ProjectRequestAssignClaimViewTest: 36 OK
- ProjectRequestExecutionViewTest: 41 OK
- Total: 116 targeted tests OK

**User manually ran full test suite after Phase 3D-4 and confirmed it passed.**

**Review confirmed:**
- Views are thin wrappers around services
- No business logic duplication in views
- Template workflow controls are gated by action_context
- No direct attachment.file.url exposure
- CSRF and POST-only pattern are enforced
- URL scope is clean
- Tests are meaningful and use real POST routes
- No blockers

**Technical Debt / Future Cleanup (Non-Blocking, Not Required):**
- `views.py` module docstring says Phase 2B (stale)
- Some test names/comments are historically stale after later Phase 3D subphases
- Light test helper refactor could reduce duplication but is optional
- Extra black-box create-to-complete UI flow is not needed now

**Phase 3D is now complete. Phase 3 is complete.**

**Exit criteria (Met):**
- Targeted review checks passed
- Views confirmed as thin wrappers
- No business logic duplication
- No blockers

---

## 6. Tests Plan

### 6.1 Approve/Reject View Tests (`tests_views.py`)

```python
class ProjectRequestApproveRejectViewTest(TestCase):
    def setUp(self):
        # Fixtures: req_dept, proj_dept, ptype, requester, approver, unrelated
        ...

    # --- Visibility ---
    def test_approver_sees_approve_controls_for_own_pending_task(self):
        # Create REVIEWING request with pending task for approver
        # Login as approver
        # GET detail -> assert approve/reject forms present in content

    def test_non_approver_does_not_see_approve_controls(self):
        # Create REVIEWING request with pending task for approver
        # Login as unrelated user
        # GET detail -> assert approve/reject forms NOT in content

    def test_superuser_sees_approve_controls(self):
        # Create REVIEWING request with pending task
        # Login as superuser
        # GET detail -> assert approve/reject forms present

    # --- Approve POST ---
    def test_approve_post_transitions_to_approved_when_final_approval(self):
        # Create REVIEWING request with one pending task
        # POST to approve
        # Assert status == APPROVED
        # Assert activity log created

    def test_approve_post_keeps_reviewing_when_more_approvals_remain(self):
        # Create REVIEWING request with two pending tasks
        # POST to approve one task
        # Assert status == REVIEWING
        # Assert task status == APPROVED

    def test_approve_post_with_comment_saves_comment(self):
        # POST to approve with comment
        # Assert task.decision_comment == comment

    def test_approve_post_without_comment_is_allowed(self):
        # POST to approve without comment
        # Assert succeeds

    # --- Reject POST ---
    def test_reject_post_requires_comment(self):
        # POST to reject without comment
        # Assert form error or redirect with error message

    def test_reject_post_with_comment_transitions_to_rejected(self):
        # POST to reject with comment
        # Assert status == REJECTED
        # Assert activity log created

    def test_reject_post_saves_comment(self):
        # POST to reject with comment
        # Assert task.decision_comment == comment

    # --- Security ---
    def test_wrong_task_id_from_another_request_rejected(self):
        # Create two requests, each with a pending task
        # POST to approve request A using task ID from request B
        # Assert error message and no status change

    def test_unauthorized_post_returns_403_or_error(self):
        # Login as user without approval permission
        # POST to approve
        # Assert 403 or redirect with error message

    def test_csrf_bearing_forms_exist_in_template(self):
        # GET detail as approver
        # Assert 'csrfmiddlewaretoken' in content for approve form
        # Assert 'csrfmiddlewaretoken' in content for reject form

    def test_approve_post_login_required(self):
        # Logout
        # POST to approve
        # Assert redirect to login

    def test_reject_post_login_required(self):
        # Logout
        # POST to reject
        # Assert redirect to login
```

### 6.2 Assign/Claim View Tests (`tests_views.py`)

```python
class ProjectRequestAssignClaimViewTest(TestCase):
    def setUp(self):
        # Fixtures: req_dept, proj_dept, ptype, requester, proj_mgr, staff, unrelated
        ...

    # --- Assignment Form Visibility ---
    def test_project_dept_manager_sees_assignment_form_when_can_assign(self):
        # Create APPROVED request
        # Login as project dept manager
        # GET detail -> assert assignment form present

    def test_request_dept_manager_alone_does_not_see_assignment_form(self):
        # Create APPROVED request (cross-department)
        # Login as request dept manager (not project dept manager)
        # GET detail -> assert assignment form NOT present

    def test_superuser_sees_assignment_form(self):
        # Create APPROVED request
        # Login as superuser
        # GET detail -> assert assignment form present

    # --- Assign POST ---
    def test_assign_post_creates_assignment_and_transitions_approved_to_assigned(self):
        # Create APPROVED request
        # POST to assign to staff in project dept
        # Assert status == ASSIGNED
        # Assert assignment created with is_active=True

    def test_reassign_post_deactivates_old_assignment(self):
        # Create ASSIGNED request with active assignment
        # POST to reassign to different user
        # Assert old assignment is_active=False
        # Assert new assignment is_active=True

    def test_assign_post_to_inactive_user_fails(self):
        # POST to assign to inactive user
        # Assert error message

    def test_assign_post_to_user_outside_project_dept_fails(self):
        # POST to assign to user not in project dept
        # Assert error message

    def test_assign_post_requires_user_selection(self):
        # POST with empty assigned_to
        # Assert form error

    # --- Claim Visibility ---
    def test_staff_sees_claim_button_when_can_claim(self):
        # Create APPROVED request, no active assignment
        # Login as staff in project dept
        # GET detail -> assert claim button present

    def test_staff_does_not_see_claim_button_for_assigned(self):
        # Create ASSIGNED request
        # Login as staff in project dept
        # GET detail -> assert claim button NOT present

    def test_unrelated_staff_does_not_see_claim_button(self):
        # Create APPROVED request
        # Login as staff NOT in project dept
        # GET detail -> assert claim button NOT present

    # --- Claim POST ---
    def test_claim_post_transitions_approved_to_assigned(self):
        # Create APPROVED request, no active assignment
        # POST to claim
        # Assert status == ASSIGNED
        # Assert assignment created with assigned_to=actor

    def test_claim_post_on_already_assigned_fails(self):
        # Create ASSIGNED request
        # POST to claim
        # Assert error message

    def test_unauthorized_claim_post_fails(self):
        # Login as user without claim permission
        # POST to claim
        # Assert error message

    def test_csrf_bearing_forms_exist(self):
        # GET detail as project dept manager
        # Assert 'csrfmiddlewaretoken' in content for assign form
```

### 6.3 Execution View Tests (`tests_views.py`)

```python
class ProjectRequestExecutionViewTest(TestCase):
    def setUp(self):
        # Fixtures: req_dept, proj_dept, ptype, requester, assignee, proj_mgr, unrelated
        ...

    # --- Start Visibility ---
    def test_active_assignee_sees_start_button_when_assigned(self):
        # Create ASSIGNED request with active assignment to test user
        # Login as assignee
        # GET detail -> assert start button present

    def test_project_dept_manager_sees_start_button_when_assigned(self):
        # Create ASSIGNED request
        # Login as project dept manager
        # GET detail -> assert start button present

    def test_request_dept_manager_alone_does_not_see_start_button(self):
        # Create ASSIGNED request (cross-department)
        # Login as request dept manager (not project dept manager)
        # GET detail -> assert start button NOT present

    def test_no_start_button_for_in_progress(self):
        # Create IN_PROGRESS request
        # Login as assignee
        # GET detail -> assert start button NOT present

    # --- Start POST ---
    def test_start_post_transitions_assigned_to_in_progress(self):
        # Create ASSIGNED request
        # POST to start
        # Assert status == IN_PROGRESS
        # Assert started_at is set
        # Assert activity log created

    def test_start_post_without_comment_is_allowed(self):
        # POST to start without comment
        # Assert succeeds

    # --- Hold Visibility ---
    def test_active_assignee_sees_hold_form_when_in_progress(self):
        # Create IN_PROGRESS request
        # Login as assignee
        # GET detail -> assert hold form present

    def test_no_hold_form_for_assigned(self):
        # Create ASSIGNED request
        # Login as assignee
        # GET detail -> assert hold form NOT present

    # --- Hold POST ---
    def test_hold_post_requires_comment(self):
        # POST to hold without comment
        # Assert form error or error message

    def test_hold_post_with_comment_transitions_to_on_hold(self):
        # Create IN_PROGRESS request
        # POST to hold with comment
        # Assert status == ON_HOLD
        # Assert activity log with comment

    # --- Resume Visibility ---
    def test_active_assignee_sees_resume_button_when_on_hold(self):
        # Create ON_HOLD request
        # Login as assignee
        # GET detail -> assert resume button present

    def test_no_resume_button_for_in_progress(self):
        # Create IN_PROGRESS request
        # Login as assignee
        # GET detail -> assert resume button NOT present

    # --- Resume POST ---
    def test_resume_post_transitions_on_hold_to_in_progress(self):
        # Create ON_HOLD request
        # POST to resume
        # Assert status == IN_PROGRESS
        # Assert activity log created

    # --- Complete Visibility ---
    def test_active_assignee_sees_complete_button_when_in_progress(self):
        # Create IN_PROGRESS request
        # Login as assignee
        # GET detail -> assert complete button present

    def test_no_complete_button_for_on_hold(self):
        # Create ON_HOLD request
        # Login as assignee
        # GET detail -> assert complete button NOT present

    def test_no_complete_button_for_assigned(self):
        # Create ASSIGNED request
        # Login as assignee
        # GET detail -> assert complete button NOT present

    # --- Complete POST ---
    def test_complete_post_transitions_in_progress_to_completed(self):
        # Create IN_PROGRESS request
        # POST to complete
        # Assert status == COMPLETED
        # Assert completed_at is set
        # Assert activity log created

    def test_on_hold_cannot_complete_directly(self):
        # Create ON_HOLD request
        # POST to complete
        # Assert error message or 403

    # --- Security ---
    def test_no_active_assignment_means_no_execution_controls(self):
        # Create ASSIGNED request with no active assignment
        # Login as project dept manager
        # GET detail -> assert no execution controls present

    def test_unauthorized_start_post_fails(self):
        # Login as user without start permission
        # POST to start
        # Assert error message

    def test_unauthorized_hold_post_fails(self):
        # Login as user without hold permission
        # POST to hold
        # Assert error message

    def test_unauthorized_resume_post_fails(self):
        # Login as user without resume permission
        # POST to resume
        # Assert error message

    def test_unauthorized_complete_post_fails(self):
        # Login as user without complete permission
        # POST to complete
        # Assert error message

    def test_csrf_bearing_forms_exist(self):
        # GET detail as assignee
        # Assert 'csrfmiddlewaretoken' in content for start form
        # Assert 'csrfmiddlewaretoken' in content for hold form
        # Assert 'csrfmiddlewaretoken' in content for resume form
        # Assert 'csrfmiddlewaretoken' in content for complete form
```

### 6.4 End-to-End Workflow Tests (`tests_views.py`)

```python
class ProjectRequestWorkflowEndToEndTest(TestCase):
    def setUp(self):
        # Fixtures: req_dept, proj_dept, ptype, requester, approver, assignee
        ...

    def test_full_workflow_submit_approve_assign_start_complete(self):
        # 1. Create and submit draft
        # 2. Approve (single approver)
        # 3. Assert status == APPROVED
        # 4. Assign to assignee
        # 5. Assert status == ASSIGNED
        # 6. Start
        # 7. Assert status == IN_PROGRESS
        # 8. Complete
        # 9. Assert status == COMPLETED

    def test_full_workflow_submit_approve_claim_start_hold_resume_complete(self):
        # 1. Create and submit draft
        # 2. Approve
        # 3. Assert status == APPROVED
        # 4. Claim by staff
        # 5. Assert status == ASSIGNED
        # 6. Start
        # 7. Assert status == IN_PROGRESS
        # 8. Hold with comment
        # 9. Assert status == ON_HOLD
        # 10. Resume
        # 11. Assert status == IN_PROGRESS
        # 12. Complete
        # 13. Assert status == COMPLETED

    def test_reject_workflow(self):
        # 1. Create and submit draft
        # 2. Reject with comment
        # 3. Assert status == REJECTED
        # 4. Assert activity log has rejection comment

    def test_reassign_workflow(self):
        # 1. Create, submit, approve, assign to user A
        # 2. Reassign to user B
        # 3. Assert user A assignment is_active=False
        # 4. Assert user B assignment is_active=True
```

### 6.5 Regression Tests

```python
class Phase3DRegressionTest(TestCase):
    def test_attachment_upload_still_works(self):
        # Existing attachment upload test

    def test_attachment_download_still_works(self):
        # Existing attachment download test

    def test_list_view_permissions_still_work(self):
        # Existing list view permission tests

    def test_detail_view_permissions_still_work(self):
        # Existing detail view permission tests

    def test_no_direct_attachment_file_url_exposed(self):
        # Existing attachment URL test

    def test_phase_3a_service_tests_still_pass(self):
        # Run approve/reject service tests

    def test_phase_3b_service_tests_still_pass(self):
        # Run assign/claim service tests

    def test_phase_3c_service_tests_still_pass(self):
        # Run execution service tests
```

---

## 7. Risk Review

### Risk 1: Duplicating Service Logic in Views
**Severity:** High
**Mitigation:** All views are thin wrappers. They parse forms, call services, catch exceptions, and redirect. No business rules in views. Service layer is the single source of truth.

### Risk 2: Showing Buttons Based Only on Status
**Severity:** High
**Mitigation:** All template controls are gated by `action_context` flags from `get_project_request_action_context()`. No raw status checks in templates. Service layer permission helpers are the authority.

### Risk 3: Stale action_context After POST
**Severity:** Medium
**Mitigation:** After any POST action, the view redirects to the detail page. The detail view's GET handler re-computes `action_context` from the database, ensuring fresh permissions. No in-memory state carried across requests.

### Risk 4: Wrong approval_task_id
**Severity:** High
**Mitigation:** Views validate that `approval_task.project_request_id == project_request.pk` before calling the service. If validation fails, an error message is shown and the user is redirected. The service also validates this (defense-in-depth).

### Risk 5: Assignment Queryset Leaking Users from Other Departments
**Severity:** High
**Mitigation:** `AssignmentForm.__init__` receives `project_request` and filters the `assigned_to` queryset to only users with active `UserDepartment` membership in `project_request.project_department`. The service also validates this (defense-in-depth).

### Risk 6: UI Allowing ON_HOLD -> COMPLETED
**Severity:** High
**Mitigation:** Template only shows complete button when `action_context.can_complete` is True. `can_complete_project_request` only returns True when `status == IN_PROGRESS`. Service also validates status (defense-in-depth).

### Risk 7: Error Handling Pattern Inconsistency
**Severity:** Medium
**Mitigation:** All action views follow the same pattern: parse form, call service, catch `PermissionDenied` and `ValidationError`, use `messages.error()`, redirect to detail. Consistent with existing attachment upload error pattern.

### Risk 8: Large Phase 3D Task Becoming Too Big
**Severity:** Medium
**Mitigation:** Phase 3D is broken into 5 subphases (3D-1 through 3D-5), each with clear scope, exit criteria, and targeted tests. Each subphase is independently testable and reversible.

---

## 8. Recommendation

### Recommended Subphase Breakdown
1. **Phase 3D-1:** Approve/Reject UI (forms, views, URLs, template, tests)
2. **Phase 3D-2:** Assign/Claim UI (forms, views, URLs, template, tests)
3. **Phase 3D-3:** Start/Hold/Resume/Complete UI (forms, views, URLs, template, tests)
4. **Phase 3D-4:** Detail template integration and end-to-end workflow tests
5. **Phase 3D-5:** Hardening and review

### Files Likely Changed
- `project_requests/forms.py` — add 5 new forms
- `project_requests/views.py` — add 8 new action views
- `project_requests/urls.py` — add 8 new URL routes
- `project_requests/tests_views.py` — add ~50+ new view tests
- `templates/project_requests/projectrequest_detail.html` — add workflow action controls

### Exact First Implementation Subphase Recommendation
**Phase 3D-1: Approve/Reject UI**

Rationale:
- Approve/reject is the most security-sensitive workflow (affects request lifecycle)
- The approval task ID validation is the most complex view logic
- Starting with the most complex subphase first ensures the hardest problems are solved early
- Approve/reject has the clearest success criteria (status transitions, task state changes)
- Completing Phase 3D-1 first validates the view pattern before applying to other actions

### Blockers or Decisions Needed Before Coding
1. **None.** All service layer, permission helpers, and action context are complete and tested.
2. **Decision:** Should the hold form be a collapsible section or always visible? (Recommendation: always visible when `can_hold` is True, matching the pattern of other action forms)
3. **Decision:** Should the assignment form `assigned_to` dropdown show users sorted by `display_name` or `username`? (Recommendation: `display_name` with `username` fallback, matching existing template patterns)

### Targeted Tests for First Subphase (Phase 3D-1)
```bash
# Run Phase 3D-1 specific tests
python manage.py test project_requests.tests_views.ProjectRequestApproveRejectViewTest

# Run targeted regression
python manage.py test project_requests.tests_views.ProjectRequestDetailViewTest
python manage.py test project_requests.tests_views.ProjectRequestAttachmentUploadViewTest
python manage.py test project_requests.tests.ProjectRequestApprovalServiceTest
```

### Confirmations
- **No files were modified.** This is a planning document only.
- **No outside workspace files were read.** All work stayed within `C:/dev/MIS_PROJECT`.
- **No code was implemented.** This document contains design decisions and implementation guidance only.
- **No migrations were created.** No model changes are needed for Phase 3D.
- **No legacy_php files were modified.** Legacy PHP remains read-only reference.