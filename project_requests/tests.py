"""Tests for project_requests foundation models."""

import os
from datetime import date

from django.test import TestCase
from django.core.management import call_command
from django.db import IntegrityError

from accounts.models import Department, User, AccessLevel, UserDepartment
from project_requests.models import (
    ProjectRequestStatus,
    ProjectRequestPriority,
    ProjectApprovalTaskStatus,
    ProjectApprovalRole,
    ProjectRequestActionType,
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


# ---------------------------------------------------------------------------
# 1. TextChoices tests
# ---------------------------------------------------------------------------

class TextChoicesTest(TestCase):
    """Verify all TextChoices contain expected values."""

    def test_project_request_status_values(self):
        expected = [
            "DRAFT", "SUBMITTED", "REVIEWING", "APPROVED", "REJECTED",
            "ASSIGNED", "IN_PROGRESS", "ON_HOLD", "COMPLETED", "CANCELLED",
        ]
        actual = [c.value for c in ProjectRequestStatus]
        self.assertEqual(actual, expected)

    def test_project_request_priority_values(self):
        expected_values = [1, 2, 3, 4, 5]
        actual_values = [c.value for c in ProjectRequestPriority]
        self.assertEqual(actual_values, expected_values)

    def test_project_approval_task_status_values(self):
        expected = ["PENDING", "APPROVED", "REJECTED"]
        actual = [c.value for c in ProjectApprovalTaskStatus]
        self.assertEqual(actual, expected)

    def test_project_approval_role_values(self):
        expected = ["REQUEST_DEPT_MANAGER", "PROJECT_DEPT_MANAGER", "PROJECT_DEPT_VP"]
        actual = [c.value for c in ProjectApprovalRole]
        self.assertEqual(actual, expected)

    def test_project_request_action_type_values(self):
        expected = [
            "DRAFT_CREATED", "SUBMITTED", "APPROVAL_CREATED", "APPROVED",
            "REJECTED", "ADDITIONAL_APPROVAL_REQUESTED", "ASSIGNED",
            "CLAIMED", "STARTED", "PUT_ON_HOLD", "RESUMED", "COMPLETED",
            "CANCELLED", "COMMENTED", "FILE_ATTACHED",
        ]
        actual = [c.value for c in ProjectRequestActionType]
        self.assertEqual(actual, expected)


# ---------------------------------------------------------------------------
# 2. RequestNumberSequence tests
# ---------------------------------------------------------------------------

class RequestNumberSequenceTest(TestCase):
    def test_create_sequence(self):
        seq = RequestNumberSequence.objects.create(year=2026, sequence=0)
        self.assertEqual(seq.year, 2026)
        self.assertEqual(seq.sequence, 0)

    def test_str_representation(self):
        seq = RequestNumberSequence.objects.create(year=2026, sequence=5)
        self.assertEqual(str(seq), "2026 — sequence 5")

    def test_year_unique(self):
        RequestNumberSequence.objects.create(year=2026, sequence=0)
        with self.assertRaises(IntegrityError):
            RequestNumberSequence.objects.create(year=2026, sequence=1)


# ---------------------------------------------------------------------------
# 3. ProjectRequestType and ProjectRequestFileType tests
# ---------------------------------------------------------------------------

class ProjectRequestTypeTest(TestCase):
    def test_create_type(self):
        ptype = ProjectRequestType.objects.create(code="new", name="New System")
        self.assertEqual(ptype.code, "new")
        self.assertTrue(ptype.is_active)

    def test_str_representation(self):
        ptype = ProjectRequestType.objects.create(code="enh", name="Enhancement")
        self.assertEqual(str(ptype), "Enhancement")


class ProjectRequestFileTypeTest(TestCase):
    def test_create_file_type(self):
        ftype = ProjectRequestFileType.objects.create(
            code="doc", name="Document", allowed_extensions="pdf,docx",
        )
        self.assertEqual(ftype.max_file_size_mb, 25)
        self.assertTrue(ftype.is_active)

    def test_str_representation(self):
        ftype = ProjectRequestFileType.objects.create(
            code="img", name="Image", allowed_extensions="png,jpg",
        )
        self.assertEqual(str(ftype), "Image")


# ---------------------------------------------------------------------------
# 4-5. ProjectDepartmentProfile tests
# ---------------------------------------------------------------------------

class ProjectDepartmentProfileTest(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(dept_code="MIS", dept_name="Management Information Systems")

    def test_one_to_one_prevents_duplicate(self):
        ProjectDepartmentProfile.objects.create(department=self.dept)
        with self.assertRaises(IntegrityError):
            ProjectDepartmentProfile.objects.create(department=self.dept)

    def test_allow_staff_claim_defaults_true(self):
        profile = ProjectDepartmentProfile.objects.create(department=self.dept)
        self.assertTrue(profile.allow_staff_claim)

    def test_str_representation(self):
        profile = ProjectDepartmentProfile.objects.create(department=self.dept)
        self.assertEqual(str(profile), f"Profile for {self.dept}")


# ---------------------------------------------------------------------------
# 6-9. ProjectRequest tests
# ---------------------------------------------------------------------------

class ProjectRequestTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pass")
        self.dept = Department.objects.create(dept_code="ACCT", dept_name="Accounting")
        self.proj_dept = Department.objects.create(dept_code="MIS", dept_name="MIS")
        self.ptype = ProjectRequestType.objects.create(code="new", name="New System")

    def test_create_draft_with_nullable_fields(self):
        """ProjectRequest can be created as an incomplete DRAFT."""
        pr = ProjectRequest.objects.create(
            requester=self.user,
            request_department=self.dept,
        )
        self.assertEqual(pr.status, ProjectRequestStatus.DRAFT)
        self.assertIsNone(pr.request_no)
        self.assertEqual(pr.project_name, "")

    def test_str_with_request_no(self):
        pr = ProjectRequest.objects.create(
            request_no="PR-2026-0001",
            project_name="Test Project",
            requester=self.user,
            request_department=self.dept,
        )
        self.assertEqual(str(pr), "PR-2026-0001 - Test Project")

    def test_str_without_request_no(self):
        pr = ProjectRequest.objects.create(
            requester=self.user,
            request_department=self.dept,
        )
        self.assertEqual(str(pr), "Draft Project Request")

    def test_status_defaults_to_draft(self):
        pr = ProjectRequest.objects.create(
            requester=self.user,
            request_department=self.dept,
        )
        self.assertEqual(pr.status, ProjectRequestStatus.DRAFT)

    def test_priority_accepts_valid_values(self):
        for val in [1, 2, 3, 4, 5]:
            pr = ProjectRequest.objects.create(
                requester=self.user,
                request_department=self.dept,
                priority=val,
            )
            pr.full_clean()  # Should not raise

    def test_priority_rejects_invalid_values(self):
        pr = ProjectRequest.objects.create(
            requester=self.user,
            request_department=self.dept,
            priority=99,
        )
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            pr.full_clean()


# ---------------------------------------------------------------------------
# 10-11. ProjectRequestApprovalTask tests
# ---------------------------------------------------------------------------

class ProjectRequestApprovalTaskTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="bob", password="pass")
        self.dept = Department.objects.create(dept_code="MIS", dept_name="MIS")
        self.pr = ProjectRequest.objects.create(
            requester=self.user,
            request_department=self.dept,
        )

    def test_unique_constraint_prevents_duplicate(self):
        ProjectRequestApprovalTask.objects.create(
            project_request=self.pr,
            department=self.dept,
            role=ProjectApprovalRole.REQUEST_DEPT_MANAGER,
        )
        with self.assertRaises(IntegrityError):
            ProjectRequestApprovalTask.objects.create(
                project_request=self.pr,
                department=self.dept,
                role=ProjectApprovalRole.REQUEST_DEPT_MANAGER,
            )

    def test_acted_fields(self):
        approver = User.objects.create_user(username="mgr", password="pass")
        task = ProjectRequestApprovalTask.objects.create(
            project_request=self.pr,
            department=self.dept,
            role=ProjectApprovalRole.REQUEST_DEPT_MANAGER,
        )
        task.acted_by = approver
        task.status = ProjectApprovalTaskStatus.APPROVED
        task.decision_comment = "Looks good"
        task.save()
        self.assertEqual(task.acted_by, approver)
        self.assertEqual(task.decision_comment, "Looks good")


# ---------------------------------------------------------------------------
# 12. ProjectRequestAssignment tests
# ---------------------------------------------------------------------------

class ProjectRequestAssignmentTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="dev1", password="pass")
        self.assigner = User.objects.create_user(username="mgr", password="pass")
        self.dept = Department.objects.create(dept_code="MIS", dept_name="MIS")
        self.pr = ProjectRequest.objects.create(
            requester=self.user,
            request_department=self.dept,
        )

    def test_active_duplicate_blocked(self):
        ProjectRequestAssignment.objects.create(
            project_request=self.pr,
            assigned_to=self.user,
            assigned_by=self.assigner,
        )
        with self.assertRaises(IntegrityError):
            ProjectRequestAssignment.objects.create(
                project_request=self.pr,
                assigned_to=self.user,
                assigned_by=self.assigner,
            )

    def test_inactive_does_not_block_reassign(self):
        old = ProjectRequestAssignment.objects.create(
            project_request=self.pr,
            assigned_to=self.user,
            assigned_by=self.assigner,
        )
        old.is_active = False
        old.save()
        # Re-assigning same user should work now
        new = ProjectRequestAssignment.objects.create(
            project_request=self.pr,
            assigned_to=self.user,
            assigned_by=self.assigner,
        )
        self.assertTrue(new.is_active)


