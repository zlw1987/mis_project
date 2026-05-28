"""Comprehensive tests for project_requests Phase 2A service layer."""

from datetime import date, timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

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
from project_requests.services import (
    generate_request_no,
    create_project_request_draft,
    validate_required_for_submit,
    check_duplicate_open_request,
    create_activity_log,
    generate_required_approvals,
    submit_project_request,
    upload_project_request_attachment,
    approve_project_request,
    reject_project_request,
    assign_project_request,
    claim_project_request,
    OPEN_STATUSES,
)
from project_requests.permissions import (
    can_view_project_request,
    can_submit_project_request,
    can_assign_project_request,
    can_claim_project_request,
    can_attach_file,
    can_approve_project_request_task,
    can_reject_project_request_task,
    get_project_request_action_context,
)
from project_requests.selectors import (
    get_visible_project_requests,
    get_my_project_requests,
    get_assigned_to_me,
    get_my_pending_approval_tasks,
    get_overdue_project_requests,
)


# ============================================================================
# Fixtures helper
# ============================================================================

def _create_full_draft(user, req_dept, proj_dept, ptype, **overrides):
    """Create a complete draft ready for submission."""
    defaults = {
        "project_name": "Test Project",
        "requester": user,
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
# 1. Request Number Generation Tests
# ============================================================================

class RequestNumberGenerationTest(TestCase):
    def test_format_matches_prj_yyyy_000001(self):
        no = generate_request_no()
        self.assertRegex(no, r"^PRJ-\d{4}-\d{6}$")

    def test_sequence_increments(self):
        no1 = generate_request_no()
        no2 = generate_request_no()
        # Extract sequence portion
        seq1 = int(no1.split("-")[2])
        seq2 = int(no2.split("-")[2])
        self.assertEqual(seq2, seq1 + 1)

    def test_create_draft_generates_number(self):
        user = User.objects.create_user(username="u1", password="pass")
        dept = Department.objects.create(dept_code="D1", dept_name="Dept 1")
        pr = create_project_request_draft(requester=user, request_department=dept)
        self.assertIsNotNone(pr.request_no)
        self.assertRegex(pr.request_no, r"^PRJ-\d{4}-\d{6}$")
        self.assertEqual(pr.status, ProjectRequestStatus.DRAFT)

    def test_abandoned_draft_gap_accepted(self):
        """Two drafts created, second has sequence +1 (gap acceptable)."""
        user = User.objects.create_user(username="u1", password="pass")
        dept = Department.objects.create(dept_code="D1", dept_name="Dept 1")
        pr1 = create_project_request_draft(requester=user, request_department=dept)
        pr2 = create_project_request_draft(requester=user, request_department=dept)
        seq1 = int(pr1.request_no.split("-")[2])
        seq2 = int(pr2.request_no.split("-")[2])
        self.assertEqual(seq2, seq1 + 1)


# ============================================================================
# 2. Required-on-submit Validation Tests
# ============================================================================

class RequiredOnSubmitValidationTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pass")
        self.dept = Department.objects.create(dept_code="ACCT", dept_name="Accounting")
        self.proj_dept = Department.objects.create(dept_code="MIS", dept_name="MIS")
        self.profile = ProjectDepartmentProfile.objects.create(
            department=self.proj_dept,
            is_active=True,
            can_receive_project_requests=True,
        )
        self.ptype = ProjectRequestType.objects.create(code="new", name="New System", is_active=True)
        UserDepartment.objects.create(
            user=self.user, department=self.dept,
            access_level=AccessLevel.STAFF, is_active=True,
        )

    def test_incomplete_draft_can_exist(self):
        pr = ProjectRequest.objects.create(
            requester=self.user,
            request_department=self.dept,
        )
        self.assertEqual(pr.status, ProjectRequestStatus.DRAFT)

    def test_submit_missing_scope_summary_fails(self):
        pr = ProjectRequest.objects.create(
            requester=self.user,
            request_department=self.dept,
            project_department=self.proj_dept,
            request_type=self.ptype,
            priority=3,
            needed_by_date=date(2026, 12, 31),
            project_name="Test",
            business_problem="P",
            in_scope="I",
            expected_deliverables="D",
            acceptance_criteria="A",
            # scope_summary missing
        )
        with self.assertRaises(ValidationError) as cm:
            validate_required_for_submit(pr)
        self.assertIn("scope_summary", cm.exception.message_dict)

    def test_submit_missing_project_department_fails(self):
        pr = ProjectRequest.objects.create(
            requester=self.user,
            request_department=self.dept,
            project_name="Test",
            request_type=self.ptype,
            priority=3,
            needed_by_date=date(2026, 12, 31),
            scope_summary="S",
            business_problem="P",
            in_scope="I",
            expected_deliverables="D",
            acceptance_criteria="A",
        )
        with self.assertRaises(ValidationError):
            validate_required_for_submit(pr)

    def test_inactive_project_dept_profile_blocks_submit(self):
        self.profile.is_active = False
        self.profile.save()
        pr = ProjectRequest.objects.create(
            requester=self.user,
            request_department=self.dept,
            project_department=self.proj_dept,
            request_type=self.ptype,
            priority=3,
            needed_by_date=date(2026, 12, 31),
            project_name="Test",
            scope_summary="S",
            business_problem="P",
            in_scope="I",
            expected_deliverables="D",
            acceptance_criteria="A",
        )
        with self.assertRaises(ValidationError) as cm:
            validate_required_for_submit(pr)
        self.assertIn("project_department", cm.exception.message_dict)

    def test_can_receive_false_blocks_submit(self):
        self.profile.can_receive_project_requests = False
        self.profile.save()
        pr = ProjectRequest.objects.create(
            requester=self.user,
            request_department=self.dept,
            project_department=self.proj_dept,
            request_type=self.ptype,
            priority=3,
            needed_by_date=date(2026, 12, 31),
            project_name="Test",
            scope_summary="S",
            business_problem="P",
            in_scope="I",
            expected_deliverables="D",
            acceptance_criteria="A",
        )
        with self.assertRaises(ValidationError):
            validate_required_for_submit(pr)


# ============================================================================
# 3. Duplicate Prevention Tests
# ============================================================================

class DuplicatePreventionTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pass")
        self.dept = Department.objects.create(dept_code="ACCT", dept_name="Accounting")
        self.proj_dept = Department.objects.create(dept_code="MIS", dept_name="MIS")
        self.ptype = ProjectRequestType.objects.create(code="new", name="New System")

    def test_duplicate_open_request_blocked(self):
        pr1 = ProjectRequest.objects.create(
            requester=self.user,
            request_department=self.dept,
            project_name="Test Project",
            request_type=self.ptype,
            status=ProjectRequestStatus.DRAFT,
        )
        pr2 = ProjectRequest(
            requester=self.user,
            request_department=self.dept,
            project_name="test project",  # case-insensitive
            request_type=self.ptype,
            status=ProjectRequestStatus.DRAFT,
        )
        with self.assertRaises(ValidationError) as cm:
            check_duplicate_open_request(pr2)
        self.assertIn("duplicate", str(cm.exception).lower())

    def test_same_name_different_requester_allowed(self):
        user2 = User.objects.create_user(username="bob", password="pass")
        pr1 = ProjectRequest.objects.create(
            requester=self.user,
            request_department=self.dept,
            project_name="Test Project",
            request_type=self.ptype,
            status=ProjectRequestStatus.DRAFT,
        )
        pr2 = ProjectRequest(
            requester=user2,
            request_department=self.dept,
            project_name="Test Project",
            request_type=self.ptype,
            status=ProjectRequestStatus.DRAFT,
        )
        check_duplicate_open_request(pr2)  # Should not raise

    def test_same_name_different_type_allowed(self):
        ptype2 = ProjectRequestType.objects.create(code="enh", name="Enhancement")
        pr1 = ProjectRequest.objects.create(
            requester=self.user,
            request_department=self.dept,
            project_name="Test Project",
            request_type=self.ptype,
            status=ProjectRequestStatus.DRAFT,
        )
        pr2 = ProjectRequest(
            requester=self.user,
            request_department=self.dept,
            project_name="Test Project",
            request_type=ptype2,
            status=ProjectRequestStatus.DRAFT,
        )
        check_duplicate_open_request(pr2)  # Should not raise

    def test_completed_old_request_does_not_block(self):
        pr1 = ProjectRequest.objects.create(
            requester=self.user,
            request_department=self.dept,
            project_name="Test Project",
            request_type=self.ptype,
            status=ProjectRequestStatus.COMPLETED,
        )
        pr2 = ProjectRequest(
            requester=self.user,
            request_department=self.dept,
            project_name="Test Project",
            request_type=self.ptype,
            status=ProjectRequestStatus.DRAFT,
        )
        check_duplicate_open_request(pr2)  # Should not raise

    def test_rejected_old_request_does_not_block(self):
        pr1 = ProjectRequest.objects.create(
            requester=self.user,
            request_department=self.dept,
            project_name="Test Project",
            request_type=self.ptype,
            status=ProjectRequestStatus.REJECTED,
        )
        pr2 = ProjectRequest(
            requester=self.user,
            request_department=self.dept,
            project_name="Test Project",
            request_type=self.ptype,
            status=ProjectRequestStatus.DRAFT,
        )
        check_duplicate_open_request(pr2)  # Should not raise

    def test_reviewing_duplicate_blocks(self):
        pr1 = ProjectRequest.objects.create(
            requester=self.user,
            request_department=self.dept,
            project_name="Test Project",
            request_type=self.ptype,
            status=ProjectRequestStatus.REVIEWING,
        )
        pr2 = ProjectRequest(
            requester=self.user,
            request_department=self.dept,
            project_name="Test Project",
            request_type=self.ptype,
            status=ProjectRequestStatus.DRAFT,
        )
        with self.assertRaises(ValidationError):
            check_duplicate_open_request(pr2)


# ============================================================================
# 4. Activity Logging Tests
# ============================================================================

class ActivityLoggingTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="actor", password="pass")
        self.dept = Department.objects.create(dept_code="MIS", dept_name="MIS")
        self.pr = ProjectRequest.objects.create(
            requester=self.user,
            request_department=self.dept,
        )

    def test_activity_log_created(self):
        log = create_activity_log(
            project_request=self.pr,
            action_type=ProjectRequestActionType.DRAFT_CREATED,
            actor=self.user,
            description="Draft created",
        )
        self.assertEqual(log.action_type, ProjectRequestActionType.DRAFT_CREATED)
        self.assertEqual(log.actor, self.user)

    def test_actor_can_be_null(self):
        log = create_activity_log(
            project_request=self.pr,
            action_type=ProjectRequestActionType.APPROVAL_CREATED,
            description="System action",
        )
        self.assertIsNone(log.actor)

    def test_from_to_status_saved(self):
        log = create_activity_log(
            project_request=self.pr,
            action_type=ProjectRequestActionType.SUBMITTED,
            from_status=ProjectRequestStatus.DRAFT,
            to_status=ProjectRequestStatus.SUBMITTED,
            description="Submitted",
        )
        self.assertEqual(log.from_status, ProjectRequestStatus.DRAFT)
        self.assertEqual(log.to_status, ProjectRequestStatus.SUBMITTED)

    def test_latest_activity_ordering(self):
        import time
        create_activity_log(
            project_request=self.pr,
            action_type=ProjectRequestActionType.DRAFT_CREATED,
            description="First",
        )
        time.sleep(0.05)
        create_activity_log(
            project_request=self.pr,
            action_type=ProjectRequestActionType.COMMENTED,
            description="Second",
        )
        logs = list(ProjectRequestActivityLog.objects.filter(project_request=self.pr))
        self.assertEqual(logs[0].description, "Second")

    # ---- Fix 7: create_activity_log updates last_activity_at ----

    def test_activity_log_updates_last_activity_at(self):
        """create_activity_log updates project_request.last_activity_at."""
        old_last = self.pr.last_activity_at
        import time
        time.sleep(0.05)
        create_activity_log(self.pr, ProjectRequestActionType.DRAFT_CREATED)
        self.pr.refresh_from_db()
        self.assertGreater(self.pr.last_activity_at, old_last)


# ============================================================================
# 5. Approval Generation Tests
# ============================================================================

class ApprovalGenerationTest(TestCase):
    def setUp(self):
        self.req_dept = Department.objects.create(dept_code="ACCT", dept_name="Accounting")
        self.proj_dept = Department.objects.create(dept_code="MIS", dept_name="MIS")
        self.ptype = ProjectRequestType.objects.create(code="new", name="New System")
        ProjectDepartmentProfile.objects.create(department=self.proj_dept)

    def _make_requester(self, username, req_dept_level, proj_dept_level=None):
        user = User.objects.create_user(username=username, password="pass")
        UserDepartment.objects.create(
            user=user, department=self.req_dept,
            access_level=req_dept_level, is_active=True,
        )
        if proj_dept_level:
            UserDepartment.objects.create(
                user=user, department=self.proj_dept,
                access_level=proj_dept_level, is_active=True,
            )
        return user

    def _make_pr(self, requester, priority=3):
        return ProjectRequest(
            requester=requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            request_type=self.ptype,
            priority=priority,
            project_name="Test",
        )

    # Staff in both depts, cross-dept request => both managers required
    def test_staff_in_both_depts_cross_dept(self):
        user = self._make_requester("staff_both", AccessLevel.STAFF, AccessLevel.STAFF)
        pr = self._make_pr(user)
        approvals = generate_required_approvals(pr)
        roles = [r for _, r in approvals]
        self.assertIn(ProjectApprovalRole.PROJECT_DEPT_MANAGER, roles)
        self.assertIn(ProjectApprovalRole.REQUEST_DEPT_MANAGER, roles)

    # Staff cross dept => request dept manager + project dept manager
    def test_staff_cross_dept(self):
        user = self._make_requester("staff_cross", AccessLevel.STAFF)
        pr = self._make_pr(user)
        approvals = generate_required_approvals(pr)
        roles = [r for _, r in approvals]
        self.assertIn(ProjectApprovalRole.REQUEST_DEPT_MANAGER, roles)
        self.assertIn(ProjectApprovalRole.PROJECT_DEPT_MANAGER, roles)

    # Staff cross dept P1 => + project dept VP
    def test_staff_cross_dept_p1(self):
        user = self._make_requester("staff_cross_p1", AccessLevel.STAFF)
        pr = self._make_pr(user, priority=1)
        approvals = generate_required_approvals(pr)
        roles = [r for _, r in approvals]
        self.assertIn(ProjectApprovalRole.REQUEST_DEPT_MANAGER, roles)
        self.assertIn(ProjectApprovalRole.PROJECT_DEPT_MANAGER, roles)
        self.assertIn(ProjectApprovalRole.PROJECT_DEPT_VP, roles)

    # Manager same project dept non-P1 => auto-approved (no approvals)
    # "Same dept" means req_dept == proj_dept (same Department object)
    def test_manager_same_dept_non_p1(self):
        # Use same department for both request and project
        same_dept = Department.objects.create(dept_code="SAME", dept_name="Same Dept")
        ProjectDepartmentProfile.objects.create(department=same_dept)
        user = User.objects.create_user(username="mgr_same", password="pass")
        UserDepartment.objects.create(
            user=user, department=same_dept,
            access_level=AccessLevel.MANAGER, is_active=True,
        )
        pr = ProjectRequest(
            requester=user,
            request_department=same_dept,
            project_department=same_dept,
            request_type=self.ptype,
            priority=3,
            project_name="Test",
        )
        approvals = generate_required_approvals(pr)
        self.assertEqual(len(approvals), 0)

    # Manager same project dept P1 => project dept VP only
    def test_manager_same_dept_p1(self):
        same_dept = Department.objects.create(dept_code="SAME2", dept_name="Same Dept 2")
        ProjectDepartmentProfile.objects.create(department=same_dept)
        user = User.objects.create_user(username="mgr_same_p1", password="pass")
        UserDepartment.objects.create(
            user=user, department=same_dept,
            access_level=AccessLevel.MANAGER, is_active=True,
        )
        pr = ProjectRequest(
            requester=user,
            request_department=same_dept,
            project_department=same_dept,
            request_type=self.ptype,
            priority=1,
            project_name="Test",
        )
        approvals = generate_required_approvals(pr)
        roles = [r for _, r in approvals]
        self.assertIn(ProjectApprovalRole.PROJECT_DEPT_VP, roles)
        self.assertNotIn(ProjectApprovalRole.PROJECT_DEPT_MANAGER, roles)

    # Manager cross dept non-P1 => project dept manager only
    def test_manager_cross_dept_non_p1(self):
        user = self._make_requester("mgr_cross", AccessLevel.MANAGER, AccessLevel.STAFF)
        pr = self._make_pr(user)
        approvals = generate_required_approvals(pr)
        roles = [r for _, r in approvals]
        self.assertIn(ProjectApprovalRole.PROJECT_DEPT_MANAGER, roles)
        self.assertNotIn(ProjectApprovalRole.REQUEST_DEPT_MANAGER, roles)

    # Manager cross dept P1 => project dept manager + project dept VP
    def test_manager_cross_dept_p1(self):
        user = self._make_requester("mgr_cross_p1", AccessLevel.MANAGER, AccessLevel.STAFF)
        pr = self._make_pr(user, priority=1)
        approvals = generate_required_approvals(pr)
        roles = [r for _, r in approvals]
        self.assertIn(ProjectApprovalRole.PROJECT_DEPT_MANAGER, roles)
        self.assertIn(ProjectApprovalRole.PROJECT_DEPT_VP, roles)
        self.assertNotIn(ProjectApprovalRole.REQUEST_DEPT_MANAGER, roles)

    # VP in project department same dept P1 => auto-approved (no VP approval)
    def test_vp_same_dept_p1(self):
        same_dept = Department.objects.create(dept_code="SAME3", dept_name="Same Dept 3")
        ProjectDepartmentProfile.objects.create(department=same_dept)
        user = User.objects.create_user(username="vp_same", password="pass")
        UserDepartment.objects.create(
            user=user, department=same_dept,
            access_level=AccessLevel.VP, is_active=True,
        )
        pr = ProjectRequest(
            requester=user,
            request_department=same_dept,
            project_department=same_dept,
            request_type=self.ptype,
            priority=1,
            project_name="Test",
        )
        approvals = generate_required_approvals(pr)
        self.assertEqual(len(approvals), 0)

    # VP cross dept P1 => project dept manager + project dept VP (VP is not VP in proj dept)
    def test_vp_cross_dept_p1_not_vp_in_proj(self):
        user = self._make_requester("vp_cross", AccessLevel.VP, AccessLevel.STAFF)
        pr = self._make_pr(user, priority=1)
        approvals = generate_required_approvals(pr)
        roles = [r for _, r in approvals]
        self.assertIn(ProjectApprovalRole.PROJECT_DEPT_MANAGER, roles)
        self.assertIn(ProjectApprovalRole.PROJECT_DEPT_VP, roles)


# ============================================================================
# 6. Submit Workflow Tests
# ============================================================================

class SubmitWorkflowTest(TestCase):
    def setUp(self):
        self.req_dept = Department.objects.create(dept_code="ACCT", dept_name="Accounting")
        self.proj_dept = Department.objects.create(dept_code="MIS", dept_name="MIS")
        self.profile = ProjectDepartmentProfile.objects.create(department=self.proj_dept)
        self.ptype = ProjectRequestType.objects.create(code="new", name="New System")

    def _make_staff_requester(self):
        user = User.objects.create_user(username="staff_sub", password="pass")
        UserDepartment.objects.create(
            user=user, department=self.req_dept,
            access_level=AccessLevel.STAFF, is_active=True,
        )
        return user

    def _make_manager_requester(self):
        user = User.objects.create_user(username="mgr_sub", password="pass")
        UserDepartment.objects.create(
            user=user, department=self.req_dept,
            access_level=AccessLevel.MANAGER, is_active=True,
        )
        UserDepartment.objects.create(
            user=user, department=self.proj_dept,
            access_level=AccessLevel.MANAGER, is_active=True,
        )
        return user

    def test_submit_incomplete_draft_fails_remains_draft(self):
        user = self._make_staff_requester()
        pr = create_project_request_draft(
            requester=user,
            request_department=self.req_dept,
        )
        with self.assertRaises(ValidationError):
            submit_project_request(pr, user)
        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.DRAFT)

    def test_submit_complete_draft_with_approvals_becomes_reviewing(self):
        user = self._make_staff_requester()
        pr = _create_full_draft(user, self.req_dept, self.proj_dept, self.ptype)
        result = submit_project_request(pr, user)
        self.assertEqual(result.status, ProjectRequestStatus.REVIEWING)
        self.assertIsNotNone(result.submitted_at)
        self.assertTrue(result.approval_tasks.exists())

    def test_submit_manager_same_dept_non_p1_becomes_approved(self):
        same_dept = Department.objects.create(
            dept_name="Same Dept", dept_code="SAME",
        )
        ProjectDepartmentProfile.objects.create(
            department=same_dept, is_active=True,
            can_receive_project_requests=True,
        )
        user = User.objects.create_user(
            username="same_mgr", is_active=True,
        )
        UserDepartment.objects.create(
            user=user, department=same_dept,
            access_level=AccessLevel.MANAGER, is_active=True,
        )
        pr = _create_full_draft(user, same_dept, same_dept, self.ptype)
        result = submit_project_request(pr, user)
        self.assertEqual(result.status, ProjectRequestStatus.APPROVED)
        self.assertIsNotNone(result.approved_at)
        self.assertEqual(result.approval_tasks.count(), 0)

    def test_submitted_at_set(self):
        user = self._make_staff_requester()
        pr = _create_full_draft(user, self.req_dept, self.proj_dept, self.ptype)
        result = submit_project_request(pr, user)
        self.assertIsNotNone(result.submitted_at)

    def test_approved_at_set_only_for_auto_approved(self):
        user = self._make_staff_requester()
        pr = _create_full_draft(user, self.req_dept, self.proj_dept, self.ptype)
        result = submit_project_request(pr, user)
        # Has approvals, so approved_at should be None
        self.assertIsNone(result.approved_at)

    def test_cannot_submit_non_draft(self):
        user = self._make_staff_requester()
        pr = _create_full_draft(user, self.req_dept, self.proj_dept, self.ptype)
        pr.status = ProjectRequestStatus.REVIEWING
        pr.save()
        with self.assertRaises(ValidationError):
            submit_project_request(pr, user)

    def test_activity_logs_created_in_sequence(self):
        user = self._make_staff_requester()
        pr = _create_full_draft(user, self.req_dept, self.proj_dept, self.ptype)
        submit_project_request(pr, user)
        logs = list(pr.activity_log.all())
        # Should have SUBMITTED log at minimum
        actions = [l.action_type for l in logs]
        self.assertIn(ProjectRequestActionType.SUBMITTED, actions)

    def test_approval_tasks_created_exactly_once(self):
        user = self._make_staff_requester()
        pr = _create_full_draft(user, self.req_dept, self.proj_dept, self.ptype)
        submit_project_request(pr, user)
        # Should not have duplicate approval tasks
        tasks = pr.approval_tasks.all()
        role_dept_pairs = [(t.role, t.department_id) for t in tasks]
        self.assertEqual(len(role_dept_pairs), len(set(role_dept_pairs)))

    # ---- Fix 5: Submit workflow row locking and actor validation ----

    def test_non_requester_cannot_submit(self):
        """Non-requester cannot submit someone else's draft."""
        requester = self._make_staff_requester()
        other = User.objects.create_user(username="other", password="pass", is_active=True)
        pr = _create_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        with self.assertRaises(PermissionDenied):
            submit_project_request(pr, other)

    def test_inactive_requester_cannot_submit(self):
        """Inactive requester cannot submit."""
        user = User.objects.create_user(username="inactive", password="pass", is_active=False)
        UserDepartment.objects.create(
            user=user, department=self.req_dept,
            access_level=AccessLevel.STAFF, is_active=True,
        )
        UserDepartment.objects.create(
            user=user, department=self.proj_dept,
            access_level=AccessLevel.STAFF, is_active=True,
        )
        pr = _create_full_draft(user, self.req_dept, self.proj_dept, self.ptype)
        with self.assertRaises(PermissionDenied):
            submit_project_request(pr, user)

    def test_superuser_can_submit_on_behalf(self):
        """Superuser can submit on behalf of requester."""
        requester = self._make_staff_requester()
        superuser = User.objects.create_user(
            username="super", password="pass",
            is_active=True, is_superuser=True,
        )
        pr = _create_full_draft(requester, self.req_dept, self.proj_dept, self.ptype)
        result = submit_project_request(pr, superuser)
        self.assertEqual(result.status, ProjectRequestStatus.REVIEWING)

    def test_submit_uses_db_state_not_stale_object(self):
        """Service uses DB state, not stale in-memory object."""
        user = self._make_staff_requester()
        pr = _create_full_draft(user, self.req_dept, self.proj_dept, self.ptype)
        # Update DB to REVIEWING (simulating concurrent modification)
        ProjectRequest.objects.filter(pk=pr.pk).update(
            status=ProjectRequestStatus.REVIEWING,
        )
        # pr in memory still says DRAFT, but DB says REVIEWING
        with self.assertRaises(ValidationError):
            submit_project_request(pr, user)

    # ---- Fix 6: Approval-required status decision ----

    def test_pre_existing_task_does_not_cause_auto_approve(self):
        """Pre-existing approval task for a draft does not cause auto-approval."""
        user = self._make_staff_requester()
        pr = _create_full_draft(user, self.req_dept, self.proj_dept, self.ptype)
        # Pre-create an approval task (simulating a leftover from a previous attempt)
        ProjectRequestApprovalTask.objects.create(
            project_request=pr,
            department=self.proj_dept,
            role=ProjectApprovalRole.PROJECT_DEPT_MANAGER,
            status=ProjectApprovalTaskStatus.PENDING,
        )
        result = submit_project_request(pr, user)
        # Must be REVIEWING because required_approvals is non-empty
        self.assertEqual(result.status, ProjectRequestStatus.REVIEWING)

    def test_required_approvals_always_lead_to_reviewing(self):
        """Required approvals always lead to REVIEWING even if get_or_create created zero new tasks."""
        user = self._make_staff_requester()
        pr = _create_full_draft(user, self.req_dept, self.proj_dept, self.ptype)
        # Pre-create all approval tasks that would be generated
        approvals = generate_required_approvals(pr)
        for dept, role in approvals:
            ProjectRequestApprovalTask.objects.create(
                project_request=pr,
                department=dept,
                role=role,
                status=ProjectApprovalTaskStatus.PENDING,
            )
        result = submit_project_request(pr, user)
        self.assertEqual(result.status, ProjectRequestStatus.REVIEWING)


