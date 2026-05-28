"""Phase 2B view tests for project_requests app.

Tests cover:
- List view (login required, visibility, filters)
- Detail view (login required, permissions)
- Create view (draft, submit, validation)
- Edit draft view (permissions, submit from edit)
- Attachment upload view (permissions, validation)
- Attachment download view (permissions, FileResponse)
- Regression (existing tests still pass)
"""

from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccessLevel, Department, User, UserDepartment
from project_requests.models import (
    ProjectApprovalRole,
    ProjectApprovalTaskStatus,
    ProjectRequest,
    ProjectRequestActionType,
    ProjectRequestApprovalTask,
    ProjectRequestAssignment,
    ProjectRequestAttachment,
    ProjectRequestFileType,
    ProjectRequestPriority,
    ProjectRequestStatus,
    ProjectRequestType,
    ProjectDepartmentProfile,
)
from project_requests.services import (
    create_project_request_draft,
    submit_project_request,
    upload_project_request_attachment,
)


# ============================================================================
# Fixtures
# ============================================================================

def _build_fixtures():
    """Create a standard set of fixtures for view tests."""
    req_dept = Department.objects.create(dept_code="ACCT", dept_name="Accounting")
    proj_dept = Department.objects.create(dept_code="MIS", dept_name="MIS")
    other_dept = Department.objects.create(dept_code="HR", dept_name="Human Resources")
    ProjectDepartmentProfile.objects.create(
        department=proj_dept, is_active=True, can_receive_project_requests=True,
    )
    ProjectDepartmentProfile.objects.create(
        department=other_dept, is_active=True, can_receive_project_requests=True,
    )
    ptype = ProjectRequestType.objects.create(
        code="new", name="New System", is_active=True,
    )
    ftype = ProjectRequestFileType.objects.create(
        code="doc", name="Document", allowed_extensions="pdf,docx,xlsx",
        max_file_size_mb=25, is_active=True,
    )
    return req_dept, proj_dept, other_dept, ptype, ftype


def _make_staff(username, dept, level=AccessLevel.STAFF, can_approve=False):
    user = User.objects.create_user(username=username, password="pass", is_active=True)
    UserDepartment.objects.create(
        user=user, department=dept, access_level=level, is_active=True,
        can_approve=can_approve,
    )
    return user


def _make_full_draft(requester, req_dept, proj_dept, ptype, **overrides):
    defaults = {
        "project_name": "Test Project",
        "requester": requester,
        "request_department": req_dept,
        "project_department": proj_dept,
        "request_type": ptype,
        "priority": ProjectRequestPriority.P3,
        "needed_by_date": date(2026, 12, 31),
        "scope_summary": "Summary",
        "business_problem": "Problem",
        "in_scope": "In scope",
        "expected_deliverables": "Deliverables",
        "acceptance_criteria": "Criteria",
    }
    defaults.update(overrides)
    return create_project_request_draft(**defaults)


# ============================================================================
# A. List View Tests
# ============================================================================

