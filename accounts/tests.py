from django.test import TestCase
from django.conf import settings
from django.db import IntegrityError
from django.core.exceptions import ValidationError
from accounts.models import User, Department, UserDepartment, AccessLevel
from accounts.services import (
    get_user_department_membership,
    get_user_access_level,
    is_staff_in_department,
    is_manager_or_above,
    is_vp_or_above,
    get_user_departments,
    get_user_department_ids,
    get_user_managed_departments,
    get_user_managed_department_ids,
    can_approve_in_department,
    can_approve_as_manager_or_above,
    can_approve_as_vp,
)


class AuthUserModelTest(TestCase):
    """Verify AUTH_USER_MODEL is configured correctly."""

    def test_auth_user_model_is_accounts_user(self):
        self.assertEqual(settings.AUTH_USER_MODEL, 'accounts.User')


class UserModelTest(TestCase):
    """Tests for the custom User model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            display_name='Test User',
            employee_id='EMP001',
        )

    def test_user_can_be_created(self):
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(self.user.username, 'testuser')
        self.assertEqual(self.user.employee_id, 'EMP001')

    def test_str_returns_display_name_when_present(self):
        self.assertEqual(str(self.user), 'Test User')

    def test_str_returns_username_when_display_name_empty(self):
        self.user.display_name = ''
        self.user.save()
        self.assertEqual(str(self.user), 'testuser')

    def test_employee_id_defaults_to_empty(self):
        user = User.objects.create_user(username='noempid', password='pass123')
        self.assertEqual(user.employee_id, '')

    def test_display_name_defaults_to_empty(self):
        user = User.objects.create_user(username='nodisplay', password='pass123')
        self.assertEqual(user.display_name, '')

    # Fix 2 — employee_id conditional uniqueness
    def test_multiple_users_with_blank_employee_id_allowed(self):
        User.objects.create_user(username='user_a', password='pass123', employee_id='')
        User.objects.create_user(username='user_b', password='pass123', employee_id='')
        self.assertEqual(User.objects.filter(employee_id='').count(), 2)

    def test_duplicate_non_blank_employee_id_raises_integrity_error(self):
        User.objects.create_user(username='dup_a', password='pass123', employee_id='DUP001')
        with self.assertRaises(IntegrityError):
            User.objects.create_user(username='dup_b', password='pass123', employee_id='DUP001')


class DepartmentModelTest(TestCase):
    """Tests for the Department model."""

    def test_department_can_be_created(self):
        dept = Department.objects.create(dept_code='MIS', dept_name='Management Information Systems')
        self.assertEqual(dept.dept_code, 'MIS')
        self.assertEqual(dept.dept_name, 'Management Information Systems')
        self.assertTrue(dept.is_active)

    def test_str_returns_code_and_name(self):
        dept = Department.objects.create(dept_code='IT', dept_name='Information Technology')
        self.assertEqual(str(dept), 'IT - Information Technology')

    def test_unique_dept_code(self):
        Department.objects.create(dept_code='MIS', dept_name='MIS Dept')
        with self.assertRaises(IntegrityError):
            Department.objects.create(dept_code='MIS', dept_name='Duplicate Code')


class UserDepartmentModelTest(TestCase):
    """Tests for the UserDepartment model."""

    def setUp(self):
        self.user = User.objects.create_user(username='multidept', password='pass123')
        self.dept_mis = Department.objects.create(dept_code='MIS', dept_name='MIS')
        self.dept_it = Department.objects.create(dept_code='IT', dept_name='IT')
        self.dept_acct = Department.objects.create(dept_code='ACCT', dept_name='Accounting')

    def test_user_can_link_to_multiple_departments(self):
        UserDepartment.objects.create(user=self.user, department=self.dept_mis, access_level=AccessLevel.STAFF)
        UserDepartment.objects.create(user=self.user, department=self.dept_it, access_level=AccessLevel.MANAGER)
        self.assertEqual(self.user.user_departments.count(), 2)

    def test_same_user_different_access_levels_in_different_departments(self):
        UserDepartment.objects.create(user=self.user, department=self.dept_mis, access_level=AccessLevel.STAFF)
        UserDepartment.objects.create(user=self.user, department=self.dept_it, access_level=AccessLevel.VP)
        mis_level = self.user.user_departments.get(department=self.dept_mis).access_level
        it_level = self.user.user_departments.get(department=self.dept_it).access_level
        self.assertEqual(mis_level, AccessLevel.STAFF)
        self.assertEqual(it_level, AccessLevel.VP)

    def test_unique_user_department_constraint(self):
        UserDepartment.objects.create(user=self.user, department=self.dept_mis)
        with self.assertRaises(IntegrityError):
            UserDepartment.objects.create(user=self.user, department=self.dept_mis)

    # Fix 1 — primary department constraint (active only)
    def test_one_active_primary_department_allowed(self):
        UserDepartment.objects.create(user=self.user, department=self.dept_mis, is_primary=True)
        self.assertTrue(
            self.user.user_departments.filter(is_primary=True, is_active=True).exists()
        )

    def test_second_active_primary_department_raises_integrity_error(self):
        UserDepartment.objects.create(user=self.user, department=self.dept_mis, is_primary=True, is_active=True)
        with self.assertRaises(IntegrityError):
            UserDepartment.objects.create(user=self.user, department=self.dept_it, is_primary=True, is_active=True)

    def test_inactive_primary_does_not_block_new_active_primary(self):
        UserDepartment.objects.create(user=self.user, department=self.dept_mis, is_primary=True, is_active=False)
        # Should succeed because the existing primary is inactive
        UserDepartment.objects.create(user=self.user, department=self.dept_it, is_primary=True, is_active=True)
        active_primary = self.user.user_departments.filter(is_primary=True, is_active=True)
        self.assertEqual(active_primary.count(), 1)
        self.assertEqual(active_primary.first().department, self.dept_it)

    def test_str_representation(self):
        ud = UserDepartment.objects.create(
            user=self.user, department=self.dept_mis, access_level=AccessLevel.MANAGER
        )
        self.assertIn('MANAGER', str(ud))


class DepartmentRoleHelpersTest(TestCase):
    """Tests for department-scoped role helper functions."""

    def setUp(self):
        self.user = User.objects.create_user(username='roleuser', password='pass123')
        self.dept_mis = Department.objects.create(dept_code='MIS', dept_name='MIS')
        self.dept_it = Department.objects.create(dept_code='IT', dept_name='IT')

    def test_get_user_access_level_returns_department_specific_value(self):
        UserDepartment.objects.create(user=self.user, department=self.dept_mis, access_level=AccessLevel.STAFF)
        UserDepartment.objects.create(user=self.user, department=self.dept_it, access_level=AccessLevel.MANAGER)
        self.assertEqual(get_user_access_level(self.user, self.dept_mis), AccessLevel.STAFF)
        self.assertEqual(get_user_access_level(self.user, self.dept_it), AccessLevel.MANAGER)

    def test_get_user_access_level_defaults_to_staff_when_no_membership(self):
        self.assertEqual(get_user_access_level(self.user, self.dept_mis), AccessLevel.STAFF)

    def test_is_manager_or_above_works_by_department(self):
        UserDepartment.objects.create(user=self.user, department=self.dept_mis, access_level=AccessLevel.STAFF)
        UserDepartment.objects.create(user=self.user, department=self.dept_it, access_level=AccessLevel.MANAGER)
        self.assertFalse(is_manager_or_above(self.user, self.dept_mis))
        self.assertTrue(is_manager_or_above(self.user, self.dept_it))

    def test_is_manager_or_above_for_director(self):
        UserDepartment.objects.create(user=self.user, department=self.dept_mis, access_level=AccessLevel.DIRECTOR)
        self.assertTrue(is_manager_or_above(self.user, self.dept_mis))

    def test_is_vp_or_above_works_by_department(self):
        UserDepartment.objects.create(user=self.user, department=self.dept_mis, access_level=AccessLevel.STAFF)
        UserDepartment.objects.create(user=self.user, department=self.dept_it, access_level=AccessLevel.VP)
        self.assertFalse(is_vp_or_above(self.user, self.dept_mis))
        self.assertTrue(is_vp_or_above(self.user, self.dept_it))

    def test_is_staff_in_department(self):
        UserDepartment.objects.create(user=self.user, department=self.dept_mis, access_level=AccessLevel.STAFF)
        UserDepartment.objects.create(user=self.user, department=self.dept_it, access_level=AccessLevel.MANAGER)
        self.assertTrue(is_staff_in_department(self.user, self.dept_mis))
        self.assertFalse(is_staff_in_department(self.user, self.dept_it))

    # Fix 4 — helper return naming
    def test_get_user_departments_returns_active_departments(self):
        UserDepartment.objects.create(user=self.user, department=self.dept_mis, is_active=True)
        UserDepartment.objects.create(user=self.user, department=self.dept_it, is_active=False)
        depts = list(get_user_departments(self.user))
        self.assertEqual(len(depts), 1)
        self.assertEqual(depts[0], self.dept_mis.id)

    def test_get_user_department_ids_returns_active_ids(self):
        UserDepartment.objects.create(user=self.user, department=self.dept_mis, is_active=True)
        ids = list(get_user_department_ids(self.user))
        self.assertEqual(ids, [self.dept_mis.id])

    def test_get_user_managed_departments_returns_manager_and_above(self):
        UserDepartment.objects.create(user=self.user, department=self.dept_mis, access_level=AccessLevel.STAFF)
        UserDepartment.objects.create(user=self.user, department=self.dept_it, access_level=AccessLevel.MANAGER)
        managed = list(get_user_managed_departments(self.user))
        self.assertEqual(len(managed), 1)
        self.assertEqual(managed[0], self.dept_it.id)

    def test_get_user_managed_department_ids_returns_ids(self):
        UserDepartment.objects.create(user=self.user, department=self.dept_it, access_level=AccessLevel.MANAGER)
        ids = list(get_user_managed_department_ids(self.user))
        self.assertEqual(ids, [self.dept_it.id])

    def test_get_user_department_membership_returns_none_when_no_membership(self):
        membership = get_user_department_membership(self.user, self.dept_mis)
        self.assertIsNone(membership)

    def test_get_user_department_membership_returns_record_when_exists(self):
        ud = UserDepartment.objects.create(user=self.user, department=self.dept_mis, access_level=AccessLevel.VP)
        membership = get_user_department_membership(self.user, self.dept_mis)
        self.assertEqual(membership, ud)


class ApprovalHelpersTest(TestCase):
    """Tests for can_approve helper functions (Fix 5)."""

    def setUp(self):
        self.user = User.objects.create_user(username='approver', password='pass123')
        self.dept_mis = Department.objects.create(dept_code='MIS', dept_name='MIS')
        self.dept_it = Department.objects.create(dept_code='IT', dept_name='IT')

    # can_approve_in_department
    def test_can_approve_in_department_true_when_active_and_can_approve(self):
        UserDepartment.objects.create(
            user=self.user, department=self.dept_mis,
            access_level=AccessLevel.MANAGER, can_approve=True, is_active=True,
        )
        self.assertTrue(can_approve_in_department(self.user, self.dept_mis))

    def test_can_approve_in_department_false_when_can_approve_false(self):
        UserDepartment.objects.create(
            user=self.user, department=self.dept_mis,
            access_level=AccessLevel.MANAGER, can_approve=False, is_active=True,
        )
        self.assertFalse(can_approve_in_department(self.user, self.dept_mis))

    def test_can_approve_in_department_false_when_no_membership(self):
        self.assertFalse(can_approve_in_department(self.user, self.dept_mis))

    # can_approve_as_manager_or_above
    def test_manager_with_can_approve_can_approve_as_manager(self):
        UserDepartment.objects.create(
            user=self.user, department=self.dept_mis,
            access_level=AccessLevel.MANAGER, can_approve=True, is_active=True,
        )
        self.assertTrue(can_approve_as_manager_or_above(self.user, self.dept_mis))

    def test_manager_with_can_approve_false_cannot_approve(self):
        UserDepartment.objects.create(
            user=self.user, department=self.dept_mis,
            access_level=AccessLevel.MANAGER, can_approve=False, is_active=True,
        )
        self.assertFalse(can_approve_as_manager_or_above(self.user, self.dept_mis))

    def test_director_with_can_approve_can_approve_as_manager(self):
        UserDepartment.objects.create(
            user=self.user, department=self.dept_mis,
            access_level=AccessLevel.DIRECTOR, can_approve=True, is_active=True,
        )
        self.assertTrue(can_approve_as_manager_or_above(self.user, self.dept_mis))

    def test_staff_with_can_approve_does_not_pass_manager_helper(self):
        UserDepartment.objects.create(
            user=self.user, department=self.dept_mis,
            access_level=AccessLevel.STAFF, can_approve=True, is_active=True,
        )
        self.assertFalse(can_approve_as_manager_or_above(self.user, self.dept_mis))

    # can_approve_as_vp
    def test_vp_with_can_approve_can_approve_as_vp(self):
        UserDepartment.objects.create(
            user=self.user, department=self.dept_mis,
            access_level=AccessLevel.VP, can_approve=True, is_active=True,
        )
        self.assertTrue(can_approve_as_vp(self.user, self.dept_mis))

    def test_vp_with_can_approve_false_cannot_approve_as_vp(self):
        UserDepartment.objects.create(
            user=self.user, department=self.dept_mis,
            access_level=AccessLevel.VP, can_approve=False, is_active=True,
        )
        self.assertFalse(can_approve_as_vp(self.user, self.dept_mis))

    def test_manager_with_can_approve_does_not_pass_vp_helper(self):
        UserDepartment.objects.create(
            user=self.user, department=self.dept_mis,
            access_level=AccessLevel.MANAGER, can_approve=True, is_active=True,
        )
        self.assertFalse(can_approve_as_vp(self.user, self.dept_mis))