# ============================================================================
# 7. Permission Tests
# ============================================================================

class PermissionTests(TestCase):
    def setUp(self):
        self.req_dept = Department.objects.create(dept_code="ACCT", dept_name="Accounting")
        self.proj_dept = Department.objects.create(dept_code="MIS", dept_name="MIS")
        self.profile = ProjectDepartmentProfile.objects.create(
            department=self.proj_dept, allow_staff_claim=True,
        )
        self.ptype = ProjectRequestType.objects.create(code="new", name="New System")

    def _make_pr(self, requester, status=ProjectRequestStatus.DRAFT):
        return ProjectRequest.objects.create(
            requester=requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            request_type=self.ptype,
            status=status,
        )

    def test_requester_can_view_own(self):
        user = User.objects.create_user(username="req", password="pass")
        pr = self._make_pr(user)
        self.assertTrue(can_view_project_request(user, pr))

    def test_request_dept_manager_can_view(self):
        requester = User.objects.create_user(username="req", password="pass")
        mgr = User.objects.create_user(username="mgr", password="pass")
        UserDepartment.objects.create(
            user=mgr, department=self.req_dept,
            access_level=AccessLevel.MANAGER, is_active=True,
        )
        pr = self._make_pr(requester)
        self.assertTrue(can_view_project_request(mgr, pr))

    def test_project_dept_manager_can_view(self):
        requester = User.objects.create_user(username="req", password="pass")
        mgr = User.objects.create_user(username="pmgr", password="pass")
        UserDepartment.objects.create(
            user=mgr, department=self.proj_dept,
            access_level=AccessLevel.MANAGER, is_active=True,
        )
        pr = self._make_pr(requester)
        self.assertTrue(can_view_project_request(mgr, pr))

    def test_assigned_user_can_view(self):
        requester = User.objects.create_user(username="req", password="pass")
        assignee = User.objects.create_user(username="dev", password="pass")
        pr = self._make_pr(requester, status=ProjectRequestStatus.ASSIGNED)
        ProjectRequestAssignment.objects.create(
            project_request=pr, assigned_to=assignee, assigned_by=requester,
        )
        self.assertTrue(can_view_project_request(assignee, pr))

    def test_unrelated_user_denied(self):
        requester = User.objects.create_user(username="req", password="pass")
        unrelated = User.objects.create_user(username="unrelated", password="pass")
        pr = self._make_pr(requester)
        self.assertFalse(can_view_project_request(unrelated, pr))

    def test_claimable_visible_only_if_allow_staff_claim_true(self):
        requester = User.objects.create_user(username="req", password="pass")
        staff = User.objects.create_user(username="staff", password="pass")
        UserDepartment.objects.create(
            user=staff, department=self.proj_dept,
            access_level=AccessLevel.STAFF, is_active=True,
        )
        pr = self._make_pr(requester, status=ProjectRequestStatus.APPROVED)
        self.assertTrue(can_view_project_request(staff, pr))

        self.profile.allow_staff_claim = False
        self.profile.save()
        self.assertFalse(can_view_project_request(staff, pr))

    def test_claim_blocked_if_active_assignment_exists(self):
        requester = User.objects.create_user(username="req", password="pass")
        staff = User.objects.create_user(username="staff", password="pass")
        UserDepartment.objects.create(
            user=staff, department=self.proj_dept,
            access_level=AccessLevel.STAFF, is_active=True,
        )
        pr = self._make_pr(requester, status=ProjectRequestStatus.APPROVED)
        ProjectRequestAssignment.objects.create(
            project_request=pr, assigned_to=staff, assigned_by=requester,
        )
        self.assertFalse(can_claim_project_request(staff, pr))

    # ---- Fix 1: Claimable means NO active assignments at all ----

    def test_proj_dept_staff_can_claim_approved_no_assignments(self):
        """Project dept staff can view/claim approved request with no active assignments."""
        requester = User.objects.create_user(username="req", password="pass")
        staff = User.objects.create_user(username="staff", password="pass")
        UserDepartment.objects.create(
            user=staff, department=self.proj_dept,
            access_level=AccessLevel.STAFF, is_active=True,
        )
        pr = self._make_pr(requester, status=ProjectRequestStatus.APPROVED)
        self.assertTrue(can_view_project_request(staff, pr))
        self.assertTrue(can_claim_project_request(staff, pr))

    def test_proj_dept_staff_cannot_claim_assigned_to_another(self):
        """Project dept staff cannot view/claim approved request assigned to another user."""
        requester = User.objects.create_user(username="req", password="pass")
        staff = User.objects.create_user(username="staff", password="pass")
        other = User.objects.create_user(username="other", password="pass")
        UserDepartment.objects.create(
            user=staff, department=self.proj_dept,
            access_level=AccessLevel.STAFF, is_active=True,
        )
        UserDepartment.objects.create(
            user=other, department=self.proj_dept,
            access_level=AccessLevel.STAFF, is_active=True,
        )
        pr = self._make_pr(requester, status=ProjectRequestStatus.APPROVED)
        ProjectRequestAssignment.objects.create(
            project_request=pr, assigned_to=other, assigned_by=requester,
        )
        self.assertFalse(can_view_project_request(staff, pr))
        self.assertFalse(can_claim_project_request(staff, pr))

    def test_proj_dept_staff_cannot_claim_assigned_status_to_another(self):
        """Project dept staff cannot view/claim ASSIGNED request assigned to another user."""
        requester = User.objects.create_user(username="req", password="pass")
        staff = User.objects.create_user(username="staff", password="pass")
        other = User.objects.create_user(username="other", password="pass")
        UserDepartment.objects.create(
            user=staff, department=self.proj_dept,
            access_level=AccessLevel.STAFF, is_active=True,
        )
        UserDepartment.objects.create(
            user=other, department=self.proj_dept,
            access_level=AccessLevel.STAFF, is_active=True,
        )
        pr = self._make_pr(requester, status=ProjectRequestStatus.ASSIGNED)
        ProjectRequestAssignment.objects.create(
            project_request=pr, assigned_to=other, assigned_by=requester,
        )
        self.assertFalse(can_view_project_request(staff, pr))
        self.assertFalse(can_claim_project_request(staff, pr))

    def test_inactive_assignment_does_not_block_claim(self):
        """Inactive old assignment does not block claim."""
        requester = User.objects.create_user(username="req", password="pass")
        staff = User.objects.create_user(username="staff", password="pass")
        UserDepartment.objects.create(
            user=staff, department=self.proj_dept,
            access_level=AccessLevel.STAFF, is_active=True,
        )
        pr = self._make_pr(requester, status=ProjectRequestStatus.APPROVED)
        ProjectRequestAssignment.objects.create(
            project_request=pr, assigned_to=staff, assigned_by=requester,
            is_active=False,
        )
        self.assertTrue(can_view_project_request(staff, pr))
        self.assertTrue(can_claim_project_request(staff, pr))

    def test_submit_allowed_for_active_user(self):
        user = User.objects.create_user(username="active", password="pass", is_active=True)
        self.assertTrue(can_submit_project_request(user))

    def test_submit_denied_for_inactive_user(self):
        user = User.objects.create_user(username="inactive", password="pass", is_active=False)
        self.assertFalse(can_submit_project_request(user))

    def test_action_context_returns_dict(self):
        user = User.objects.create_user(username="ctx", password="pass")
        pr = self._make_pr(user)
        ctx = get_project_request_action_context(user, pr)
        self.assertIn("can_view", ctx)
        self.assertIn("can_submit", ctx)
        self.assertIn("can_assign", ctx)
        self.assertIn("can_claim", ctx)
        self.assertIn("can_attach_file", ctx)


# ============================================================================
# 8. Selector Tests
# ============================================================================

class SelectorTests(TestCase):
    def setUp(self):
        self.req_dept = Department.objects.create(dept_code="ACCT", dept_name="Accounting")
        self.proj_dept = Department.objects.create(dept_code="MIS", dept_name="MIS")
        self.profile = ProjectDepartmentProfile.objects.create(
            department=self.proj_dept, allow_staff_claim=True,
        )
        self.ptype = ProjectRequestType.objects.create(code="new", name="New System")

    def test_visible_queryset_includes_own(self):
        user = User.objects.create_user(username="owner", password="pass")
        pr = ProjectRequest.objects.create(
            requester=user,
            request_department=self.req_dept,
            project_department=self.proj_dept,
        )
        visible = get_visible_project_requests(user)
        self.assertIn(pr, visible)

    def test_visible_excludes_unrelated(self):
        requester = User.objects.create_user(username="req", password="pass")
        unrelated = User.objects.create_user(username="unrelated", password="pass")
        pr = ProjectRequest.objects.create(
            requester=requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
        )
        visible = get_visible_project_requests(unrelated)
        self.assertNotIn(pr, visible)

    def test_project_dept_staff_does_not_see_all_dept_requests(self):
        requester = User.objects.create_user(username="req", password="pass")
        staff = User.objects.create_user(username="staff", password="pass")
        UserDepartment.objects.create(
            user=staff, department=self.proj_dept,
            access_level=AccessLevel.STAFF, is_active=True,
        )
        # DRAFT request should not be visible to staff
        pr = ProjectRequest.objects.create(
            requester=requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            status=ProjectRequestStatus.DRAFT,
        )
        visible = get_visible_project_requests(staff)
        self.assertNotIn(pr, visible)

    def test_allow_staff_claim_false_hides_claimable(self):
        requester = User.objects.create_user(username="req", password="pass")
        staff = User.objects.create_user(username="staff", password="pass")
        UserDepartment.objects.create(
            user=staff, department=self.proj_dept,
            access_level=AccessLevel.STAFF, is_active=True,
        )
        pr = ProjectRequest.objects.create(
            requester=requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            status=ProjectRequestStatus.APPROVED,
        )
        self.profile.allow_staff_claim = False
        self.profile.save()
        visible = get_visible_project_requests(staff)
        self.assertNotIn(pr, visible)

    def test_my_project_requests(self):
        user = User.objects.create_user(username="mine", password="pass")
        pr = ProjectRequest.objects.create(
            requester=user,
            request_department=self.req_dept,
        )
        self.assertIn(pr, get_my_project_requests(user))

    def test_assigned_to_me(self):
        requester = User.objects.create_user(username="req", password="pass")
        assignee = User.objects.create_user(username="dev", password="pass")
        pr = ProjectRequest.objects.create(
            requester=requester,
            request_department=self.req_dept,
            status=ProjectRequestStatus.ASSIGNED,
        )
        ProjectRequestAssignment.objects.create(
            project_request=pr, assigned_to=assignee, assigned_by=requester,
        )
        self.assertIn(pr, get_assigned_to_me(assignee))

    def test_overdue_excludes_terminal(self):
        user = User.objects.create_user(username="dev", password="pass")
        pr = ProjectRequest.objects.create(
            requester=user,
            request_department=self.req_dept,
            status=ProjectRequestStatus.COMPLETED,
            needed_by_date=date(2020, 1, 1),
        )
        ProjectRequestAssignment.objects.create(
            project_request=pr, assigned_to=user, assigned_by=user,
        )
        self.assertNotIn(pr, get_overdue_project_requests(user))

    # ---- Fix 2: Claimable selector excludes any active assignment ----

    def test_staff_sees_approved_unassigned_claimable(self):
        """Staff sees approved/unassigned claimable request."""
        requester = User.objects.create_user(username="req", password="pass")
        staff = User.objects.create_user(username="staff", password="pass")
        UserDepartment.objects.create(
            user=staff, department=self.proj_dept,
            access_level=AccessLevel.STAFF, is_active=True,
        )
        pr = ProjectRequest.objects.create(
            requester=requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            status=ProjectRequestStatus.APPROVED,
        )
        visible = get_visible_project_requests(staff)
        self.assertIn(pr, visible)

    def test_staff_does_not_see_approved_assigned_to_another(self):
        """Staff does not see approved request assigned to another user."""
        requester = User.objects.create_user(username="req", password="pass")
        staff = User.objects.create_user(username="staff", password="pass")
        other = User.objects.create_user(username="other", password="pass")
        UserDepartment.objects.create(
            user=staff, department=self.proj_dept,
            access_level=AccessLevel.STAFF, is_active=True,
        )
        UserDepartment.objects.create(
            user=other, department=self.proj_dept,
            access_level=AccessLevel.STAFF, is_active=True,
        )
        pr = ProjectRequest.objects.create(
            requester=requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            status=ProjectRequestStatus.APPROVED,
        )
        ProjectRequestAssignment.objects.create(
            project_request=pr, assigned_to=other, assigned_by=requester,
        )
        visible = get_visible_project_requests(staff)
        self.assertNotIn(pr, visible)

    def test_staff_does_not_see_assigned_status_to_another(self):
        """Staff does not see ASSIGNED request assigned to another user."""
        requester = User.objects.create_user(username="req", password="pass")
        staff = User.objects.create_user(username="staff", password="pass")
        other = User.objects.create_user(username="other", password="pass")
        UserDepartment.objects.create(
            user=staff, department=self.proj_dept,
            access_level=AccessLevel.STAFF, is_active=True,
        )
        UserDepartment.objects.create(
            user=other, department=self.proj_dept,
            access_level=AccessLevel.STAFF, is_active=True,
        )
        pr = ProjectRequest.objects.create(
            requester=requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            status=ProjectRequestStatus.ASSIGNED,
        )
        ProjectRequestAssignment.objects.create(
            project_request=pr, assigned_to=other, assigned_by=requester,
        )
        visible = get_visible_project_requests(staff)
        self.assertNotIn(pr, visible)

    def test_inactive_assignment_does_not_hide_claimable(self):
        """Inactive assignment does not hide claimable request."""
        requester = User.objects.create_user(username="req", password="pass")
        staff = User.objects.create_user(username="staff", password="pass")
        UserDepartment.objects.create(
            user=staff, department=self.proj_dept,
            access_level=AccessLevel.STAFF, is_active=True,
        )
        pr = ProjectRequest.objects.create(
            requester=requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            status=ProjectRequestStatus.APPROVED,
        )
        ProjectRequestAssignment.objects.create(
            project_request=pr, assigned_to=staff, assigned_by=requester,
            is_active=False,
        )
        visible = get_visible_project_requests(staff)
        self.assertIn(pr, visible)

    # ---- Fix 8: get_my_pending_approval_tasks optimization tests ----

    def test_manager_with_can_approve_sees_manager_tasks(self):
        """Manager with can_approve=True sees manager tasks for REVIEWING requests."""
        dept = Department.objects.create(dept_code="SEL", dept_name="Selector")
        user = User.objects.create_user(username="sel_mgr", password="pass")
        UserDepartment.objects.create(
            user=user, department=dept,
            access_level=AccessLevel.MANAGER, is_active=True,
            can_approve=True,
        )
        pr = ProjectRequest.objects.create(
            requester=user, request_department=dept,
            status=ProjectRequestStatus.REVIEWING,
        )
        task = ProjectRequestApprovalTask.objects.create(
            project_request=pr, department=dept,
            role=ProjectApprovalRole.PROJECT_DEPT_MANAGER,
            status=ProjectApprovalTaskStatus.PENDING,
        )
        tasks = get_my_pending_approval_tasks(user)
        self.assertIn(task, tasks)

    def test_manager_with_can_approve_false_does_not_see(self):
        """Manager with can_approve=False does not see manager tasks."""
        dept = Department.objects.create(dept_code="SEL2", dept_name="Selector2")
        user = User.objects.create_user(username="sel2_mgr", password="pass")
        UserDepartment.objects.create(
            user=user, department=dept,
            access_level=AccessLevel.MANAGER, is_active=True,
            can_approve=False,
        )
        pr = ProjectRequest.objects.create(
            requester=user, request_department=dept,
        )
        ProjectRequestApprovalTask.objects.create(
            project_request=pr, department=dept,
            role=ProjectApprovalRole.PROJECT_DEPT_MANAGER,
            status=ProjectApprovalTaskStatus.PENDING,
        )
        tasks = get_my_pending_approval_tasks(user)
        self.assertEqual(tasks.count(), 0)

    def test_vp_with_can_approve_sees_vp_tasks(self):
        """VP with can_approve=True sees VP tasks for REVIEWING requests."""
        dept = Department.objects.create(dept_code="SEL3", dept_name="Selector3")
        user = User.objects.create_user(username="sel3_vp", password="pass")
        UserDepartment.objects.create(
            user=user, department=dept,
            access_level=AccessLevel.VP, is_active=True,
            can_approve=True,
        )
        pr = ProjectRequest.objects.create(
            requester=user, request_department=dept,
            status=ProjectRequestStatus.REVIEWING,
        )
        task = ProjectRequestApprovalTask.objects.create(
            project_request=pr, department=dept,
            role=ProjectApprovalRole.PROJECT_DEPT_VP,
            status=ProjectApprovalTaskStatus.PENDING,
        )
        tasks = get_my_pending_approval_tasks(user)
        self.assertIn(task, tasks)

    def test_staff_cannot_see_manager_or_vp_tasks(self):
        """Staff with can_approve=True does not see manager/VP tasks."""
        dept = Department.objects.create(dept_code="SEL4", dept_name="Selector4")
        user = User.objects.create_user(username="sel4_staff", password="pass")
        UserDepartment.objects.create(
            user=user, department=dept,
            access_level=AccessLevel.STAFF, is_active=True,
            can_approve=True,
        )
        pr = ProjectRequest.objects.create(
            requester=user, request_department=dept,
        )
        ProjectRequestApprovalTask.objects.create(
            project_request=pr, department=dept,
            role=ProjectApprovalRole.PROJECT_DEPT_MANAGER,
            status=ProjectApprovalTaskStatus.PENDING,
        )
        ProjectRequestApprovalTask.objects.create(
            project_request=pr, department=dept,
            role=ProjectApprovalRole.PROJECT_DEPT_VP,
            status=ProjectApprovalTaskStatus.PENDING,
        )
        tasks = get_my_pending_approval_tasks(user)
        self.assertEqual(tasks.count(), 0)

    def test_user_does_not_see_unrelated_dept_tasks(self):
        """User does not see tasks from unrelated departments."""
        other_dept = Department.objects.create(dept_code="SEL5", dept_name="Selector5")
        user = User.objects.create_user(username="sel5_mgr", password="pass")
        UserDepartment.objects.create(
            user=user, department=other_dept,
            access_level=AccessLevel.MANAGER, is_active=True,
            can_approve=True,
        )
        pr = ProjectRequest.objects.create(
            requester=user, request_department=self.proj_dept,
        )
        ProjectRequestApprovalTask.objects.create(
            project_request=pr, department=self.proj_dept,
            role=ProjectApprovalRole.PROJECT_DEPT_MANAGER,
            status=ProjectApprovalTaskStatus.PENDING,
        )
        tasks = get_my_pending_approval_tasks(user)
        self.assertEqual(tasks.count(), 0)


# ============================================================================
# 9. Attachment Upload Service Tests
# ============================================================================

class AttachmentUploadTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="uploader", password="pass")
        self.dept = Department.objects.create(dept_code="MIS", dept_name="MIS")
        self.pr = ProjectRequest.objects.create(
            requester=self.user,
            request_department=self.dept,
        )
        self.ftype = ProjectRequestFileType.objects.create(
            code="doc", name="Document",
            allowed_extensions="pdf,docx,xlsx",
            max_file_size_mb=25,
        )

    def test_valid_file_creates_attachment(self):
        content = b"valid pdf content"
        uploaded = SimpleUploadedFile(
            "report.pdf", content, content_type="application/pdf",
        )
        attachment = upload_project_request_attachment(
            self.pr, uploaded, self.ftype, self.user,
        )
        self.assertEqual(attachment.original_filename, "report.pdf")
        self.assertEqual(attachment.file_size, len(content))

    def test_invalid_extension_rejected(self):
        uploaded = SimpleUploadedFile(
            "image.png", b"data", content_type="image/png",
        )
        with self.assertRaises(ValidationError) as cm:
            upload_project_request_attachment(
                self.pr, uploaded, self.ftype, self.user,
            )
        self.assertIn("not allowed", str(cm.exception).lower())

    def test_oversized_file_rejected(self):
        self.ftype.max_file_size_mb = 0  # 0 bytes max
        self.ftype.save()
        uploaded = SimpleUploadedFile(
            "big.pdf", b"x" * 100, content_type="application/pdf",
        )
        with self.assertRaises(ValidationError):
            upload_project_request_attachment(
                self.pr, uploaded, self.ftype, self.user,
            )

    def test_inactive_file_type_rejected(self):
        self.ftype.is_active = False
        self.ftype.save()
        uploaded = SimpleUploadedFile(
            "report.pdf", b"data", content_type="application/pdf",
        )
        with self.assertRaises(ValidationError):
            upload_project_request_attachment(
                self.pr, uploaded, self.ftype, self.user,
            )

    def test_file_attached_activity_log_created(self):
        content = b"valid content"
        uploaded = SimpleUploadedFile(
            "report.pdf", content, content_type="application/pdf",
        )
        upload_project_request_attachment(
            self.pr, uploaded, self.ftype, self.user,
        )
        log = self.pr.activity_log.filter(
            action_type=ProjectRequestActionType.FILE_ATTACHED,
        ).first()
        self.assertIsNotNone(log)
        self.assertIn("report.pdf", log.description)

    # ---- Fix 3: Upload permission check ----

    def test_requester_can_upload(self):
        """Requester can upload files."""
        uploaded = SimpleUploadedFile("r.pdf", b"data")
        attachment = upload_project_request_attachment(
            self.pr, uploaded, self.ftype, self.user,
        )
        self.assertIsNotNone(attachment)

    def test_assignee_can_upload(self):
        """Assignee can upload files."""
        assignee = User.objects.create_user(username="assignee", password="pass")
        ProjectRequestAssignment.objects.create(
            project_request=self.pr, assigned_to=assignee, assigned_by=self.user,
        )
        uploaded = SimpleUploadedFile("a.pdf", b"data")
        attachment = upload_project_request_attachment(
            self.pr, uploaded, self.ftype, assignee,
        )
        self.assertIsNotNone(attachment)

    def test_req_dept_manager_can_upload(self):
        """Request dept manager can upload files."""
        mgr = User.objects.create_user(username="mgr", password="pass")
        UserDepartment.objects.create(
            user=mgr, department=self.dept,
            access_level=AccessLevel.MANAGER, is_active=True,
        )
        uploaded = SimpleUploadedFile("m.pdf", b"data")
        attachment = upload_project_request_attachment(
            self.pr, uploaded, self.ftype, mgr,
        )
        self.assertIsNotNone(attachment)

    def test_proj_dept_manager_can_upload(self):
        """Project dept manager can upload files."""
        proj_dept = Department.objects.create(dept_code="IT", dept_name="IT")
        self.pr.project_department = proj_dept
        self.pr.save()
        mgr = User.objects.create_user(username="pmgr", password="pass")
        UserDepartment.objects.create(
            user=mgr, department=proj_dept,
            access_level=AccessLevel.MANAGER, is_active=True,
        )
        uploaded = SimpleUploadedFile("pm.pdf", b"data")
        attachment = upload_project_request_attachment(
            self.pr, uploaded, self.ftype, mgr,
        )
        self.assertIsNotNone(attachment)

    def test_unrelated_user_rejected(self):
        """Unrelated user is rejected when uploading."""
        unrelated = User.objects.create_user(username="unrelated", password="pass")
        uploaded = SimpleUploadedFile("u.pdf", b"data")
        with self.assertRaises(PermissionDenied):
            upload_project_request_attachment(
                self.pr, uploaded, self.ftype, unrelated,
            )

    def test_terminal_status_rejects_upload(self):
        """Terminal status rejects upload even for requester."""
        self.pr.status = ProjectRequestStatus.COMPLETED
        self.pr.save()
        uploaded = SimpleUploadedFile("c.pdf", b"data")
        with self.assertRaises(PermissionDenied):
            upload_project_request_attachment(
                self.pr, uploaded, self.ftype, self.user,
            )

    # ---- Fix 4: File size and extension validation ----

    def test_uppercase_extension_accepted(self):
        """Uppercase extension PDF is accepted when pdf is allowed."""
        uploaded = SimpleUploadedFile(
            "report.PDF", b"data", content_type="application/pdf",
        )
        attachment = upload_project_request_attachment(
            self.pr, uploaded, self.ftype, self.user,
        )
        self.assertIsNotNone(attachment)

    def test_no_extension_rejected(self):
        """No-extension file is rejected."""
        uploaded = SimpleUploadedFile(
            "README", b"data", content_type="text/plain",
        )
        with self.assertRaises(ValidationError) as cm:
            upload_project_request_attachment(
                self.pr, uploaded, self.ftype, self.user,
            )
        self.assertIn("extension", str(cm.exception).lower())

    def test_empty_allowed_extensions_rejected(self):
        """Empty allowed_extensions rejects upload."""
        self.ftype.allowed_extensions = ""
        self.ftype.save()
        uploaded = SimpleUploadedFile("r.pdf", b"data")
        with self.assertRaises(ValidationError) as cm:
            upload_project_request_attachment(
                self.pr, uploaded, self.ftype, self.user,
            )
        self.assertIn("configured", str(cm.exception).lower())

    def test_file_size_uses_uploaded_file_size(self):
        """File size uses uploaded_file.size if available."""
        content = b"x" * 200
        uploaded = SimpleUploadedFile(
            "sized.pdf", content, content_type="application/pdf",
        )
        attachment = upload_project_request_attachment(
            self.pr, uploaded, self.ftype, self.user,
        )
        self.assertEqual(attachment.file_size, len(content))

    # ---- Fix 7: Upload updates last_activity_at ----

    def test_upload_updates_last_activity_at(self):
        """Upload attachment updates project_request.last_activity_at through FILE_ATTACHED log."""
        old_last = self.pr.last_activity_at
        import time
        time.sleep(0.05)
        uploaded = SimpleUploadedFile("t.pdf", b"data")
        upload_project_request_attachment(
            self.pr, uploaded, self.ftype, self.user,
        )
        self.pr.refresh_from_db()
        self.assertGreater(self.pr.last_activity_at, old_last)