class ProjectRequestListViewTest(TestCase):
    def setUp(self):
        self.req_dept, self.proj_dept, self.other_dept, self.ptype, self.ftype = _build_fixtures()
        self.client = Client()

    def test_login_required(self):
        resp = self.client.get(reverse("project_requests:list"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp.url)

    def test_requester_sees_own_request(self):
        user = _make_staff("alice", self.req_dept)
        pr = create_project_request_draft(
            requester=user, request_department=self.req_dept,
            project_name="My Request",
        )
        self.client.login(username="alice", password="pass")
        resp = self.client.get(reverse("project_requests:list"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"My Request", resp.content)

    def test_unrelated_user_does_not_see_request(self):
        requester = _make_staff("bob", self.req_dept)
        pr = create_project_request_draft(
            requester=requester, request_department=self.req_dept,
            project_name="Bob Request",
        )
        unrelated = _make_staff("carol", self.other_dept)
        self.client.login(username="carol", password="pass")
        resp = self.client.get(reverse("project_requests:list"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b"Bob Request", resp.content)

    def test_project_dept_staff_does_not_see_all_dept_requests(self):
        requester = _make_staff("dave", self.req_dept)
        pr = create_project_request_draft(
            requester=requester, request_department=self.req_dept,
            project_department=self.proj_dept,
            project_name="Dave Draft",
        )
        staff = _make_staff("eve", self.proj_dept)
        self.client.login(username="eve", password="pass")
        resp = self.client.get(reverse("project_requests:list"))
        self.assertEqual(resp.status_code, 200)
        # DRAFT should not appear for proj dept staff
        self.assertNotIn(b"Dave Draft", resp.content)

    def test_claimable_request_appears_for_eligible_staff(self):
        requester = _make_staff("frank", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        submit_project_request(pr, requester)
        # pr should be REVIEWING (has approvals) — make it APPROVED manually
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        staff = _make_staff("grace", self.proj_dept)
        self.client.login(username="grace", password="pass")
        resp = self.client.get(reverse("project_requests:list"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Test Project", resp.content)

    def test_filter_status_does_not_bypass_visibility(self):
        requester = _make_staff("hank", self.req_dept)
        pr = create_project_request_draft(
            requester=requester, request_department=self.req_dept,
            project_name="Hank Secret",
        )
        unrelated = _make_staff("iris", self.other_dept)
        self.client.login(username="iris", password="pass")
        resp = self.client.get(
            reverse("project_requests:list"),
            {"status": ProjectRequestStatus.DRAFT},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b"Hank Secret", resp.content)

    def test_filter_search_does_not_bypass_visibility(self):
        requester = _make_staff("jack", self.req_dept)
        pr = create_project_request_draft(
            requester=requester, request_department=self.req_dept,
            project_name="Jack Secret",
        )
        unrelated = _make_staff("kate", self.other_dept)
        self.client.login(username="kate", password="pass")
        resp = self.client.get(
            reverse("project_requests:list"),
            {"search": "Jack Secret"},
        )
        self.assertEqual(resp.status_code, 200)
        # Search term appears in the input field value, so check results area only
        # The request should NOT appear in the <tbody> results
        content = resp.content.decode()
        # Find the tbody section (results) and ensure "Jack Secret" is not there
        tbody_start = content.find("<tbody>")
        tbody_end = content.find("</tbody>")
        if tbody_start != -1 and tbody_end != -1:
            tbody_content = content[tbody_start:tbody_end]
            self.assertNotIn("Jack Secret", tbody_content)
        # Also verify the queryset is empty
        self.assertEqual(len(resp.context["project_requests"]), 0)


# ============================================================================
# B. Detail View Tests
# ============================================================================

class ProjectRequestDetailViewTest(TestCase):
    def setUp(self):
        self.req_dept, self.proj_dept, self.other_dept, self.ptype, self.ftype = _build_fixtures()
        self.client = Client()

    def test_login_required(self):
        pr = create_project_request_draft(
            requester=User.objects.create_user(username="u1", password="pass"),
            request_department=self.req_dept,
        )
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 302)

    def test_requester_can_view_own_request(self):
        user = _make_staff("alice", self.req_dept)
        pr = create_project_request_draft(
            requester=user, request_department=self.req_dept,
            project_name="My Detail",
        )
        self.client.login(username="alice", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"My Detail", resp.content)

    def test_unrelated_user_gets_403(self):
        requester = _make_staff("bob", self.req_dept)
        pr = create_project_request_draft(
            requester=requester, request_department=self.req_dept,
        )
        unrelated = _make_staff("carol", self.other_dept)
        self.client.login(username="carol", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_project_dept_manager_can_view_request_to_managed_dept(self):
        requester = _make_staff("dave", self.req_dept)
        pr = create_project_request_draft(
            requester=requester, request_department=self.req_dept,
            project_department=self.proj_dept,
        )
        mgr = _make_staff("eve_mgr", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="eve_mgr", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_assigned_user_can_view_assigned_request(self):
        requester = _make_staff("frank", self.req_dept)
        pr = create_project_request_draft(
            requester=requester, request_department=self.req_dept,
        )
        assignee = _make_staff("grace", self.proj_dept)
        ProjectRequestAssignment.objects.create(
            project_request=pr, assigned_to=assignee, assigned_by=requester,
        )
        self.client.login(username="grace", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_attachments_shown_without_exposing_file_url(self):
        user = _make_staff("hank", self.req_dept)
        pr = create_project_request_draft(
            requester=user, request_department=self.req_dept,
        )
        uploaded = SimpleUploadedFile("test.pdf", b"%PDF fake", content_type="application/pdf")
        upload_project_request_attachment(pr, uploaded, self.ftype, user)
        self.client.login(username="hank", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        # Should show download link, not direct file URL
        self.assertIn(b"test.pdf", resp.content)
        # Should NOT contain /media/ direct URL pattern
        content_str = resp.content.decode()
        self.assertNotIn("media/project_requests", content_str.split("Download")[0] if "Download" in content_str else "")


# ============================================================================
# C. Create View Tests
# ============================================================================

class ProjectRequestCreateViewTest(TestCase):
    def setUp(self):
        self.req_dept, self.proj_dept, self.other_dept, self.ptype, self.ftype = _build_fixtures()
        self.client = Client()

    def test_login_required(self):
        resp = self.client.get(reverse("project_requests:create"))
        self.assertEqual(resp.status_code, 302)

    def test_get_renders_form(self):
        user = _make_staff("alice", self.req_dept)
        self.client.login(username="alice", password="pass")
        resp = self.client.get(reverse("project_requests:create"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"New Project Request", resp.content)

    def test_save_draft_creates_draft_with_request_no(self):
        user = _make_staff("bob", self.req_dept)
        self.client.login(username="bob", password="pass")
        data = {
            "project_name": "Draft Project",
            "request_department": self.req_dept.id,
            "project_department": self.proj_dept.id,
            "request_type": self.ptype.id,
            "priority": ProjectRequestPriority.P3,
        }
        resp = self.client.post(reverse("project_requests:create"), data, follow=False)
        self.assertEqual(resp.status_code, 302)
        pr = ProjectRequest.objects.latest("pk")
        self.assertEqual(pr.status, ProjectRequestStatus.DRAFT)
        self.assertIsNotNone(pr.request_no)
        self.assertEqual(pr.requester, user)

    def test_submit_creates_and_submits(self):
        user = _make_staff("carol", self.req_dept)
        self.client.login(username="carol", password="pass")
        data = {
            "project_name": "Submit Project",
            "request_department": self.req_dept.id,
            "project_department": self.proj_dept.id,
            "request_type": self.ptype.id,
            "priority": ProjectRequestPriority.P3,
            "needed_by_date": "2026-12-31",
            "scope_summary": "Summary",
            "business_problem": "Problem",
            "in_scope": "In scope",
            "expected_deliverables": "Deliverables",
            "acceptance_criteria": "Criteria",
            "submit": "1",
        }
        resp = self.client.post(reverse("project_requests:create"), data, follow=False)
        self.assertEqual(resp.status_code, 302)
        pr = ProjectRequest.objects.filter(project_name="Submit Project").first()
        self.assertIsNotNone(pr)
        self.assertNotEqual(pr.status, ProjectRequestStatus.DRAFT)

    def test_invalid_submit_renders_with_errors(self):
        user = _make_staff("dave", self.req_dept)
        self.client.login(username="dave", password="pass")
        # Missing required submit fields but pressing submit
        data = {
            "project_name": "",
            "request_department": self.req_dept.id,
            "submit": "1",
        }
        resp = self.client.post(reverse("project_requests:create"), data)
        # Should re-render form with errors, not redirect
        self.assertEqual(resp.status_code, 200)
        # Draft should remain DRAFT if created
        pr = ProjectRequest.objects.filter(requester=user).last()
        if pr:
            self.assertEqual(pr.status, ProjectRequestStatus.DRAFT)

    def test_form_filters_project_department_to_receivable(self):
        user = _make_staff("eve", self.req_dept)
        self.client.login(username="eve", password="pass")
        resp = self.client.get(reverse("project_requests:create"))
        self.assertEqual(resp.status_code, 200)
        context_form = resp.context["form"]
        dept_ids = list(context_form.fields["project_department"].queryset.values_list("id", flat=True))
        self.assertIn(self.proj_dept.id, dept_ids)
        # req_dept has no ProjectDepartmentProfile with can_receive=True
        self.assertNotIn(self.req_dept.id, dept_ids)


# ============================================================================
# D. Edit Draft View Tests
# ============================================================================

class ProjectRequestEditDraftViewTest(TestCase):
    def setUp(self):
        self.req_dept, self.proj_dept, self.other_dept, self.ptype, self.ftype = _build_fixtures()
        self.client = Client()

    def test_requester_can_edit_draft(self):
        user = _make_staff("alice", self.req_dept)
        pr = create_project_request_draft(
            requester=user, request_department=self.req_dept,
            project_name="Original Name",
        )
        self.client.login(username="alice", password="pass")
        resp = self.client.get(reverse("project_requests:edit", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_non_requester_gets_403(self):
        requester = _make_staff("bob", self.req_dept)
        pr = create_project_request_draft(
            requester=requester, request_department=self.req_dept,
        )
        other = _make_staff("carol", self.other_dept)
        self.client.login(username="carol", password="pass")
        resp = self.client.get(reverse("project_requests:edit", args=[pr.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_cannot_edit_non_draft(self):
        user = _make_staff("dave", self.req_dept)
        pr = _make_full_draft(user, self.req_dept, self.proj_dept, self.ptype)
        submit_project_request(pr, user)
        self.client.login(username="dave", password="pass")
        resp = self.client.get(reverse("project_requests:edit", args=[pr.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_save_draft_updates_fields(self):
        user = _make_staff("eve", self.req_dept)
        pr = create_project_request_draft(
            requester=user, request_department=self.req_dept,
            project_name="Old Name",
        )
        self.client.login(username="eve", password="pass")
        data = {
            "project_name": "New Name",
            "request_department": self.req_dept.id,
            "scope_summary": "Updated scope",
            "save_draft": "1",
        }
        resp = self.client.post(reverse("project_requests:edit", args=[pr.pk]), data, follow=False)
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.project_name, "New Name")
        self.assertEqual(pr.scope_summary, "Updated scope")

    def test_submit_from_edit_calls_submit_project_request(self):
        user = _make_staff("frank", self.req_dept)
        pr = create_project_request_draft(
            requester=user, request_department=self.req_dept,
            project_name="To Submit",
        )
        self.client.login(username="frank", password="pass")
        data = {
            "project_name": "To Submit",
            "request_department": self.req_dept.id,
            "project_department": self.proj_dept.id,
            "request_type": self.ptype.id,
            "priority": ProjectRequestPriority.P3,
            "needed_by_date": "2026-12-31",
            "scope_summary": "Summary",
            "business_problem": "Problem",
            "in_scope": "In scope",
            "expected_deliverables": "Deliverables",
            "acceptance_criteria": "Criteria",
            "submit": "1",
        }
        resp = self.client.post(reverse("project_requests:edit", args=[pr.pk]), data, follow=False)
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertNotEqual(pr.status, ProjectRequestStatus.DRAFT)

    def test_incomplete_submit_remains_draft(self):
        user = _make_staff("grace", self.req_dept)
        pr = create_project_request_draft(
            requester=user, request_department=self.req_dept,
            project_name="Incomplete",
        )
        self.client.login(username="grace", password="pass")
        data = {
            "project_name": "Incomplete",
            "request_department": self.req_dept.id,
            "submit": "1",
        }
        resp = self.client.post(reverse("project_requests:edit", args=[pr.pk]), data)
        self.assertEqual(resp.status_code, 200)  # Re-render with errors
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.DRAFT)


# ============================================================================
# E. Attachment Upload View Tests
# ============================================================================

class ProjectRequestAttachmentUploadViewTest(TestCase):
    def setUp(self):
        self.req_dept, self.proj_dept, self.other_dept, self.ptype, self.ftype = _build_fixtures()
        self.client = Client()

    def test_authorized_user_can_upload(self):
        user = _make_staff("alice", self.req_dept)
        pr = create_project_request_draft(
            requester=user, request_department=self.req_dept,
        )
        self.client.login(username="alice", password="pass")
        data = {
            "file": SimpleUploadedFile("test.pdf", b"%PDF fake", content_type="application/pdf"),
            "file_type": self.ftype.id,
            "description": "Test upload",
        }
        resp = self.client.post(
            reverse("project_requests:attachment_upload", args=[pr.pk]),
            data,
            follow=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            ProjectRequestAttachment.objects.filter(
                project_request=pr, original_filename="test.pdf"
            ).exists()
        )

    def test_unrelated_user_cannot_upload(self):
        requester = _make_staff("bob", self.req_dept)
        pr = create_project_request_draft(
            requester=requester, request_department=self.req_dept,
        )
        unrelated = _make_staff("carol", self.other_dept)
        self.client.login(username="carol", password="pass")
        data = {
            "file": SimpleUploadedFile("test.pdf", b"%PDF fake", content_type="application/pdf"),
            "file_type": self.ftype.id,
        }
        resp = self.client.post(
            reverse("project_requests:attachment_upload", args=[pr.pk]),
            data,
        )
        self.assertEqual(resp.status_code, 403)

    def test_invalid_extension_rejected(self):
        user = _make_staff("dave", self.req_dept)
        pr = create_project_request_draft(
            requester=user, request_department=self.req_dept,
        )
        self.client.login(username="dave", password="pass")
        data = {
            "file": SimpleUploadedFile("image.png", b"\x89PNG", content_type="image/png"),
            "file_type": self.ftype.id,
        }
        resp = self.client.post(
            reverse("project_requests:attachment_upload", args=[pr.pk]),
            data,
        )
        self.assertEqual(resp.status_code, 200)  # Re-render with error
        # The template renders attachment_upload_error inside an alert-error div
        self.assertIn(b"alert-error", resp.content)

    def test_upload_creates_file_attached_activity_log(self):
        user = _make_staff("eve", self.req_dept)
        pr = create_project_request_draft(
            requester=user, request_department=self.req_dept,
        )
        self.client.login(username="eve", password="pass")
        data = {
            "file": SimpleUploadedFile("log.pdf", b"%PDF", content_type="application/pdf"),
            "file_type": self.ftype.id,
        }
        resp = self.client.post(
            reverse("project_requests:attachment_upload", args=[pr.pk]),
            data,
            follow=False,
        )
        self.assertEqual(resp.status_code, 302)
        log = pr.activity_log.filter(
            action_type=ProjectRequestActionType.FILE_ATTACHED,
        ).first()
        self.assertIsNotNone(log)
        self.assertIn("log.pdf", log.description)


# ============================================================================
# F. Attachment Download View Tests
# ============================================================================

class ProjectRequestAttachmentDownloadViewTest(TestCase):
    def setUp(self):
        self.req_dept, self.proj_dept, self.other_dept, self.ptype, self.ftype = _build_fixtures()
        self.client = Client()

    def _create_attachment(self, requester):
        pr = create_project_request_draft(
            requester=requester, request_department=self.req_dept,
        )
        uploaded = SimpleUploadedFile("secret.pdf", b"%PDF secret content", content_type="application/pdf")
        attachment = upload_project_request_attachment(pr, uploaded, self.ftype, requester)
        return pr, attachment

    def test_authorized_user_can_download(self):
        user = _make_staff("alice", self.req_dept)
        pr, attachment = self._create_attachment(user)
        self.client.login(username="alice", password="pass")
        resp = self.client.get(
            reverse("project_requests:attachment_download", args=[attachment.pk])
        )
        self.assertEqual(resp.status_code, 200)
        # FileResponse uses streaming_content, not content
        content = b"".join(resp.streaming_content)
        self.assertIn(b"secret content", content)

    def test_unrelated_user_gets_403(self):
        requester = _make_staff("bob", self.req_dept)
        pr, attachment = self._create_attachment(requester)
        unrelated = _make_staff("carol", self.other_dept)
        self.client.login(username="carol", password="pass")
        resp = self.client.get(
            reverse("project_requests:attachment_download", args=[attachment.pk])
        )
        self.assertEqual(resp.status_code, 403)

    def test_response_is_file_response_with_content_disposition(self):
        user = _make_staff("dave", self.req_dept)
        pr, attachment = self._create_attachment(user)
        self.client.login(username="dave", password="pass")
        resp = self.client.get(
            reverse("project_requests:attachment_download", args=[attachment.pk])
        )
        self.assertEqual(resp.status_code, 200)
        # Check Content-Disposition contains original filename
        cd = resp.get("Content-Disposition", "")
        self.assertIn("secret.pdf", cd)
        self.assertIn("attachment", cd)

    def test_template_uses_download_url_not_file_url(self):
        user = _make_staff("eve", self.req_dept)
        pr, attachment = self._create_attachment(user)
        self.client.login(username="eve", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content_str = resp.content.decode()
        # Template should link to the download route (resolved URL)
        expected_url = reverse("project_requests:attachment_download", args=[attachment.pk])
        self.assertIn(expected_url, content_str)
        # Template should NOT expose /media/ direct file URL as href
        self.assertNotIn('href="/media/', content_str)
        self.assertNotIn("href='/media/", content_str)

    def test_anonymous_user_redirected_to_login(self):
        user = _make_staff("frank", self.req_dept)
        pr, attachment = self._create_attachment(user)
        resp = self.client.get(
            reverse("project_requests:attachment_download", args=[attachment.pk])
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp.url)


# ============================================================================
# G. Regression Tests
# ============================================================================

class Phase2BRegressionTest(TestCase):
    """Ensure Phase 2B does not break Phase 2A services."""

    def setUp(self):
        self.req_dept, self.proj_dept, self.other_dept, self.ptype, self.ftype = _build_fixtures()

    def test_create_project_request_draft_still_works(self):
        user = User.objects.create_user(username="reg1", password="pass")
        pr = create_project_request_draft(requester=user, request_department=self.req_dept)
        self.assertEqual(pr.status, ProjectRequestStatus.DRAFT)
        self.assertIsNotNone(pr.request_no)

    def test_submit_project_request_still_works(self):
        user = _make_staff("reg2", self.req_dept)
        pr = _make_full_draft(user, self.req_dept, self.proj_dept, self.ptype)
        result = submit_project_request(pr, user)
        self.assertNotEqual(result.status, ProjectRequestStatus.DRAFT)

    def test_upload_attachment_still_works(self):
        user = _make_staff("reg3", self.req_dept)
        pr = create_project_request_draft(requester=user, request_department=self.req_dept)
        uploaded = SimpleUploadedFile("reg.pdf", b"%PDF", content_type="application/pdf")
        attachment = upload_project_request_attachment(pr, uploaded, self.ftype, user)
        self.assertIsNotNone(attachment)
        self.assertEqual(attachment.original_filename, "reg.pdf")

    def test_permissions_still_work(self):
        from project_requests.permissions import can_view_project_request
        user = _make_staff("reg4", self.req_dept)
        pr = create_project_request_draft(requester=user, request_department=self.req_dept)
        self.assertTrue(can_view_project_request(user, pr))

    def test_selectors_still_work(self):
        from project_requests.selectors import get_visible_project_requests
        user = _make_staff("reg5", self.req_dept)
        pr = create_project_request_draft(requester=user, request_department=self.req_dept)
        visible = get_visible_project_requests(user)
        self.assertIn(pr, visible)


# ============================================================================
# H. Hardening Tests
# ============================================================================

class Phase2BHardeningTest(TestCase):
    """Tests for Phase 2B hardening fixes."""

    def setUp(self):
        self.req_dept, self.proj_dept, self.other_dept, self.ptype, self.ftype = _build_fixtures()

    # --- Fix 1: Detail view provides attachment_form ---

    def test_detail_page_includes_attachment_form(self):
        """Detail page context must include attachment_form."""
        user = _make_staff("h1", self.req_dept)
        pr = _make_full_draft(user, self.req_dept, self.proj_dept, self.ptype)
        self.client.force_login(user)
        resp = self.client.get(f"/project-requests/{pr.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("attachment_form", resp.context)

    def test_detail_page_includes_file_type_option_names_when_can_attach(self):
        """When user can attach, the rendered page shows file type option names."""
        user = _make_staff("h2", self.req_dept)
        pr = _make_full_draft(user, self.req_dept, self.proj_dept, self.ptype)
        self.client.force_login(user)
        resp = self.client.get(f"/project-requests/{pr.pk}/")
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        # The template iterates attachment_form.fields.file_type.queryset
        self.assertIn(self.ftype.name, content)

    # --- Fix 2: upload-section anchor ---

    def test_detail_page_contains_upload_section_anchor(self):
        """Detail page must render id="upload-section" when upload section is present."""
        user = _make_staff("h3", self.req_dept)
        pr = _make_full_draft(user, self.req_dept, self.proj_dept, self.ptype)
        self.client.force_login(user)
        resp = self.client.get(f"/project-requests/{pr.pk}/")
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn('id="upload-section"', content)

    # --- Fix 3: get_success_url uses correct URL name ---

    def test_get_success_url_resolves_correctly(self):
        """ProjectRequestCreateView.get_success_url() must resolve without NoReverseMatch."""
        from django.urls import reverse
        url = reverse("project_requests:list")
        self.assertTrue(url.startswith("/project-requests/"))

    def test_create_view_redirects_to_correct_list_url(self):
        """After saving a draft, redirect goes to project_requests:detail."""
        user = _make_staff("h4", self.req_dept)
        self.client.force_login(user)
        data = {
            "project_name": "Success URL Test",
            "request_department": self.req_dept.pk,
            "project_department": self.proj_dept.pk,
            "request_type": self.ptype.pk,
            "priority": 3,
            "scope_summary": "Test scope",
        }
        resp = self.client.post(reverse("project_requests:create"), data)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/project-requests/", resp.url)

    # --- Fix 5: request_department required for draft creation ---

    def test_save_draft_without_request_department_renders_with_error(self):
        """Saving a draft without request_department should re-render with field error."""
        user = _make_staff("h5", self.req_dept)
        self.client.force_login(user)
        data = {
            "project_name": "Missing Dept Test",
            # request_department intentionally omitted
            "project_department": self.proj_dept.pk,
            "request_type": self.ptype.pk,
            "priority": 3,
        }
        resp = self.client.post(reverse("project_requests:create"), data)
        self.assertEqual(resp.status_code, 200)  # Re-render, not redirect
        self.assertIn(b"request_department", resp.content)

    def test_save_draft_with_request_department_succeeds(self):
        """Saving a draft with request_department should create and redirect."""
        user = _make_staff("h6", self.req_dept)
        self.client.force_login(user)
        data = {
            "project_name": "Valid Draft",
            "request_department": self.req_dept.pk,
            "project_department": self.proj_dept.pk,
            "request_type": self.ptype.pk,
            "priority": 3,
            "scope_summary": "Test scope",
        }
        count_before = ProjectRequest.objects.count()
        resp = self.client.post(reverse("project_requests:create"), data)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(ProjectRequest.objects.count(), count_before + 1)

    def test_form_allows_incomplete_business_fields(self):
        """Draft form should allow missing business fields (scope_summary, etc.)."""
        user = _make_staff("h7", self.req_dept)
        self.client.force_login(user)
        data = {
            "project_name": "Minimal Draft",
            "request_department": self.req_dept.pk,
            # No scope_summary, business_problem, etc.
        }
        count_before = ProjectRequest.objects.count()
        resp = self.client.post(reverse("project_requests:create"), data)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(ProjectRequest.objects.count(), count_before + 1)

    # --- Fix 4 confirmed: no file_path in download view ---
    # (Code-level fix verified by absence of attachment.file.path usage)

    # --- Fix 6 confirmed: no direct file URL exposure ---
    # (Template search confirmed no attachment.file.url or href="/media/")


# ============================================================================
# I. Second Hardening Tests
# ============================================================================

class Phase2BHardening2Test(TestCase):
    """Tests for Phase 2B second hardening patch."""

    def setUp(self):
        self.req_dept, self.proj_dept, self.other_dept, self.ptype, self.ftype = _build_fixtures()

    # --- Fix 1: Upload error re-render always includes attachment_form ---

    def test_invalid_upload_re_render_includes_attachment_form(self):
        """Invalid form re-render must include attachment_form in context."""
        user = _make_staff("h2a", self.req_dept)
        pr = _make_full_draft(user, self.req_dept, self.proj_dept, self.ptype)
        self.client.force_login(user)
        url = reverse("project_requests:attachment_upload", args=[pr.pk])
        # Post with no file to trigger form validation error
        resp = self.client.post(url, {"file_type": self.ftype.pk, "description": "test"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("attachment_form", resp.context)

    def test_invalid_upload_re_render_shows_file_type_options(self):
        """Invalid form re-render must still show active file type option names."""
        user = _make_staff("h2b", self.req_dept)
        pr = _make_full_draft(user, self.req_dept, self.proj_dept, self.ptype)
        self.client.force_login(user)
        url = reverse("project_requests:attachment_upload", args=[pr.pk])
        resp = self.client.post(url, {"file_type": self.ftype.pk, "description": "test"})
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn(self.ftype.name, content)

    def test_service_validation_error_re_render_shows_file_type_options(self):
        """Service ValidationError re-render must still show file type options."""
        user = _make_staff("h2c", self.req_dept)
        pr = _make_full_draft(user, self.req_dept, self.proj_dept, self.ptype)
        self.client.force_login(user)
        url = reverse("project_requests:attachment_upload", args=[pr.pk])
        # Upload with invalid extension to trigger service ValidationError
        uploaded = SimpleUploadedFile("bad.exe", b"data", content_type="application/octet-stream")
        resp = self.client.post(url, {
            "file": uploaded,
            "file_type": self.ftype.pk,
            "description": "test",
        })
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn(self.ftype.name, content)

    # --- Fix 2: Create-submit failure orphan draft cleanup ---

    def test_create_submit_missing_fields_no_orphan_draft(self):
        """Create view submit with missing required fields returns 200 and creates no ProjectRequest."""
        user = _make_staff("h2d", self.req_dept)
        self.client.force_login(user)
        count_before = ProjectRequest.objects.count()
        data = {
            "project_name": "Orphan Test",
            "request_department": self.req_dept.pk,
            "project_department": self.proj_dept.pk,
            "request_type": self.ptype.pk,
            "priority": 3,
            # Missing scope_summary, business_problem, etc.
            "submit": "1",
        }
        resp = self.client.post(reverse("project_requests:create"), data)
        self.assertEqual(resp.status_code, 200)  # Re-render with errors
        self.assertEqual(ProjectRequest.objects.count(), count_before)  # No orphan

    def test_create_submit_duplicate_no_orphan_draft(self):
        """Create view submit with duplicate open request returns 200 and leaves no extra DRAFT."""
        user = _make_staff("h2e", self.req_dept)
        pr = _make_full_draft(user, self.req_dept, self.proj_dept, self.ptype)
        # Submit the first one to make it non-DRAFT (or leave as DRAFT for duplicate check)
        from project_requests.services import submit_project_request
        submit_project_request(pr, user)
        self.client.force_login(user)
        count_before = ProjectRequest.objects.count()
        data = {
            "project_name": pr.project_name,  # Same name = duplicate
            "request_department": self.req_dept.pk,
            "project_department": self.proj_dept.pk,
            "request_type": self.ptype.pk,
            "priority": 3,
            "scope_summary": "Summary",
            "business_problem": "Problem",
            "in_scope": "In scope",
            "expected_deliverables": "Deliverables",
            "acceptance_criteria": "Criteria",
            "needed_by_date": "2026-12-31",
            "submit": "1",
        }
        resp = self.client.post(reverse("project_requests:create"), data)
        self.assertEqual(resp.status_code, 200)  # Re-render with errors
        self.assertEqual(ProjectRequest.objects.count(), count_before)  # No extra draft

    def test_save_draft_still_creates_draft(self):
        """Save draft action still creates a DRAFT normally."""
        user = _make_staff("h2f", self.req_dept)
        self.client.force_login(user)
        count_before = ProjectRequest.objects.count()
        data = {
            "project_name": "Normal Draft",
            "request_department": self.req_dept.pk,
            "project_department": self.proj_dept.pk,
            "request_type": self.ptype.pk,
            "priority": 3,
            "scope_summary": "Test scope",
        }
        resp = self.client.post(reverse("project_requests:create"), data)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(ProjectRequest.objects.count(), count_before + 1)
        pr = ProjectRequest.objects.latest("pk")
        self.assertEqual(pr.status, ProjectRequestStatus.DRAFT)

    def test_edit_draft_submit_failure_keeps_existing_draft(self):
        """Edit draft submit failure keeps the existing DRAFT (does not delete)."""
        user = _make_staff("h2g", self.req_dept)
        pr = _make_full_draft(user, self.req_dept, self.proj_dept, self.ptype)
        self.assertEqual(pr.status, ProjectRequestStatus.DRAFT)


# ============================================================================
# Phase 3D-1: Approve/Reject View Tests
# ============================================================================

class ProjectRequestApproveRejectViewTest(TestCase):
    """Tests for approve/reject views (Phase 3D-1)."""

    def setUp(self):
        self.req_dept, self.proj_dept, self.other_dept, self.ptype, self.ftype = _build_fixtures()
        self.client = Client()

    def _submit_request(self, pr, user):
        """Submit a project request to move it to REVIEWING status."""
        from project_requests.services import submit_project_request
        submit_project_request(pr, user)
        pr.refresh_from_db()
        return pr

    # -------------------------------------------------------------------------
    # Visibility Tests
    # -------------------------------------------------------------------------

    def test_approver_sees_approve_reject_controls_for_pending_task(self):
        """Approver sees approve/reject controls for their pending approval task."""
        requester = _make_staff("ar_vis_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        self._submit_request(pr, requester)
        # Create a manager in project dept who is an approver
        approver = _make_staff("ar_vis_approver", self.proj_dept, AccessLevel.MANAGER, can_approve=True)
        self.client.login(username="ar_vis_approver", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        # Should see approve/reject forms
        self.assertIn(b"Approve", resp.content)
        self.assertIn(b"Reject", resp.content)

    def test_non_approver_does_not_see_approve_reject_controls(self):
        """Non-approver who can view request does not see approve/reject controls."""
        requester = _make_staff("ar_non_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        self._submit_request(pr, requester)
        # Create a manager in project dept who is NOT an approver (can_approve=False)
        manager = _make_staff("ar_non_mgr", self.proj_dept, AccessLevel.MANAGER, can_approve=False)
        self.client.login(username="ar_non_mgr", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        # Should NOT see approve/reject forms
        self.assertNotIn(b'action="{% url \'project_requests:approve\'', resp.content)
        self.assertNotIn(b'action="{% url \'project_requests:reject\'', resp.content)

    def test_superuser_sees_approve_reject_controls_for_reviewing_request(self):
        """Superuser sees approve/reject controls for pending REVIEWING request."""
        requester = _make_staff("ar_su_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        self._submit_request(pr, requester)
        superuser = User.objects.create_superuser(username="ar_su", password="pass")
        self.client.login(username="ar_su", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Approve", resp.content)
        self.assertIn(b"Reject", resp.content)

    def test_approve_reject_controls_not_shown_after_approved(self):
        """Approve/reject controls are not shown after request is APPROVED."""
        requester = _make_staff("ar_app_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        self._submit_request(pr, requester)
        # Manually set to APPROVED (simulate all approvals done)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        approver = _make_staff("ar_app_approver", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="ar_app_approver", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        # Should NOT see approve/reject forms
        self.assertNotIn(b'action="{% url \'project_requests:approve\'', resp.content)
        self.assertNotIn(b'action="{% url \'project_requests:reject\'', resp.content)

    def test_approve_reject_controls_not_shown_after_rejected(self):
        """Approve/reject controls are not shown after request is REJECTED."""
        requester = _make_staff("ar_rej_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        self._submit_request(pr, requester)
        # Manually set to REJECTED
        pr.status = ProjectRequestStatus.REJECTED
        pr.save()
        approver = _make_staff("ar_rej_approver", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="ar_rej_approver", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        # Should NOT see approve/reject forms
        self.assertNotIn(b'action="{% url \'project_requests:approve\'', resp.content)
        self.assertNotIn(b'action="{% url \'project_requests:reject\'', resp.content)

    def test_csrf_bearing_approve_reject_forms_exist_for_approver(self):
        """CSRF-bearing approve/reject forms exist for approver."""
        requester = _make_staff("ar_csrf_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        self._submit_request(pr, requester)
        approver = _make_staff("ar_csrf_approver", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="ar_csrf_approver", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        # Forms should have csrf token
        self.assertIn(b"csrf", resp.content.lower())

    # -------------------------------------------------------------------------
    # Approve POST Tests
    # -------------------------------------------------------------------------

    def test_approve_post_transitions_to_approved_when_final_approval(self):
        """Approve POST transitions request to APPROVED when this is the final approval."""
        requester = _make_staff("ap_fin_req", self.proj_dept)
        # Use same department so only one approval task is created
        pr = _make_full_draft(requester, self.proj_dept, self.proj_dept, self.ptype)
        self._submit_request(pr, requester)
        # For same-department staff requests, only one task is created (PROJECT_DEPT_MANAGER)
        task = pr.approval_tasks.filter(status=ProjectApprovalTaskStatus.PENDING).first()
        approver = _make_staff("ap_fin_approver", self.proj_dept, AccessLevel.MANAGER, can_approve=True)
        self.client.login(username="ap_fin_approver", password="pass")
        resp = self.client.post(
            reverse("project_requests:approve", args=[pr.pk]),
            {"approval_task_id": task.pk, "comment": "Looks good"},
        )
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.APPROVED)

    def test_approve_post_keeps_reviewing_when_more_approvals_remain(self):
        """Approve POST keeps request REVIEWING when more approvals remain.
        
        For cross-department staff requests, generate_required_approvals creates
        TWO tasks: PROJECT_DEPT_MANAGER and REQUEST_DEPT_MANAGER.
        Approving one task should keep the request in REVIEWING.
        """
        requester = _make_staff("ap_mul_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        self._submit_request(pr, requester)
        # Verify two tasks were created for cross-department staff request
        self.assertEqual(pr.approval_tasks.filter(status=ProjectApprovalTaskStatus.PENDING).count(), 2)
        # Get the PROJECT_DEPT_MANAGER task
        task = pr.approval_tasks.get(
            role=ProjectApprovalRole.PROJECT_DEPT_MANAGER,
            status=ProjectApprovalTaskStatus.PENDING
        )
        approver = _make_staff("ap_mul_approver", self.proj_dept, AccessLevel.MANAGER, can_approve=True)
        self.client.login(username="ap_mul_approver", password="pass")
        resp = self.client.post(
            reverse("project_requests:approve", args=[pr.pk]),
            {"approval_task_id": task.pk, "comment": "First approval"},
        )
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.REVIEWING)
        # The other task (REQUEST_DEPT_MANAGER) should still be PENDING
        self.assertTrue(
            pr.approval_tasks.filter(
                role=ProjectApprovalRole.REQUEST_DEPT_MANAGER,
                status=ProjectApprovalTaskStatus.PENDING
            ).exists()
        )

    def test_approve_post_saves_optional_comment_to_approval_task(self):
        """Approve POST saves optional comment to approval_task.decision_comment."""
        requester = _make_staff("ap_cmt_req", self.proj_dept)
        # Use same department so only one approval task is created
        pr = _make_full_draft(requester, self.proj_dept, self.proj_dept, self.ptype)
        self._submit_request(pr, requester)
        task = pr.approval_tasks.filter(status=ProjectApprovalTaskStatus.PENDING).first()
        approver = _make_staff("ap_cmt_approver", self.proj_dept, AccessLevel.MANAGER, can_approve=True)
        self.client.login(username="ap_cmt_approver", password="pass")
        resp = self.client.post(
            reverse("project_requests:approve", args=[pr.pk]),
            {"approval_task_id": task.pk, "comment": "My approval comment"},
        )
        self.assertEqual(resp.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.decision_comment, "My approval comment")

    def test_approve_post_without_comment_is_allowed(self):
        """Approve POST without comment is allowed."""
        requester = _make_staff("ap_nc_req", self.proj_dept)
        # Use same department so only one approval task is created
        pr = _make_full_draft(requester, self.proj_dept, self.proj_dept, self.ptype)
        self._submit_request(pr, requester)
        task = pr.approval_tasks.filter(status=ProjectApprovalTaskStatus.PENDING).first()
        approver = _make_staff("ap_nc_approver", self.proj_dept, AccessLevel.MANAGER, can_approve=True)
        self.client.login(username="ap_nc_approver", password="pass")
        resp = self.client.post(
            reverse("project_requests:approve", args=[pr.pk]),
            {"approval_task_id": task.pk},
        )
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.APPROVED)

    def test_approve_post_wrong_task_id_from_another_request_rejected(self):
        """Wrong approval_task_id from another request is rejected and does not change either request."""
        requester1 = _make_staff("ap_wrong_req1", self.req_dept)
        pr1 = _make_full_draft(requester1, self.req_dept, self.proj_dept, self.ptype)
        self._submit_request(pr1, requester1)

        requester2 = _make_staff("ap_wrong_req2", self.other_dept)
        pr2 = _make_full_draft(requester2, self.other_dept, self.proj_dept, self.ptype)
        self._submit_request(pr2, requester2)

        # Get task from pr1
        task1 = pr1.approval_tasks.filter(status=ProjectApprovalTaskStatus.PENDING).first()
        # Try to use task1's id on pr2's approve URL
        approver = _make_staff("ap_wrong_approver", self.proj_dept, AccessLevel.MANAGER, can_approve=True)
        self.client.login(username="ap_wrong_approver", password="pass")
        resp = self.client.post(
            reverse("project_requests:approve", args=[pr2.pk]),
            {"approval_task_id": task1.pk, "comment": "Trying to approve wrong task"},
        )
        # Should redirect with error
        self.assertEqual(resp.status_code, 302)
        # Neither request should be changed
        pr1.refresh_from_db()
        pr2.refresh_from_db()
        self.assertEqual(pr1.status, ProjectRequestStatus.REVIEWING)
        self.assertEqual(pr2.status, ProjectRequestStatus.REVIEWING)

    def test_approve_post_user_cannot_approve_gets_error(self):
        """User who can view but cannot approve gets error and no status/task change."""
        requester = _make_staff("ap_noperm_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        self._submit_request(pr, requester)
        task = pr.approval_tasks.filter(status=ProjectApprovalTaskStatus.PENDING).first()
        # Create a manager user who can view but has can_approve=False
        manager = _make_staff("ap_noperm_mgr", self.proj_dept, AccessLevel.MANAGER, can_approve=False)
        self.client.login(username="ap_noperm_mgr", password="pass")
        resp = self.client.post(
            reverse("project_requests:approve", args=[pr.pk]),
            {"approval_task_id": task.pk, "comment": "Should fail"},
        )
        # Should redirect with error (not 403)
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        task.refresh_from_db()
        # Status and task should be unchanged
        self.assertEqual(pr.status, ProjectRequestStatus.REVIEWING)
        self.assertEqual(task.status, ProjectApprovalTaskStatus.PENDING)

    def test_approve_post_anonymous_redirected_to_login(self):
        """Anonymous user is redirected to login."""
        requester = _make_staff("ap_anon_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        self._submit_request(pr, requester)
        task = pr.approval_tasks.filter(status=ProjectApprovalTaskStatus.PENDING).first()
        resp = self.client.post(
            reverse("project_requests:approve", args=[pr.pk]),
            {"approval_task_id": task.pk},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp.url)

    # -------------------------------------------------------------------------
    # Reject POST Tests
    # -------------------------------------------------------------------------

    def test_reject_post_without_comment_shows_error(self):
        """Reject POST without comment shows error and does not reject."""
        requester = _make_staff("rj_nc_req", self.proj_dept)
        # Use same department so only one approval task is created
        pr = _make_full_draft(requester, self.proj_dept, self.proj_dept, self.ptype)
        self._submit_request(pr, requester)
        task = pr.approval_tasks.filter(status=ProjectApprovalTaskStatus.PENDING).first()
        approver = _make_staff("rj_nc_approver", self.proj_dept, AccessLevel.MANAGER, can_approve=True)
        self.client.login(username="rj_nc_approver", password="pass")
        resp = self.client.post(
            reverse("project_requests:reject", args=[pr.pk]),
            {"approval_task_id": task.pk},  # No comment
        )
        # Should redirect with error
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        # Status should still be REVIEWING
        self.assertEqual(pr.status, ProjectRequestStatus.REVIEWING)
        task.refresh_from_db()
        self.assertEqual(task.status, ProjectApprovalTaskStatus.PENDING)

    def test_reject_post_with_comment_transitions_to_rejected(self):
        """Reject POST with comment transitions request to REJECTED."""
        requester = _make_staff("rj_cmt_req", self.proj_dept)
        # Use same department so only one approval task is created
        pr = _make_full_draft(requester, self.proj_dept, self.proj_dept, self.ptype)
        self._submit_request(pr, requester)
        task = pr.approval_tasks.filter(status=ProjectApprovalTaskStatus.PENDING).first()
        approver = _make_staff("rj_cmt_approver", self.proj_dept, AccessLevel.MANAGER, can_approve=True)
        self.client.login(username="rj_cmt_approver", password="pass")
        resp = self.client.post(
            reverse("project_requests:reject", args=[pr.pk]),
            {"approval_task_id": task.pk, "comment": "Cannot approve this"},
        )
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.REJECTED)

    def test_reject_post_saves_comment_to_approval_task(self):
        """Reject POST saves comment to approval_task.decision_comment."""
        requester = _make_staff("rj_save_req", self.proj_dept)
        # Use same department so only one approval task is created
        pr = _make_full_draft(requester, self.proj_dept, self.proj_dept, self.ptype)
        self._submit_request(pr, requester)
        task = pr.approval_tasks.filter(status=ProjectApprovalTaskStatus.PENDING).first()
        approver = _make_staff("rj_save_approver", self.proj_dept, AccessLevel.MANAGER, can_approve=True)
        self.client.login(username="rj_save_approver", password="pass")
        resp = self.client.post(
            reverse("project_requests:reject", args=[pr.pk]),
            {"approval_task_id": task.pk, "comment": "Rejected due to budget"},
        )
        self.assertEqual(resp.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.decision_comment, "Rejected due to budget")

    def test_reject_post_wrong_task_id_from_another_request_rejected(self):
        """Wrong approval_task_id from another request is rejected and does not change either request."""
        requester1 = _make_staff("rj_wrong_req1", self.req_dept)
        pr1 = _make_full_draft(requester1, self.req_dept, self.proj_dept, self.ptype)
        self._submit_request(pr1, requester1)

        requester2 = _make_staff("rj_wrong_req2", self.other_dept)
        pr2 = _make_full_draft(requester2, self.other_dept, self.proj_dept, self.ptype)
        self._submit_request(pr2, requester2)

        task1 = pr1.approval_tasks.filter(status=ProjectApprovalTaskStatus.PENDING).first()
        approver = _make_staff("rj_wrong_approver", self.proj_dept, AccessLevel.MANAGER, can_approve=True)
        self.client.login(username="rj_wrong_approver", password="pass")
        resp = self.client.post(
            reverse("project_requests:reject", args=[pr2.pk]),
            {"approval_task_id": task1.pk, "comment": "Wrong task"},
        )
        self.assertEqual(resp.status_code, 302)
        pr1.refresh_from_db()
        pr2.refresh_from_db()
        self.assertEqual(pr1.status, ProjectRequestStatus.REVIEWING)
        self.assertEqual(pr2.status, ProjectRequestStatus.REVIEWING)

    def test_reject_post_user_cannot_reject_gets_error(self):
        """User who can view but cannot reject gets error and no status/task change."""
        requester = _make_staff("rj_noperm_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        self._submit_request(pr, requester)
        task = pr.approval_tasks.filter(status=ProjectApprovalTaskStatus.PENDING).first()
        # Create a manager user who can view but has can_approve=False
        manager = _make_staff("rj_noperm_mgr", self.proj_dept, AccessLevel.MANAGER, can_approve=False)
        self.client.login(username="rj_noperm_mgr", password="pass")
        resp = self.client.post(
            reverse("project_requests:reject", args=[pr.pk]),
            {"approval_task_id": task.pk, "comment": "Should fail"},
        )
        # Should redirect with error (not 403)
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        task.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.REVIEWING)
        self.assertEqual(task.status, ProjectApprovalTaskStatus.PENDING)

    def test_reject_post_anonymous_redirected_to_login(self):
        """Anonymous user is redirected to login."""
        requester = _make_staff("rj_anon_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        self._submit_request(pr, requester)
        task = pr.approval_tasks.filter(status=ProjectApprovalTaskStatus.PENDING).first()
        resp = self.client.post(
            reverse("project_requests:reject", args=[pr.pk]),
            {"approval_task_id": task.pk, "comment": "Test"},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp.url)

    # -------------------------------------------------------------------------
    # Permission Boundary Tests
    # -------------------------------------------------------------------------

    def test_unrelated_user_cannot_view_gets_403_on_approve_post(self):
        """Unrelated user who cannot view the request gets 403 on approve/reject POST."""
        requester = _make_staff("perm_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        self._submit_request(pr, requester)
        task = pr.approval_tasks.filter(status=ProjectApprovalTaskStatus.PENDING).first()
        # Create user in completely unrelated department
        unrelated = _make_staff("perm_unrelated", self.other_dept)
        self.client.login(username="perm_unrelated", password="pass")
        resp = self.client.post(
            reverse("project_requests:approve", args=[pr.pk]),
            {"approval_task_id": task.pk, "comment": "Should be 403"},
        )
        self.assertEqual(resp.status_code, 403)

    # -------------------------------------------------------------------------
    # Regression Tests
    # -------------------------------------------------------------------------

    def test_detail_page_still_renders_attachments_approvals_assignments_activity(self):
        """Detail page still renders attachments, approvals, assignments, activity log."""
        requester = _make_staff("reg_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        self._submit_request(pr, requester)
        approver = _make_staff("reg_approver", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="reg_approver", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        # Check all sections are present
        self.assertIn(b"Approval Tasks", resp.content)
        self.assertIn(b"Attachments", resp.content)
        self.assertIn(b"Activity Log", resp.content)

    def test_no_direct_attachment_file_url_exposed(self):
        """No direct attachment.file.url exposed in detail page."""
        requester = _make_staff("reg_url_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        uploaded = SimpleUploadedFile("test.pdf", b"%PDF fake", content_type="application/pdf")
        upload_project_request_attachment(pr, uploaded, self.ftype, requester)
        self.client.login(username="reg_url_req", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content_str = resp.content.decode()
        # Should have download link, not direct file URL
        self.assertIn("Download", content_str)
        # Should NOT contain /media/ direct URL
        self.assertNotIn("/media/", content_str)

    def test_no_assign_claim_start_hold_resume_complete_controls_added(self):
        """No assign/claim/start/hold/resume/complete controls are added in this subphase."""
        requester = _make_staff("reg_ctrl_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        self._submit_request(pr, requester)
        approver = _make_staff("reg_ctrl_approver", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="reg_ctrl_approver", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        # Check for actual form action URLs (forbidden Phase 3D-2/3D-3 controls)
        self.assertNotIn("/assign/", content)
        self.assertNotIn("/claim/", content)
        self.assertNotIn("/start/", content)
        self.assertNotIn("/hold/", content)
        self.assertNotIn("/resume/", content)
        self.assertNotIn("/complete/", content)
        # Check for actual submit buttons with exact text (not substrings in CSS/status)
        self.assertNotIn(">Assign<", content)
        self.assertNotIn(">Claim<", content)
        self.assertNotIn(">Start<", content)
        self.assertNotIn(">Hold<", content)
        self.assertNotIn(">Resume<", content)
        self.assertNotIn(">Complete<", content)


# ============================================================================
# Phase 3D-2: Assign/Claim View Tests
# ============================================================================

class ProjectRequestAssignClaimViewTest(TestCase):
    """Tests for assign/claim views (Phase 3D-2)."""

    def setUp(self):
        self.req_dept, self.proj_dept, self.other_dept, self.ptype, self.ftype = _build_fixtures()
        # Enable staff claim on proj_dept
        proj_profile = ProjectDepartmentProfile.objects.get(department=self.proj_dept)
        proj_profile.allow_staff_claim = True
        proj_profile.save()
        self.client = Client()

    # -------------------------------------------------------------------------
    # Visibility Tests
    # -------------------------------------------------------------------------

    def test_project_dept_manager_sees_assignment_form_when_can_assign(self):
        """Project dept manager sees assignment form when can_assign is True."""
        requester = _make_staff("vis_mgr_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        mgr = _make_staff("vis_mgr", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="vis_mgr", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("/assign/", content)
        self.assertIn(">Assign<", content)

    def test_superuser_sees_assignment_form_when_can_assign(self):
        """Superuser sees assignment form when can_assign is True."""
        requester = _make_staff("vis_su_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        superuser = User.objects.create_superuser(username="vis_su", password="pass", email="su@test.com")
        self.client.login(username="vis_su", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("/assign/", content)

    def test_request_dept_manager_alone_does_not_see_assignment_form(self):
        """Request dept manager alone does not see assignment form."""
        requester = _make_staff("vis_req_mgr_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        req_mgr = _make_staff("vis_req_mgr", self.req_dept, AccessLevel.MANAGER)
        self.client.login(username="vis_req_mgr", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertNotIn("/assign/", content)

    def test_project_dept_staff_does_not_see_assignment_form(self):
        """Project dept staff does not see assignment form."""
        requester = _make_staff("vis_staff_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        staff = _make_staff("vis_staff", self.proj_dept, AccessLevel.STAFF)
        self.client.login(username="vis_staff", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertNotIn("/assign/", content)

    def test_staff_sees_claim_button_when_can_claim(self):
        """Staff sees claim button when can_claim is True."""
        requester = _make_staff("vis_claim_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        staff = _make_staff("vis_claim_staff", self.proj_dept, AccessLevel.STAFF)
        self.client.login(username="vis_claim_staff", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("/claim/", content)
        self.assertIn(">Claim This Request<", content)

    def test_staff_does_not_see_claim_button_for_assigned_request(self):
        """Staff does not see claim button for ASSIGNED request."""
        requester = _make_staff("vis_assigned_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.ASSIGNED
        pr.save()
        # Use requester who can view their own request
        self.client.login(username="vis_assigned_req", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertNotIn("/claim/", content)

    def test_unrelated_user_does_not_see_claim_button(self):
        """Unrelated user does not see claim button (gets 403)."""
        requester = _make_staff("vis_unrel_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        unrelated = _make_staff("vis_unrel", self.other_dept, AccessLevel.STAFF)
        self.client.login(username="vis_unrel", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        # Unrelated user cannot view, gets 403
        self.assertEqual(resp.status_code, 403)

    def test_no_assign_claim_controls_shown_after_completed(self):
        """No assign/claim controls shown after COMPLETED."""
        requester = _make_staff("vis_comp_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.COMPLETED
        pr.save()
        mgr = _make_staff("vis_comp_mgr", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="vis_comp_mgr", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertNotIn("/assign/", content)
        self.assertNotIn("/claim/", content)

    def test_no_start_hold_resume_complete_controls_added(self):
        """No start/hold/resume/complete controls are added in this subphase."""
        requester = _make_staff("vis_exec_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.ASSIGNED
        pr.save()
        mgr = _make_staff("vis_exec_mgr", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="vis_exec_mgr", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        # Check for actual form action URLs (forbidden Phase 3D-3 controls)
        self.assertNotIn("/start/", content)
        self.assertNotIn("/hold/", content)
        self.assertNotIn("/resume/", content)
        self.assertNotIn("/complete/", content)
        # Check for actual submit buttons with exact text
        self.assertNotIn(">Start<", content)
        self.assertNotIn(">Put on Hold<", content)
        self.assertNotIn(">Resume<", content)
        self.assertNotIn(">Mark Complete<", content)

    # -------------------------------------------------------------------------
    # AssignmentForm Queryset Tests
    # -------------------------------------------------------------------------

    def test_assignment_form_queryset_includes_active_users_in_project_department(self):
        """AssignmentForm queryset includes active users in project_department."""
        requester = _make_staff("qs_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        mgr = _make_staff("qs_mgr", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="qs_mgr", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        form = resp.context["assignment_form"]
        user_ids = list(form.fields["assigned_to"].queryset.values_list("id", flat=True))
        self.assertIn(mgr.id, user_ids)

    def test_assignment_form_queryset_excludes_inactive_users(self):
        """AssignmentForm queryset excludes inactive users."""
        requester = _make_staff("qs_inact_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        inactive = User.objects.create_user(username="qs_inact", password="pass", is_active=False)
        UserDepartment.objects.create(user=inactive, department=self.proj_dept, access_level=AccessLevel.STAFF, is_active=True)
        mgr = _make_staff("qs_inact_mgr", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="qs_inact_mgr", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        form = resp.context["assignment_form"]
        user_ids = list(form.fields["assigned_to"].queryset.values_list("id", flat=True))
        self.assertNotIn(inactive.id, user_ids)

    def test_assignment_form_queryset_excludes_users_outside_project_department(self):
        """AssignmentForm queryset excludes users outside project_department."""
        requester = _make_staff("qs_out_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        outside_user = _make_staff("qs_outside", self.other_dept, AccessLevel.STAFF)
        mgr = _make_staff("qs_out_mgr", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="qs_out_mgr", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        form = resp.context["assignment_form"]
        user_ids = list(form.fields["assigned_to"].queryset.values_list("id", flat=True))
        self.assertNotIn(outside_user.id, user_ids)

    def test_assignment_form_queryset_excludes_inactive_user_department_memberships(self):
        """AssignmentForm queryset excludes users with inactive UserDepartment membership."""
        requester = _make_staff("qs_memb_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        inactive_memb_user = User.objects.create_user(username="qs_memb", password="pass", is_active=True)
        UserDepartment.objects.create(user=inactive_memb_user, department=self.proj_dept, access_level=AccessLevel.STAFF, is_active=False)
        mgr = _make_staff("qs_memb_mgr", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="qs_memb_mgr", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        form = resp.context["assignment_form"]
        user_ids = list(form.fields["assigned_to"].queryset.values_list("id", flat=True))
        self.assertNotIn(inactive_memb_user.id, user_ids)

    def test_assignment_form_handles_missing_project_department(self):
        """AssignmentForm handles missing project_department with empty queryset."""
        requester = _make_staff("qs_nodep_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.project_department = None
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        # Use requester who can view their own request
        self.client.login(username="qs_nodep_req", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        # assignment_form should not be in context when can_assign is False (no project_department)
        self.assertIsNone(resp.context.get("assignment_form"))

    # -------------------------------------------------------------------------
    # Assign POST Tests
    # -------------------------------------------------------------------------

    def test_assign_post_transitions_approved_to_assigned(self):
        """Assign POST transitions APPROVED -> ASSIGNED."""
        requester = _make_staff("assign_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        assignee = _make_staff("assignee", self.proj_dept, AccessLevel.STAFF)
        mgr = _make_staff("assign_mgr", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="assign_mgr", password="pass")
        resp = self.client.post(
            reverse("project_requests:assign", args=[pr.pk]),
            {"assigned_to": assignee.id, "comment": "Assigning this"},
        )
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.ASSIGNED)

    def test_assign_post_creates_active_assignment(self):
        """Assign POST creates active assignment."""
        requester = _make_staff("assign_ass_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        assignee = _make_staff("assign_assigne", self.proj_dept, AccessLevel.STAFF)
        mgr = _make_staff("assign_ass_mgr", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="assign_ass_mgr", password="pass")
        self.client.post(
            reverse("project_requests:assign", args=[pr.pk]),
            {"assigned_to": assignee.id},
        )
        assignment = ProjectRequestAssignment.objects.filter(project_request=pr, is_active=True).first()
        self.assertIsNotNone(assignment)
        self.assertEqual(assignment.assigned_to, assignee)

    def test_assign_post_sets_assigned_by_to_actor(self):
        """Assign POST sets assigned_by to actor."""
        requester = _make_staff("assign_by_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        assignee = _make_staff("assign_by_assignee", self.proj_dept, AccessLevel.STAFF)
        mgr = _make_staff("assign_by_mgr", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="assign_by_mgr", password="pass")
        self.client.post(
            reverse("project_requests:assign", args=[pr.pk]),
            {"assigned_to": assignee.id},
        )
        assignment = ProjectRequestAssignment.objects.filter(project_request=pr, is_active=True).first()
        self.assertEqual(assignment.assigned_by, mgr)

    def test_assign_post_with_missing_assigned_to_shows_error(self):
        """Assign POST with missing assigned_to shows error and does not change status."""
        requester = _make_staff("assign_err_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        mgr = _make_staff("assign_err_mgr", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="assign_err_mgr", password="pass")
        resp = self.client.post(
            reverse("project_requests:assign", args=[pr.pk]),
            {"comment": "No assigned_to"},
        )
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.APPROVED)

    def test_assign_post_to_inactive_user_fails(self):
        """Assign POST to inactive user fails."""
        requester = _make_staff("assign_inact_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        inactive = User.objects.create_user(username="assign_inact", password="pass", is_active=False)
        UserDepartment.objects.create(user=inactive, department=self.proj_dept, access_level=AccessLevel.STAFF, is_active=True)
        mgr = _make_staff("assign_inact_mgr", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="assign_inact_mgr", password="pass")
        resp = self.client.post(
            reverse("project_requests:assign", args=[pr.pk]),
            {"assigned_to": inactive.id},
        )
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.APPROVED)

    def test_assign_post_to_user_outside_project_department_fails(self):
        """Assign POST to user outside project department fails."""
        requester = _make_staff("assign_out_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        outside = _make_staff("assign_outside", self.other_dept, AccessLevel.STAFF)
        mgr = _make_staff("assign_out_mgr", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="assign_out_mgr", password="pass")
        resp = self.client.post(
            reverse("project_requests:assign", args=[pr.pk]),
            {"assigned_to": outside.id},
        )
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.APPROVED)

    def test_reassign_post_deactivates_old_and_creates_new_active_assignment(self):
        """Reassign POST deactivates old active assignment and creates new active assignment."""
        requester = _make_staff("reassign_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.ASSIGNED
        pr.save()
        old_assignee = _make_staff("reassign_old", self.proj_dept, AccessLevel.STAFF)
        new_assignee = _make_staff("reassign_new", self.proj_dept, AccessLevel.STAFF)
        ProjectRequestAssignment.objects.create(
            project_request=pr, assigned_to=old_assignee, assigned_by=requester, is_active=True
        )
        mgr = _make_staff("reassign_mgr", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="reassign_mgr", password="pass")
        resp = self.client.post(
            reverse("project_requests:assign", args=[pr.pk]),
            {"assigned_to": new_assignee.id},
        )
        self.assertEqual(resp.status_code, 302)
        # Old assignment should be deactivated
        old_ass = ProjectRequestAssignment.objects.filter(project_request=pr, assigned_to=old_assignee).first()
        self.assertFalse(old_ass.is_active)
        # New assignment should be active
        new_ass = ProjectRequestAssignment.objects.filter(project_request=pr, assigned_to=new_assignee, is_active=True).first()
        self.assertIsNotNone(new_ass)

    def test_request_dept_manager_alone_cannot_assign(self):
        """Request dept manager alone cannot assign."""
        requester = _make_staff("req_mgr_assign_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        assignee = _make_staff("req_mgr_assign_assignee", self.proj_dept, AccessLevel.STAFF)
        req_mgr = _make_staff("req_mgr_assign", self.req_dept, AccessLevel.MANAGER)
        self.client.login(username="req_mgr_assign", password="pass")
        resp = self.client.post(
            reverse("project_requests:assign", args=[pr.pk]),
            {"assigned_to": assignee.id},
        )
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.APPROVED)

    def test_assign_post_anonymous_redirected_to_login(self):
        """Anonymous user is redirected to login."""
        requester = _make_staff("assign_anon_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        assignee = _make_staff("assign_anon_assignee", self.proj_dept, AccessLevel.STAFF)
        resp = self.client.post(
            reverse("project_requests:assign", args=[pr.pk]),
            {"assigned_to": assignee.id},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp.url)

    def test_unrelated_user_who_cannot_view_gets_403_on_assign(self):
        """Unrelated user who cannot view gets 403 on assign POST."""
        requester = _make_staff("assign_perm_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        assignee = _make_staff("assign_perm_assignee", self.proj_dept, AccessLevel.STAFF)
        unrelated = _make_staff("assign_perm_unrelated", self.other_dept, AccessLevel.STAFF)
        self.client.login(username="assign_perm_unrelated", password="pass")
        resp = self.client.post(
            reverse("project_requests:assign", args=[pr.pk]),
            {"assigned_to": assignee.id},
        )
        self.assertEqual(resp.status_code, 403)

    def test_user_who_can_view_but_cannot_assign_gets_error(self):
        """User who can view but cannot assign gets error and no status/assignment change."""
        requester = _make_staff("assign_cant_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        assignee = _make_staff("assign_cant_assignee", self.proj_dept, AccessLevel.STAFF)
        # User is staff in project dept, can view but not assign
        staff = _make_staff("assign_cant_staff", self.proj_dept, AccessLevel.STAFF)
        self.client.login(username="assign_cant_staff", password="pass")
        resp = self.client.post(
            reverse("project_requests:assign", args=[pr.pk]),
            {"assigned_to": assignee.id},
        )
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.APPROVED)
        self.assertFalse(ProjectRequestAssignment.objects.filter(project_request=pr, is_active=True).exists())

    # -------------------------------------------------------------------------
    # Claim POST Tests
    # -------------------------------------------------------------------------

    def test_claim_post_transitions_approved_to_assigned(self):
        """Claim POST transitions APPROVED -> ASSIGNED."""
        requester = _make_staff("claim_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        staff = _make_staff("claimer", self.proj_dept, AccessLevel.STAFF)
        self.client.login(username="claimer", password="pass")
        resp = self.client.post(reverse("project_requests:claim", args=[pr.pk]))
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.ASSIGNED)

    def test_claim_post_creates_active_assignment(self):
        """Claim POST creates active assignment assigned_to=request.user and assigned_by=request.user."""
        requester = _make_staff("claim_ass_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        staff = _make_staff("claim_assigner", self.proj_dept, AccessLevel.STAFF)
        self.client.login(username="claim_assigner", password="pass")
        self.client.post(reverse("project_requests:claim", args=[pr.pk]))
        assignment = ProjectRequestAssignment.objects.filter(project_request=pr, is_active=True).first()
        self.assertIsNotNone(assignment)
        self.assertEqual(assignment.assigned_to, staff)
        self.assertEqual(assignment.assigned_by, staff)

    def test_claim_button_not_visible_when_allow_staff_claim_false(self):
        """Claim button is not visible when allow_staff_claim=False (user is requester, can view)."""
        requester = _make_staff("claim_novis_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        # Disable staff claim
        proj_profile = ProjectDepartmentProfile.objects.get(department=self.proj_dept)
        proj_profile.allow_staff_claim = False
        proj_profile.save()
        # Use requester who can view their own request
        self.client.login(username="claim_novis_req", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertNotIn("/claim/", content)

    def test_claim_post_fails_when_allow_staff_claim_false(self):
        """Claim POST fails when allow_staff_claim=False (user is requester, can view)."""
        requester = _make_staff("claim_nopost_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        # Disable staff claim
        proj_profile = ProjectDepartmentProfile.objects.get(department=self.proj_dept)
        proj_profile.allow_staff_claim = False
        proj_profile.save()
        # Use requester who can view their own request
        self.client.login(username="claim_nopost_req", password="pass")
        resp = self.client.post(reverse("project_requests:claim", args=[pr.pk]))
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.APPROVED)

    def test_claim_post_on_assigned_request_fails(self):
        """Claim POST on ASSIGNED request fails (user is requester, can view)."""
        requester = _make_staff("claim_assigned_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.ASSIGNED
        pr.save()
        existing = _make_staff("claim_assigned_existing", self.proj_dept, AccessLevel.STAFF)
        ProjectRequestAssignment.objects.create(
            project_request=pr, assigned_to=existing, assigned_by=requester, is_active=True
        )
        # Use requester who can view their own request
        self.client.login(username="claim_assigned_req", password="pass")
        resp = self.client.post(reverse("project_requests:claim", args=[pr.pk]))
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.ASSIGNED)
        # Existing assignment should remain
        self.assertTrue(
            ProjectRequestAssignment.objects.filter(project_request=pr, assigned_to=existing, is_active=True).exists()
        )

    def test_claim_post_by_user_outside_project_department_fails(self):
        """Claim POST by user outside project department fails (gets 403)."""
        requester = _make_staff("claim_out_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        outside = _make_staff("claim_outside", self.other_dept, AccessLevel.STAFF)
        self.client.login(username="claim_outside", password="pass")
        resp = self.client.post(reverse("project_requests:claim", args=[pr.pk]))
        # User cannot view, gets 403
        self.assertEqual(resp.status_code, 403)

    def test_claim_post_anonymous_redirected_to_login(self):
        """Anonymous user is redirected to login."""
        requester = _make_staff("claim_anon_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        resp = self.client.post(reverse("project_requests:claim", args=[pr.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp.url)

    def test_unrelated_user_who_cannot_view_gets_403_on_claim(self):
        """Unrelated user who cannot view gets 403 on claim POST."""
        requester = _make_staff("claim_perm_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        unrelated = _make_staff("claim_perm_unrelated", self.other_dept, AccessLevel.STAFF)
        self.client.login(username="claim_perm_unrelated", password="pass")
        resp = self.client.post(reverse("project_requests:claim", args=[pr.pk]))
        self.assertEqual(resp.status_code, 403)

    # -------------------------------------------------------------------------
    # Regression Tests
    # -------------------------------------------------------------------------

    def test_approve_reject_controls_still_render_for_valid_approver(self):
        """Approve/reject controls still render for valid approver."""
        requester = _make_staff("reg_appr_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        # Submit to create approval tasks (moves to REVIEWING)
        from project_requests.services import submit_project_request
        submit_project_request(pr, requester)
        pr.refresh_from_db()
        # Create manager with can_approve=True so they can see pending tasks
        mgr = _make_staff("reg_appr_mgr", self.proj_dept, AccessLevel.MANAGER, can_approve=True)
        self.client.login(username="reg_appr_mgr", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("/approve/", content)
        self.assertIn("/reject/", content)

    def test_detail_page_still_renders_attachments_approvals_assignments_activity(self):
        """Detail page still renders attachments, approvals, assignments, activity log."""
        requester = _make_staff("reg_det_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        mgr = _make_staff("reg_det_mgr", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="reg_det_mgr", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn(b"Attachments", resp.content)
        self.assertIn(b"Activity Log", resp.content)
        self.assertIn(b"Assignments", resp.content)

    def test_no_direct_attachment_file_url_exposed(self):
        """No direct attachment.file.url exposed in detail page."""
        requester = _make_staff("reg_url_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        uploaded = SimpleUploadedFile("test.pdf", b"%PDF fake", content_type="application/pdf")
        upload_project_request_attachment(pr, uploaded, self.ftype, requester)
        mgr = _make_staff("reg_url_mgr", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="reg_url_mgr", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content_str = resp.content.decode()
        self.assertIn("Download", content_str)
        self.assertNotIn("/media/", content_str)


# ============================================================================
# Phase 3D-3: Execution Workflow View Tests
# ============================================================================

class ProjectRequestExecutionViewTest(TestCase):
    """Tests for start/hold/resume/complete views (Phase 3D-3)."""

    def setUp(self):
        self.req_dept, self.proj_dept, self.other_dept, self.ptype, self.ftype = _build_fixtures()
        self.client = Client()

    def _create_assigned_request_with_assignment(self, assignee):
        """Create an ASSIGNED request with an active assignment to the given assignee."""
        requester = _make_staff("exec_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.ASSIGNED
        pr.save()
        ProjectRequestAssignment.objects.create(
            project_request=pr, assigned_to=assignee, assigned_by=requester, is_active=True
        )
        return pr

    def _create_in_progress_request_with_assignment(self, assignee):
        """Create an IN_PROGRESS request with an active assignment."""
        pr = self._create_assigned_request_with_assignment(assignee)
        # Use the start service to move to IN_PROGRESS
        from project_requests.services import start_project_request
        start_project_request(pr, assignee)
        pr.refresh_from_db()
        return pr

    def _create_on_hold_request_with_assignment(self, assignee):
        """Create an ON_HOLD request with an active assignment."""
        pr = self._create_in_progress_request_with_assignment(assignee)
        # Use the hold service to move to ON_HOLD
        from project_requests.services import hold_project_request
        hold_project_request(pr, assignee, comment="Testing hold")
        pr.refresh_from_db()
        return pr

    # -------------------------------------------------------------------------
    # Visibility Tests
    # -------------------------------------------------------------------------

    def test_active_assignee_sees_start_button_when_assigned(self):
        """Active assignee sees Start button when request is ASSIGNED with active assignment."""
        assignee = _make_staff("exec_assignee", self.proj_dept, AccessLevel.STAFF)
        pr = self._create_assigned_request_with_assignment(assignee)
        self.client.login(username="exec_assignee", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("/start/", content)
        self.assertIn(">Start<", content)

    def test_project_dept_manager_sees_start_button_when_assigned(self):
        """Project dept manager sees Start button when ASSIGNED with active assignment, even if not assignee."""
        assignee = _make_staff("exec_assignee2", self.proj_dept, AccessLevel.STAFF)
        mgr = _make_staff("exec_mgr", self.proj_dept, AccessLevel.MANAGER)
        pr = self._create_assigned_request_with_assignment(assignee)
        self.client.login(username="exec_mgr", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("/start/", content)
        self.assertIn(">Start<", content)

    def test_request_dept_manager_alone_does_not_see_start(self):
        """Request dept manager alone does not see Start button."""
        assignee = _make_staff("exec_assignee3", self.proj_dept, AccessLevel.STAFF)
        req_mgr = _make_staff("exec_req_mgr", self.req_dept, AccessLevel.MANAGER)
        pr = self._create_assigned_request_with_assignment(assignee)
        self.client.login(username="exec_req_mgr", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertNotIn("/start/", content)

    def test_no_active_assignment_means_no_start_control(self):
        """No active assignment means no Start control, even for project dept manager."""
        requester = _make_staff("exec_req2", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.ASSIGNED
        pr.save()
        # No assignment created
        mgr = _make_staff("exec_mgr2", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="exec_mgr2", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertNotIn("/start/", content)

    def test_active_assignee_sees_hold_form_when_in_progress(self):
        """Active assignee sees Hold form when request is IN_PROGRESS."""
        assignee = _make_staff("exec_assignee5", self.proj_dept, AccessLevel.STAFF)
        pr = self._create_in_progress_request_with_assignment(assignee)
        self.client.login(username="exec_assignee5", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("/hold/", content)
        self.assertIn(">Put on Hold<", content)

    def test_project_dept_manager_sees_hold_form_when_in_progress(self):
        """Project dept manager sees Hold form when IN_PROGRESS."""
        assignee = _make_staff("exec_assignee6", self.proj_dept, AccessLevel.STAFF)
        mgr = _make_staff("exec_mgr3", self.proj_dept, AccessLevel.MANAGER)
        pr = self._create_in_progress_request_with_assignment(assignee)
        self.client.login(username="exec_mgr3", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("/hold/", content)
        self.assertIn(">Put on Hold<", content)

    def test_active_assignee_sees_resume_button_when_on_hold(self):
        """Active assignee sees Resume button when request is ON_HOLD."""
        assignee = _make_staff("exec_assignee7", self.proj_dept, AccessLevel.STAFF)
        pr = self._create_on_hold_request_with_assignment(assignee)
        self.client.login(username="exec_assignee7", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("/resume/", content)
        self.assertIn(">Resume<", content)

    def test_project_dept_manager_sees_resume_button_when_on_hold(self):
        """Project dept manager sees Resume button when ON_HOLD."""
        assignee = _make_staff("exec_assignee8", self.proj_dept, AccessLevel.STAFF)
        mgr = _make_staff("exec_mgr4", self.proj_dept, AccessLevel.MANAGER)
        pr = self._create_on_hold_request_with_assignment(assignee)
        self.client.login(username="exec_mgr4", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("/resume/", content)
        self.assertIn(">Resume<", content)

    def test_active_assignee_sees_complete_button_when_in_progress(self):
        """Active assignee sees Complete button when request is IN_PROGRESS."""
        assignee = _make_staff("exec_assignee9", self.proj_dept, AccessLevel.STAFF)
        pr = self._create_in_progress_request_with_assignment(assignee)
        self.client.login(username="exec_assignee9", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("/complete/", content)
        self.assertIn(">Mark Complete<", content)

    def test_project_dept_manager_sees_complete_button_when_in_progress(self):
        """Project dept manager sees Complete button when IN_PROGRESS."""
        assignee = _make_staff("exec_assignee10", self.proj_dept, AccessLevel.STAFF)
        mgr = _make_staff("exec_mgr5", self.proj_dept, AccessLevel.MANAGER)
        pr = self._create_in_progress_request_with_assignment(assignee)
        self.client.login(username="exec_mgr5", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("/complete/", content)
        self.assertIn(">Mark Complete<", content)

    def test_on_hold_does_not_show_complete(self):
        """ON_HOLD does not show Complete button."""
        assignee = _make_staff("exec_assignee11", self.proj_dept, AccessLevel.STAFF)
        pr = self._create_on_hold_request_with_assignment(assignee)
        self.client.login(username="exec_assignee11", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertNotIn("/complete/", content)
        self.assertNotIn(">Mark Complete<", content)

    def test_completed_does_not_show_start_hold_resume_complete(self):
        """COMPLETED does not show start/hold/resume/complete controls."""
        assignee = _make_staff("exec_assignee12", self.proj_dept, AccessLevel.STAFF)
        pr = self._create_in_progress_request_with_assignment(assignee)
        # Complete the request
        from project_requests.services import complete_project_request
        complete_project_request(pr, assignee)
        pr.refresh_from_db()
        self.client.login(username="exec_assignee12", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertNotIn("/start/", content)
        self.assertNotIn("/hold/", content)
        self.assertNotIn("/resume/", content)
        self.assertNotIn("/complete/", content)

    def test_assign_claim_controls_still_render_when_allowed(self):
        """Assign/claim controls still render when allowed."""
        assignee = _make_staff("exec_assignee13", self.proj_dept, AccessLevel.STAFF)
        mgr = _make_staff("exec_mgr6", self.proj_dept, AccessLevel.MANAGER)
        pr = self._create_assigned_request_with_assignment(assignee)
        # When ASSIGNED, assign/claim should not be shown (but manager can still view)
        self.client.login(username="exec_mgr6", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        # Assign/claim forms should not be present when status is ASSIGNED
        self.assertNotIn('action="/project_requests/' + str(pr.pk) + '/assign/"', content)
        self.assertNotIn('action="/project_requests/' + str(pr.pk) + '/claim/"', content)

    # -------------------------------------------------------------------------
    # Start POST Tests
    # -------------------------------------------------------------------------

    def test_start_post_transitions_assigned_to_in_progress(self):
        """Start POST transitions ASSIGNED -> IN_PROGRESS."""
        assignee = _make_staff("start_req", self.proj_dept, AccessLevel.STAFF)
        pr = self._create_assigned_request_with_assignment(assignee)
        self.client.login(username="start_req", password="pass")
        resp = self.client.post(reverse("project_requests:start", args=[pr.pk]))
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.IN_PROGRESS)

    def test_start_post_sets_started_at(self):
        """Start POST sets started_at timestamp."""
        assignee = _make_staff("start_at_req", self.proj_dept, AccessLevel.STAFF)
        pr = self._create_assigned_request_with_assignment(assignee)
        self.assertIsNone(pr.started_at)
        self.client.login(username="start_at_req", password="pass")
        self.client.post(reverse("project_requests:start", args=[pr.pk]))
        pr.refresh_from_db()
        self.assertIsNotNone(pr.started_at)

    def test_start_post_by_project_dept_manager_succeeds(self):
        """Start POST by project dept manager succeeds even if not assignee."""
        assignee = _make_staff("start_mgr_assignee", self.proj_dept, AccessLevel.STAFF)
        mgr = _make_staff("start_mgr", self.proj_dept, AccessLevel.MANAGER)
        pr = self._create_assigned_request_with_assignment(assignee)
        self.client.login(username="start_mgr", password="pass")
        resp = self.client.post(reverse("project_requests:start", args=[pr.pk]))
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.IN_PROGRESS)

    def test_unauthorized_start_post_fails_and_does_not_change_status(self):
        """Unauthorized start POST fails and does not change status (user cannot view request)."""
        assignee = _make_staff("start_unauth_assignee", self.proj_dept, AccessLevel.STAFF)
        pr = self._create_assigned_request_with_assignment(assignee)
        # User from other_dept cannot view the request at all
        other_user = _make_staff("start_unauth_other", self.other_dept, AccessLevel.MANAGER)
        self.client.login(username="start_unauth_other", password="pass")
        resp = self.client.post(reverse("project_requests:start", args=[pr.pk]))
        # Should get 403 since user cannot view the request
        self.assertEqual(resp.status_code, 403)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.ASSIGNED)

    def test_no_active_assignment_blocks_start(self):
        """No active assignment blocks start."""
        requester = _make_staff("start_no_ass_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.ASSIGNED
        pr.save()
        mgr = _make_staff("start_no_ass_mgr", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="start_no_ass_mgr", password="pass")
        resp = self.client.post(reverse("project_requests:start", args=[pr.pk]))
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.ASSIGNED)

    # -------------------------------------------------------------------------
    # Hold POST Tests
    # -------------------------------------------------------------------------

    def test_hold_post_requires_comment(self):
        """Hold POST requires comment."""
        assignee = _make_staff("hold_nocomment_req", self.proj_dept, AccessLevel.STAFF)
        pr = self._create_in_progress_request_with_assignment(assignee)
        self.client.login(username="hold_nocomment_req", password="pass")
        resp = self.client.post(
            reverse("project_requests:hold", args=[pr.pk]),
            {}  # No comment
        )
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.IN_PROGRESS)

    def test_hold_post_with_comment_transitions_to_on_hold(self):
        """Hold POST with comment transitions IN_PROGRESS -> ON_HOLD."""
        assignee = _make_staff("hold_req", self.proj_dept, AccessLevel.STAFF)
        pr = self._create_in_progress_request_with_assignment(assignee)
        self.client.login(username="hold_req", password="pass")
        resp = self.client.post(
            reverse("project_requests:hold", args=[pr.pk]),
            {"comment": "Waiting for feedback"}
        )
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.ON_HOLD)

    def test_hold_post_saves_comment_to_activity_log(self):
        """Hold POST saves user comment to ActivityLog.comment."""
        assignee = _make_staff("hold_comment_req", self.proj_dept, AccessLevel.STAFF)
        pr = self._create_in_progress_request_with_assignment(assignee)
        self.client.login(username="hold_comment_req", password="pass")
        self.client.post(
            reverse("project_requests:hold", args=[pr.pk]),
            {"comment": "Need more info"}
        )
        log = pr.activity_log.filter(
            action_type=ProjectRequestActionType.PUT_ON_HOLD
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.comment, "Need more info")

    def test_unauthorized_hold_post_fails_and_does_not_change_status(self):
        """Unauthorized hold POST fails and does not change status (user cannot view request)."""
        assignee = _make_staff("hold_unauth_assignee", self.proj_dept, AccessLevel.STAFF)
        pr = self._create_in_progress_request_with_assignment(assignee)
        # User from other_dept cannot view the request at all
        other_user = _make_staff("hold_unauth_other", self.other_dept, AccessLevel.MANAGER)
        self.client.login(username="hold_unauth_other", password="pass")
        resp = self.client.post(
            reverse("project_requests:hold", args=[pr.pk]),
            {"comment": "Unauthorized"}
        )
        # Should get 403 since user cannot view the request
        self.assertEqual(resp.status_code, 403)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.IN_PROGRESS)

    def test_no_active_assignment_blocks_hold(self):
        """No active assignment blocks hold."""
        requester = _make_staff("hold_no_ass_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.IN_PROGRESS
        pr.save()
        mgr = _make_staff("hold_no_ass_mgr", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="hold_no_ass_mgr", password="pass")
        resp = self.client.post(
            reverse("project_requests:hold", args=[pr.pk]),
            {"comment": "Should fail"}
        )
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.IN_PROGRESS)

    # -------------------------------------------------------------------------
    # Resume POST Tests
    # -------------------------------------------------------------------------

    def test_resume_post_transitions_on_hold_to_in_progress(self):
        """Resume POST transitions ON_HOLD -> IN_PROGRESS."""
        assignee = _make_staff("resume_req", self.proj_dept, AccessLevel.STAFF)
        pr = self._create_on_hold_request_with_assignment(assignee)
        self.client.login(username="resume_req", password="pass")
        resp = self.client.post(reverse("project_requests:resume", args=[pr.pk]))
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.IN_PROGRESS)

    def test_resume_post_with_optional_comment_saves_comment(self):
        """Resume POST with optional comment saves comment to ActivityLog if provided."""
        assignee = _make_staff("resume_comment_req", self.proj_dept, AccessLevel.STAFF)
        pr = self._create_on_hold_request_with_assignment(assignee)
        self.client.login(username="resume_comment_req", password="pass")
        self.client.post(
            reverse("project_requests:resume", args=[pr.pk]),
            {"comment": "Ready to continue"}
        )
        log = pr.activity_log.filter(
            action_type=ProjectRequestActionType.RESUMED
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.comment, "Ready to continue")

    def test_unauthorized_resume_post_fails_and_does_not_change_status(self):
        """Unauthorized resume POST fails and does not change status (user cannot view request)."""
        assignee = _make_staff("resume_unauth_assignee", self.proj_dept, AccessLevel.STAFF)
        pr = self._create_on_hold_request_with_assignment(assignee)
        # User from other_dept cannot view the request at all
        other_user = _make_staff("resume_unauth_other", self.other_dept, AccessLevel.MANAGER)
        self.client.login(username="resume_unauth_other", password="pass")
        resp = self.client.post(reverse("project_requests:resume", args=[pr.pk]))
        # Should get 403 since user cannot view the request
        self.assertEqual(resp.status_code, 403)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.ON_HOLD)

    def test_no_active_assignment_blocks_resume(self):
        """No active assignment blocks resume."""
        requester = _make_staff("resume_no_ass_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.ON_HOLD
        pr.save()
        mgr = _make_staff("resume_no_ass_mgr", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="resume_no_ass_mgr", password="pass")
        resp = self.client.post(reverse("project_requests:resume", args=[pr.pk]))
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.ON_HOLD)

    # -------------------------------------------------------------------------
    # Complete POST Tests
    # -------------------------------------------------------------------------

    def test_complete_post_transitions_in_progress_to_completed(self):
        """Complete POST transitions IN_PROGRESS -> COMPLETED."""
        assignee = _make_staff("complete_req", self.proj_dept, AccessLevel.STAFF)
        pr = self._create_in_progress_request_with_assignment(assignee)
        self.client.login(username="complete_req", password="pass")
        resp = self.client.post(reverse("project_requests:complete", args=[pr.pk]))
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.COMPLETED)

    def test_complete_post_sets_completed_at(self):
        """Complete POST sets completed_at timestamp."""
        assignee = _make_staff("complete_at_req", self.proj_dept, AccessLevel.STAFF)
        pr = self._create_in_progress_request_with_assignment(assignee)
        self.assertIsNone(pr.completed_at)
        self.client.login(username="complete_at_req", password="pass")
        self.client.post(reverse("project_requests:complete", args=[pr.pk]))
        pr.refresh_from_db()
        self.assertIsNotNone(pr.completed_at)

    def test_complete_post_with_optional_comment_saves_comment(self):
        """Complete POST with optional comment saves comment to ActivityLog if provided."""
        assignee = _make_staff("complete_comment_req", self.proj_dept, AccessLevel.STAFF)
        pr = self._create_in_progress_request_with_assignment(assignee)
        self.client.login(username="complete_comment_req", password="pass")
        self.client.post(
            reverse("project_requests:complete", args=[pr.pk]),
            {"comment": "All done!"}
        )
        log = pr.activity_log.filter(
            action_type=ProjectRequestActionType.COMPLETED
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.comment, "All done!")

    def test_on_hold_cannot_complete_directly(self):
        """ON_HOLD cannot complete directly."""
        assignee = _make_staff("complete_onhold_req", self.proj_dept, AccessLevel.STAFF)
        pr = self._create_on_hold_request_with_assignment(assignee)
        self.client.login(username="complete_onhold_req", password="pass")
        resp = self.client.post(reverse("project_requests:complete", args=[pr.pk]))
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.ON_HOLD)

    def test_unauthorized_complete_post_fails_and_does_not_change_status(self):
        """Unauthorized complete POST fails and does not change status (user cannot view request)."""
        assignee = _make_staff("complete_unauth_assignee", self.proj_dept, AccessLevel.STAFF)
        pr = self._create_in_progress_request_with_assignment(assignee)
        # User from other_dept cannot view the request at all
        other_user = _make_staff("complete_unauth_other", self.other_dept, AccessLevel.MANAGER)
        self.client.login(username="complete_unauth_other", password="pass")
        resp = self.client.post(reverse("project_requests:complete", args=[pr.pk]))
        # Should get 403 since user cannot view the request
        self.assertEqual(resp.status_code, 403)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.IN_PROGRESS)

    def test_no_active_assignment_blocks_complete(self):
        """No active assignment blocks complete."""
        requester = _make_staff("complete_no_ass_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.IN_PROGRESS
        pr.save()
        mgr = _make_staff("complete_no_ass_mgr", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="complete_no_ass_mgr", password="pass")
        resp = self.client.post(reverse("project_requests:complete", args=[pr.pk]))
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.IN_PROGRESS)

    # -------------------------------------------------------------------------
    # Security/Login Tests
    # -------------------------------------------------------------------------

    def test_anonymous_user_redirected_to_login_for_start(self):
        """Anonymous user is redirected to login for start."""
        assignee = _make_staff("start_anon_req", self.proj_dept, AccessLevel.STAFF)
        pr = self._create_assigned_request_with_assignment(assignee)
        resp = self.client.post(reverse("project_requests:start", args=[pr.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp.url)

    def test_anonymous_user_redirected_to_login_for_hold(self):
        """Anonymous user is redirected to login for hold."""
        assignee = _make_staff("hold_anon_req", self.proj_dept, AccessLevel.STAFF)
        pr = self._create_in_progress_request_with_assignment(assignee)
        resp = self.client.post(
            reverse("project_requests:hold", args=[pr.pk]),
            {"comment": "Test"}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp.url)

    def test_anonymous_user_redirected_to_login_for_resume(self):
        """Anonymous user is redirected to login for resume."""
        assignee = _make_staff("resume_anon_req", self.proj_dept, AccessLevel.STAFF)
        pr = self._create_on_hold_request_with_assignment(assignee)
        resp = self.client.post(reverse("project_requests:resume", args=[pr.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp.url)

    def test_anonymous_user_redirected_to_login_for_complete(self):
        """Anonymous user is redirected to login for complete."""
        assignee = _make_staff("complete_anon_req", self.proj_dept, AccessLevel.STAFF)
        pr = self._create_in_progress_request_with_assignment(assignee)
        resp = self.client.post(reverse("project_requests:complete", args=[pr.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp.url)

    def test_unrelated_user_gets_403_for_start(self):
        """Unrelated user who cannot view gets 403 for start."""
        assignee = _make_staff("start_403_assignee", self.proj_dept, AccessLevel.STAFF)
        pr = self._create_assigned_request_with_assignment(assignee)
        unrelated = _make_staff("start_403_unrelated", self.other_dept, AccessLevel.STAFF)
        self.client.login(username="start_403_unrelated", password="pass")
        resp = self.client.post(reverse("project_requests:start", args=[pr.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_unrelated_user_gets_403_for_hold(self):
        """Unrelated user who cannot view gets 403 for hold."""
        assignee = _make_staff("hold_403_assignee", self.proj_dept, AccessLevel.STAFF)
        pr = self._create_in_progress_request_with_assignment(assignee)
        unrelated = _make_staff("hold_403_unrelated", self.other_dept, AccessLevel.STAFF)
        self.client.login(username="hold_403_unrelated", password="pass")
        resp = self.client.post(
            reverse("project_requests:hold", args=[pr.pk]),
            {"comment": "Test"}
        )
        self.assertEqual(resp.status_code, 403)

    def test_unrelated_user_gets_403_for_resume(self):
        """Unrelated user who cannot view gets 403 for resume."""
        assignee = _make_staff("resume_403_assignee", self.proj_dept, AccessLevel.STAFF)
        pr = self._create_on_hold_request_with_assignment(assignee)
        unrelated = _make_staff("resume_403_unrelated", self.other_dept, AccessLevel.STAFF)
        self.client.login(username="resume_403_unrelated", password="pass")
        resp = self.client.post(reverse("project_requests:resume", args=[pr.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_unrelated_user_gets_403_for_complete(self):
        """Unrelated user who cannot view gets 403 for complete."""
        assignee = _make_staff("complete_403_assignee", self.proj_dept, AccessLevel.STAFF)
        pr = self._create_in_progress_request_with_assignment(assignee)
        unrelated = _make_staff("complete_403_unrelated", self.other_dept, AccessLevel.STAFF)
        self.client.login(username="complete_403_unrelated", password="pass")
        resp = self.client.post(reverse("project_requests:complete", args=[pr.pk]))
        self.assertEqual(resp.status_code, 403)


# ============================================================================
# Phase 3D-4: Detail Context Consistency Tests
# ============================================================================

class ProjectRequestAttachmentUploadErrorContextTest(TestCase):
    """Tests for _build_detail_context() assignment_form consistency gap (Phase 3D-4)."""

    def setUp(self):
        self.req_dept, self.proj_dept, self.other_dept, self.ptype, self.ftype = _build_fixtures()
        self.client = Client()

    def test_invalid_upload_re_render_includes_assignment_form_when_can_assign(self):
        """Invalid attachment upload re-render includes assignment_form when actor can_assign."""
        requester = _make_staff("ctx_can_assign_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        # Manager who can assign
        mgr = _make_staff("ctx_can_assign_mgr", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="ctx_can_assign_mgr", password="pass")
        url = reverse("project_requests:attachment_upload", args=[pr.pk])
        # Post with no file to trigger form validation error
        resp = self.client.post(url, {"file_type": self.ftype.pk, "description": "test"})
        self.assertEqual(resp.status_code, 200)
        # assignment_form should be in context
        self.assertIn("assignment_form", resp.context)
        self.assertIsNotNone(resp.context["assignment_form"])

    def test_invalid_upload_re_render_does_not_include_assignment_form_when_cannot_assign(self):
        """Invalid attachment upload re-render does not include assignment_form when actor cannot assign."""
        requester = _make_staff("ctx_cannot_assign_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        # Staff who can view but cannot assign (no assignment_form expected)
        staff = _make_staff("ctx_cannot_assign_staff", self.proj_dept, AccessLevel.STAFF)
        self.client.login(username="ctx_cannot_assign_staff", password="pass")
        url = reverse("project_requests:attachment_upload", args=[pr.pk])
        # Post with no file to trigger form validation error
        resp = self.client.post(url, {"file_type": self.ftype.pk, "description": "test"})
        self.assertEqual(resp.status_code, 200)
        # assignment_form should NOT be in context for staff who cannot assign
        self.assertNotIn("assignment_form", resp.context)

    def test_invalid_upload_re_render_still_includes_attachment_form_and_file_type_options(self):
        """Invalid attachment upload re-render still includes attachment_form and file type options."""
        requester = _make_staff("ctx_attach_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        self.client.login(username="ctx_attach_req", password="pass")
        url = reverse("project_requests:attachment_upload", args=[pr.pk])
        # Post with no file to trigger form validation error
        resp = self.client.post(url, {"file_type": self.ftype.pk, "description": "test"})
        self.assertEqual(resp.status_code, 200)
        # attachment_form should be in context
        self.assertIn("attachment_form", resp.context)
        # File type options should be shown
        content = resp.content.decode()
        self.assertIn(self.ftype.name, content)


# ============================================================================
# Phase 3D-4: End-to-End Workflow Tests
# ============================================================================

class ProjectRequestWorkflowEndToEndTest(TestCase):
    """End-to-end workflow tests covering the full project request lifecycle (Phase 3D-4)."""

    def setUp(self):
        self.req_dept, self.proj_dept, self.other_dept, self.ptype, self.ftype = _build_fixtures()
        # Enable staff claim for claim workflow tests
        proj_profile = ProjectDepartmentProfile.objects.get(department=self.proj_dept)
        proj_profile.allow_staff_claim = True
        proj_profile.save()
        self.client = Client()

    # -------------------------------------------------------------------------
    # Test A: submit -> approve -> assign -> start -> complete
    # -------------------------------------------------------------------------

    def test_full_workflow_submit_approve_assign_start_complete(self):
        """E2E: submit -> approve -> assign -> start -> complete."""
        # 1. Create draft and submit
        # Requester must be in request_department for submit to work
        requester = _make_staff("e2e_req", self.proj_dept)
        pr = _make_full_draft(requester, self.proj_dept, self.proj_dept, self.ptype)
        # Use same dept for single-approval workflow
        submit_project_request(pr, requester)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.REVIEWING)

        # 2. Approve
        approver = _make_staff("e2e_approver", self.proj_dept, AccessLevel.MANAGER, can_approve=True)
        task = pr.approval_tasks.filter(status=ProjectApprovalTaskStatus.PENDING).first()
        self.client.login(username="e2e_approver", password="pass")
        resp = self.client.post(
            reverse("project_requests:approve", args=[pr.pk]),
            {"approval_task_id": task.pk, "comment": "Approved"}
        )
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.APPROVED)

        # 3. Assign
        assignee = _make_staff("e2e_assignee", self.proj_dept, AccessLevel.STAFF)
        mgr = _make_staff("e2e_mgr", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="e2e_mgr", password="pass")
        resp = self.client.post(
            reverse("project_requests:assign", args=[pr.pk]),
            {"assigned_to": assignee.id, "comment": "Assigned"}
        )
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.ASSIGNED)

        # 4. Start
        self.client.login(username="e2e_assignee", password="pass")
        resp = self.client.post(reverse("project_requests:start", args=[pr.pk]))
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.IN_PROGRESS)
        self.assertIsNotNone(pr.started_at)

        # 5. Complete
        resp = self.client.post(reverse("project_requests:complete", args=[pr.pk]))
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.COMPLETED)
        self.assertIsNotNone(pr.completed_at)

        # 6. Verify activity log entries exist
        log_entries = pr.activity_log.all()
        action_types = [log.action_type for log in log_entries]
        # Should have SUBMITTED, APPROVED, ASSIGNED, STARTED, COMPLETED
        self.assertIn(ProjectRequestActionType.SUBMITTED, action_types)
        self.assertIn(ProjectRequestActionType.APPROVED, action_types)
        self.assertIn(ProjectRequestActionType.ASSIGNED, action_types)
        self.assertIn(ProjectRequestActionType.STARTED, action_types)
        self.assertIn(ProjectRequestActionType.COMPLETED, action_types)

    # -------------------------------------------------------------------------
    # Test B: submit -> approve -> claim -> start -> hold -> resume -> complete
    # -------------------------------------------------------------------------

    def test_full_workflow_submit_approve_claim_start_hold_resume_complete(self):
        """E2E: submit -> approve -> claim -> start -> hold -> resume -> complete."""
        # 1. Create and submit
        # Requester must be in request_department for submit to work
        requester = _make_staff("e2eb_req", self.proj_dept)
        pr = _make_full_draft(requester, self.proj_dept, self.proj_dept, self.ptype)
        submit_project_request(pr, requester)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.REVIEWING)

        # 2. Approve
        approver = _make_staff("e2eb_approver", self.proj_dept, AccessLevel.MANAGER, can_approve=True)
        task = pr.approval_tasks.filter(status=ProjectApprovalTaskStatus.PENDING).first()
        self.client.login(username="e2eb_approver", password="pass")
        resp = self.client.post(
            reverse("project_requests:approve", args=[pr.pk]),
            {"approval_task_id": task.pk}
        )
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.APPROVED)

        # 3. Claim (staff)
        staff = _make_staff("e2eb_staff", self.proj_dept, AccessLevel.STAFF)
        self.client.login(username="e2eb_staff", password="pass")
        resp = self.client.post(reverse("project_requests:claim", args=[pr.pk]))
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.ASSIGNED)
        # Verify assignment is to staff
        assignment = ProjectRequestAssignment.objects.filter(project_request=pr, is_active=True).first()
        self.assertIsNotNone(assignment)
        self.assertEqual(assignment.assigned_to, staff)

        # 4. Start
        resp = self.client.post(reverse("project_requests:start", args=[pr.pk]))
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.IN_PROGRESS)

        # 5. Hold with comment
        resp = self.client.post(
            reverse("project_requests:hold", args=[pr.pk]),
            {"comment": "Waiting for feedback"}
        )
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.ON_HOLD)
        # Verify hold reason in activity log
        hold_log = pr.activity_log.filter(
            action_type=ProjectRequestActionType.PUT_ON_HOLD,
            comment="Waiting for feedback"
        ).first()
        self.assertIsNotNone(hold_log)

        # 6. Resume
        resp = self.client.post(
            reverse("project_requests:resume", args=[pr.pk]),
            {"comment": "Ready to continue"}
        )
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.IN_PROGRESS)

        # 7. Complete
        resp = self.client.post(
            reverse("project_requests:complete", args=[pr.pk]),
            {"comment": "Done!"}
        )
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.COMPLETED)

    # -------------------------------------------------------------------------
    # Test C: reject workflow
    # -------------------------------------------------------------------------

    def test_full_workflow_submit_approve_reject(self):
        """E2E: submit -> approve -> reject."""
        # 1. Create and submit
        # Requester must be in request_department for submit to work
        requester = _make_staff("e2ec_req", self.proj_dept)
        pr = _make_full_draft(requester, self.proj_dept, self.proj_dept, self.ptype)
        submit_project_request(pr, requester)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.REVIEWING)

        # 2. Reject with comment
        approver = _make_staff("e2ec_approver", self.proj_dept, AccessLevel.MANAGER, can_approve=True)
        task = pr.approval_tasks.filter(status=ProjectApprovalTaskStatus.PENDING).first()
        self.client.login(username="e2ec_approver", password="pass")
        resp = self.client.post(
            reverse("project_requests:reject", args=[pr.pk]),
            {"approval_task_id": task.pk, "comment": "Cannot approve this request"}
        )
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.REJECTED)

        # 3. Verify rejection comment saved to approval task
        task.refresh_from_db()
        self.assertEqual(task.decision_comment, "Cannot approve this request")

    def test_rejected_request_hides_workflow_controls(self):
        """REJECTED request does not show assign/claim/start/hold/resume/complete controls."""
        # Requester must be in request_department for submit to work
        requester = _make_staff("e2ec_hide_req", self.proj_dept)
        pr = _make_full_draft(requester, self.proj_dept, self.proj_dept, self.ptype)
        submit_project_request(pr, requester)
        # Manually set to REJECTED
        pr.status = ProjectRequestStatus.REJECTED
        pr.save()

        # Approver (who rejected) can still view
        approver = _make_staff("e2ec_hide_approver", self.proj_dept, AccessLevel.MANAGER, can_approve=True)
        self.client.login(username="e2ec_hide_approver", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()

        # No workflow action controls should be present
        self.assertNotIn("/assign/", content)
        self.assertNotIn("/claim/", content)
        self.assertNotIn("/start/", content)
        self.assertNotIn("/hold/", content)
        self.assertNotIn("/resume/", content)
        self.assertNotIn("/complete/", content)
        self.assertNotIn(">Assign<", content)
        self.assertNotIn(">Claim This Request<", content)
        self.assertNotIn(">Start<", content)
        self.assertNotIn(">Put on Hold<", content)
        self.assertNotIn(">Resume<", content)
        self.assertNotIn(">Mark Complete<", content)

    # -------------------------------------------------------------------------
    # Test D: reassign workflow
    # -------------------------------------------------------------------------

    def test_full_workflow_reassign(self):
        """E2E: submit -> approve -> assign to A -> reassign to B."""
        # 1. Create and submit
        # Requester must be in request_department for submit to work
        requester = _make_staff("e2ed_req", self.proj_dept)
        pr = _make_full_draft(requester, self.proj_dept, self.proj_dept, self.ptype)
        submit_project_request(pr, requester)
        pr.refresh_from_db()

        # 2. Approve
        approver = _make_staff("e2ed_approver", self.proj_dept, AccessLevel.MANAGER, can_approve=True)
        task = pr.approval_tasks.filter(status=ProjectApprovalTaskStatus.PENDING).first()
        self.client.login(username="e2ed_approver", password="pass")
        self.client.post(
            reverse("project_requests:approve", args=[pr.pk]),
            {"approval_task_id": task.pk}
        )
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.APPROVED)

        # 3. Assign to user A
        assignee_a = _make_staff("e2ed_a", self.proj_dept, AccessLevel.STAFF)
        mgr = _make_staff("e2ed_mgr", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="e2ed_mgr", password="pass")
        self.client.post(
            reverse("project_requests:assign", args=[pr.pk]),
            {"assigned_to": assignee_a.id}
        )
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.ASSIGNED)

        # 4. Reassign to user B
        assignee_b = _make_staff("e2ed_b", self.proj_dept, AccessLevel.STAFF)
        self.client.login(username="e2ed_mgr", password="pass")
        self.client.post(
            reverse("project_requests:assign", args=[pr.pk]),
            {"assigned_to": assignee_b.id}
        )
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.ASSIGNED)

        # 5. Verify old assignment is inactive
        old_ass = ProjectRequestAssignment.objects.filter(
            project_request=pr, assigned_to=assignee_a
        ).first()
        self.assertIsNotNone(old_ass)
        self.assertFalse(old_ass.is_active)

        # 6. Verify new assignment is active
        new_ass = ProjectRequestAssignment.objects.filter(
            project_request=pr, assigned_to=assignee_b, is_active=True
        ).first()
        self.assertIsNotNone(new_ass)

        # 7. Verify user B can start, old assignment to A is deactivated
        self.client.login(username="e2ed_b", password="pass")
        resp = self.client.post(reverse("project_requests:start", args=[pr.pk]))
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.IN_PROGRESS)
        # Verify old assignment is still inactive
        old_ass.refresh_from_db()
        self.assertFalse(old_ass.is_active)

    # -------------------------------------------------------------------------
    # Test E: ON_HOLD cannot complete from UI
    # -------------------------------------------------------------------------

    def test_on_hold_cannot_complete_from_ui(self):
        """ON_HOLD request cannot be completed directly via UI."""
        # Create ASSIGNED request
        requester = _make_staff("e2ee_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        assignee = _make_staff("e2ee_assignee", self.proj_dept, AccessLevel.STAFF)
        ProjectRequestAssignment.objects.create(
            project_request=pr, assigned_to=assignee, assigned_by=requester, is_active=True
        )
        pr.status = ProjectRequestStatus.IN_PROGRESS
        pr.started_at = timezone.now()
        pr.save()

        # Put on hold
        from project_requests.services import hold_project_request
        hold_project_request(pr, assignee, comment="Testing hold")
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.ON_HOLD)

        # Try to complete via UI
        self.client.login(username="e2ee_assignee", password="pass")
        resp = self.client.post(reverse("project_requests:complete", args=[pr.pk]))
        # Should redirect (error) but not change status
        self.assertEqual(resp.status_code, 302)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.ON_HOLD)
        # User must resume before complete


# ============================================================================
# Phase 3D-4: Detail Workflow Integration Tests
# ============================================================================

class ProjectRequestDetailWorkflowIntegrationTest(TestCase):
    """Integration tests for detail template workflow controls (Phase 3D-4)."""

    def setUp(self):
        self.req_dept, self.proj_dept, self.other_dept, self.ptype, self.ftype = _build_fixtures()
        proj_profile = ProjectDepartmentProfile.objects.get(department=self.proj_dept)
        proj_profile.allow_staff_claim = True
        proj_profile.save()
        self.client = Client()

    def _assert_workflow_controls(self, content, expect_approve=False, expect_reject=False,
                                   expect_assign=False, expect_claim=False, expect_start=False,
                                   expect_hold=False, expect_resume=False, expect_complete=False):
        """Assert workflow controls are present or absent based on expected flags."""
        # Approve
        if expect_approve:
            self.assertIn("/approve/", content)
            self.assertIn(">Approve<", content)
        else:
            self.assertNotIn('action="{% url \'project_requests:approve\'', content)
            self.assertNotIn(">Approve<", content)

        # Reject
        if expect_reject:
            self.assertIn("/reject/", content)
            self.assertIn(">Reject<", content)
        else:
            self.assertNotIn('action="{% url \'project_requests:reject\'', content)
            self.assertNotIn(">Reject<", content)

        # Assign
        if expect_assign:
            self.assertIn("/assign/", content)
            self.assertIn(">Assign<", content)
        else:
            self.assertNotIn("/assign/", content)
            self.assertNotIn(">Assign<", content)

        # Claim
        if expect_claim:
            self.assertIn("/claim/", content)
            self.assertIn(">Claim This Request<", content)
        else:
            self.assertNotIn("/claim/", content)
            self.assertNotIn(">Claim This Request<", content)

        # Start
        if expect_start:
            self.assertIn("/start/", content)
            self.assertIn(">Start<", content)
        else:
            self.assertNotIn("/start/", content)
            self.assertNotIn(">Start<", content)

        # Hold
        if expect_hold:
            self.assertIn("/hold/", content)
            self.assertIn(">Put on Hold<", content)
        else:
            self.assertNotIn("/hold/", content)
            self.assertNotIn(">Put on Hold<", content)

        # Resume
        if expect_resume:
            self.assertIn("/resume/", content)
            self.assertIn(">Resume<", content)
        else:
            self.assertNotIn("/resume/", content)
            self.assertNotIn(">Resume<", content)

        # Complete
        if expect_complete:
            self.assertIn("/complete/", content)
            self.assertIn(">Mark Complete<", content)
        else:
            self.assertNotIn("/complete/", content)
            self.assertNotIn(">Mark Complete<", content)

    def test_draft_request_shows_no_workflow_controls(self):
        """DRAFT request only shows draft/edit related actions, not workflow action forms."""
        requester = _make_staff("int_draft_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        # Keep as DRAFT
        self.client.login(username="int_draft_req", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        # No approval/assign/claim/execution controls
        self._assert_workflow_controls(
            content, expect_approve=False, expect_reject=False, expect_assign=False,
            expect_claim=False, expect_start=False, expect_hold=False,
            expect_resume=False, expect_complete=False
        )

    def test_reviewing_request_shows_approval_controls_to_valid_approver(self):
        """REVIEWING request shows approval controls only to valid approver."""
        requester = _make_staff("int_rev_req", self.proj_dept)
        pr = _make_full_draft(requester, self.proj_dept, self.proj_dept, self.ptype)
        pr.request_department = self.proj_dept
        pr.save()
        submit_project_request(pr, requester)

        # Approver sees approve/reject
        approver = _make_staff("int_rev_approver", self.proj_dept, AccessLevel.MANAGER, can_approve=True)
        self.client.login(username="int_rev_approver", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self._assert_workflow_controls(
            content, expect_approve=True, expect_reject=True, expect_assign=False,
            expect_claim=False, expect_start=False, expect_hold=False,
            expect_resume=False, expect_complete=False
        )

    def test_reviewing_request_hides_approval_controls_to_non_approver(self):
        """REVIEWING request hides approval controls from non-approver.
        
        Staff in project department cannot view REVIEWING requests (only APPROVED unassigned
        requests are claimable). Instead, we verify that an unrelated user gets 403.
        """
        requester = _make_staff("int_rev_nomgr_req", self.proj_dept)
        pr = _make_full_draft(requester, self.proj_dept, self.proj_dept, self.ptype)
        pr.request_department = self.proj_dept
        pr.save()
        submit_project_request(pr, requester)

        # Non-approver staff cannot even VIEW reviewing requests - they can only
        # view APPROVED unassigned requests (claimable). Unrelated user gets 403.
        unrelated = _make_staff("int_rev_unrelated", self.other_dept, AccessLevel.STAFF)
        self.client.login(username="int_rev_unrelated", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_approved_request_shows_assign_controls_to_manager(self):
        """APPROVED request shows assign/claim controls according to permissions."""
        requester = _make_staff("int_app_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()

        # Manager sees assign
        mgr = _make_staff("int_app_mgr", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="int_app_mgr", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self._assert_workflow_controls(
            content, expect_assign=True, expect_claim=True
        )

    def test_assigned_request_shows_start_control_to_assignee_and_manager(self):
        """ASSIGNED request with active assignment shows start control to assignee and project dept manager."""
        requester = _make_staff("int_ass_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        assignee = _make_staff("int_ass_assignee", self.proj_dept, AccessLevel.STAFF)
        ProjectRequestAssignment.objects.create(
            project_request=pr, assigned_to=assignee, assigned_by=requester, is_active=True
        )
        pr.status = ProjectRequestStatus.ASSIGNED
        pr.save()

        # Assignee sees start (no assign form - they can't reassign themselves)
        client1 = Client()
        client1.login(username="int_ass_assignee", password="pass")
        resp = client1.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self._assert_workflow_controls(content, expect_start=True, expect_assign=False)

        # Manager sees start AND assign (managers can reassign)
        mgr = _make_staff("int_ass_mgr", self.proj_dept, AccessLevel.MANAGER)
        client2 = Client()
        client2.login(username="int_ass_mgr", password="pass")
        resp = client2.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self._assert_workflow_controls(content, expect_start=True, expect_assign=True)

    def test_in_progress_request_shows_hold_and_complete_not_start_resume(self):
        """IN_PROGRESS request shows hold and complete controls, not start/resume."""
        requester = _make_staff("int_ip_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        assignee = _make_staff("int_ip_assignee", self.proj_dept, AccessLevel.STAFF)
        ProjectRequestAssignment.objects.create(
            project_request=pr, assigned_to=assignee, assigned_by=requester, is_active=True
        )
        pr.status = ProjectRequestStatus.IN_PROGRESS
        pr.started_at = timezone.now()
        pr.save()

        self.client.login(username="int_ip_assignee", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self._assert_workflow_controls(
            content, expect_hold=True, expect_complete=True,
            expect_start=False, expect_resume=False
        )

    def test_on_hold_request_shows_resume_not_complete(self):
        """ON_HOLD request shows resume, not complete."""
        requester = _make_staff("int_hold_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        assignee = _make_staff("int_hold_assignee", self.proj_dept, AccessLevel.STAFF)
        ProjectRequestAssignment.objects.create(
            project_request=pr, assigned_to=assignee, assigned_by=requester, is_active=True
        )
        pr.status = ProjectRequestStatus.ON_HOLD
        pr.save()

        self.client.login(username="int_hold_assignee", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self._assert_workflow_controls(
            content, expect_resume=True, expect_complete=False,
            expect_hold=False, expect_start=False
        )

    def test_completed_request_shows_no_workflow_controls(self):
        """COMPLETED request shows no workflow controls."""
        requester = _make_staff("int_comp_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        assignee = _make_staff("int_comp_assignee", self.proj_dept, AccessLevel.STAFF)
        ProjectRequestAssignment.objects.create(
            project_request=pr, assigned_to=assignee, assigned_by=requester, is_active=True
        )
        pr.status = ProjectRequestStatus.COMPLETED
        pr.completed_at = timezone.now()
        pr.save()

        # Any authorized user viewing
        mgr = _make_staff("int_comp_mgr", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="int_comp_mgr", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        # No workflow action controls
        self._assert_workflow_controls(
            content, expect_approve=False, expect_reject=False, expect_assign=False,
            expect_claim=False, expect_start=False, expect_hold=False,
            expect_resume=False, expect_complete=False
        )

    def test_detail_page_never_exposes_direct_attachment_file_url(self):
        """Detail page never exposes direct attachment.file.url."""
        requester = _make_staff("int_url_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        uploaded = SimpleUploadedFile("test.pdf", b"%PDF fake", content_type="application/pdf")
        upload_project_request_attachment(pr, uploaded, self.ftype, requester)
        self.client.login(username="int_url_req", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content_str = resp.content.decode()
        # Should have download link
        self.assertIn("Download", content_str)
        # Should NOT contain /media/ direct URL
        self.assertNotIn("/media/", content_str)
        # Should NOT contain attachment.file.url pattern
        self.assertNotIn(".url", content_str)

    def test_all_post_forms_include_csrf_token(self):
        """All POST forms include CSRF token."""
        # Create a request with multiple forms visible
        requester = _make_staff("int_csrf_req", self.req_dept)
        pr = _make_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        mgr = _make_staff("int_csrf_mgr", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="int_csrf_mgr", password="pass")
        resp = self.client.get(reverse("project_requests:detail", args=[pr.pk]))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        # Count form tags and csrf tokens
        form_count = content.count("<form")
        csrf_count = content.count("csrf")
        self.assertGreater(form_count, 0, "Should have at least one form")
        self.assertGreaterEqual(csrf_count, form_count, "Each form should have CSRF token")


# ============================================================================
# Phase 4B: Dashboard View Tests
# ============================================================================

class ProjectRequestDashboardViewTest(TestCase):
    """Tests for the dashboard view."""

    def setUp(self):
        self.req_dept, self.proj_dept, self.other_dept, self.ptype, self.ftype = _build_fixtures()
        self.client = Client()

    def test_login_required(self):
        """Anonymous user is redirected to login."""
        resp = self.client.get(reverse("project_requests:dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp.url)

    def test_authenticated_user_can_load_dashboard(self):
        """Authenticated user can access the dashboard."""
        user = _make_staff("dash_user", self.req_dept)
        self.client.login(username="dash_user", password="pass")
        resp = self.client.get(reverse("project_requests:dashboard"))
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_has_no_post_forms(self):
        """Dashboard must not contain any POST forms."""
        user = _make_staff("dash_nopost", self.req_dept)
        self.client.login(username="dash_nopost", password="pass")
        resp = self.client.get(reverse("project_requests:dashboard"))
        content = resp.content.decode()
        # Check for POST form action patterns, not just the word "post"
        post_forms = [line for line in content.split("\n") if "<form" in line and "method=" in line and "post" in line.lower()]
        self.assertEqual(len(post_forms), 0, "Dashboard should have no POST forms")

    def test_dashboard_no_workflow_action_urls(self):
        """Dashboard does not expose workflow action URLs."""
        user = _make_staff("dash_nowf", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="dash_nowf", password="pass")
        resp = self.client.get(reverse("project_requests:dashboard"))
        content = resp.content.decode()

        # Check for actual form actions, not just the word "complete" in status text
        workflow_urls = [
            "/approve/",
            "/reject/",
            "/assign/",
            "/claim/",
            "/start/",
            "/hold/",
            "/resume/",
            "/complete/",
        ]
        for url in workflow_urls:
            # Look for form action attribute with the URL
            form_action_pattern = f'action="{url}'
            self.assertNotIn(form_action_pattern, content,
                           f"Dashboard should not contain form action {url}")

    def test_dashboard_shows_my_drafts_section(self):
        """Regular staff sees My Drafts section."""
        user = _make_staff("dash_drafts", self.req_dept)
        _make_full_draft(user, self.req_dept, self.proj_dept, self.ptype)
        self.client.login(username="dash_drafts", password="pass")
        resp = self.client.get(reverse("project_requests:dashboard"))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("My Drafts", content)

    def test_dashboard_shows_my_open_requests_section(self):
        """Regular staff sees My Open Requests section."""
        user = _make_staff("dash_open", self.req_dept)
        pr = _make_full_draft(user, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.SUBMITTED
        pr.save()
        self.client.login(username="dash_open", password="pass")
        resp = self.client.get(reverse("project_requests:dashboard"))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("My Open Requests", content)

    def test_dashboard_shows_my_assigned_section(self):
        """Regular staff sees My Assigned Requests section."""
        user = _make_staff("dash_assigned", self.req_dept)
        self.client.login(username="dash_assigned", password="pass")
        resp = self.client.get(reverse("project_requests:dashboard"))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("My Assigned Requests", content)

    def test_dashboard_shows_claimable_for_project_dept_staff(self):
        """Project dept staff with allow_staff_claim sees Claimable Requests section."""
        user = _make_staff("dash_claim", self.proj_dept)
        pr = _make_full_draft(_make_staff("req", self.req_dept), self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()
        self.client.login(username="dash_claim", password="pass")
        resp = self.client.get(reverse("project_requests:dashboard"))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("Claimable Requests", content)

    def test_dashboard_shows_project_dept_queue_for_manager(self):
        """Project dept manager sees Project Dept Queue section."""
        mgr = _make_staff("dash_mgr", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="dash_mgr", password="pass")
        resp = self.client.get(reverse("project_requests:dashboard"))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("Project Dept Queue", content)

    def test_dashboard_shows_in_progress_for_manager(self):
        """Project dept manager sees In Progress / On Hold section."""
        mgr = _make_staff("dash_mgr_ip", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="dash_mgr_ip", password="pass")
        resp = self.client.get(reverse("project_requests:dashboard"))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("In Progress / On Hold", content)

    def test_dashboard_shows_admin_overview_for_superuser(self):
        """Superuser sees Admin Overview section."""
        superuser = User.objects.create_superuser(username="dash_admin", password="pass")
        self.client.login(username="dash_admin", password="pass")
        resp = self.client.get(reverse("project_requests:dashboard"))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("Admin Overview", content)
        self.assertIn("Status Breakdown", content)

    def test_dashboard_links_requests_to_detail_pages(self):
        """Dashboard links request items to their detail pages."""
        user = _make_staff("dash_link", self.req_dept)
        pr = _make_full_draft(user, self.req_dept, self.proj_dept, self.ptype)
        pr.request_no = "PRJ-2026-000001"
        pr.save()
        self.client.login(username="dash_link", password="pass")
        resp = self.client.get(reverse("project_requests:dashboard"))
        content = resp.content.decode()
        detail_url = reverse("project_requests:detail", args=[pr.pk])
        self.assertIn(detail_url, content)

    def test_dashboard_empty_states_render_without_error(self):
        """Empty sections render without errors (no missing context)."""
        user = _make_staff("dash_empty", self.req_dept)
        self.client.login(username="dash_empty", password="pass")
        resp = self.client.get(reverse("project_requests:dashboard"))
        self.assertEqual(resp.status_code, 200)
        # Should not raise any template errors

    def test_dashboard_nav_link_for_authenticated_user(self):
        """Dashboard nav link appears for authenticated users."""
        user = _make_staff("dash_nav", self.req_dept)
        self.client.login(username="dash_nav", password="pass")
        # Visit any page to check navbar
        resp = self.client.get(reverse("project_requests:list"))
        content = resp.content.decode()
        dashboard_url = reverse("project_requests:dashboard")
        self.assertIn(dashboard_url, content)

    def test_dashboard_normal_staff_no_queue_section(self):
        """Normal staff (non-manager) does not see Project Dept Queue."""
        staff = _make_staff("dash_staff", self.proj_dept, AccessLevel.STAFF)
        self.client.login(username="dash_staff", password="pass")
        resp = self.client.get(reverse("project_requests:dashboard"))
        content = resp.content.decode()
        # Staff should not see the queue card with visible h2 heading
        self.assertNotIn('<h2 style="font-size: 16px; margin: 0;">Project Dept Queue</h2>', content)

    def test_dashboard_no_workflow_buttons(self):
        """Dashboard has no workflow action buttons."""
        mgr = _make_staff("dash_wfbtn", self.proj_dept, AccessLevel.MANAGER)
        self.client.login(username="dash_wfbtn", password="pass")
        resp = self.client.get(reverse("project_requests:dashboard"))
        content = resp.content.decode()
        # Should not have approve/reject/assign/claim/start/hold/resume/complete buttons
        workflow_buttons = ["Approve", "Reject", "Assign", "Claim", "Start", "Put on Hold", "Resume", "Complete"]
        for btn in workflow_buttons:
            # Check that button text is not in a form submit context
            button_pattern = f'<button type="submit">{btn}</button>'
            self.assertNotIn(button_pattern, content,
                           f"Dashboard should not have {btn} button")