# ---------------------------------------------------------------------------
# 13. ProjectRequestAttachment tests
# ---------------------------------------------------------------------------

class ProjectRequestAttachmentTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="uploader", password="pass")
        self.dept = Department.objects.create(dept_code="MIS", dept_name="MIS")
        self.pr = ProjectRequest.objects.create(
            requester=self.user,
            request_department=self.dept,
        )
        self.ftype = ProjectRequestFileType.objects.create(
            code="doc", name="Document", allowed_extensions="pdf,docx",
        )

    def test_create_attachment_with_metadata(self):
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.write(b"fake content")
        tmp.close()
        attachment = ProjectRequestAttachment.objects.create(
            project_request=self.pr,
            file=tmp.name,
            original_filename="proposal.pdf",
            file_type=self.ftype,
            uploaded_by=self.user,
            file_size=1234,
        )
        self.assertEqual(attachment.file_size, 1234)
        self.assertEqual(attachment.original_filename, "proposal.pdf")
        os.unlink(tmp.name)


# ---------------------------------------------------------------------------
# 14-15. ProjectRequestActivityLog tests
# ---------------------------------------------------------------------------

class ProjectRequestActivityLogTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="actor", password="pass")
        self.dept = Department.objects.create(dept_code="MIS", dept_name="MIS")
        self.pr = ProjectRequest.objects.create(
            requester=self.user,
            request_department=self.dept,
        )

    def test_create_activity_log(self):
        log = ProjectRequestActivityLog.objects.create(
            project_request=self.pr,
            action_type=ProjectRequestActionType.DRAFT_CREATED,
            description="Draft created",
            actor=self.user,
        )
        self.assertEqual(log.action_type, ProjectRequestActionType.DRAFT_CREATED)

    def test_ordering_newest_first(self):
        import time
        ProjectRequestActivityLog.objects.create(
            project_request=self.pr,
            action_type=ProjectRequestActionType.DRAFT_CREATED,
            description="First",
        )
        time.sleep(0.05)
        ProjectRequestActivityLog.objects.create(
            project_request=self.pr,
            action_type=ProjectRequestActionType.COMMENTED,
            description="Second",
        )
        logs = list(ProjectRequestActivityLog.objects.all())
        self.assertEqual(logs[0].description, "Second")
        self.assertEqual(logs[1].description, "First")


# ---------------------------------------------------------------------------
# 16. Admin import test
# ---------------------------------------------------------------------------

class AdminImportTest(TestCase):
    def test_admin_imports_do_not_fail(self):
        """Ensure admin module can be imported without errors."""
        from project_requests import admin  # noqa: F401
        self.assertTrue(True)