# ============================================================================
# Exists-based claimable selector tests
# ============================================================================

class ExistsClaimableSelectorTest(TestCase):
    """Test that claimable selector uses Exists subquery correctly."""

    def setUp(self):
        self.req_dept = Department.objects.create(dept_code="ACCT", dept_name="Accounting")
        self.proj_dept = Department.objects.create(dept_code="MIS", dept_name="MIS")
        self.profile = ProjectDepartmentProfile.objects.create(
            department=self.proj_dept, allow_staff_claim=True,
        )
        self.ptype = ProjectRequestType.objects.create(code="new", name="New System")

    def _make_staff(self, username):
        user = User.objects.create_user(username=username, password="pass")
        UserDepartment.objects.create(
            user=user, department=self.proj_dept,
            access_level=AccessLevel.STAFF, is_active=True,
        )
        return user

    def test_staff_sees_approved_no_assignment(self):
        """Staff sees approved request with no assignment at all."""
        requester = User.objects.create_user(username="req", password="pass")
        staff = self._make_staff("staff")
        pr = ProjectRequest.objects.create(
            requester=requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            status=ProjectRequestStatus.APPROVED,
        )
        visible = get_visible_project_requests(staff)
        self.assertIn(pr, visible)

    def test_staff_sees_approved_only_inactive_assignment(self):
        """Staff sees approved request with only inactive assignment."""
        requester = User.objects.create_user(username="req", password="pass")
        staff = self._make_staff("staff")
        pr = ProjectRequest.objects.create(
            requester=requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            status=ProjectRequestStatus.APPROVED,
        )
        ProjectRequestAssignment.objects.create(
            project_request=pr, assigned_to=staff, assigned_by=requester,
            is_active=False,
        )
        visible = get_visible_project_requests(staff)
        self.assertIn(pr, visible)

    def test_staff_does_not_see_approved_with_active_assignment(self):
        """Staff does NOT see approved request with active assignment."""
        requester = User.objects.create_user(username="req", password="pass")
        staff = self._make_staff("staff")
        other = self._make_staff("other")
        pr = ProjectRequest.objects.create(
            requester=requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            status=ProjectRequestStatus.APPROVED,
        )
        ProjectRequestAssignment.objects.create(
            project_request=pr, assigned_to=other, assigned_by=requester,
        )
        visible = get_visible_project_requests(staff)
        self.assertNotIn(pr, visible)

    def test_staff_does_not_see_approved_with_both_active_and_inactive(self):
        """Staff does NOT see when both active and inactive assignments exist."""
        requester = User.objects.create_user(username="req", password="pass")
        staff = self._make_staff("staff")
        other = self._make_staff("other")
        pr = ProjectRequest.objects.create(
            requester=requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            status=ProjectRequestStatus.APPROVED,
        )
        ProjectRequestAssignment.objects.create(
            project_request=pr, assigned_to=staff, assigned_by=requester,
            is_active=False,
        )
        ProjectRequestAssignment.objects.create(
            project_request=pr, assigned_to=other, assigned_by=requester,
        )
        visible = get_visible_project_requests(staff)
        self.assertNotIn(pr, visible)

    def test_staff_does_not_see_assigned_status_active_to_another(self):
        """Staff does NOT see ASSIGNED request with active assignment to another."""
        requester = User.objects.create_user(username="req", password="pass")
        staff = self._make_staff("staff")
        other = self._make_staff("other")
        pr = ProjectRequest.objects.create(
            requester=requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            status=ProjectRequestStatus.ASSIGNED,
        )
        ProjectRequestAssignment.objects.create(
            project_request=pr, assigned_to=other, assigned_by=requester,
        )
        visible = get_visible_project_requests(staff)
        self.assertNotIn(pr, visible)

    def test_requester_visibility_still_works(self):
        """Requester can still see own requests regardless of assignments."""
        requester = User.objects.create_user(username="req", password="pass")
        other = self._make_staff("other")
        pr = ProjectRequest.objects.create(
            requester=requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            status=ProjectRequestStatus.APPROVED,
        )
        ProjectRequestAssignment.objects.create(
            project_request=pr, assigned_to=other, assigned_by=requester,
        )
        visible = get_visible_project_requests(requester)
        self.assertIn(pr, visible)

    def test_manager_visibility_still_works(self):
        """Manager can still see requests in managed department."""
        requester = User.objects.create_user(username="req", password="pass")
        manager = User.objects.create_user(username="mgr", password="pass")
        UserDepartment.objects.create(
            user=manager, department=self.proj_dept,
            access_level=AccessLevel.MANAGER, is_active=True,
        )
        other = self._make_staff("other")
        pr = ProjectRequest.objects.create(
            requester=requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            status=ProjectRequestStatus.APPROVED,
        )
        ProjectRequestAssignment.objects.create(
            project_request=pr, assigned_to=other, assigned_by=requester,
        )
        visible = get_visible_project_requests(manager)
        self.assertIn(pr, visible)


# ============================================================================
# Strengthened validate_required_for_submit tests
# ============================================================================

class StrengthenedSubmitValidationTest(TestCase):
    """Test strengthened validate_required_for_submit checks."""

    def setUp(self):
        self.req_dept = Department.objects.create(dept_code="ACCT", dept_name="Accounting")
        self.proj_dept = Department.objects.create(dept_code="MIS", dept_name="MIS")
        self.profile = ProjectDepartmentProfile.objects.create(
            department=self.proj_dept,
            is_active=True,
            can_receive_project_requests=True,
        )
        self.ptype = ProjectRequestType.objects.create(code="new", name="New System", is_active=True)
        self.user = User.objects.create_user(username="user", password="pass")
        UserDepartment.objects.create(
            user=self.user, department=self.req_dept,
            access_level=AccessLevel.STAFF, is_active=True,
        )

    def _make_pr(self, **overrides):
        overrides.setdefault("requester", self.user)
        overrides.setdefault("request_department", self.req_dept)
        overrides.setdefault("project_department", self.proj_dept)
        overrides.setdefault("request_type", self.ptype)
        overrides.setdefault("priority", 3)
        overrides.setdefault("needed_by_date", date(2027, 12, 31))
        overrides.setdefault("project_name", "Test Project")
        overrides.setdefault("scope_summary", "Scope")
        overrides.setdefault("business_problem", "Problem")
        overrides.setdefault("in_scope", "In scope")
        overrides.setdefault("expected_deliverables", "Deliverables")
        overrides.setdefault("acceptance_criteria", "Criteria")
        return ProjectRequest.objects.create(**overrides)

    def test_whitespace_only_project_name_fails(self):
        """Whitespace-only project_name fails submit validation."""
        pr = self._make_pr(project_name="   ")
        with self.assertRaises(ValidationError) as cm:
            validate_required_for_submit(pr)
        self.assertIn("project_name", cm.exception.message_dict)

    def test_whitespace_only_scope_summary_fails(self):
        """Whitespace-only scope_summary fails submit validation."""
        pr = self._make_pr(scope_summary="\t\n")
        with self.assertRaises(ValidationError) as cm:
            validate_required_for_submit(pr)
        self.assertIn("scope_summary", cm.exception.message_dict)

    def test_inactive_requester_fails(self):
        """Inactive requester fails validation even if actor is superuser."""
        inactive_user = User.objects.create_user(username="inactive", password="pass", is_active=False)
        UserDepartment.objects.create(
            user=inactive_user, department=self.req_dept,
            access_level=AccessLevel.STAFF, is_active=True,
        )
        pr = self._make_pr(requester=inactive_user)
        with self.assertRaises(ValidationError) as cm:
            validate_required_for_submit(pr)
        self.assertIn("requester", cm.exception.message_dict)

    def test_inactive_request_department_fails(self):
        """Inactive request_department fails validation."""
        inactive_dept = Department.objects.create(dept_code="OLD", dept_name="Old", is_active=False)
        UserDepartment.objects.create(
            user=self.user, department=inactive_dept,
            access_level=AccessLevel.STAFF, is_active=True,
        )
        pr = self._make_pr(request_department=inactive_dept)
        with self.assertRaises(ValidationError) as cm:
            validate_required_for_submit(pr)
        self.assertIn("request_department", cm.exception.message_dict)

    def test_requester_not_member_of_request_department_fails(self):
        """Requester without active membership in request_department fails."""
        other_dept = Department.objects.create(dept_code="OTHER", dept_name="Other Dept")
        pr = self._make_pr(request_department=other_dept)
        with self.assertRaises(ValidationError) as cm:
            validate_required_for_submit(pr)
        self.assertIn("request_department", cm.exception.message_dict)

    def test_inactive_request_type_fails(self):
        """Inactive request_type fails validation."""
        inactive_type = ProjectRequestType.objects.create(
            code="old", name="Old Type", is_active=False,
        )
        pr = self._make_pr(request_type=inactive_type)
        with self.assertRaises(ValidationError) as cm:
            validate_required_for_submit(pr)
        self.assertIn("request_type", cm.exception.message_dict)

    def test_valid_requester_with_active_membership_passes(self):
        """Active requester with active membership passes validation."""
        pr = self._make_pr()
        validate_required_for_submit(pr)  # Should not raise


# ============================================================================
# Superuser submit validation tests
# ============================================================================

class SuperuserSubmitValidationTest(TestCase):
    """Test that superuser cannot submit invalid requester/request_department data."""

    def setUp(self):
        self.req_dept = Department.objects.create(dept_code="ACCT", dept_name="Accounting")
        self.proj_dept = Department.objects.create(dept_code="MIS", dept_name="MIS")
        self.profile = ProjectDepartmentProfile.objects.create(
            department=self.proj_dept,
            is_active=True,
            can_receive_project_requests=True,
        )
        self.ptype = ProjectRequestType.objects.create(code="new", name="New System", is_active=True)
        self.superuser = User.objects.create_superuser(username="admin", password="pass")
        self.user = User.objects.create_user(username="user", password="pass")
        UserDepartment.objects.create(
            user=self.user, department=self.req_dept,
            access_level=AccessLevel.STAFF, is_active=True,
        )

    def _make_draft(self, **overrides):
        overrides.setdefault("requester", self.user)
        overrides.setdefault("request_department", self.req_dept)
        overrides.setdefault("project_department", self.proj_dept)
        overrides.setdefault("request_type", self.ptype)
        overrides.setdefault("priority", 3)
        overrides.setdefault("needed_by_date", date(2027, 12, 31))
        overrides.setdefault("project_name", "Test Project")
        overrides.setdefault("scope_summary", "Scope")
        overrides.setdefault("business_problem", "Problem")
        overrides.setdefault("in_scope", "In scope")
        overrides.setdefault("expected_deliverables", "Deliverables")
        overrides.setdefault("acceptance_criteria", "Criteria")
        overrides.setdefault("status", ProjectRequestStatus.DRAFT)
        return ProjectRequest.objects.create(**overrides)

    def test_superuser_cannot_submit_for_inactive_requester(self):
        """Superuser cannot submit a request for an inactive requester."""
        inactive_user = User.objects.create_user(username="inactive", password="pass", is_active=False)
        UserDepartment.objects.create(
            user=inactive_user, department=self.req_dept,
            access_level=AccessLevel.STAFF, is_active=True,
        )
        pr = self._make_draft(requester=inactive_user)
        with self.assertRaises(ValidationError):
            submit_project_request(pr, self.superuser)

    def test_superuser_cannot_submit_requester_not_in_dept(self):
        """Superuser cannot submit when requester is not a member of request_department."""
        other_dept = Department.objects.create(dept_code="OTHER", dept_name="Other Dept")
        pr = self._make_draft(request_department=other_dept)
        with self.assertRaises(ValidationError):
            submit_project_request(pr, self.superuser)

    def test_valid_requester_can_submit_normally(self):
        """Valid requester can still submit normally."""
        pr = self._make_draft()
        result = submit_project_request(pr, self.user)
        self.assertNotEqual(result.status, ProjectRequestStatus.DRAFT)


# ============================================================================
# 11. Cleanup Fix Tests
# ============================================================================

class ProjectDepartmentActiveValidationTest(TestCase):
    """Test that project_department.is_active is validated on submit."""

    def setUp(self):
        from accounts.models import User, Department, UserDepartment, AccessLevel
        from project_requests.models import (
            ProjectRequestType, ProjectDepartmentProfile,
        )
        from project_requests.services import create_project_request_draft
        from datetime import date

        self.req_dept = Department.objects.create(
            dept_name="IT", dept_code="IT", is_active=True,
        )
        self.proj_dept = Department.objects.create(
            dept_name="Finance", dept_code="FIN", is_active=True,
        )
        self.user = User.objects.create_user(
            username="staff1", password="pass", is_staff=True, is_active=True,
        )
        UserDepartment.objects.create(
            user=self.user, department=self.req_dept,
            access_level=AccessLevel.STAFF, is_active=True,
        )
        self.type = ProjectRequestType.objects.create(
            name="Report", code="RPT", is_active=True,
        )
        self.profile = ProjectDepartmentProfile.objects.create(
            department=self.proj_dept,
            is_active=True,
            can_receive_project_requests=True,
        )

    def _make_full_draft(self, **overrides):
        """Create a draft with all required fields populated."""
        from project_requests.models import ProjectRequestStatus, ProjectRequestPriority
        data = {
            "requester": self.user,
            "request_department": self.req_dept,
            "project_department": self.proj_dept,
            "request_type": self.type,
            "project_name": "CRM Report",
            "scope_summary": "Build CRM reporting module.",
            "business_problem": "Need better reporting.",
            "in_scope": "CRM module.",
            "expected_deliverables": "Working CRM.",
            "acceptance_criteria": "Passes UAT.",
            "needed_by_date": date(2026, 12, 31),
            "priority": ProjectRequestPriority.P3,
            "status": ProjectRequestStatus.DRAFT,
        }
        data.update(overrides)
        return create_project_request_draft(**data)

    def test_inactive_project_department_fails_submit_validation(self):
        """Inactive project_department fails validate_required_for_submit."""
        from project_requests.services import validate_required_for_submit
        from django.core.exceptions import ValidationError
        self.proj_dept.is_active = False
        self.proj_dept.save(update_fields=["is_active"])
        pr = self._make_full_draft()
        with self.assertRaises(ValidationError) as cm:
            validate_required_for_submit(pr)
        self.assertIn("project_department", cm.exception.message_dict)

    def test_active_project_department_with_active_profile_passes(self):
        """Active project_department with active profile passes validation."""
        from project_requests.services import validate_required_for_submit
        from django.core.exceptions import ValidationError
        pr = self._make_full_draft()
        # Should not raise ValidationError
        try:
            validate_required_for_submit(pr)
        except ValidationError as e:
            self.fail(f"Validation should pass but got: {e.message_dict}")


class NormalizeBeforeDuplicateCheckTest(TestCase):
    """Test that text fields are normalized before duplicate prevention."""

    def setUp(self):
        from accounts.models import User, Department, UserDepartment, AccessLevel
        from project_requests.models import (
            ProjectRequestType, ProjectDepartmentProfile,
        )
        from project_requests.services import create_project_request_draft
        from datetime import date

        self.req_dept = Department.objects.create(
            dept_name="IT", dept_code="IT", is_active=True,
        )
        self.proj_dept = Department.objects.create(
            dept_name="Finance", dept_code="FIN", is_active=True,
        )
        self.user = User.objects.create_user(
            username="staff1", password="pass", is_staff=True, is_active=True,
        )
        self.user2 = User.objects.create_user(
            username="staff2", password="pass", is_staff=True, is_active=True,
        )
        UserDepartment.objects.create(
            user=self.user, department=self.req_dept,
            access_level=AccessLevel.STAFF, is_active=True,
        )
        UserDepartment.objects.create(
            user=self.user2, department=self.req_dept,
            access_level=AccessLevel.STAFF, is_active=True,
        )
        self.type = ProjectRequestType.objects.create(
            name="Report", code="RPT", is_active=True,
        )
        self.profile = ProjectDepartmentProfile.objects.create(
            department=self.proj_dept,
            is_active=True,
            can_receive_project_requests=True,
        )

    def _make_full_draft(self, requester, **overrides):
        """Create a draft with all required fields populated."""
        from project_requests.models import ProjectRequestStatus, ProjectRequestPriority
        data = {
            "requester": requester,
            "request_department": self.req_dept,
            "project_department": self.proj_dept,
            "request_type": self.type,
            "project_name": "CRM Report",
            "scope_summary": "Build CRM reporting module.",
            "business_problem": "Need better reporting.",
            "in_scope": "CRM module.",
            "expected_deliverables": "Working CRM.",
            "acceptance_criteria": "Passes UAT.",
            "needed_by_date": date(2026, 12, 31),
            "priority": ProjectRequestPriority.P3,
            "status": ProjectRequestStatus.DRAFT,
        }
        data.update(overrides)
        return create_project_request_draft(**data)

    def test_project_name_stripped_after_submit(self):
        """project_name with leading/trailing spaces is saved stripped."""
        from project_requests.services import submit_project_request
        pr = self._make_full_draft(requester=self.user, project_name="  CRM Report  ")
        submit_project_request(pr, self.user)
        pr.refresh_from_db()
        self.assertEqual(pr.project_name, "CRM Report")

    def test_duplicate_prevention_blocks_whitespace_variant(self):
        """Duplicate prevention blocks 'CRM Report' vs ' CRM Report '."""
        from project_requests.services import submit_project_request
        from project_requests.services import check_duplicate_open_request
        from project_requests.services import normalize_project_request_for_submit
        from django.core.exceptions import ValidationError

        # First request submits successfully
        pr1 = self._make_full_draft(requester=self.user, project_name="CRM Report")
        submit_project_request(pr1, self.user)

        # Second request by same requester with whitespace-padded name
        pr2 = self._make_full_draft(
            requester=self.user,
            project_name=" CRM Report ",
        )
        # After normalization, pr2.project_name becomes "CRM Report" which
        # is a duplicate of pr1 (same requester, same type, open status)
        normalize_project_request_for_submit(pr2)
        with self.assertRaises(ValidationError):
            check_duplicate_open_request(pr2)

    def test_whitespace_only_required_field_still_fails(self):
        """Whitespace-only required field still fails validation."""
        from project_requests.services import validate_required_for_submit
        from django.core.exceptions import ValidationError
        pr = self._make_full_draft(requester=self.user, project_name="   ")
        with self.assertRaises(ValidationError) as cm:
            validate_required_for_submit(pr)
        self.assertIn("project_name", cm.exception.message_dict)


class UploadTransactionTest(TestCase):
    """Test that upload_project_request_attachment uses atomic transaction."""

    def setUp(self):
        from accounts.models import User, Department, UserDepartment, AccessLevel
        from project_requests.models import (
            ProjectRequestType, ProjectDepartmentProfile,
            ProjectRequestFileType, ProjectRequestStatus,
        )
        from project_requests.services import create_project_request_draft
        from datetime import date

        self.req_dept = Department.objects.create(
            dept_name="IT", dept_code="IT", is_active=True,
        )
        self.proj_dept = Department.objects.create(
            dept_name="Finance", dept_code="FIN", is_active=True,
        )
        self.user = User.objects.create_user(
            username="staff1", password="pass", is_staff=True, is_active=True,
        )
        UserDepartment.objects.create(
            user=self.user, department=self.req_dept,
            access_level=AccessLevel.STAFF, is_active=True,
        )
        self.type = ProjectRequestType.objects.create(
            name="Report", code="RPT", is_active=True,
        )
        self.profile = ProjectDepartmentProfile.objects.create(
            department=self.proj_dept,
            is_active=True,
            can_receive_project_requests=True,
        )
        self.ftype = ProjectRequestFileType.objects.create(
            code="pdf", name="PDF", allowed_extensions="pdf,PDF",
            max_file_size_mb=10, is_active=True,
        )
        from project_requests.models import ProjectRequestPriority
        data = {
            "requester": self.user,
            "request_department": self.req_dept,
            "project_department": self.proj_dept,
            "request_type": self.type,
            "project_name": "CRM Report",
            "scope_summary": "Build CRM reporting module.",
            "business_problem": "Need better reporting.",
            "in_scope": "CRM module.",
            "expected_deliverables": "Working CRM.",
            "acceptance_criteria": "Passes UAT.",
            "needed_by_date": date(2026, 12, 31),
            "priority": ProjectRequestPriority.P3,
        }
        self.pr = create_project_request_draft(**data)
        # Force SUBMITTED status after draft creation
        self.pr.status = ProjectRequestStatus.SUBMITTED
        self.pr.save(update_fields=["status"])

    def test_upload_creates_attachment_and_log_atomically(self):
        """Valid upload creates both attachment and FILE_ATTACHED log."""
        from project_requests.services import upload_project_request_attachment
        from project_requests.models import (
            ProjectRequestAttachment, ProjectRequestActivityLog,
            ProjectRequestActionType,
        )
        from django.core.files.uploadedfile import SimpleUploadedFile

        uploaded = SimpleUploadedFile(
            "test.pdf", b"%PDF-1.4 fake pdf content",
            content_type="application/pdf",
        )
        attachment = upload_project_request_attachment(
            self.pr, uploaded, self.ftype, self.user, description="Test",
        )
        self.assertIsInstance(attachment, ProjectRequestAttachment)
        self.assertEqual(attachment.project_request, self.pr)

        logs = ProjectRequestActivityLog.objects.filter(
            project_request=self.pr,
            action_type=ProjectRequestActionType.FILE_ATTACHED,
        )
        self.assertEqual(logs.count(), 1)
        log = logs.first()
        self.assertIn("test.pdf", log.description)


# ============================================================================
# 12. Draft Force DRAFT Tests
# ============================================================================

class DraftForceDraftTest(TestCase):
    """Test that create_project_request_draft always forces DRAFT status."""

    def test_draft_forces_draft_even_when_submitted_passed(self):
        """create_project_request_draft(status=SUBMITTED) still creates DRAFT."""
        from accounts.models import Department
        user = User.objects.create_user(username="u1", password="pass")
        dept = Department.objects.create(dept_code="D1", dept_name="Dept 1")
        pr = create_project_request_draft(
            requester=user,
            request_department=dept,
            status=ProjectRequestStatus.SUBMITTED,
        )
        self.assertEqual(pr.status, ProjectRequestStatus.DRAFT)

    def test_draft_generates_request_number(self):
        """Request number generation behavior remains unchanged."""
        from accounts.models import Department
        user = User.objects.create_user(username="u2", password="pass")
        dept = Department.objects.create(dept_code="D2", dept_name="Dept 2")
        pr = create_project_request_draft(
            requester=user,
            request_department=dept,
        )
        self.assertIsNotNone(pr.request_no)
        self.assertRegex(pr.request_no, r"^PRJ-\d{4}-\d{6}$")


# ============================================================================
# 13. Normalized Duplicate Prevention Tests
# ============================================================================

class NormalizedDuplicatePreventionTest(TestCase):
    """Test that duplicate prevention compares normalized project names."""

    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pass")
        self.user2 = User.objects.create_user(username="bob", password="pass")
        self.dept = Department.objects.create(dept_code="ACCT", dept_name="Accounting")
        self.ptype = ProjectRequestType.objects.create(code="new", name="New System")
        self.ptype2 = ProjectRequestType.objects.create(code="enh", name="Enhancement")

    def test_existing_with_spaces_blocks_clean_name(self):
        """Existing open request project_name=' CRM Report ' blocks 'CRM Report'."""
        ProjectRequest.objects.create(
            requester=self.user,
            request_department=self.dept,
            project_name=" CRM Report ",
            request_type=self.ptype,
            status=ProjectRequestStatus.DRAFT,
        )
        pr2 = ProjectRequest(
            requester=self.user,
            request_department=self.dept,
            project_name="CRM Report",
            request_type=self.ptype,
            status=ProjectRequestStatus.DRAFT,
        )
        with self.assertRaises(ValidationError):
            check_duplicate_open_request(pr2)

    def test_existing_clean_blocks_lowercased_with_spaces(self):
        """Existing 'CRM Report' blocks new ' crm report '."""
        ProjectRequest.objects.create(
            requester=self.user,
            request_department=self.dept,
            project_name="CRM Report",
            request_type=self.ptype,
            status=ProjectRequestStatus.DRAFT,
        )
        pr2 = ProjectRequest(
            requester=self.user,
            request_department=self.dept,
            project_name=" crm report ",
            request_type=self.ptype,
            status=ProjectRequestStatus.DRAFT,
        )
        with self.assertRaises(ValidationError):
            check_duplicate_open_request(pr2)

    def test_same_normalized_name_different_requester_allowed(self):
        """Same normalized project_name but different requester is allowed."""
        ProjectRequest.objects.create(
            requester=self.user,
            request_department=self.dept,
            project_name=" CRM Report ",
            request_type=self.ptype,
            status=ProjectRequestStatus.DRAFT,
        )
        pr2 = ProjectRequest(
            requester=self.user2,
            request_department=self.dept,
            project_name="CRM Report",
            request_type=self.ptype,
            status=ProjectRequestStatus.DRAFT,
        )
        check_duplicate_open_request(pr2)  # Should not raise

    def test_same_normalized_name_different_type_allowed(self):
        """Same normalized project_name but different request_type is allowed."""
        ProjectRequest.objects.create(
            requester=self.user,
            request_department=self.dept,
            project_name=" CRM Report ",
            request_type=self.ptype,
            status=ProjectRequestStatus.DRAFT,
        )
        pr2 = ProjectRequest(
            requester=self.user,
            request_department=self.dept,
            project_name="CRM Report",
            request_type=self.ptype2,
            status=ProjectRequestStatus.DRAFT,
        )
        check_duplicate_open_request(pr2)  # Should not raise

    def test_completed_request_with_spaces_does_not_block(self):
        """Completed old request with spaces still does not block."""
        ProjectRequest.objects.create(
            requester=self.user,
            request_department=self.dept,
            project_name=" CRM Report ",
            request_type=self.ptype,
            status=ProjectRequestStatus.COMPLETED,
        )
        pr2 = ProjectRequest(
            requester=self.user,
            request_department=self.dept,
            project_name="CRM Report",
            request_type=self.ptype,
            status=ProjectRequestStatus.DRAFT,
        )
        check_duplicate_open_request(pr2)  # Should not raise

    def test_rejected_request_with_spaces_does_not_block(self):
        """Rejected old request with spaces still does not block."""
        ProjectRequest.objects.create(
            requester=self.user,
            request_department=self.dept,
            project_name=" CRM Report ",
            request_type=self.ptype,
            status=ProjectRequestStatus.REJECTED,
        )
        pr2 = ProjectRequest(
            requester=self.user,
            request_department=self.dept,
            project_name="CRM Report",
            request_type=self.ptype,
            status=ProjectRequestStatus.DRAFT,
        )
        check_duplicate_open_request(pr2)  # Should not raise

    def test_cancelled_request_with_spaces_does_not_block(self):
        """Cancelled old request with spaces still does not block."""
        ProjectRequest.objects.create(
            requester=self.user,
            request_department=self.dept,
            project_name=" CRM Report ",
            request_type=self.ptype,
            status=ProjectRequestStatus.CANCELLED,
        )
        pr2 = ProjectRequest(
            requester=self.user,
            request_department=self.dept,
            project_name="CRM Report",
            request_type=self.ptype,
            status=ProjectRequestStatus.DRAFT,
        )
        check_duplicate_open_request(pr2)  # Should not raise


# ============================================================================
# 14. Extension Dot Handling Tests
# ============================================================================

class ExtensionDotHandlingTest(TestCase):
    """Test that allowed_extensions parsing handles dots correctly."""

    def setUp(self):
        self.user = User.objects.create_user(username="uploader", password="pass")
        self.dept = Department.objects.create(dept_code="MIS", dept_name="MIS")
        self.pr = ProjectRequest.objects.create(
            requester=self.user,
            request_department=self.dept,
        )

    def test_allowed_extensions_without_dots_accepts_file(self):
        """allowed_extensions='pdf' accepts test.pdf."""
        ftype = ProjectRequestFileType.objects.create(
            code="pdf", name="PDF", allowed_extensions="pdf",
            max_file_size_mb=10, is_active=True,
        )
        uploaded = SimpleUploadedFile(
            "test.pdf", b"%PDF-1.4", content_type="application/pdf",
        )
        attachment = upload_project_request_attachment(
            self.pr, uploaded, ftype, self.user,
        )
        self.assertEqual(attachment.original_filename, "test.pdf")

    def test_allowed_extensions_with_dots_accepts_file(self):
        """allowed_extensions='.pdf,.PDF' also accepts test.pdf."""
        ftype = ProjectRequestFileType.objects.create(
            code="pdf2", name="PDF2", allowed_extensions=".pdf,.PDF",
            max_file_size_mb=10, is_active=True,
        )
        uploaded = SimpleUploadedFile(
            "test.pdf", b"%PDF-1.4", content_type="application/pdf",
        )
        attachment = upload_project_request_attachment(
            self.pr, uploaded, ftype, self.user,
        )
        self.assertEqual(attachment.original_filename, "test.pdf")


# ============================================================================
# 15. Admin Import Test
# ============================================================================

class AdminImportTest(TestCase):
    def test_admin_imports_do_not_fail(self):
        from project_requests import admin  # noqa: F401
        self.assertTrue(True)


# ============================================================================
# 16. Approval Task Permission Tests (Phase 3A)
# ============================================================================

class ApprovalTaskPermissionTest(TestCase):
    """Test can_approve_project_request_task and can_reject_project_request_task."""

    def setUp(self):
        # Create departments
        self.req_dept = Department.objects.create(dept_code="ACCT", dept_name="Accounting")
        self.proj_dept = Department.objects.create(dept_code="MIS", dept_name="MIS")
        self.ptype = ProjectRequestType.objects.create(code="new", name="New System")
        ProjectDepartmentProfile.objects.create(
            department=self.proj_dept,
            is_active=True,
            can_receive_project_requests=True,
        )

        # Create requester (staff in request dept)
        self.requester = User.objects.create_user(username="requester", password="pass")
        UserDepartment.objects.create(
            user=self.requester,
            department=self.req_dept,
            access_level=AccessLevel.STAFF,
            is_active=True,
        )

        # Create project request in REVIEWING status
        self.pr = ProjectRequest.objects.create(
            requester=self.requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            request_type=self.ptype,
            priority=ProjectRequestPriority.P3,
            needed_by_date=date(2026, 12, 31),
            project_name="Test Project",
            scope_summary="Summary",
            business_problem="Problem",
            in_scope="In scope",
            expected_deliverables="Deliverables",
            acceptance_criteria="Criteria",
            status=ProjectRequestStatus.REVIEWING,
        )

        # Create approval tasks
        self.proj_mgr_task = ProjectRequestApprovalTask.objects.create(
            project_request=self.pr,
            department=self.proj_dept,
            role=ProjectApprovalRole.PROJECT_DEPT_MANAGER,
            status=ProjectApprovalTaskStatus.PENDING,
        )
        self.req_mgr_task = ProjectRequestApprovalTask.objects.create(
            project_request=self.pr,
            department=self.req_dept,
            role=ProjectApprovalRole.REQUEST_DEPT_MANAGER,
            status=ProjectApprovalTaskStatus.PENDING,
        )
        self.vp_task = ProjectRequestApprovalTask.objects.create(
            project_request=self.pr,
            department=self.proj_dept,
            role=ProjectApprovalRole.PROJECT_DEPT_VP,
            status=ProjectApprovalTaskStatus.PENDING,
        )

    def _make_manager(self, username, dept, can_approve=True):
        """Create a manager-level user in the given department."""
        user = User.objects.create_user(username=username, password="pass")
        UserDepartment.objects.create(
            user=user,
            department=dept,
            access_level=AccessLevel.MANAGER,
            is_active=True,
            can_approve=can_approve,
        )
        return user

    def _make_director(self, username, dept, can_approve=True):
        """Create a director-level user in the given department."""
        user = User.objects.create_user(username=username, password="pass")
        UserDepartment.objects.create(
            user=user,
            department=dept,
            access_level=AccessLevel.DIRECTOR,
            is_active=True,
            can_approve=can_approve,
        )
        return user

    def _make_vp(self, username, dept, can_approve=True):
        """Create a VP-level user in the given department."""
        user = User.objects.create_user(username=username, password="pass")
        UserDepartment.objects.create(
            user=user,
            department=dept,
            access_level=AccessLevel.VP,
            is_active=True,
            can_approve=can_approve,
        )
        return user

    def _make_staff(self, username, dept):
        """Create a staff-level user in the given department."""
        user = User.objects.create_user(username=username, password="pass")
        UserDepartment.objects.create(
            user=user,
            department=dept,
            access_level=AccessLevel.STAFF,
            is_active=True,
            can_approve=False,
        )
        return user

    # ---- can_approve_project_request_task tests ----

    def test_manager_with_can_approve_can_approve_project_dept_manager_task(self):
        """Manager with can_approve=True can approve PROJECT_DEPT_MANAGER task."""
        manager = self._make_manager("mgr1", self.proj_dept, can_approve=True)
        self.assertTrue(can_approve_project_request_task(manager, self.proj_mgr_task))

    def test_director_with_can_approve_can_approve_project_dept_manager_task(self):
        """Director with can_approve=True can approve PROJECT_DEPT_MANAGER task."""
        director = self._make_director("dir1", self.proj_dept, can_approve=True)
        self.assertTrue(can_approve_project_request_task(director, self.proj_mgr_task))

    def test_vp_with_can_approve_can_approve_project_dept_manager_task(self):
        """VP with can_approve=True can approve PROJECT_DEPT_MANAGER task."""
        vp = self._make_vp("vp_mgr", self.proj_dept, can_approve=True)
        self.assertTrue(can_approve_project_request_task(vp, self.proj_mgr_task))

    def test_staff_cannot_approve_manager_task(self):
        """Staff cannot approve PROJECT_DEPT_MANAGER task."""
        staff = self._make_staff("staff1", self.proj_dept)
        self.assertFalse(can_approve_project_request_task(staff, self.proj_mgr_task))

    def test_manager_with_can_approve_false_cannot_approve(self):
        """Manager with can_approve=False cannot approve."""
        manager = self._make_manager("mgr2", self.proj_dept, can_approve=False)
        self.assertFalse(can_approve_project_request_task(manager, self.proj_mgr_task))

    def test_vp_task_requires_vp_access_level(self):
        """VP task requires VP access level in the department."""
        # Manager cannot approve VP task
        manager = self._make_manager("mgr_vp_task", self.proj_dept, can_approve=True)
        self.assertFalse(can_approve_project_request_task(manager, self.vp_task))

        # Director cannot approve VP task
        director = self._make_director("dir_vp_task", self.proj_dept, can_approve=True)
        self.assertFalse(can_approve_project_request_task(director, self.vp_task))

        # VP can approve VP task
        vp = self._make_vp("vp_approve", self.proj_dept, can_approve=True)
        self.assertTrue(can_approve_project_request_task(vp, self.vp_task))

    def test_wrong_department_manager_cannot_approve(self):
        """Manager in wrong department cannot approve."""
        # Create a manager in request_dept, not proj_dept
        wrong_manager = self._make_manager("wrong_mgr", self.req_dept, can_approve=True)
        self.assertFalse(can_approve_project_request_task(wrong_manager, self.proj_mgr_task))

    def test_can_reject_mirrors_can_approve(self):
        """can_reject_project_request_task mirrors can_approve_project_request_task."""
        manager = self._make_manager("mgr_reject", self.proj_dept, can_approve=True)
        self.assertEqual(
            can_reject_project_request_task(manager, self.proj_mgr_task),
            can_approve_project_request_task(manager, self.proj_mgr_task),
        )

    def test_non_pending_task_cannot_be_approved(self):
        """Non-PENDING task cannot be approved."""
        manager = self._make_manager("mgr_approved", self.proj_dept, can_approve=True)
        self.proj_mgr_task.status = ProjectApprovalTaskStatus.APPROVED
        self.proj_mgr_task.save()
        self.assertFalse(can_approve_project_request_task(manager, self.proj_mgr_task))

    def test_non_pending_task_cannot_be_rejected(self):
        """Non-PENDING task cannot be rejected."""
        manager = self._make_manager("mgr_rejected", self.proj_dept, can_approve=True)
        self.proj_mgr_task.status = ProjectApprovalTaskStatus.REJECTED
        self.proj_mgr_task.save()
        self.assertFalse(can_reject_project_request_task(manager, self.proj_mgr_task))

    def test_task_whose_project_request_not_reviewing_cannot_be_approved(self):
        """Task whose project_request is not REVIEWING cannot be approved."""
        manager = self._make_manager("mgr_not_reviewing", self.proj_dept, can_approve=True)
        self.pr.status = ProjectRequestStatus.APPROVED
        self.pr.save()
        self.assertFalse(can_approve_project_request_task(manager, self.proj_mgr_task))

    def test_task_whose_project_request_not_reviewing_cannot_be_rejected(self):
        """Task whose project_request is not REVIEWING cannot be rejected."""
        manager = self._make_manager("mgr_not_reviewing_rej", self.proj_dept, can_approve=True)
        self.pr.status = ProjectRequestStatus.REJECTED
        self.pr.save()
        self.assertFalse(can_reject_project_request_task(manager, self.proj_mgr_task))

    def test_superuser_can_approve_when_reviewing(self):
        """Superuser can approve pending task when parent request is REVIEWING."""
        superuser = User.objects.create_superuser(username="super", password="pass", email="s@test.com")
        self.assertTrue(can_approve_project_request_task(superuser, self.proj_mgr_task))

    def test_superuser_cannot_approve_when_not_reviewing(self):
        """Superuser cannot approve task when parent request is not REVIEWING."""
        superuser = User.objects.create_superuser(username="super2", password="pass", email="s2@test.com")
        self.pr.status = ProjectRequestStatus.APPROVED
        self.pr.save()
        self.assertFalse(can_approve_project_request_task(superuser, self.proj_mgr_task))

    def test_unauthenticated_user_cannot_approve(self):
        """Unauthenticated user cannot approve."""
        self.assertFalse(can_approve_project_request_task(None, self.proj_mgr_task))

    def test_inactive_user_cannot_approve(self):
        """Inactive user cannot approve."""
        manager = self._make_manager("mgr_inactive", self.proj_dept, can_approve=True)
        manager.is_active = False
        manager.save()
        self.assertFalse(can_approve_project_request_task(manager, self.proj_mgr_task))


# ============================================================================
# 17. Approve Project Request Service Tests (Phase 3A)
# ============================================================================

class ApproveProjectRequestServiceTest(TestCase):
    """Test approve_project_request service."""

    def setUp(self):
        # Create departments
        self.req_dept = Department.objects.create(dept_code="ACCT", dept_name="Accounting")
        self.proj_dept = Department.objects.create(dept_code="MIS", dept_name="MIS")
        self.ptype = ProjectRequestType.objects.create(code="new", name="New System")
        ProjectDepartmentProfile.objects.create(
            department=self.proj_dept,
            is_active=True,
            can_receive_project_requests=True,
        )

        # Create requester (staff in request dept)
        self.requester = User.objects.create_user(username="requester", password="pass")
        UserDepartment.objects.create(
            user=self.requester,
            department=self.req_dept,
            access_level=AccessLevel.STAFF,
            is_active=True,
        )

        # Create approver (manager in project dept)
        self.approver = User.objects.create_user(username="approver", password="pass")
        UserDepartment.objects.create(
            user=self.approver,
            department=self.proj_dept,
            access_level=AccessLevel.MANAGER,
            is_active=True,
            can_approve=True,
        )

    def _create_reviewing_pr(self):
        """Create a project request in REVIEWING status with one approval task."""
        pr = ProjectRequest.objects.create(
            requester=self.requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            request_type=self.ptype,
            priority=ProjectRequestPriority.P3,
            needed_by_date=date(2026, 12, 31),
            project_name="Test Project",
            scope_summary="Summary",
            business_problem="Problem",
            in_scope="In scope",
            expected_deliverables="Deliverables",
            acceptance_criteria="Criteria",
            status=ProjectRequestStatus.REVIEWING,
        )
        task = ProjectRequestApprovalTask.objects.create(
            project_request=pr,
            department=self.proj_dept,
            role=ProjectApprovalRole.PROJECT_DEPT_MANAGER,
            status=ProjectApprovalTaskStatus.PENDING,
        )
        return pr, task

    def test_approve_single_pending_task_transitions_to_approved(self):
        """Approve single pending task transitions ProjectRequest REVIEWING -> APPROVED."""
        pr, task = self._create_reviewing_pr()
        result = approve_project_request(pr, task, self.approver, comment="Looks good")

        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.APPROVED)
        self.assertIsNotNone(pr.approved_at)

    def test_approve_first_of_two_tasks_keeps_reviewing(self):
        """Approve first of two pending tasks keeps ProjectRequest REVIEWING."""
        pr, task1 = self._create_reviewing_pr()
        task2 = ProjectRequestApprovalTask.objects.create(
            project_request=pr,
            department=self.req_dept,
            role=ProjectApprovalRole.REQUEST_DEPT_MANAGER,
            status=ProjectApprovalTaskStatus.PENDING,
        )
        # Add approver for task2
        req_approver = User.objects.create_user(username="req_approver", password="pass")
        UserDepartment.objects.create(
            user=req_approver,
            department=self.req_dept,
            access_level=AccessLevel.MANAGER,
            is_active=True,
            can_approve=True,
        )

        result = approve_project_request(pr, task1, self.approver, comment="First approved")

        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.REVIEWING)
        self.assertIsNone(pr.approved_at)

    def test_approve_second_task_transitions_to_approved(self):
        """Approve second of two tasks transitions ProjectRequest -> APPROVED."""
        pr, task1 = self._create_reviewing_pr()
        task2 = ProjectRequestApprovalTask.objects.create(
            project_request=pr,
            department=self.req_dept,
            role=ProjectApprovalRole.REQUEST_DEPT_MANAGER,
            status=ProjectApprovalTaskStatus.PENDING,
        )
        # Add approvers
        req_approver = User.objects.create_user(username="req_approver2", password="pass")
        UserDepartment.objects.create(
            user=req_approver,
            department=self.req_dept,
            access_level=AccessLevel.MANAGER,
            is_active=True,
            can_approve=True,
        )

        # Approve first task
        approve_project_request(pr, task1, self.approver, comment="First")

        # Approve second task
        result = approve_project_request(pr, task2, req_approver, comment="Second")

        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.APPROVED)
        self.assertIsNotNone(pr.approved_at)

    def test_approved_at_set_only_when_project_becomes_approved(self):
        """approved_at is set only when project becomes APPROVED."""
        pr, task1 = self._create_reviewing_pr()
        task2 = ProjectRequestApprovalTask.objects.create(
            project_request=pr,
            department=self.req_dept,
            role=ProjectApprovalRole.REQUEST_DEPT_MANAGER,
            status=ProjectApprovalTaskStatus.PENDING,
        )
        req_approver = User.objects.create_user(username="req_approver3", password="pass")
        UserDepartment.objects.create(
            user=req_approver,
            department=self.req_dept,
            access_level=AccessLevel.MANAGER,
            is_active=True,
            can_approve=True,
        )

        # Approve first task - approved_at should still be None
        approve_project_request(pr, task1, self.approver, comment="First")
        pr.refresh_from_db()
        self.assertIsNone(pr.approved_at)

        # Approve second task - approved_at should now be set
        approve_project_request(pr, task2, req_approver, comment="Second")
        pr.refresh_from_db()
        self.assertIsNotNone(pr.approved_at)

    def test_approval_task_fields_set(self):
        """Approval task acted_by, acted_at, decision_comment are set."""
        pr, task = self._create_reviewing_pr()
        approve_project_request(pr, task, self.approver, comment="  Looks good  ")

        task.refresh_from_db()
        self.assertEqual(task.status, ProjectApprovalTaskStatus.APPROVED)
        self.assertEqual(task.acted_by, self.approver)
        self.assertIsNotNone(task.acted_at)
        self.assertEqual(task.decision_comment, "Looks good")

    def test_unauthorized_user_raises_permission_denied(self):
        """Unauthorized user raises PermissionDenied."""
        pr, task = self._create_reviewing_pr()
        # Create a user without approval permissions
        wrong_user = User.objects.create_user(username="wrong", password="pass")
        UserDepartment.objects.create(
            user=wrong_user,
            department=self.proj_dept,
            access_level=AccessLevel.STAFF,
            is_active=True,
            can_approve=False,
        )

        with self.assertRaises(PermissionDenied):
            approve_project_request(pr, task, wrong_user)

    def test_wrong_department_manager_raises_permission_denied(self):
        """Wrong department manager raises PermissionDenied."""
        pr, task = self._create_reviewing_pr()
        # Create a manager in the wrong department
        wrong_dept = Department.objects.create(dept_code="HR", dept_name="HR")
        wrong_manager = User.objects.create_user(username="wrong_mgr", password="pass")
        UserDepartment.objects.create(
            user=wrong_manager,
            department=wrong_dept,
            access_level=AccessLevel.MANAGER,
            is_active=True,
            can_approve=True,
        )

        with self.assertRaises(PermissionDenied):
            approve_project_request(pr, task, wrong_manager)

    def test_non_pending_task_raises_validation_error(self):
        """Non-PENDING task raises ValidationError."""
        pr, task = self._create_reviewing_pr()
        task.status = ProjectApprovalTaskStatus.APPROVED
        task.save()

        with self.assertRaises(ValidationError):
            approve_project_request(pr, task, self.approver)

    def test_approval_task_from_another_project_raises_validation_error(self):
        """Approval task from another project_request raises ValidationError."""
        pr1, task1 = self._create_reviewing_pr()
        pr2, task2 = self._create_reviewing_pr()

        with self.assertRaises(ValidationError):
            approve_project_request(pr1, task2, self.approver)

    def test_stale_in_memory_project_request_does_not_bypass_db_check(self):
        """Stale in-memory ProjectRequest object does not bypass DB status check."""
        pr, task = self._create_reviewing_pr()
        # Modify in-memory status to APPROVED (but DB is still REVIEWING)
        pr.status = ProjectRequestStatus.APPROVED

        # Should still work because DB has REVIEWING
        result = approve_project_request(pr, task, self.approver, comment="Works")

        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.APPROVED)

    def test_activity_log_created_when_project_becomes_approved(self):
        """Activity log created when project becomes APPROVED."""
        pr, task = self._create_reviewing_pr()
        approve_project_request(pr, task, self.approver, comment="Approved")

        logs = ProjectRequestActivityLog.objects.filter(
            project_request=pr,
            action_type=ProjectRequestActionType.APPROVED,
        )
        self.assertEqual(logs.count(), 1)
        log = logs.first()
        self.assertEqual(log.from_status, ProjectRequestStatus.REVIEWING)
        self.assertEqual(log.to_status, ProjectRequestStatus.APPROVED)
        self.assertEqual(log.actor, self.approver)


# ============================================================================
# 18. Reject Project Request Service Tests (Phase 3A)
# ============================================================================

class RejectProjectRequestServiceTest(TestCase):
    """Test reject_project_request service."""

    def setUp(self):
        # Create departments
        self.req_dept = Department.objects.create(dept_code="ACCT", dept_name="Accounting")
        self.proj_dept = Department.objects.create(dept_code="MIS", dept_name="MIS")
        self.ptype = ProjectRequestType.objects.create(code="new", name="New System")
        ProjectDepartmentProfile.objects.create(
            department=self.proj_dept,
            is_active=True,
            can_receive_project_requests=True,
        )

        # Create requester (staff in request dept)
        self.requester = User.objects.create_user(username="requester", password="pass")
        UserDepartment.objects.create(
            user=self.requester,
            department=self.req_dept,
            access_level=AccessLevel.STAFF,
            is_active=True,
        )

        # Create rejector (manager in project dept)
        self.rejector = User.objects.create_user(username="rejector", password="pass")
        UserDepartment.objects.create(
            user=self.rejector,
            department=self.proj_dept,
            access_level=AccessLevel.MANAGER,
            is_active=True,
            can_approve=True,
        )

    def _create_reviewing_pr(self):
        """Create a project request in REVIEWING status with one approval task."""
        pr = ProjectRequest.objects.create(
            requester=self.requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            request_type=self.ptype,
            priority=ProjectRequestPriority.P3,
            needed_by_date=date(2026, 12, 31),
            project_name="Test Project",
            scope_summary="Summary",
            business_problem="Problem",
            in_scope="In scope",
            expected_deliverables="Deliverables",
            acceptance_criteria="Criteria",
            status=ProjectRequestStatus.REVIEWING,
        )
        task = ProjectRequestApprovalTask.objects.create(
            project_request=pr,
            department=self.proj_dept,
            role=ProjectApprovalRole.PROJECT_DEPT_MANAGER,
            status=ProjectApprovalTaskStatus.PENDING,
        )
        return pr, task

    def test_reject_single_pending_task_transitions_to_rejected(self):
        """Reject single pending task transitions ProjectRequest REVIEWING -> REJECTED."""
        pr, task = self._create_reviewing_pr()
        result = reject_project_request(pr, task, self.rejector, comment="Not feasible")

        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.REJECTED)

    def test_reject_first_of_two_tasks_transitions_to_rejected(self):
        """Reject first of two pending tasks transitions ProjectRequest -> REJECTED."""
        pr, task1 = self._create_reviewing_pr()
        task2 = ProjectRequestApprovalTask.objects.create(
            project_request=pr,
            department=self.req_dept,
            role=ProjectApprovalRole.REQUEST_DEPT_MANAGER,
            status=ProjectApprovalTaskStatus.PENDING,
        )

        result = reject_project_request(pr, task1, self.rejector, comment="Rejected")

        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.REJECTED)

    def test_rejection_comment_required(self):
        """Rejection comment is required."""
        pr, task = self._create_reviewing_pr()

        with self.assertRaises(ValidationError):
            reject_project_request(pr, task, self.rejector, comment="")

    def test_whitespace_only_rejection_comment_raises_validation_error(self):
        """Whitespace-only rejection comment raises ValidationError."""
        pr, task = self._create_reviewing_pr()

        with self.assertRaises(ValidationError):
            reject_project_request(pr, task, self.rejector, comment="   ")

    def test_unauthorized_user_raises_permission_denied(self):
        """Unauthorized user raises PermissionDenied."""
        pr, task = self._create_reviewing_pr()
        wrong_user = User.objects.create_user(username="wrong", password="pass")
        UserDepartment.objects.create(
            user=wrong_user,
            department=self.proj_dept,
            access_level=AccessLevel.STAFF,
            is_active=True,
            can_approve=False,
        )

        with self.assertRaises(PermissionDenied):
            reject_project_request(pr, task, wrong_user, comment="No")

    def test_wrong_department_manager_raises_permission_denied(self):
        """Wrong department manager raises PermissionDenied."""
        pr, task = self._create_reviewing_pr()
        wrong_dept = Department.objects.create(dept_code="HR", dept_name="HR")
        wrong_manager = User.objects.create_user(username="wrong_mgr_rej", password="pass")
        UserDepartment.objects.create(
            user=wrong_manager,
            department=wrong_dept,
            access_level=AccessLevel.MANAGER,
            is_active=True,
            can_approve=True,
        )

        with self.assertRaises(PermissionDenied):
            reject_project_request(pr, task, wrong_manager, comment="No")

    def test_non_pending_task_raises_validation_error(self):
        """Non-PENDING task raises ValidationError."""
        pr, task = self._create_reviewing_pr()
        task.status = ProjectApprovalTaskStatus.REJECTED
        task.save()

        with self.assertRaises(ValidationError):
            reject_project_request(pr, task, self.rejector, comment="Already rejected")

    def test_approval_task_from_another_project_raises_validation_error(self):
        """Approval task from another project_request raises ValidationError."""
        pr1, task1 = self._create_reviewing_pr()
        pr2, task2 = self._create_reviewing_pr()

        with self.assertRaises(ValidationError):
            reject_project_request(pr1, task2, self.rejector, comment="Wrong project")

    def test_rejected_task_fields_set(self):
        """Rejected task acted_by, acted_at, decision_comment are set."""
        pr, task = self._create_reviewing_pr()
        reject_project_request(pr, task, self.rejector, comment="  Not feasible  ")

        task.refresh_from_db()
        self.assertEqual(task.status, ProjectApprovalTaskStatus.REJECTED)
        self.assertEqual(task.acted_by, self.rejector)
        self.assertIsNotNone(task.acted_at)
        self.assertEqual(task.decision_comment, "Not feasible")

    def test_activity_log_created(self):
        """Activity log created when project is rejected."""
        pr, task = self._create_reviewing_pr()
        reject_project_request(pr, task, self.rejector, comment="Not feasible")

        logs = ProjectRequestActivityLog.objects.filter(
            project_request=pr,
            action_type=ProjectRequestActionType.REJECTED,
        )
        self.assertEqual(logs.count(), 1)
        log = logs.first()
        self.assertEqual(log.from_status, ProjectRequestStatus.REVIEWING)
        self.assertEqual(log.to_status, ProjectRequestStatus.REJECTED)
        self.assertEqual(log.actor, self.rejector)

    def test_remaining_pending_task_not_actionable(self):
        """Remaining pending task is not actionable because parent request is REJECTED."""
        pr, task1 = self._create_reviewing_pr()
        task2 = ProjectRequestApprovalTask.objects.create(
            project_request=pr,
            department=self.req_dept,
            role=ProjectApprovalRole.REQUEST_DEPT_MANAGER,
            status=ProjectApprovalTaskStatus.PENDING,
        )

        # Reject first task
        reject_project_request(pr, task1, self.rejector, comment="Rejected")

        # Verify task2 is still PENDING but parent is REJECTED
        task2.refresh_from_db()
        self.assertEqual(task2.status, ProjectApprovalTaskStatus.PENDING)

        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.REJECTED)

    def test_get_my_pending_approval_tasks_excludes_rejected_request(self):
        """get_my_pending_approval_tasks does not return pending tasks from rejected request."""
        pr, task1 = self._create_reviewing_pr()
        task2 = ProjectRequestApprovalTask.objects.create(
            project_request=pr,
            department=self.req_dept,
            role=ProjectApprovalRole.REQUEST_DEPT_MANAGER,
            status=ProjectApprovalTaskStatus.PENDING,
        )

        # Create approver for task2
        req_approver = User.objects.create_user(username="req_approver_rej", password="pass")
        UserDepartment.objects.create(
            user=req_approver,
            department=self.req_dept,
            access_level=AccessLevel.MANAGER,
            is_active=True,
            can_approve=True,
        )

        # Reject first task
        reject_project_request(pr, task1, self.rejector, comment="Rejected")

        # Verify task2 is not in pending approval tasks
        pending = get_my_pending_approval_tasks(req_approver).filter(pk=task2.pk)
        self.assertEqual(pending.count(), 0)


# ============================================================================
# 19. Regression Tests (Phase 3A)
# ============================================================================

class Phase3ARegressionTest(TestCase):
    """Regression tests to ensure existing functionality still works."""

    def setUp(self):
        self.req_dept = Department.objects.create(dept_code="ACCT", dept_name="Accounting")
        self.proj_dept = Department.objects.create(dept_code="MIS", dept_name="MIS")
        self.ptype = ProjectRequestType.objects.create(code="new", name="New System")
        ProjectDepartmentProfile.objects.create(
            department=self.proj_dept,
            is_active=True,
            can_receive_project_requests=True,
        )

    def test_submit_project_request_approval_task_generation_still_works(self):
        """Existing submit_project_request() approval task generation still works."""
        user = User.objects.create_user(username="submitter", password="pass")
        UserDepartment.objects.create(
            user=user,
            department=self.req_dept,
            access_level=AccessLevel.STAFF,
            is_active=True,
        )

        pr = create_project_request_draft(
            requester=user,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            request_type=self.ptype,
            priority=ProjectRequestPriority.P3,
            needed_by_date=date(2026, 12, 31),
            project_name="Test Project",
            scope_summary="Summary",
            business_problem="Problem",
            in_scope="In scope",
            expected_deliverables="Deliverables",
            acceptance_criteria="Criteria",
        )

        result = submit_project_request(pr, user)

        # Should be in REVIEWING status with approval tasks
        self.assertEqual(result.status, ProjectRequestStatus.REVIEWING)
        tasks = ProjectRequestApprovalTask.objects.filter(project_request=result)
        self.assertGreater(tasks.count(), 0)

    def test_existing_tests_still_pass(self):
        """Smoke test that existing functionality is not broken."""
        # Just verify imports work
        from project_requests.services import (
            generate_request_no,
            create_project_request_draft,
            submit_project_request,
        )
        from project_requests.permissions import (
            can_view_project_request,
            can_submit_project_request,
        )
        from project_requests.selectors import get_visible_project_requests
        self.assertTrue(True)


# ============================================================================
# 20. Phase 3A Hardening Tests
# ============================================================================

class Phase3AHardeningTest(TestCase):
    """Hardening tests for Phase 3A implementation."""

    def setUp(self):
        # Create departments
        self.req_dept = Department.objects.create(dept_code="ACCT", dept_name="Accounting")
        self.proj_dept = Department.objects.create(dept_code="MIS", dept_name="MIS")
        self.ptype = ProjectRequestType.objects.create(code="new", name="New System")
        ProjectDepartmentProfile.objects.create(
            department=self.proj_dept,
            is_active=True,
            can_receive_project_requests=True,
        )

        # Create requester (staff in request dept)
        self.requester = User.objects.create_user(username="requester", password="pass")
        UserDepartment.objects.create(
            user=self.requester,
            department=self.req_dept,
            access_level=AccessLevel.STAFF,
            is_active=True,
        )

        # Create approver (manager in project dept)
        self.approver = User.objects.create_user(username="approver", password="pass")
        UserDepartment.objects.create(
            user=self.approver,
            department=self.proj_dept,
            access_level=AccessLevel.MANAGER,
            is_active=True,
            can_approve=True,
        )

    def _create_reviewing_pr(self):
        """Create a project request in REVIEWING status with one approval task."""
        pr = ProjectRequest.objects.create(
            requester=self.requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            request_type=self.ptype,
            priority=ProjectRequestPriority.P3,
            needed_by_date=date(2026, 12, 31),
            project_name="Test Project",
            scope_summary="Summary",
            business_problem="Problem",
            in_scope="In scope",
            expected_deliverables="Deliverables",
            acceptance_criteria="Criteria",
            status=ProjectRequestStatus.REVIEWING,
        )
        task = ProjectRequestApprovalTask.objects.create(
            project_request=pr,
            department=self.proj_dept,
            role=ProjectApprovalRole.PROJECT_DEPT_MANAGER,
            status=ProjectApprovalTaskStatus.PENDING,
        )
        return pr, task

    # ---- Superuser selector tests ----

    def test_superuser_sees_pending_approval_task_for_reviewing_request(self):
        """Superuser sees pending approval task for REVIEWING request in get_my_pending_approval_tasks()."""
        superuser = User.objects.create_superuser(username="super", password="pass", email="s@test.com")
        pr, task = self._create_reviewing_pr()

        tasks = get_my_pending_approval_tasks(superuser)
        self.assertIn(task, tasks)

    def test_superuser_does_not_see_pending_task_if_parent_approved(self):
        """Superuser does not see pending approval task if parent request is APPROVED."""
        superuser = User.objects.create_superuser(username="super2", password="pass", email="s2@test.com")
        pr, task = self._create_reviewing_pr()
        pr.status = ProjectRequestStatus.APPROVED
        pr.save()

        tasks = get_my_pending_approval_tasks(superuser)
        self.assertNotIn(task, tasks)

    def test_superuser_does_not_see_pending_task_if_parent_rejected(self):
        """Superuser does not see pending approval task if parent request is REJECTED."""
        superuser = User.objects.create_superuser(username="super3", password="pass", email="s3@test.com")
        pr, task = self._create_reviewing_pr()
        pr.status = ProjectRequestStatus.REJECTED
        pr.save()

        tasks = get_my_pending_approval_tasks(superuser)
        self.assertNotIn(task, tasks)

    def test_superuser_action_context_shows_can_approve(self):
        """get_project_request_action_context(superuser, reviewing_request) shows can_approve_any_task=True."""
        superuser = User.objects.create_superuser(username="super4", password="pass", email="s4@test.com")
        pr, task = self._create_reviewing_pr()

        context = get_project_request_action_context(superuser, pr)
        self.assertTrue(context["can_approve_any_task"])
        self.assertTrue(context["can_reject_any_task"])
        self.assertIn(task, context["pending_approval_tasks_user_can_act_on"])

    # ---- Stale DB status tests ----

    def test_approve_uses_db_status_rejects_stale_reviewing_when_db_approved(self):
        """approve_project_request uses DB status and rejects stale REVIEWING when DB is APPROVED."""
        pr, task = self._create_reviewing_pr()
        # Keep stale in-memory object
        stale_pr = pr

        # Update DB row to APPROVED
        ProjectRequest.objects.filter(pk=pr.pk).update(status=ProjectRequestStatus.APPROVED)

        # Should raise ValidationError because DB status is APPROVED
        with self.assertRaises(ValidationError):
            approve_project_request(stale_pr, task, self.approver, comment="Approved")

    def test_reject_uses_db_status_rejects_stale_reviewing_when_db_approved(self):
        """reject_project_request uses DB status and rejects stale REVIEWING when DB is APPROVED."""
        pr, task = self._create_reviewing_pr()
        # Keep stale in-memory object
        stale_pr = pr

        # Update DB row to APPROVED
        ProjectRequest.objects.filter(pk=pr.pk).update(status=ProjectRequestStatus.APPROVED)

        # Should raise ValidationError because DB status is APPROVED
        with self.assertRaises(ValidationError):
            reject_project_request(stale_pr, task, self.approver, comment="Rejected")

    def test_reject_uses_db_status_rejects_stale_reviewing_when_db_rejected(self):
        """reject_project_request uses DB status and rejects stale REVIEWING when DB is REJECTED."""
        pr, task = self._create_reviewing_pr()
        # Keep stale in-memory object
        stale_pr = pr

        # Update DB row to REJECTED
        ProjectRequest.objects.filter(pk=pr.pk).update(status=ProjectRequestStatus.REJECTED)

        # Should raise ValidationError because DB status is REJECTED
        with self.assertRaises(ValidationError):
            reject_project_request(stale_pr, task, self.approver, comment="Rejected")

    # ---- All-approved check tests ----

    def test_approve_does_not_transition_if_other_task_rejected(self):
        """Approving a pending task does NOT transition project to APPROVED if another task is REJECTED."""
        pr, task1 = self._create_reviewing_pr()
        task2 = ProjectRequestApprovalTask.objects.create(
            project_request=pr,
            department=self.req_dept,
            role=ProjectApprovalRole.REQUEST_DEPT_MANAGER,
            status=ProjectApprovalTaskStatus.REJECTED,  # Already rejected
        )

        # Approve task1 - should NOT transition to APPROVED because task2 is REJECTED
        result = approve_project_request(pr, task1, self.approver, comment="Approved")

        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.REVIEWING)
        self.assertIsNone(pr.approved_at)


# ============================================================================
# Phase 3B: Assignment/Claim Services Tests
# ============================================================================

class AssignProjectRequestPermissionTest(TestCase):
    """Test can_assign_project_request permission helper."""

    def setUp(self):
        # Create departments
        self.req_dept = Department.objects.create(dept_code="ACCT", dept_name="Accounting")
        self.proj_dept = Department.objects.create(dept_code="MIS", dept_name="MIS")
        self.ptype = ProjectRequestType.objects.create(code="new", name="New System")
        ProjectDepartmentProfile.objects.create(
            department=self.proj_dept,
            is_active=True,
            can_receive_project_requests=True,
        )

        # Create requester (staff in request dept)
        self.requester = User.objects.create_user(username="requester", password="pass")
        UserDepartment.objects.create(
            user=self.requester,
            department=self.req_dept,
            access_level=AccessLevel.STAFF,
            is_active=True,
        )

        # Create project dept manager
        self.proj_mgr = User.objects.create_user(username="proj_mgr", password="pass")
        UserDepartment.objects.create(
            user=self.proj_mgr,
            department=self.proj_dept,
            access_level=AccessLevel.MANAGER,
            is_active=True,
        )

        # Create project dept director
        self.proj_dir = User.objects.create_user(username="proj_dir", password="pass")
        UserDepartment.objects.create(
            user=self.proj_dir,
            department=self.proj_dept,
            access_level=AccessLevel.DIRECTOR,
            is_active=True,
        )

        # Create project dept VP
        self.proj_vp = User.objects.create_user(username="proj_vp", password="pass")
        UserDepartment.objects.create(
            user=self.proj_vp,
            department=self.proj_dept,
            access_level=AccessLevel.VP,
            is_active=True,
        )

        # Create request dept manager (not project dept manager)
        self.req_mgr = User.objects.create_user(username="req_mgr", password="pass")
        UserDepartment.objects.create(
            user=self.req_mgr,
            department=self.req_dept,
            access_level=AccessLevel.MANAGER,
            is_active=True,
        )

        # Create project dept staff
        self.proj_staff = User.objects.create_user(username="proj_staff", password="pass")
        UserDepartment.objects.create(
            user=self.proj_staff,
            department=self.proj_dept,
            access_level=AccessLevel.STAFF,
            is_active=True,
        )

        # Create superuser
        self.superuser = User.objects.create_superuser(username="admin", password="pass")

    def _create_approved_pr(self):
        """Create a project request in APPROVED status."""
        return ProjectRequest.objects.create(
            requester=self.requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            request_type=self.ptype,
            priority=ProjectRequestPriority.P3,
            needed_by_date=date(2026, 12, 31),
            project_name="Test Project",
            scope_summary="Summary",
            business_problem="Problem",
            in_scope="In scope",
            expected_deliverables="Deliverables",
            acceptance_criteria="Criteria",
            status=ProjectRequestStatus.APPROVED,
        )

    def test_superuser_can_assign_approved_request(self):
        """Superuser can assign an APPROVED request."""
        pr = self._create_approved_pr()
        self.assertTrue(can_assign_project_request(self.superuser, pr))

    def test_project_dept_manager_can_assign_approved_request(self):
        """Project dept manager can assign an APPROVED request."""
        pr = self._create_approved_pr()
        self.assertTrue(can_assign_project_request(self.proj_mgr, pr))

    def test_project_dept_director_can_assign_approved_request(self):
        """Project dept director can assign an APPROVED request."""
        pr = self._create_approved_pr()
        self.assertTrue(can_assign_project_request(self.proj_dir, pr))

    def test_project_dept_vp_can_assign_approved_request(self):
        """Project dept VP can assign an APPROVED request."""
        pr = self._create_approved_pr()
        self.assertTrue(can_assign_project_request(self.proj_vp, pr))

    def test_request_dept_manager_who_is_not_project_dept_manager_cannot_assign(self):
        """Request dept manager who is not project dept manager cannot assign."""
        pr = self._create_approved_pr()
        # req_mgr is manager in req_dept but NOT in proj_dept
        self.assertFalse(can_assign_project_request(self.req_mgr, pr))

    def test_project_dept_staff_cannot_assign(self):
        """Project dept staff cannot assign."""
        pr = self._create_approved_pr()
        self.assertFalse(can_assign_project_request(self.proj_staff, pr))

    def test_cannot_assign_draft(self):
        """Cannot assign DRAFT request."""
        pr = self._create_approved_pr()
        pr.status = ProjectRequestStatus.DRAFT
        pr.save()
        self.assertFalse(can_assign_project_request(self.proj_mgr, pr))

    def test_cannot_assign_reviewing(self):
        """Cannot assign REVIEWING request."""
        pr = self._create_approved_pr()
        pr.status = ProjectRequestStatus.REVIEWING
        pr.save()
        self.assertFalse(can_assign_project_request(self.proj_mgr, pr))

    def test_cannot_assign_rejected(self):
        """Cannot assign REJECTED request."""
        pr = self._create_approved_pr()
        pr.status = ProjectRequestStatus.REJECTED
        pr.save()
        self.assertFalse(can_assign_project_request(self.proj_mgr, pr))

    def test_cannot_assign_completed(self):
        """Cannot assign COMPLETED request."""
        pr = self._create_approved_pr()
        pr.status = ProjectRequestStatus.COMPLETED
        pr.save()
        self.assertFalse(can_assign_project_request(self.proj_mgr, pr))

    def test_cannot_assign_assigned_request_by_non_project_dept_manager(self):
        """Cannot assign ASSIGNED request by non-project-dept manager."""
        pr = self._create_approved_pr()
        pr.status = ProjectRequestStatus.ASSIGNED
        pr.save()
        # req_mgr is not manager in proj_dept
        self.assertFalse(can_assign_project_request(self.req_mgr, pr))

    def test_project_dept_manager_can_assign_assigned_request(self):
        """Project dept manager can assign an ASSIGNED request (reassignment)."""
        pr = self._create_approved_pr()
        pr.status = ProjectRequestStatus.ASSIGNED
        pr.save()
        self.assertTrue(can_assign_project_request(self.proj_mgr, pr))

    def test_cannot_assign_when_project_department_inactive(self):
        """can_assign_project_request returns False when project_department.is_active=False."""
        pr = self._create_approved_pr()
        self.proj_dept.is_active = False
        self.proj_dept.save()
        self.assertFalse(can_assign_project_request(self.proj_mgr, pr))

    def test_cannot_assign_when_profile_inactive(self):
        """can_assign_project_request returns False when ProjectDepartmentProfile.is_active=False."""
        pr = self._create_approved_pr()
        profile = ProjectDepartmentProfile.objects.get(department=self.proj_dept)
        profile.is_active = False
        profile.save()
        # Refresh project_request to get fresh project_department with updated profile
        pr.refresh_from_db()
        self.assertFalse(can_assign_project_request(self.proj_mgr, pr))

    def test_cannot_assign_when_profile_missing(self):
        """can_assign_project_request returns False when ProjectDepartmentProfile is missing."""
        pr = self._create_approved_pr()
        # Delete the profile to simulate missing profile
        ProjectDepartmentProfile.objects.filter(department=self.proj_dept).delete()
        # Refresh project_request to clear cached project_department
        pr.refresh_from_db()
        self.assertFalse(can_assign_project_request(self.proj_mgr, pr))


class AssignProjectRequestServiceTest(TestCase):
    """Test assign_project_request service."""

    def setUp(self):
        # Create departments
        self.req_dept = Department.objects.create(dept_code="ACCT", dept_name="Accounting")
        self.proj_dept = Department.objects.create(dept_code="MIS", dept_name="MIS")
        self.ptype = ProjectRequestType.objects.create(code="new", name="New System")
        ProjectDepartmentProfile.objects.create(
            department=self.proj_dept,
            is_active=True,
            can_receive_project_requests=True,
        )

        # Create requester (staff in request dept)
        self.requester = User.objects.create_user(username="requester", password="pass")
        UserDepartment.objects.create(
            user=self.requester,
            department=self.req_dept,
            access_level=AccessLevel.STAFF,
            is_active=True,
        )

        # Create project dept manager (assigner)
        self.assigner = User.objects.create_user(username="assigner", password="pass")
        UserDepartment.objects.create(
            user=self.assigner,
            department=self.proj_dept,
            access_level=AccessLevel.MANAGER,
            is_active=True,
        )

        # Create assignee (staff in project dept)
        self.assignee = User.objects.create_user(username="assignee", password="pass")
        UserDepartment.objects.create(
            user=self.assignee,
            department=self.proj_dept,
            access_level=AccessLevel.STAFF,
            is_active=True,
        )

        # Create another assignee for reassignment tests
        self.assignee2 = User.objects.create_user(username="assignee2", password="pass")
        UserDepartment.objects.create(
            user=self.assignee2,
            department=self.proj_dept,
            access_level=AccessLevel.STAFF,
            is_active=True,
        )

        # Create superuser
        self.superuser = User.objects.create_superuser(username="admin", password="pass")

    def _create_approved_pr(self):
        """Create a project request in APPROVED status."""
        return ProjectRequest.objects.create(
            requester=self.requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            request_type=self.ptype,
            priority=ProjectRequestPriority.P3,
            needed_by_date=date(2026, 12, 31),
            project_name="Test Project",
            scope_summary="Summary",
            business_problem="Problem",
            in_scope="In scope",
            expected_deliverables="Deliverables",
            acceptance_criteria="Criteria",
            status=ProjectRequestStatus.APPROVED,
        )

    def test_assign_approved_request_transitions_to_assigned(self):
        """Assign APPROVED request transitions to ASSIGNED."""
        pr = self._create_approved_pr()
        result = assign_project_request(pr, self.assignee, self.assigner)

        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.ASSIGNED)
        self.assertIsNotNone(pr.assigned_at)

    def test_assignment_row_created_and_active(self):
        """Assignment row is created and is_active=True."""
        pr = self._create_approved_pr()
        assign_project_request(pr, self.assignee, self.assigner)

        assignment = ProjectRequestAssignment.objects.get(
            project_request=pr,
            assigned_to=self.assignee,
        )
        self.assertTrue(assignment.is_active)

    def test_assigned_by_is_set(self):
        """Assignment assigned_by is set to the assigner."""
        pr = self._create_approved_pr()
        assign_project_request(pr, self.assignee, self.assigner)

        assignment = ProjectRequestAssignment.objects.get(
            project_request=pr,
            assigned_to=self.assignee,
        )
        self.assertEqual(assignment.assigned_by, self.assigner)

    def test_assigned_to_must_be_active(self):
        """Assigning to inactive user raises PermissionDenied."""
        pr = self._create_approved_pr()
        self.assignee.is_active = False
        self.assignee.save()

        with self.assertRaises(PermissionDenied):
            assign_project_request(pr, self.assignee, self.assigner)

    def test_assigned_to_must_belong_to_project_department(self):
        """Assigning to user not in project department raises ValidationError."""
        pr = self._create_approved_pr()
        # Create user not in project dept
        outsider = User.objects.create_user(username="outsider", password="pass")
        UserDepartment.objects.create(
            user=outsider,
            department=self.req_dept,  # Different department
            access_level=AccessLevel.STAFF,
            is_active=True,
        )

        with self.assertRaises(ValidationError):
            assign_project_request(pr, outsider, self.assigner)

    def test_unauthorized_assigner_raises_permission_denied(self):
        """Assigner without permission raises PermissionDenied."""
        pr = self._create_approved_pr()
        # Create user who cannot assign
        outsider = User.objects.create_user(username="outsider2", password="pass")
        UserDepartment.objects.create(
            user=outsider,
            department=self.req_dept,
            access_level=AccessLevel.STAFF,
            is_active=True,
        )

        with self.assertRaises(PermissionDenied):
            assign_project_request(pr, self.assignee, outsider)

    def test_assigning_same_active_assignee_raises_validation_error(self):
        """Assigning the same user who is already actively assigned raises ValidationError."""
        pr = self._create_approved_pr()
        assign_project_request(pr, self.assignee, self.assigner)

        # Try to assign again to the same user
        with self.assertRaises(ValidationError) as cm:
            assign_project_request(pr, self.assignee, self.assigner)
        self.assertIn("already actively assigned", str(cm.exception))

    def test_reassign_deactivates_old_active_assignment(self):
        """Reassigning to a different user deactivates the old active assignment."""
        pr = self._create_approved_pr()
        assign_project_request(pr, self.assignee, self.assigner)

        # Reassign to assignee2
        assign_project_request(pr, self.assignee2, self.assigner)

        # Old assignment should be inactive
        old_assignment = ProjectRequestAssignment.objects.get(
            project_request=pr,
            assigned_to=self.assignee,
        )
        self.assertFalse(old_assignment.is_active)

    def test_reassign_creates_new_active_assignment(self):
        """Reassigning creates a new active assignment for the new user."""
        pr = self._create_approved_pr()
        assign_project_request(pr, self.assignee, self.assigner)

        # Reassign to assignee2
        assign_project_request(pr, self.assignee2, self.assigner)

        # New assignment should be active
        new_assignment = ProjectRequestAssignment.objects.get(
            project_request=pr,
            assigned_to=self.assignee2,
        )
        self.assertTrue(new_assignment.is_active)

    def test_reassignment_keeps_status_assigned(self):
        """Reassignment keeps ProjectRequest status as ASSIGNED."""
        pr = self._create_approved_pr()
        assign_project_request(pr, self.assignee, self.assigner)

        # Reassign to assignee2
        result = assign_project_request(pr, self.assignee2, self.assigner)

        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.ASSIGNED)

    def test_stale_approved_object_rejected_if_db_status_changed_to_reviewing(self):
        """Stale in-memory APPROVED object is rejected if DB status changed to REVIEWING."""
        pr = self._create_approved_pr()
        stale_pr = pr

        # Update DB row to REVIEWING
        ProjectRequest.objects.filter(pk=pr.pk).update(status=ProjectRequestStatus.REVIEWING)

        with self.assertRaises(ValidationError):
            assign_project_request(stale_pr, self.assignee, self.assigner)

    def test_stale_approved_object_rejected_if_db_status_changed_to_rejected(self):
        """Stale in-memory APPROVED object is rejected if DB status changed to REJECTED."""
        pr = self._create_approved_pr()
        stale_pr = pr

        # Update DB row to REJECTED
        ProjectRequest.objects.filter(pk=pr.pk).update(status=ProjectRequestStatus.REJECTED)

        with self.assertRaises(ValidationError):
            assign_project_request(stale_pr, self.assignee, self.assigner)

    def test_activity_log_created_for_initial_assignment(self):
        """Activity log is created for initial assignment with correct from_status/to_status."""
        pr = self._create_approved_pr()
        assign_project_request(pr, self.assignee, self.assigner)

        log = ProjectRequestActivityLog.objects.filter(
            project_request=pr,
            action_type=ProjectRequestActionType.ASSIGNED,
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.from_status, ProjectRequestStatus.APPROVED)
        self.assertEqual(log.to_status, ProjectRequestStatus.ASSIGNED)
        self.assertEqual(log.actor, self.assigner)

    def test_activity_log_created_for_reassignment(self):
        """Activity log is created for reassignment with ASSIGNED -> ASSIGNED."""
        pr = self._create_approved_pr()
        assign_project_request(pr, self.assignee, self.assigner)

        # Reassign
        assign_project_request(pr, self.assignee2, self.assigner)

        # Get the reassignment log (most recent)
        log = ProjectRequestActivityLog.objects.filter(
            project_request=pr,
            action_type=ProjectRequestActionType.ASSIGNED,
        ).order_by("-created_at").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.from_status, ProjectRequestStatus.ASSIGNED)
        self.assertEqual(log.to_status, ProjectRequestStatus.ASSIGNED)

    def test_superuser_can_assign(self):
        """Superuser can assign even without project department membership."""
        pr = self._create_approved_pr()
        # Superuser has no UserDepartment in proj_dept
        result = assign_project_request(pr, self.assignee, self.superuser)

        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.ASSIGNED)

    def test_assign_raises_permission_denied_when_project_department_inactive(self):
        """assign_project_request raises PermissionDenied when project_department.is_active=False."""
        pr = self._create_approved_pr()
        self.proj_dept.is_active = False
        self.proj_dept.save()

        with self.assertRaises(PermissionDenied):
            assign_project_request(pr, self.assignee, self.assigner)

    def test_assign_raises_permission_denied_when_profile_inactive(self):
        """assign_project_request raises PermissionDenied when ProjectDepartmentProfile.is_active=False."""
        pr = self._create_approved_pr()
        profile = ProjectDepartmentProfile.objects.get(department=self.proj_dept)
        profile.is_active = False
        profile.save()

        with self.assertRaises(PermissionDenied):
            assign_project_request(pr, self.assignee, self.assigner)

    def test_assign_raises_permission_denied_when_profile_missing(self):
        """assign_project_request raises PermissionDenied when ProjectDepartmentProfile is missing."""
        pr = self._create_approved_pr()
        # Delete the profile to simulate missing profile
        ProjectDepartmentProfile.objects.filter(department=self.proj_dept).delete()

        with self.assertRaises(PermissionDenied):
            assign_project_request(pr, self.assignee, self.assigner)


class ClaimProjectRequestServiceTest(TestCase):
    """Test claim_project_request service."""

    def setUp(self):
        # Create departments
        self.req_dept = Department.objects.create(dept_code="ACCT", dept_name="Accounting")
        self.proj_dept = Department.objects.create(dept_code="MIS", dept_name="MIS")
        self.ptype = ProjectRequestType.objects.create(code="new", name="New System")
        self.profile = ProjectDepartmentProfile.objects.create(
            department=self.proj_dept,
            is_active=True,
            can_receive_project_requests=True,
            allow_staff_claim=True,
        )

        # Create requester (staff in request dept)
        self.requester = User.objects.create_user(username="requester", password="pass")
        UserDepartment.objects.create(
            user=self.requester,
            department=self.req_dept,
            access_level=AccessLevel.STAFF,
            is_active=True,
        )

        # Create project dept staff (claimant)
        self.claimant = User.objects.create_user(username="claimant", password="pass")
        UserDepartment.objects.create(
            user=self.claimant,
            department=self.proj_dept,
            access_level=AccessLevel.STAFF,
            is_active=True,
        )

        # Create another project dept staff
        self.claimant2 = User.objects.create_user(username="claimant2", password="pass")
        UserDepartment.objects.create(
            user=self.claimant2,
            department=self.proj_dept,
            access_level=AccessLevel.STAFF,
            is_active=True,
        )

        # Create project dept manager
        self.proj_mgr = User.objects.create_user(username="proj_mgr", password="pass")
        UserDepartment.objects.create(
            user=self.proj_mgr,
            department=self.proj_dept,
            access_level=AccessLevel.MANAGER,
            is_active=True,
        )

    def _create_approved_pr(self):
        """Create a project request in APPROVED status."""
        return ProjectRequest.objects.create(
            requester=self.requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            request_type=self.ptype,
            priority=ProjectRequestPriority.P3,
            needed_by_date=date(2026, 12, 31),
            project_name="Test Project",
            scope_summary="Summary",
            business_problem="Problem",
            in_scope="In scope",
            expected_deliverables="Deliverables",
            acceptance_criteria="Criteria",
            status=ProjectRequestStatus.APPROVED,
        )

    def test_eligible_project_dept_staff_can_claim_approved_request(self):
        """Eligible project dept staff can claim APPROVED request."""
        pr = self._create_approved_pr()
        result = claim_project_request(pr, self.claimant)

        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.ASSIGNED)

    def test_claim_transitions_approved_to_assigned(self):
        """Claim transitions APPROVED -> ASSIGNED."""
        pr = self._create_approved_pr()
        claim_project_request(pr, self.claimant)

        pr.refresh_from_db()
        self.assertEqual(pr.status, ProjectRequestStatus.ASSIGNED)
        self.assertIsNotNone(pr.assigned_at)

    def test_claim_creates_active_assignment(self):
        """Claim creates active assignment with assigned_to=actor, assigned_by=actor."""
        pr = self._create_approved_pr()
        claim_project_request(pr, self.claimant)

        assignment = ProjectRequestAssignment.objects.get(
            project_request=pr,
            assigned_to=self.claimant,
        )
        self.assertTrue(assignment.is_active)
        self.assertEqual(assignment.assigned_by, self.claimant)

    def test_allow_staff_claim_false_blocks_claim(self):
        """allow_staff_claim=False blocks claim."""
        self.profile.allow_staff_claim = False
        self.profile.save()

        pr = self._create_approved_pr()
        with self.assertRaises(PermissionDenied):
            claim_project_request(pr, self.claimant)

    def test_actor_not_in_project_department_cannot_claim(self):
        """Actor not in project department cannot claim."""
        pr = self._create_approved_pr()
        # Create user not in project dept
        outsider = User.objects.create_user(username="outsider", password="pass")
        UserDepartment.objects.create(
            user=outsider,
            department=self.req_dept,
            access_level=AccessLevel.STAFF,
            is_active=True,
        )

        with self.assertRaises(PermissionDenied):
            claim_project_request(pr, outsider)

    def test_inactive_actor_cannot_claim(self):
        """Inactive actor cannot claim."""
        pr = self._create_approved_pr()
        self.claimant.is_active = False
        self.claimant.save()

        with self.assertRaises(PermissionDenied):
            claim_project_request(pr, self.claimant)

    def test_existing_active_assignment_blocks_claim(self):
        """Existing active assignment blocks claim (status is now ASSIGNED, not APPROVED)."""
        pr = self._create_approved_pr()
        # First claimant claims - transitions APPROVED -> ASSIGNED
        claim_project_request(pr, self.claimant)

        # Second claimant tries to claim but status is now ASSIGNED
        with self.assertRaises(ValidationError) as cm:
            claim_project_request(pr, self.claimant2)
        # The claim fails because status is ASSIGNED (not APPROVED)
        self.assertIn("Only APPROVED requests can be claimed", str(cm.exception))

    def test_claim_on_assigned_request_raises_validation_error(self):
        """Claim on ASSIGNED request raises ValidationError."""
        pr = self._create_approved_pr()
        pr.status = ProjectRequestStatus.ASSIGNED
        pr.save()

        with self.assertRaises(ValidationError) as cm:
            claim_project_request(pr, self.claimant)
        self.assertIn("Only APPROVED requests can be claimed", str(cm.exception))

    def test_claim_on_reviewing_raises_validation_error(self):
        """Claim on REVIEWING request raises ValidationError."""
        pr = self._create_approved_pr()
        pr.status = ProjectRequestStatus.REVIEWING
        pr.save()

        with self.assertRaises(ValidationError):
            claim_project_request(pr, self.claimant)

    def test_claim_on_rejected_raises_validation_error(self):
        """Claim on REJECTED request raises ValidationError."""
        pr = self._create_approved_pr()
        pr.status = ProjectRequestStatus.REJECTED
        pr.save()

        with self.assertRaises(ValidationError):
            claim_project_request(pr, self.claimant)

    def test_claim_on_completed_raises_validation_error(self):
        """Claim on COMPLETED request raises ValidationError."""
        pr = self._create_approved_pr()
        pr.status = ProjectRequestStatus.COMPLETED
        pr.save()

        with self.assertRaises(ValidationError):
            claim_project_request(pr, self.claimant)

    def test_stale_approved_object_rejected_if_db_status_changed(self):
        """Stale in-memory APPROVED object is rejected if DB status changed."""
        pr = self._create_approved_pr()
        stale_pr = pr

        # Update DB row to REVIEWING
        ProjectRequest.objects.filter(pk=pr.pk).update(status=ProjectRequestStatus.REVIEWING)

        with self.assertRaises(ValidationError):
            claim_project_request(stale_pr, self.claimant)

    def test_activity_log_created(self):
        """Activity log is created with correct action_type and from_status/to_status."""
        pr = self._create_approved_pr()
        claim_project_request(pr, self.claimant)

        log = ProjectRequestActivityLog.objects.filter(
            project_request=pr,
            action_type=ProjectRequestActionType.CLAIMED,
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.from_status, ProjectRequestStatus.APPROVED)
        self.assertEqual(log.to_status, ProjectRequestStatus.ASSIGNED)
        self.assertEqual(log.actor, self.claimant)

    # ---- Phase 3B hardening: profile.is_active checks ----

    def test_claim_raises_permission_denied_when_profile_inactive(self):
        """claim_project_request raises PermissionDenied when profile.is_active=False."""
        self.profile.is_active = False
        self.profile.save()

        pr = self._create_approved_pr()
        with self.assertRaises(PermissionDenied):
            claim_project_request(pr, self.claimant)

    def test_claim_raises_permission_denied_when_project_department_inactive(self):
        """claim_project_request raises PermissionDenied when project_department.is_active=False."""
        self.proj_dept.is_active = False
        self.proj_dept.save()

        pr = self._create_approved_pr()
        with self.assertRaises(PermissionDenied):
            claim_project_request(pr, self.claimant)


class ClaimProjectRequestPermissionHardeningTest(TestCase):
    """Test Phase 3B hardening for claim permissions."""

    def setUp(self):
        # Create departments
        self.req_dept = Department.objects.create(dept_code="ACCT", dept_name="Accounting")
        self.proj_dept = Department.objects.create(dept_code="MIS", dept_name="MIS")
        self.ptype = ProjectRequestType.objects.create(code="new", name="New System")
        self.profile = ProjectDepartmentProfile.objects.create(
            department=self.proj_dept,
            is_active=True,
            can_receive_project_requests=True,
            allow_staff_claim=True,
        )

        # Create requester (staff in request dept)
        self.requester = User.objects.create_user(username="requester", password="pass")
        UserDepartment.objects.create(
            user=self.requester,
            department=self.req_dept,
            access_level=AccessLevel.STAFF,
            is_active=True,
        )

        # Create project dept staff (claimant)
        self.claimant = User.objects.create_user(username="claimant", password="pass")
        UserDepartment.objects.create(
            user=self.claimant,
            department=self.proj_dept,
            access_level=AccessLevel.STAFF,
            is_active=True,
        )

    def _create_approved_pr(self):
        """Create a project request in APPROVED status."""
        return ProjectRequest.objects.create(
            requester=self.requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            request_type=self.ptype,
            priority=ProjectRequestPriority.P3,
            needed_by_date=date(2026, 12, 31),
            project_name="Test Project",
            scope_summary="Summary",
            business_problem="Problem",
            in_scope="In scope",
            expected_deliverables="Deliverables",
            acceptance_criteria="Criteria",
            status=ProjectRequestStatus.APPROVED,
        )

    def test_can_claim_returns_true_for_approved_no_assignment_allow_staff_claim(self):
        """can_claim_project_request returns True for APPROVED + no active assignment + allow_staff_claim=True."""
        pr = self._create_approved_pr()
        self.assertTrue(can_claim_project_request(self.claimant, pr))

    def test_can_claim_returns_false_for_assigned_even_no_active_assignment(self):
        """can_claim_project_request returns False for ASSIGNED even when no active assignment exists."""
        pr = self._create_approved_pr()
        pr.status = ProjectRequestStatus.ASSIGNED
        pr.save()
        self.assertFalse(can_claim_project_request(self.claimant, pr))

    def test_can_view_does_not_expose_assigned_unassigned_to_staff(self):
        """can_view_project_request does not expose ASSIGNED unassigned request to project dept staff."""
        pr = self._create_approved_pr()
        pr.status = ProjectRequestStatus.ASSIGNED
        pr.save()
        # Staff should not see ASSIGNED requests through claimable visibility
        self.assertFalse(can_view_project_request(self.claimant, pr))

    def test_claim_on_assigned_raises_validation_error(self):
        """claim_project_request on ASSIGNED raises ValidationError."""
        pr = self._create_approved_pr()
        pr.status = ProjectRequestStatus.ASSIGNED
        pr.save()

        with self.assertRaises(ValidationError) as cm:
            claim_project_request(pr, self.claimant)
        self.assertIn("Only APPROVED requests can be claimed", str(cm.exception))

    def test_can_claim_returns_false_when_profile_inactive(self):
        """can_claim_project_request returns False when ProjectDepartmentProfile.is_active=False."""
        self.profile.is_active = False
        self.profile.save()

        pr = self._create_approved_pr()
        self.assertFalse(can_claim_project_request(self.claimant, pr))

    def test_can_view_returns_false_when_profile_inactive_for_staff(self):
        """can_view_project_request returns False for project dept staff when profile.is_active=False."""
        self.profile.is_active = False
        self.profile.save()

        pr = self._create_approved_pr()
        # Staff should not see through claimable visibility when profile is inactive
        self.assertFalse(can_view_project_request(self.claimant, pr))

    def test_can_claim_returns_false_when_project_department_inactive(self):
        """can_claim_project_request returns False when project_department.is_active=False."""
        self.proj_dept.is_active = False
        self.proj_dept.save()

        pr = self._create_approved_pr()
        self.assertFalse(can_claim_project_request(self.claimant, pr))


class SelectorRegressionTest(TestCase):
    """Test get_assigned_to_me selector for regression."""

    def setUp(self):
        # Create departments
        self.req_dept = Department.objects.create(dept_code="ACCT", dept_name="Accounting")
        self.proj_dept = Department.objects.create(dept_code="MIS", dept_name="MIS")
        self.ptype = ProjectRequestType.objects.create(code="new", name="New System")
        ProjectDepartmentProfile.objects.create(
            department=self.proj_dept,
            is_active=True,
            can_receive_project_requests=True,
        )

        # Create requester
        self.requester = User.objects.create_user(username="requester", password="pass")
        UserDepartment.objects.create(
            user=self.requester,
            department=self.req_dept,
            access_level=AccessLevel.STAFF,
            is_active=True,
        )

        # Create assigner (manager)
        self.assigner = User.objects.create_user(username="assigner", password="pass")
        UserDepartment.objects.create(
            user=self.assigner,
            department=self.proj_dept,
            access_level=AccessLevel.MANAGER,
            is_active=True,
        )

        # Create assignee
        self.assignee = User.objects.create_user(username="assignee", password="pass")
        UserDepartment.objects.create(
            user=self.assignee,
            department=self.proj_dept,
            access_level=AccessLevel.STAFF,
            is_active=True,
        )

        # Create another assignee
        self.assignee2 = User.objects.create_user(username="assignee2", password="pass")
        UserDepartment.objects.create(
            user=self.assignee2,
            department=self.proj_dept,
            access_level=AccessLevel.STAFF,
            is_active=True,
        )

    def _create_approved_pr(self):
        """Create a project request in APPROVED status."""
        return ProjectRequest.objects.create(
            requester=self.requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            request_type=self.ptype,
            priority=ProjectRequestPriority.P3,
            needed_by_date=date(2026, 12, 31),
            project_name="Test Project",
            scope_summary="Summary",
            business_problem="Problem",
            in_scope="In scope",
            expected_deliverables="Deliverables",
            acceptance_criteria="Criteria",
            status=ProjectRequestStatus.APPROVED,
        )

    def test_get_assigned_to_me_returns_active_assignment(self):
        """get_assigned_to_me returns requests where user has active assignment."""
        pr = self._create_approved_pr()
        assign_project_request(pr, self.assignee, self.assigner)

        assigned_requests = get_assigned_to_me(self.assignee)
        self.assertEqual(assigned_requests.count(), 1)
        self.assertEqual(assigned_requests.first(), pr)

    def test_get_assigned_to_me_excludes_inactive_assignment(self):
        """get_assigned_to_me excludes inactive assignments."""
        pr = self._create_approved_pr()
        assign_project_request(pr, self.assignee, self.assigner)

        # Deactivate the assignment
        ProjectRequestAssignment.objects.filter(
            project_request=pr,
            assigned_to=self.assignee,
        ).update(is_active=False)

        assigned_requests = get_assigned_to_me(self.assignee)
        self.assertEqual(assigned_requests.count(), 0)

    def test_after_reassignment_old_assignee_no_longer_sees_request(self):
        """After reassignment, old assignee no longer sees request in get_assigned_to_me."""
        pr = self._create_approved_pr()
        assign_project_request(pr, self.assignee, self.assigner)

        # Reassign to assignee2
        assign_project_request(pr, self.assignee2, self.assigner)

        # Old assignee should not see the request
        old_assigned_requests = get_assigned_to_me(self.assignee)
        self.assertEqual(old_assigned_requests.count(), 0)

    def test_after_reassignment_new_assignee_sees_request(self):
        """After reassignment, new assignee sees request in get_assigned_to_me."""
        pr = self._create_approved_pr()
        assign_project_request(pr, self.assignee, self.assigner)

        # Reassign to assignee2
        assign_project_request(pr, self.assignee2, self.assigner)

        # New assignee should see the request
        new_assigned_requests = get_assigned_to_me(self.assignee2)
        self.assertEqual(new_assigned_requests.count(), 1)
        self.assertEqual(new_assigned_requests.first(), pr)


# ============================================================================
# Phase 3C — Execution Workflow Tests
# ============================================================================


class StartProjectRequestPermissionTest(TestCase):
    """Test can_start_project_request permission helper."""

    def setUp(self):
        from accounts.models import User, Department, UserDepartment, AccessLevel
        from project_requests.models import (
            ProjectDepartmentProfile,
            ProjectRequest,
            ProjectRequestAssignment,
            ProjectRequestStatus,
            ProjectRequestType,
        )

        self.req_dept = Department.objects.create(dept_code="REQ", dept_name="Requester Dept", is_active=True)
        self.proj_dept = Department.objects.create(dept_code="PRJ", dept_name="Project Dept", is_active=True)
        self.profile = ProjectDepartmentProfile.objects.create(
            department=self.proj_dept, is_active=True
        )
        self.ptype = ProjectRequestType.objects.create(name="Test Type", code="TT", is_active=True)

        self.requester = User.objects.create_user(username="requester", password="pass", is_active=True)
        self.assignee = User.objects.create_user(username="assignee", password="pass", is_active=True)
        self.assignee2 = User.objects.create_user(username="assignee2", password="pass", is_active=True)
        self.unrelated = User.objects.create_user(username="unrelated", password="pass", is_active=True)
        self.proj_manager = User.objects.create_user(username="proj_manager", password="pass", is_active=True)
        self.req_manager = User.objects.create_user(username="req_manager", password="pass", is_active=True)
        self.superuser = User.objects.create_user(username="super", password="pass", is_superuser=True, is_active=True)

        UserDepartment.objects.create(user=self.requester, department=self.req_dept, access_level=AccessLevel.STAFF, is_active=True)
        UserDepartment.objects.create(user=self.assignee, department=self.proj_dept, access_level=AccessLevel.STAFF, is_active=True)
        UserDepartment.objects.create(user=self.assignee2, department=self.proj_dept, access_level=AccessLevel.STAFF, is_active=True)
        UserDepartment.objects.create(user=self.proj_manager, department=self.proj_dept, access_level=AccessLevel.MANAGER, is_active=True)
        UserDepartment.objects.create(user=self.req_manager, department=self.req_dept, access_level=AccessLevel.MANAGER, is_active=True)

        self.pr = ProjectRequest.objects.create(
            requester=self.requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            request_type=self.ptype,
            project_name="Start Test",
            status=ProjectRequestStatus.ASSIGNED,
        )
        ProjectRequestAssignment.objects.create(
            project_request=self.pr, assigned_to=self.assignee, assigned_by=self.proj_manager, is_active=True
        )

    def test_assignee_can_start_assigned_request(self):
        from project_requests.permissions import can_start_project_request
        self.assertTrue(can_start_project_request(self.assignee, self.pr))

    def test_project_dept_manager_can_start_even_if_not_active_assignee(self):
        """Project dept manager/director/VP can start even if not the active assignee."""
        from project_requests.permissions import can_start_project_request
        self.assertTrue(can_start_project_request(self.proj_manager, self.pr))

    def test_superuser_can_start_when_status_allows(self):
        """Superuser can start when status allows and active assignment exists."""
        from project_requests.permissions import can_start_project_request
        self.assertTrue(can_start_project_request(self.superuser, self.pr))

    def test_project_dept_staff_cannot_start_if_not_active_assignee(self):
        """Project dept staff who is not active assignee cannot start."""
        from project_requests.permissions import can_start_project_request
        self.assertFalse(can_start_project_request(self.assignee2, self.pr))

    def test_req_dept_manager_cannot_start_if_not_project_dept_manager(self):
        """Request dept manager who is not project dept manager cannot start unless active assignee."""
        from project_requests.permissions import can_start_project_request
        self.assertFalse(can_start_project_request(self.req_manager, self.pr))

    def test_unrelated_user_cannot_start(self):
        from project_requests.permissions import can_start_project_request
        self.assertFalse(can_start_project_request(self.unrelated, self.pr))

    def test_inactive_user_cannot_start(self):
        from project_requests.permissions import can_start_project_request
        self.assignee.is_active = False
        self.assignee.save()
        self.assertFalse(can_start_project_request(self.assignee, self.pr))

    def test_non_assigned_status_cannot_start(self):
        from project_requests.permissions import can_start_project_request
        self.pr.status = ProjectRequestStatus.IN_PROGRESS
        self.assertFalse(can_start_project_request(self.assignee, self.pr))

    def test_inactive_project_dept_blocks_start(self):
        from project_requests.permissions import can_start_project_request
        self.proj_dept.is_active = False
        self.proj_dept.save()
        self.assertFalse(can_start_project_request(self.assignee, self.pr))

    def test_inactive_profile_blocks_start(self):
        from project_requests.permissions import can_start_project_request
        self.profile.is_active = False
        self.profile.save()
        self.assertFalse(can_start_project_request(self.assignee, self.pr))

    def test_no_active_assignment_blocks_start_for_all(self):
        """No active assignment blocks all execution actions, even for manager/superuser."""
        from project_requests.permissions import can_start_project_request
        # Create a request with no active assignments
        pr = ProjectRequest.objects.create(
            requester=self.requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            request_type=self.ptype,
            project_name="No Assignment",
            status=ProjectRequestStatus.ASSIGNED,
        )
        self.assertFalse(can_start_project_request(self.assignee, pr))
        self.assertFalse(can_start_project_request(self.proj_manager, pr))
        self.assertFalse(can_start_project_request(self.superuser, pr))


class HoldResumeCompletePermissionTest(TestCase):
    """Test can_hold, can_resume, can_complete permission helpers."""

    def setUp(self):
        from accounts.models import User, Department, UserDepartment, AccessLevel
        from project_requests.models import (
            ProjectDepartmentProfile,
            ProjectRequest,
            ProjectRequestAssignment,
            ProjectRequestStatus,
            ProjectRequestType,
        )

        self.req_dept = Department.objects.create(dept_code="REQ", dept_name="Requester Dept", is_active=True)
        self.proj_dept = Department.objects.create(dept_code="PRJ", dept_name="Project Dept", is_active=True)
        self.profile = ProjectDepartmentProfile.objects.create(
            department=self.proj_dept, is_active=True
        )
        self.ptype = ProjectRequestType.objects.create(name="Test Type", code="TT", is_active=True)

        self.assignee = User.objects.create_user(username="assignee", password="pass", is_active=True)
        self.other = User.objects.create_user(username="other", password="pass", is_active=True)
        self.proj_manager = User.objects.create_user(username="proj_manager", password="pass", is_active=True)
        self.superuser = User.objects.create_user(username="super", password="pass", is_superuser=True, is_active=True)

        UserDepartment.objects.create(user=self.assignee, department=self.proj_dept, access_level=AccessLevel.STAFF, is_active=True)
        UserDepartment.objects.create(user=self.other, department=self.proj_dept, access_level=AccessLevel.STAFF, is_active=True)
        UserDepartment.objects.create(user=self.proj_manager, department=self.proj_dept, access_level=AccessLevel.MANAGER, is_active=True)

    def _create_pr(self, status):
        from project_requests.models import ProjectRequest, ProjectRequestAssignment
        pr = ProjectRequest.objects.create(
            requester=self.assignee,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            request_type=self.ptype,
            project_name="Test",
            status=status,
        )
        ProjectRequestAssignment.objects.create(
            project_request=pr, assigned_to=self.assignee, assigned_by=self.assignee, is_active=True
        )
        return pr

    def test_assignee_can_hold_in_progress(self):
        from project_requests.permissions import can_hold_project_request
        pr = self._create_pr(ProjectRequestStatus.IN_PROGRESS)
        self.assertTrue(can_hold_project_request(self.assignee, pr))

    def test_project_dept_manager_can_hold_in_progress(self):
        """Project dept manager can hold even if not active assignee."""
        from project_requests.permissions import can_hold_project_request
        pr = self._create_pr(ProjectRequestStatus.IN_PROGRESS)
        self.assertTrue(can_hold_project_request(self.proj_manager, pr))

    def test_superuser_can_hold_in_progress(self):
        """Superuser can hold when status allows."""
        from project_requests.permissions import can_hold_project_request
        pr = self._create_pr(ProjectRequestStatus.IN_PROGRESS)
        self.assertTrue(can_hold_project_request(self.superuser, pr))

    def test_project_dept_staff_cannot_hold_if_not_active_assignee(self):
        """Project dept staff who is not active assignee cannot hold."""
        from project_requests.permissions import can_hold_project_request
        pr = self._create_pr(ProjectRequestStatus.IN_PROGRESS)
        self.assertFalse(can_hold_project_request(self.other, pr))

    def test_assignee_can_resume_on_hold(self):
        from project_requests.permissions import can_resume_project_request
        pr = self._create_pr(ProjectRequestStatus.ON_HOLD)
        self.assertTrue(can_resume_project_request(self.assignee, pr))

    def test_project_dept_manager_can_resume_on_hold(self):
        """Project dept manager can resume even if not active assignee."""
        from project_requests.permissions import can_resume_project_request
        pr = self._create_pr(ProjectRequestStatus.ON_HOLD)
        self.assertTrue(can_resume_project_request(self.proj_manager, pr))

    def test_superuser_can_resume_on_hold(self):
        """Superuser can resume when status allows."""
        from project_requests.permissions import can_resume_project_request
        pr = self._create_pr(ProjectRequestStatus.ON_HOLD)
        self.assertTrue(can_resume_project_request(self.superuser, pr))

    def test_project_dept_staff_cannot_resume_if_not_active_assignee(self):
        """Project dept staff who is not active assignee cannot resume."""
        from project_requests.permissions import can_resume_project_request
        pr = self._create_pr(ProjectRequestStatus.ON_HOLD)
        self.assertFalse(can_resume_project_request(self.other, pr))

    def test_assignee_can_complete_in_progress(self):
        from project_requests.permissions import can_complete_project_request
        pr = self._create_pr(ProjectRequestStatus.IN_PROGRESS)
        self.assertTrue(can_complete_project_request(self.assignee, pr))

    def test_project_dept_manager_can_complete_in_progress(self):
        """Project dept manager can complete even if not active assignee."""
        from project_requests.permissions import can_complete_project_request
        pr = self._create_pr(ProjectRequestStatus.IN_PROGRESS)
        self.assertTrue(can_complete_project_request(self.proj_manager, pr))

    def test_superuser_can_complete_in_progress(self):
        """Superuser can complete when status allows."""
        from project_requests.permissions import can_complete_project_request
        pr = self._create_pr(ProjectRequestStatus.IN_PROGRESS)
        self.assertTrue(can_complete_project_request(self.superuser, pr))

    def test_project_dept_staff_cannot_complete_if_not_active_assignee(self):
        """Project dept staff who is not active assignee cannot complete."""
        from project_requests.permissions import can_complete_project_request
        pr = self._create_pr(ProjectRequestStatus.IN_PROGRESS)
        self.assertFalse(can_complete_project_request(self.other, pr))

    def test_cannot_hold_non_in_progress(self):
        from project_requests.permissions import can_hold_project_request
        pr = self._create_pr(ProjectRequestStatus.ASSIGNED)
        self.assertFalse(can_hold_project_request(self.assignee, pr))

    def test_cannot_resume_non_on_hold(self):
        from project_requests.permissions import can_resume_project_request
        pr = self._create_pr(ProjectRequestStatus.IN_PROGRESS)
        self.assertFalse(can_resume_project_request(self.assignee, pr))

    def test_cannot_complete_non_in_progress(self):
        from project_requests.permissions import can_complete_project_request
        pr = self._create_pr(ProjectRequestStatus.ON_HOLD)
        self.assertFalse(can_complete_project_request(self.assignee, pr))

    def test_on_hold_cannot_complete_directly(self):
        """ON_HOLD cannot complete directly - must resume first."""
        from project_requests.permissions import can_complete_project_request
        pr = self._create_pr(ProjectRequestStatus.ON_HOLD)
        self.assertFalse(can_complete_project_request(self.assignee, pr))

    def test_no_active_assignment_blocks_hold_for_all(self):
        """No active assignment blocks hold, even for manager/superuser."""
        from project_requests.permissions import can_hold_project_request
        pr = ProjectRequest.objects.create(
            requester=self.assignee,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            request_type=self.ptype,
            project_name="No Assignment",
            status=ProjectRequestStatus.IN_PROGRESS,
        )
        self.assertFalse(can_hold_project_request(self.assignee, pr))
        self.assertFalse(can_hold_project_request(self.proj_manager, pr))
        self.assertFalse(can_hold_project_request(self.superuser, pr))


class StartProjectRequestServiceTest(TestCase):
    """Test start_project_request service."""

    def setUp(self):
        from accounts.models import User, Department, UserDepartment, AccessLevel
        from project_requests.models import (
            ProjectDepartmentProfile,
            ProjectRequest,
            ProjectRequestAssignment,
            ProjectRequestStatus,
            ProjectRequestType,
        )

        self.req_dept = Department.objects.create(dept_code="REQ", dept_name="Requester Dept", is_active=True)
        self.proj_dept = Department.objects.create(dept_code="PRJ", dept_name="Project Dept", is_active=True)
        self.profile = ProjectDepartmentProfile.objects.create(
            department=self.proj_dept, is_active=True
        )
        self.ptype = ProjectRequestType.objects.create(name="Test Type", code="TT", is_active=True)

        self.requester = User.objects.create_user(username="requester", password="pass", is_active=True)
        self.assignee = User.objects.create_user(username="assignee", password="pass", is_active=True)

        UserDepartment.objects.create(user=self.requester, department=self.req_dept, access_level=AccessLevel.STAFF, is_active=True)
        UserDepartment.objects.create(user=self.assignee, department=self.proj_dept, access_level=AccessLevel.STAFF, is_active=True)

        self.pr = ProjectRequest.objects.create(
            requester=self.requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            request_type=self.ptype,
            project_name="Start Test",
            status=ProjectRequestStatus.ASSIGNED,
        )
        ProjectRequestAssignment.objects.create(
            project_request=self.pr, assigned_to=self.assignee, assigned_by=self.assignee, is_active=True
        )

    def test_start_transitions_assigned_to_in_progress(self):
        from project_requests.services import start_project_request
        result = start_project_request(self.pr, self.assignee)
        self.assertEqual(result.status, ProjectRequestStatus.IN_PROGRESS)
        self.assertIsNotNone(result.started_at)

    def test_start_creates_activity_log(self):
        from project_requests.services import start_project_request
        from project_requests.models import ProjectRequestActivityLog, ProjectRequestActionType
        start_project_request(self.pr, self.assignee)
        log = ProjectRequestActivityLog.objects.filter(
            project_request=self.pr, action_type=ProjectRequestActionType.STARTED
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.from_status, ProjectRequestStatus.ASSIGNED)
        self.assertEqual(log.to_status, ProjectRequestStatus.IN_PROGRESS)
        self.assertEqual(log.description, "Request started")
        self.assertEqual(log.comment, "")

    def test_start_with_comment_stores_in_log_comment(self):
        from project_requests.services import start_project_request
        from project_requests.models import ProjectRequestActivityLog, ProjectRequestActionType
        start_project_request(self.pr, self.assignee, comment="Starting now")
        log = ProjectRequestActivityLog.objects.filter(
            project_request=self.pr, action_type=ProjectRequestActionType.STARTED
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.description, "Request started")
        self.assertEqual(log.comment, "Starting now")

    def test_start_non_assigned_raises_error(self):
        from project_requests.services import start_project_request
        self.pr.status = ProjectRequestStatus.IN_PROGRESS
        self.pr.save()
        with self.assertRaises((ValidationError, PermissionDenied)):
            start_project_request(self.pr, self.assignee)

    def test_start_unauthorized_raises_permission_denied(self):
        from project_requests.services import start_project_request
        other = User.objects.create_user(username="other", password="pass", is_active=True)
        with self.assertRaises(PermissionDenied):
            start_project_request(self.pr, other)


class HoldProjectRequestServiceTest(TestCase):
    """Test hold_project_request service."""

    def setUp(self):
        from accounts.models import User, Department, UserDepartment, AccessLevel
        from project_requests.models import (
            ProjectDepartmentProfile,
            ProjectRequest,
            ProjectRequestAssignment,
            ProjectRequestStatus,
            ProjectRequestType,
        )

        self.req_dept = Department.objects.create(dept_code="REQ", dept_name="Requester Dept", is_active=True)
        self.proj_dept = Department.objects.create(dept_code="PRJ", dept_name="Project Dept", is_active=True)
        self.profile = ProjectDepartmentProfile.objects.create(
            department=self.proj_dept, is_active=True
        )
        self.ptype = ProjectRequestType.objects.create(name="Test Type", code="TT", is_active=True)

        self.requester = User.objects.create_user(username="requester", password="pass", is_active=True)
        self.assignee = User.objects.create_user(username="assignee", password="pass", is_active=True)

        UserDepartment.objects.create(user=self.requester, department=self.req_dept, access_level=AccessLevel.STAFF, is_active=True)
        UserDepartment.objects.create(user=self.assignee, department=self.proj_dept, access_level=AccessLevel.STAFF, is_active=True)

        self.pr = ProjectRequest.objects.create(
            requester=self.requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            request_type=self.ptype,
            project_name="Hold Test",
            status=ProjectRequestStatus.IN_PROGRESS,
        )
        ProjectRequestAssignment.objects.create(
            project_request=self.pr, assigned_to=self.assignee, assigned_by=self.assignee, is_active=True
        )

    def test_hold_transitions_in_progress_to_on_hold(self):
        from project_requests.services import hold_project_request
        result = hold_project_request(self.pr, self.assignee, comment="Need more info")
        self.assertEqual(result.status, ProjectRequestStatus.ON_HOLD)

    def test_hold_comment_required(self):
        from project_requests.services import hold_project_request
        with self.assertRaises(ValidationError):
            hold_project_request(self.pr, self.assignee, comment="")

    def test_hold_whitespace_comment_raises_validation_error(self):
        from project_requests.services import hold_project_request
        with self.assertRaises(ValidationError):
            hold_project_request(self.pr, self.assignee, comment="   ")

    def test_hold_creates_activity_log(self):
        from project_requests.services import hold_project_request
        from project_requests.models import ProjectRequestActivityLog, ProjectRequestActionType
        hold_project_request(self.pr, self.assignee, comment="Waiting on client")
        log = ProjectRequestActivityLog.objects.filter(
            project_request=self.pr, action_type=ProjectRequestActionType.PUT_ON_HOLD
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.from_status, ProjectRequestStatus.IN_PROGRESS)
        self.assertEqual(log.to_status, ProjectRequestStatus.ON_HOLD)
        self.assertEqual(log.description, "Request put on hold")
        self.assertEqual(log.comment, "Waiting on client")

    def test_hold_non_in_progress_raises_error(self):
        from project_requests.services import hold_project_request
        self.pr.status = ProjectRequestStatus.ASSIGNED
        self.pr.save()
        with self.assertRaises((ValidationError, PermissionDenied)):
            hold_project_request(self.pr, self.assignee, comment="test")


class ResumeProjectRequestServiceTest(TestCase):
    """Test resume_project_request service."""

    def setUp(self):
        from accounts.models import User, Department, UserDepartment, AccessLevel
        from project_requests.models import (
            ProjectDepartmentProfile,
            ProjectRequest,
            ProjectRequestAssignment,
            ProjectRequestStatus,
            ProjectRequestType,
        )

        self.req_dept = Department.objects.create(dept_code="REQ", dept_name="Requester Dept", is_active=True)
        self.proj_dept = Department.objects.create(dept_code="PRJ", dept_name="Project Dept", is_active=True)
        self.profile = ProjectDepartmentProfile.objects.create(
            department=self.proj_dept, is_active=True
        )
        self.ptype = ProjectRequestType.objects.create(name="Test Type", code="TT", is_active=True)

        self.requester = User.objects.create_user(username="requester", password="pass", is_active=True)
        self.assignee = User.objects.create_user(username="assignee", password="pass", is_active=True)

        UserDepartment.objects.create(user=self.requester, department=self.req_dept, access_level=AccessLevel.STAFF, is_active=True)
        UserDepartment.objects.create(user=self.assignee, department=self.proj_dept, access_level=AccessLevel.STAFF, is_active=True)

        self.pr = ProjectRequest.objects.create(
            requester=self.requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            request_type=self.ptype,
            project_name="Resume Test",
            status=ProjectRequestStatus.ON_HOLD,
        )
        ProjectRequestAssignment.objects.create(
            project_request=self.pr, assigned_to=self.assignee, assigned_by=self.assignee, is_active=True
        )

    def test_resume_transitions_on_hold_to_in_progress(self):
        from project_requests.services import resume_project_request
        result = resume_project_request(self.pr, self.assignee)
        self.assertEqual(result.status, ProjectRequestStatus.IN_PROGRESS)

    def test_resume_creates_activity_log(self):
        from project_requests.services import resume_project_request
        from project_requests.models import ProjectRequestActivityLog, ProjectRequestActionType
        resume_project_request(self.pr, self.assignee)
        log = ProjectRequestActivityLog.objects.filter(
            project_request=self.pr, action_type=ProjectRequestActionType.RESUMED
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.from_status, ProjectRequestStatus.ON_HOLD)
        self.assertEqual(log.to_status, ProjectRequestStatus.IN_PROGRESS)
        self.assertEqual(log.description, "Request resumed")
        self.assertEqual(log.comment, "")

    def test_resume_with_comment_stores_in_log_comment(self):
        from project_requests.services import resume_project_request
        from project_requests.models import ProjectRequestActivityLog, ProjectRequestActionType
        resume_project_request(self.pr, self.assignee, comment="Resuming work")
        log = ProjectRequestActivityLog.objects.filter(
            project_request=self.pr, action_type=ProjectRequestActionType.RESUMED
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.description, "Request resumed")
        self.assertEqual(log.comment, "Resuming work")

    def test_resume_non_on_hold_raises_error(self):
        from project_requests.services import resume_project_request
        self.pr.status = ProjectRequestStatus.IN_PROGRESS
        self.pr.save()
        with self.assertRaises((ValidationError, PermissionDenied)):
            resume_project_request(self.pr, self.assignee)


class CompleteProjectRequestServiceTest(TestCase):
    """Test complete_project_request service."""

    def setUp(self):
        from accounts.models import User, Department, UserDepartment, AccessLevel
        from project_requests.models import (
            ProjectDepartmentProfile,
            ProjectRequest,
            ProjectRequestAssignment,
            ProjectRequestStatus,
            ProjectRequestType,
        )

        self.req_dept = Department.objects.create(dept_code="REQ", dept_name="Requester Dept", is_active=True)
        self.proj_dept = Department.objects.create(dept_code="PRJ", dept_name="Project Dept", is_active=True)
        self.profile = ProjectDepartmentProfile.objects.create(
            department=self.proj_dept, is_active=True
        )
        self.ptype = ProjectRequestType.objects.create(name="Test Type", code="TT", is_active=True)

        self.requester = User.objects.create_user(username="requester", password="pass", is_active=True)
        self.assignee = User.objects.create_user(username="assignee", password="pass", is_active=True)

        UserDepartment.objects.create(user=self.requester, department=self.req_dept, access_level=AccessLevel.STAFF, is_active=True)
        UserDepartment.objects.create(user=self.assignee, department=self.proj_dept, access_level=AccessLevel.STAFF, is_active=True)

        self.pr = ProjectRequest.objects.create(
            requester=self.requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            request_type=self.ptype,
            project_name="Complete Test",
            status=ProjectRequestStatus.IN_PROGRESS,
        )
        ProjectRequestAssignment.objects.create(
            project_request=self.pr, assigned_to=self.assignee, assigned_by=self.assignee, is_active=True
        )

    def test_complete_transitions_in_progress_to_completed(self):
        from project_requests.services import complete_project_request
        result = complete_project_request(self.pr, self.assignee)
        self.assertEqual(result.status, ProjectRequestStatus.COMPLETED)
        self.assertIsNotNone(result.completed_at)

    def test_complete_creates_activity_log(self):
        from project_requests.services import complete_project_request
        from project_requests.models import ProjectRequestActivityLog, ProjectRequestActionType
        complete_project_request(self.pr, self.assignee)
        log = ProjectRequestActivityLog.objects.filter(
            project_request=self.pr, action_type=ProjectRequestActionType.COMPLETED
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.from_status, ProjectRequestStatus.IN_PROGRESS)
        self.assertEqual(log.to_status, ProjectRequestStatus.COMPLETED)
        self.assertEqual(log.description, "Request completed")
        self.assertEqual(log.comment, "")

    def test_complete_with_comment_stores_in_log_comment(self):
        from project_requests.services import complete_project_request
        from project_requests.models import ProjectRequestActivityLog, ProjectRequestActionType
        complete_project_request(self.pr, self.assignee, comment="All done!")
        log = ProjectRequestActivityLog.objects.filter(
            project_request=self.pr, action_type=ProjectRequestActionType.COMPLETED
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.description, "Request completed")
        self.assertEqual(log.comment, "All done!")

    def test_complete_non_in_progress_raises_error(self):
        from project_requests.services import complete_project_request
        self.pr.status = ProjectRequestStatus.ON_HOLD
        self.pr.save()
        with self.assertRaises((ValidationError, PermissionDenied)):
            complete_project_request(self.pr, self.assignee)

    def test_complete_unauthorized_raises_permission_denied(self):
        from project_requests.services import complete_project_request
        other = User.objects.create_user(username="other", password="pass", is_active=True)
        with self.assertRaises(PermissionDenied):
            complete_project_request(self.pr, other)


class ExecutionActionContextTest(TestCase):
    """Test get_project_request_action_context includes Phase 3C keys."""

    def setUp(self):
        from accounts.models import User, Department, UserDepartment, AccessLevel
        from project_requests.models import (
            ProjectDepartmentProfile,
            ProjectRequest,
            ProjectRequestAssignment,
            ProjectRequestStatus,
            ProjectRequestType,
        )

        self.req_dept = Department.objects.create(dept_code="REQ", dept_name="Requester Dept", is_active=True)
        self.proj_dept = Department.objects.create(dept_code="PRJ", dept_name="Project Dept", is_active=True)
        self.profile = ProjectDepartmentProfile.objects.create(
            department=self.proj_dept, is_active=True
        )
        self.ptype = ProjectRequestType.objects.create(name="Test Type", code="TT", is_active=True)

        self.requester = User.objects.create_user(username="requester", password="pass", is_active=True)
        self.assignee = User.objects.create_user(username="assignee", password="pass", is_active=True)

        UserDepartment.objects.create(user=self.requester, department=self.req_dept, access_level=AccessLevel.STAFF, is_active=True)
        UserDepartment.objects.create(user=self.assignee, department=self.proj_dept, access_level=AccessLevel.STAFF, is_active=True)

    def _create_pr(self, status):
        from project_requests.models import ProjectRequest, ProjectRequestAssignment
        pr = ProjectRequest.objects.create(
            requester=self.requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            request_type=self.ptype,
            project_name="Context Test",
            status=status,
        )
        ProjectRequestAssignment.objects.create(
            project_request=pr, assigned_to=self.assignee, assigned_by=self.assignee, is_active=True
        )
        return pr

    def test_context_includes_execution_keys(self):
        from project_requests.permissions import get_project_request_action_context
        pr = self._create_pr(ProjectRequestStatus.ASSIGNED)
        ctx = get_project_request_action_context(self.assignee, pr)
        self.assertIn("can_start", ctx)
        self.assertIn("can_hold", ctx)
        self.assertIn("can_resume", ctx)
        self.assertIn("can_complete", ctx)

    def test_context_can_start_true_for_assigned(self):
        from project_requests.permissions import get_project_request_action_context
        pr = self._create_pr(ProjectRequestStatus.ASSIGNED)
        ctx = get_project_request_action_context(self.assignee, pr)
        self.assertTrue(ctx["can_start"])
        self.assertFalse(ctx["can_hold"])
        self.assertFalse(ctx["can_resume"])
        self.assertFalse(ctx["can_complete"])

    def test_context_can_hold_true_for_in_progress(self):
        from project_requests.permissions import get_project_request_action_context
        pr = self._create_pr(ProjectRequestStatus.IN_PROGRESS)
        ctx = get_project_request_action_context(self.assignee, pr)
        self.assertFalse(ctx["can_start"])
        self.assertTrue(ctx["can_hold"])
        self.assertFalse(ctx["can_resume"])
        self.assertTrue(ctx["can_complete"])

    def test_context_can_resume_true_for_on_hold(self):
        from project_requests.permissions import get_project_request_action_context
        pr = self._create_pr(ProjectRequestStatus.ON_HOLD)
        ctx = get_project_request_action_context(self.assignee, pr)
        self.assertFalse(ctx["can_start"])
        self.assertFalse(ctx["can_hold"])
        self.assertTrue(ctx["can_resume"])
        self.assertFalse(ctx["can_complete"])


class Phase3CRegressionTest(TestCase):
    """Regression tests to ensure existing functionality still works after Phase 3C."""

    def setUp(self):
        from accounts.models import User, Department, UserDepartment, AccessLevel
        from project_requests.models import (
            ProjectDepartmentProfile,
            ProjectRequest,
            ProjectRequestAssignment,
            ProjectRequestStatus,
            ProjectRequestType,
        )

        self.req_dept = Department.objects.create(dept_code="REQ", dept_name="Requester Dept", is_active=True)
        self.proj_dept = Department.objects.create(dept_code="PRJ", dept_name="Project Dept", is_active=True)
        self.profile = ProjectDepartmentProfile.objects.create(
            department=self.proj_dept, is_active=True, allow_staff_claim=True
        )
        self.ptype = ProjectRequestType.objects.create(name="Test Type", code="TT", is_active=True)

        self.requester = User.objects.create_user(username="requester", password="pass", is_active=True)
        self.manager = User.objects.create_user(username="manager", password="pass", is_active=True)
        self.assignee = User.objects.create_user(username="assignee", password="pass", is_active=True)

        UserDepartment.objects.create(user=self.requester, department=self.req_dept, access_level=AccessLevel.STAFF, is_active=True)
        UserDepartment.objects.create(user=self.manager, department=self.proj_dept, access_level=AccessLevel.MANAGER, is_active=True)
        UserDepartment.objects.create(user=self.assignee, department=self.proj_dept, access_level=AccessLevel.STAFF, is_active=True)

    def _create_approved_pr(self):
        from project_requests.models import ProjectRequest
        return ProjectRequest.objects.create(
            requester=self.requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            request_type=self.ptype,
            project_name="Regression Test",
            status=ProjectRequestStatus.APPROVED,
        )

    def test_assign_still_works(self):
        from project_requests.services import assign_project_request
        pr = self._create_approved_pr()
        result = assign_project_request(pr, self.assignee, self.manager)
        self.assertEqual(result.status, ProjectRequestStatus.ASSIGNED)

    def test_full_execution_workflow(self):
        """Test the full workflow: assign -> start -> hold -> resume -> complete."""
        from project_requests.services import (
            assign_project_request,
            start_project_request,
            hold_project_request,
            resume_project_request,
            complete_project_request,
        )
        pr = self._create_approved_pr()

        # Assign
        result = assign_project_request(pr, self.assignee, self.manager)
        self.assertEqual(result.status, ProjectRequestStatus.ASSIGNED)

        # Start
        result = start_project_request(pr, self.assignee)
        self.assertEqual(result.status, ProjectRequestStatus.IN_PROGRESS)

        # Hold
        result = hold_project_request(pr, self.assignee, comment="Need clarification")
        self.assertEqual(result.status, ProjectRequestStatus.ON_HOLD)

        # Resume
        result = resume_project_request(pr, self.assignee)
        self.assertEqual(result.status, ProjectRequestStatus.IN_PROGRESS)

        # Complete
        result = complete_project_request(pr, self.assignee)
        self.assertEqual(result.status, ProjectRequestStatus.COMPLETED)

    def test_on_hold_cannot_complete_directly(self):
        """Verify ON_HOLD cannot complete directly - must resume first."""
        from project_requests.services import (
            assign_project_request,
            start_project_request,
            hold_project_request,
            complete_project_request,
        )
        pr = self._create_approved_pr()
        assign_project_request(pr, self.assignee, self.manager)
        start_project_request(pr, self.assignee)
        hold_project_request(pr, self.assignee, comment="Waiting")

        with self.assertRaises((ValidationError, PermissionDenied)):
            complete_project_request(pr, self.assignee)

    def test_terminal_status_blocks_execution_actions(self):
        """COMPLETED request cannot be started, held, resumed, or completed again."""
        from project_requests.permissions import (
            can_start_project_request,
            can_hold_project_request,
            can_resume_project_request,
            can_complete_project_request,
        )
        from project_requests.models import ProjectRequest, ProjectRequestAssignment
        pr = ProjectRequest.objects.create(
            requester=self.requester,
            request_department=self.req_dept,
            project_department=self.proj_dept,
            request_type=self.ptype,
            project_name="Terminal Test",
            status=ProjectRequestStatus.COMPLETED,
        )
        ProjectRequestAssignment.objects.create(
            project_request=pr, assigned_to=self.assignee, assigned_by=self.assignee, is_active=True
        )
        self.assertFalse(can_start_project_request(self.assignee, pr))
        self.assertFalse(can_hold_project_request(self.assignee, pr))
        self.assertFalse(can_resume_project_request(self.assignee, pr))
        self.assertFalse(can_complete_project_request(self.assignee, pr))


# ============================================================================
# Phase 4B: Dashboard Selector Tests
# ============================================================================

class ProjectRequestDashboardSelectorTest(TestCase):
    """Tests for dashboard selectors."""

    def setUp(self):
        """Set up test fixtures."""
        from accounts.models import AccessLevel, Department, User, UserDepartment
        from project_requests.models import (
            ProjectDepartmentProfile,
            ProjectRequestType,
            ProjectRequestPriority,
        )

        self.req_dept = Department.objects.create(dept_code="ACCT", dept_name="Accounting")
        self.proj_dept = Department.objects.create(dept_code="MIS", dept_name="MIS")
        self.other_dept = Department.objects.create(dept_code="HR", dept_name="Human Resources")

        # Project department profiles
        self.proj_profile = ProjectDepartmentProfile.objects.create(
            department=self.proj_dept,
            is_active=True,
            can_receive_project_requests=True,
            allow_staff_claim=True,
        )
        self.other_profile = ProjectDepartmentProfile.objects.create(
            department=self.other_dept,
            is_active=True,
            can_receive_project_requests=True,
            allow_staff_claim=False,
        )

        self.ptype = ProjectRequestType.objects.create(
            code="new", name="New System", is_active=True,
        )

        # Users
        self.requester = User.objects.create_user(username="requester", password="pass")
        UserDepartment.objects.create(
            user=self.requester, department=self.req_dept,
            access_level=AccessLevel.STAFF, is_active=True,
        )

        self.staff_user = User.objects.create_user(username="staff", password="pass")
        UserDepartment.objects.create(
            user=self.staff_user, department=self.proj_dept,
            access_level=AccessLevel.STAFF, is_active=True,
            can_approve=False,
        )

        self.manager_user = User.objects.create_user(username="manager", password="pass")
        UserDepartment.objects.create(
            user=self.manager_user, department=self.proj_dept,
            access_level=AccessLevel.MANAGER, is_active=True,
            can_approve=True,
        )

        self.superuser = User.objects.create_superuser(username="admin", password="pass")

        # Import the selectors to test
        from project_requests.selectors import (
            get_dashboard_my_drafts,
            get_dashboard_my_open_requests,
            get_dashboard_claimable_requests,
            get_dashboard_project_department_queue,
            get_dashboard_in_progress_or_on_hold,
            get_dashboard_recently_completed,
            get_dashboard_status_counts,
            get_dashboard_overdue_count,
        )
        self.get_dashboard_my_drafts = get_dashboard_my_drafts
        self.get_dashboard_my_open_requests = get_dashboard_my_open_requests
        self.get_dashboard_claimable_requests = get_dashboard_claimable_requests
        self.get_dashboard_project_department_queue = get_dashboard_project_department_queue
        self.get_dashboard_in_progress_or_on_hold = get_dashboard_in_progress_or_on_hold
        self.get_dashboard_recently_completed = get_dashboard_recently_completed
        self.get_dashboard_status_counts = get_dashboard_status_counts
        self.get_dashboard_overdue_count = get_dashboard_overdue_count

    def _create_draft(self, requester, status=ProjectRequestStatus.DRAFT, proj_dept=None, **kwargs):
        """Helper to create a project request."""
        from project_requests.services import create_project_request_draft
        defaults = {
            "project_name": "Test Project",
            "requester": requester,
            "request_department": self.req_dept,
            "project_department": proj_dept or self.proj_dept,
            "request_type": self.ptype,
            "priority": ProjectRequestPriority.P3,
            "needed_by_date": date(2026, 12, 31),
            "scope_summary": "Summary",
            "business_problem": "Problem",
            "in_scope": "In scope",
            "expected_deliverables": "Deliverables",
            "acceptance_criteria": "Criteria",
        }
        defaults.update(kwargs)
        pr = create_project_request_draft(**defaults)
        if status != ProjectRequestStatus.DRAFT:
            pr.status = status
            pr.save()
        return pr

    # ---- get_dashboard_my_drafts tests ----

    def test_my_drafts_returns_only_own_drafts(self):
        """User sees only their own DRAFT requests, not others'."""
        # Create draft for self.requester
        self._create_draft(self.requester, status=ProjectRequestStatus.DRAFT)
        # Create draft for another user
        other_user = User.objects.create_user(username="other", password="pass")
        UserDepartment.objects.create(user=other_user, department=self.req_dept, is_active=True)
        self._create_draft(other_user, status=ProjectRequestStatus.DRAFT)

        drafts = self.get_dashboard_my_drafts(self.requester)
        self.assertEqual(drafts.count(), 1)
        self.assertEqual(drafts.first().requester, self.requester)

    def test_my_drafts_excludes_non_draft(self):
        """DRAFT selector excludes SUBMITTED and other non-DRAFT statuses."""
        self._create_draft(self.requester, status=ProjectRequestStatus.DRAFT)
        self._create_draft(self.requester, status=ProjectRequestStatus.SUBMITTED)
        self._create_draft(self.requester, status=ProjectRequestStatus.COMPLETED)

        drafts = self.get_dashboard_my_drafts(self.requester)
        self.assertEqual(drafts.count(), 1)
        self.assertEqual(drafts.first().status, ProjectRequestStatus.DRAFT)

    def test_my_drafts_empty_for_user_with_no_drafts(self):
        """User with no drafts gets empty queryset."""
        drafts = self.get_dashboard_my_drafts(self.staff_user)
        self.assertEqual(drafts.count(), 0)

    # ---- get_dashboard_my_open_requests tests ----

    def test_my_open_requests_excludes_draft_and_terminal(self):
        """Open requests excludes DRAFT, COMPLETED, REJECTED, CANCELLED."""
        self._create_draft(self.requester, status=ProjectRequestStatus.DRAFT)
        self._create_draft(self.requester, status=ProjectRequestStatus.SUBMITTED)
        self._create_draft(self.requester, status=ProjectRequestStatus.IN_PROGRESS)
        self._create_draft(self.requester, status=ProjectRequestStatus.COMPLETED)
        self._create_draft(self.requester, status=ProjectRequestStatus.REJECTED)
        self._create_draft(self.requester, status=ProjectRequestStatus.CANCELLED)

        open_reqs = self.get_dashboard_my_open_requests(self.requester)
        statuses = list(open_reqs.values_list("status", flat=True))
        self.assertNotIn(ProjectRequestStatus.DRAFT, statuses)
        self.assertNotIn(ProjectRequestStatus.COMPLETED, statuses)
        self.assertNotIn(ProjectRequestStatus.REJECTED, statuses)
        self.assertNotIn(ProjectRequestStatus.CANCELLED, statuses)
        self.assertIn(ProjectRequestStatus.SUBMITTED, statuses)
        self.assertIn(ProjectRequestStatus.IN_PROGRESS, statuses)

    def test_my_open_requests_includes_allowed_statuses(self):
        """Open requests includes SUBMITTED, REVIEWING, APPROVED, ASSIGNED, IN_PROGRESS, ON_HOLD."""
        allowed = [
            ProjectRequestStatus.SUBMITTED,
            ProjectRequestStatus.REVIEWING,
            ProjectRequestStatus.APPROVED,
            ProjectRequestStatus.ASSIGNED,
            ProjectRequestStatus.IN_PROGRESS,
            ProjectRequestStatus.ON_HOLD,
        ]
        for status in allowed:
            self._create_draft(self.requester, status=status)

        open_reqs = self.get_dashboard_my_open_requests(self.requester)
        self.assertEqual(open_reqs.count(), len(allowed))

    # ---- get_dashboard_claimable_requests tests ----

    def test_claimable_shows_approved_no_assignment(self):
        """Staff with allow_staff_claim=True sees APPROVED requests with no active assignment."""
        pr = self._create_draft(self.staff_user, status=ProjectRequestStatus.APPROVED)

        claimable = self.get_dashboard_claimable_requests(self.staff_user)
        self.assertEqual(claimable.count(), 1)
        self.assertEqual(claimable.first(), pr)

    def test_claimable_excludes_already_assigned(self):
        """Staff does not see APPROVED requests that already have an active assignment."""
        from project_requests.models import ProjectRequestAssignment
        pr = self._create_draft(self.staff_user, status=ProjectRequestStatus.APPROVED)
        ProjectRequestAssignment.objects.create(
            project_request=pr,
            assigned_to=self.manager_user,
            assigned_by=self.manager_user,
            is_active=True,
        )

        claimable = self.get_dashboard_claimable_requests(self.staff_user)
        self.assertEqual(claimable.count(), 0)

    def test_claimable_excludes_other_department(self):
        """Staff outside project department sees none."""
        other_dept_user = User.objects.create_user(username="other_dept_user", password="pass")
        UserDepartment.objects.create(
            user=other_dept_user, department=self.other_dept,
            access_level=AccessLevel.STAFF, is_active=True,
        )
        self._create_draft(other_dept_user, status=ProjectRequestStatus.APPROVED)

        claimable = self.get_dashboard_claimable_requests(other_dept_user)
        self.assertEqual(claimable.count(), 0)

    def test_claimable_excludes_inactive_profile(self):
        """Requests in departments with inactive profile are excluded."""
        self.proj_profile.allow_staff_claim = False
        self.proj_profile.save()
        self._create_draft(self.staff_user, status=ProjectRequestStatus.APPROVED)

        claimable = self.get_dashboard_claimable_requests(self.staff_user)
        self.assertEqual(claimable.count(), 0)

    def test_claimable_superuser_sees_all(self):
        """Superuser sees all claimable requests without UserDepartment restriction."""
        # Create a request APPROVED in the project dept
        self._create_draft(self.requester, status=ProjectRequestStatus.APPROVED)
        # Superuser has no UserDepartment records
        claimable = self.get_dashboard_claimable_requests(self.superuser)
        self.assertEqual(claimable.count(), 1)

    # ---- get_dashboard_project_department_queue tests ----

    def test_queue_shows_for_project_dept_manager(self):
        """Project dept manager sees non-terminal requests in managed dept."""
        pr = self._create_draft(self.requester, status=ProjectRequestStatus.SUBMITTED)

        queue = self.get_dashboard_project_department_queue(self.manager_user)
        self.assertEqual(queue.count(), 1)
        self.assertEqual(queue.first(), pr)

    def test_queue_empty_for_normal_staff(self):
        """Staff without manager role sees empty queue."""
        self._create_draft(self.requester, status=ProjectRequestStatus.SUBMITTED)

        queue = self.get_dashboard_project_department_queue(self.staff_user)
        self.assertEqual(queue.count(), 0)

    def test_queue_excludes_terminal_statuses(self):
        """Queue excludes COMPLETED, REJECTED, CANCELLED."""
        self._create_draft(self.requester, status=ProjectRequestStatus.SUBMITTED)
        self._create_draft(self.requester, status=ProjectRequestStatus.COMPLETED)
        self._create_draft(self.requester, status=ProjectRequestStatus.REJECTED)

        queue = self.get_dashboard_project_department_queue(self.manager_user)
        self.assertEqual(queue.count(), 1)

    def test_queue_superuser_sees_all(self):
        """Superuser sees all non-terminal requests without dept restriction."""
        self._create_draft(self.requester, status=ProjectRequestStatus.SUBMITTED)
        self._create_draft(self.requester, status=ProjectRequestStatus.IN_PROGRESS)

        queue = self.get_dashboard_project_department_queue(self.superuser)
        self.assertEqual(queue.count(), 2)

    # ---- get_dashboard_in_progress_or_on_hold tests ----

    def test_in_progress_shows_in_progress_and_on_hold(self):
        """Manager sees IN_PROGRESS and ON_HOLD in managed dept."""
        self._create_draft(self.requester, status=ProjectRequestStatus.IN_PROGRESS)
        self._create_draft(self.requester, status=ProjectRequestStatus.ON_HOLD)
        self._create_draft(self.requester, status=ProjectRequestStatus.SUBMITTED)

        ip = self.get_dashboard_in_progress_or_on_hold(self.manager_user)
        statuses = list(ip.values_list("status", flat=True))
        self.assertIn(ProjectRequestStatus.IN_PROGRESS, statuses)
        self.assertIn(ProjectRequestStatus.ON_HOLD, statuses)
        self.assertNotIn(ProjectRequestStatus.SUBMITTED, statuses)

    def test_in_progress_empty_for_staff(self):
        """Staff sees empty queryset."""
        self._create_draft(self.requester, status=ProjectRequestStatus.IN_PROGRESS)

        ip = self.get_dashboard_in_progress_or_on_hold(self.staff_user)
        self.assertEqual(ip.count(), 0)

    # ---- get_dashboard_recently_completed tests ----

    def test_recently_completed_within_window(self):
        """Completed requests within 30 days are included."""
        from django.utils import timezone
        pr = self._create_draft(self.requester, status=ProjectRequestStatus.COMPLETED)
        pr.completed_at = timezone.now() - timezone.timedelta(days=5)
        pr.save()

        recent = self.get_dashboard_recently_completed(self.manager_user, days=30)
        self.assertEqual(recent.count(), 1)

    def test_recently_completed_outside_window_excluded(self):
        """Completed requests older than 30 days are excluded."""
        from django.utils import timezone
        pr = self._create_draft(self.requester, status=ProjectRequestStatus.COMPLETED)
        pr.completed_at = timezone.now() - timezone.timedelta(days=60)
        pr.save()

        recent = self.get_dashboard_recently_completed(self.manager_user, days=30)
        self.assertEqual(recent.count(), 0)

    def test_recently_completed_superuser_sees_all(self):
        """Superuser sees all recently completed across depts."""
        from django.utils import timezone
        pr = self._create_draft(self.requester, status=ProjectRequestStatus.COMPLETED)
        pr.completed_at = timezone.now() - timezone.timedelta(days=5)
        pr.save()

        recent = self.get_dashboard_recently_completed(self.superuser, days=30)
        self.assertEqual(recent.count(), 1)

    # ---- get_dashboard_status_counts tests ----

    def test_status_counts_match_visible(self):
        """Status counts match what get_visible_project_requests would return."""
        from project_requests.selectors import get_visible_project_requests
        self._create_draft(self.requester, status=ProjectRequestStatus.DRAFT)
        self._create_draft(self.requester, status=ProjectRequestStatus.SUBMITTED)
        self._create_draft(self.requester, status=ProjectRequestStatus.COMPLETED)

        counts = self.get_dashboard_status_counts(self.superuser)
        counts_dict = {item["status"]: item["count"] for item in counts}

        # Superuser sees all
        total_visible = get_visible_project_requests(self.superuser).count()
        self.assertEqual(sum(counts_dict.values()), total_visible)

    def test_status_counts_empty_for_unauthenticated(self):
        """Unauthenticated user gets empty list."""
        counts = self.get_dashboard_status_counts(None)
        self.assertEqual(counts, [])

    # ---- get_dashboard_overdue_count tests ----

    def test_overdue_count_returns_integer(self):
        """Overdue count returns an integer."""
        count = self.get_dashboard_overdue_count(self.requester)
        self.assertIsInstance(count, int)
        self.assertEqual(count, 0)

    def test_overdue_count_matches_overdue_selector(self):
        """Overdue count matches get_overdue_project_requests count."""
        from project_requests.selectors import get_overdue_project_requests
        from project_requests.models import ProjectRequestAssignment

        # Create overdue assigned request
        pr = self._create_draft(self.requester, status=ProjectRequestStatus.IN_PROGRESS,
                                  needed_by_date=date(2020, 1, 1))
        ProjectRequestAssignment.objects.create(
            project_request=pr,
            assigned_to=self.requester,
            assigned_by=self.requester,
            is_active=True,
        )

        expected = get_overdue_project_requests(self.requester).count()
        actual = self.get_dashboard_overdue_count(self.requester)
        self.assertEqual(actual, expected)
