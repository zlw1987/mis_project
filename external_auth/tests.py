"""
FoxPro External Authentication Tests

Tests for the FoxPro v2 signed launch URL validation.
"""

import time
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings, RequestFactory
from django.urls import reverse

from accounts.models import Department, UserDepartment
from external_auth.models import FoxproLaunchAttempt, FoxproLaunchNonce
from external_auth.signature import (
    foxpro_norm, foxpro_canonical_v2, foxpro_sign_v2,
    validate_timestamp, parse_timestamp, hash_nonce, is_ip_allowed
)
from external_auth.views import FoxProLaunchView, get_client_ip

User = get_user_model()


class FoxProSignatureTestCase(TestCase):
    """Tests for the FoxPro v2 signature algorithm."""
    
    def test_foxpro_norm_basic(self):
        """Test basic normalization."""
        self.assertEqual(foxpro_norm('  hello  '), 'hello')
        self.assertEqual(foxpro_norm(None), '')
        self.assertEqual(foxpro_norm(''), '')
        self.assertEqual(foxpro_norm('a|b'), 'a b')
        self.assertEqual(foxpro_norm('a\nb'), 'a b')
        self.assertEqual(foxpro_norm('a\r\nb'), 'a b')
    
    def test_foxpro_canonical_v2(self):
        """Test canonical string building."""
        params = {
            'n': 'jsmith',
            'ln': 'John Smith',
            'dp': 'ACCT',
            't': 'Sr. Accountant',
            'o': '2',
            'd': '20260527192015',
            'nonce': 'test-nonce-12345678901234567890',
            'return': 'project_requests:dashboard',
        }
        canonical = foxpro_canonical_v2(params)
        expected = 'MIS2|jsmith|John Smith|ACCT|Sr. Accountant|2|20260527192015|test-nonce-12345678901234567890|project_requests:dashboard'
        self.assertEqual(canonical, expected)
    
    def test_foxpro_canonical_v2_missing_o(self):
        """Test canonical string with missing o parameter (should be empty string)."""
        params = {
            'n': 'jsmith',
            'ln': 'John Smith',
            'dp': 'ACCT',
            't': 'Sr. Accountant',
            # 'o' is missing
            'd': '20260527192015',
            'nonce': 'test-nonce-12345678901234567890',
            'return': 'project_requests:dashboard',
        }
        canonical = foxpro_canonical_v2(params)
        # o should be empty string, so we get || in the canonical
        # Expected: MIS2|jsmith|John Smith|ACCT|Sr. Accountant||20260527192015|test-nonce-12345678901234567890|project_requests:dashboard
        parts = canonical.split('|')
        self.assertEqual(parts[0], 'MIS2')
        self.assertEqual(parts[5], '')  # o is empty
        self.assertIn('||', canonical)  # double pipe for empty o
    
    def test_foxpro_sign_v2(self):
        """Test v2 signature generation and verification."""
        secret = 'test-secret-key-for-foxpro-v2'
        canonical = 'MIS2|jsmith|John Smith|ACCT|Sr. Accountant|2|20260527192015|test-nonce-12345678901234567890|project_requests:dashboard'
        
        sig1 = foxpro_sign_v2(canonical, secret)
        sig2 = foxpro_sign_v2(canonical, secret)
        
        # Same input should produce same signature
        self.assertEqual(sig1, sig2)
        
        # Signature should be in V2-{h1:010d}-{h2:010d}-{h3:010d} format
        self.assertTrue(sig1.startswith('V2-'))
        parts = sig1.split('-')
        self.assertEqual(len(parts), 4)  # V2, h1, h2, h3
        self.assertEqual(len(parts[1]), 10)  # h1 is 10 digits
        self.assertEqual(len(parts[2]), 10)  # h2 is 10 digits
        self.assertEqual(len(parts[3]), 10)  # h3 is 10 digits
    
    def test_foxpro_sign_v2_empty_secret_raises(self):
        """Test that empty secret raises ValueError."""
        canonical = 'MIS2|test|test|test|test|test|test|test|test'
        with self.assertRaises(ValueError):
            foxpro_sign_v2(canonical, '')
        with self.assertRaises(ValueError):
            foxpro_sign_v2(canonical, None)
    
    def test_foxpro_sign_v2_different_inputs_different_sigs(self):
        """Test that different inputs produce different signatures."""
        secret = 'test-secret-key'
        sig1 = foxpro_sign_v2('MIS2|a|b|c|d|e|f|g|h', secret)
        sig2 = foxpro_sign_v2('MIS2|a|b|c|d|e|f|g|i', secret)
        self.assertNotEqual(sig1, sig2)


class TimestampValidationTestCase(TestCase):
    """Tests for timestamp validation."""
    
    def test_validate_timestamp_valid(self):
        """Test valid timestamp formats."""
        self.assertTrue(validate_timestamp('20260527192015'))
        self.assertTrue(validate_timestamp('20260101000000'))
        self.assertTrue(validate_timestamp('20261231235959'))
    
    def test_validate_timestamp_invalid(self):
        """Test invalid timestamp formats."""
        self.assertFalse(validate_timestamp(''))
        self.assertFalse(validate_timestamp(None))
        self.assertFalse(validate_timestamp('20260527'))  # Too short
        self.assertFalse(validate_timestamp('202605271920151'))  # Too long
        self.assertFalse(validate_timestamp('abcdefghijklmn'))
        self.assertFalse(validate_timestamp('20260527192015a'))  # Contains letter
        self.assertFalse(validate_timestamp('2026-05-27 19:20:15'))  # Wrong format
    
    def test_parse_timestamp_valid(self):
        """Test parsing valid timestamps."""
        ts = parse_timestamp('20260527192015')
        self.assertIsNotNone(ts)
        self.assertEqual(ts.year, 2026)
        self.assertEqual(ts.month, 5)
        self.assertEqual(ts.day, 27)
        self.assertEqual(ts.hour, 19)
        self.assertEqual(ts.minute, 20)
        self.assertEqual(ts.second, 15)
    
    def test_parse_timestamp_invalid(self):
        """Test parsing invalid timestamps returns None."""
        self.assertIsNone(parse_timestamp(''))
        self.assertIsNone(parse_timestamp('invalid'))


class IPAllowlistTestCase(TestCase):
    """Tests for IP allowlist functionality."""
    
    def test_is_ip_allowed_exact_match(self):
        """Test exact IP match."""
        allowed = ['10.0.0.1', '192.168.1.1']
        self.assertTrue(is_ip_allowed('10.0.0.1', allowed))
        self.assertFalse(is_ip_allowed('10.0.0.2', allowed))
    
    def test_is_ip_allowed_cidr(self):
        """Test CIDR range matching."""
        allowed = ['10.0.0.0/24', '192.168.0.0/16']
        self.assertTrue(is_ip_allowed('10.0.0.1', allowed))
        self.assertTrue(is_ip_allowed('10.0.0.255', allowed))
        self.assertFalse(is_ip_allowed('10.1.0.1', allowed))
        self.assertTrue(is_ip_allowed('192.168.1.100', allowed))
        self.assertFalse(is_ip_allowed('192.169.1.1', allowed))
    
    def test_is_ip_allowed_empty_list(self):
        """Test that empty list allows all."""
        self.assertTrue(is_ip_allowed('10.0.0.1', []))
        self.assertTrue(is_ip_allowed('any.ip.address', []))
    
    def test_is_ip_allowed_invalid_ip(self):
        """Test invalid IP returns False."""
        allowed = ['10.0.0.0/24']
        self.assertFalse(is_ip_allowed('invalid', allowed))
        self.assertFalse(is_ip_allowed('', allowed))


@override_settings(
    FOXPRO_V2_SECRET='test-secret-key-for-foxpro-v2',
    FOXPRO_LAUNCH_MAX_AGE_SECONDS=15,
    FOXPRO_ALLOWED_IPS=['127.0.0.1', '::1', '10.0.0.0/8'],
    FOXPRO_ALLOWED_RETURN_PATHS=['project_requests:dashboard', 'project_requests:index'],
)
class FoxProLaunchViewTestCase(TestCase):
    """Integration tests for FoxPro launch view."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.dept = Department.objects.create(
            dept_code='ACCT',
            dept_name='Accounting',
            is_active=True
        )
        self.user = User.objects.create_user(
            username='jsmith',
            password='test',
            employee_id='E001',
            display_name='John Smith',
            is_active=True
        )
        self.user_dept = UserDepartment.objects.create(
            user=self.user,
            department=self.dept,
            access_level='STAFF',
            is_active=True
        )
        self.secret = 'test-secret-key-for-foxpro-v2'
        self.view = FoxProLaunchView()
        self.factory = RequestFactory()
    
    def _make_valid_params(self, overrides=None):
        """Create valid launch parameters."""
        # Generate timestamp in the configured FoxPro timezone (LA) to match server interpretation
        import pytz
        la_tz = pytz.timezone('America/Los_Angeles')
        timestamp = datetime.now(la_tz).strftime('%Y%m%d%H%M%S')
        params = {
            'v': '2',
            'n': 'jsmith',
            'ln': 'John Smith',
            'dp': 'ACCT',
            't': 'Sr. Accountant',
            'o': 'STAFF',
            'd': timestamp,
            'nonce': 'test-nonce-12345678901234567890',
            'return': 'project_requests:dashboard',
        }
        params.update(overrides or {})
        return params
    
    def _sign_params(self, params):
        """Add signature to params."""
        params = params.copy()
        canonical = foxpro_canonical_v2(params)
        params['sig'] = foxpro_sign_v2(canonical, self.secret)
        return params
    
    def _make_signed_url(self, overrides=None):
        """Create a fully signed URL with valid params."""
        params = self._make_valid_params(overrides)
        params = self._sign_params(params)
        query = '&'.join(f'{k}={v}' for k, v in params.items())
        return f'/auth/foxpro-launch/?{query}'
    
    def test_valid_v2_launch_logs_in_and_redirects(self):
        """Test that valid v2 launch logs in user and redirects to dashboard."""
        url = self._make_signed_url()
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('project_requests:dashboard'))
        
        # Check user is logged in
        self.assertTrue('_auth_user_id' in self.client.session)
        
        # Check audit record was created
        attempt = FoxproLaunchAttempt.objects.filter(short_name='jsmith').first()
        self.assertIsNotNone(attempt)
        self.assertTrue(attempt.success)
        self.assertTrue(attempt.signature_valid)
    
    def test_tampered_dp_fails_signature(self):
        """Test that tampered dp parameter fails signature validation."""
        params = self._make_valid_params()
        params = self._sign_params(params)
        params['dp'] = 'TAMPERED'  # Change dp after signing
        
        query = '&'.join(f'{k}={v}' for k, v in params.items())
        url = f'/auth/foxpro-launch/?{query}'
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)
        
        # Check audit record
        attempt = FoxproLaunchAttempt.objects.filter(
            short_name='jsmith',
            failure_reason='INVALID_SIGNATURE'
        ).first()
        self.assertIsNotNone(attempt)
        self.assertFalse(attempt.success)
    
    def test_tampered_o_fails_signature(self):
        """Test that tampered o parameter fails signature validation."""
        params = self._make_valid_params()
        params = self._sign_params(params)
        params['o'] = 'TAMPERED'  # Change o after signing
        
        query = '&'.join(f'{k}={v}' for k, v in params.items())
        url = f'/auth/foxpro-launch/?{query}'
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)
        
        attempt = FoxproLaunchAttempt.objects.filter(
            short_name='jsmith',
            failure_reason='INVALID_SIGNATURE'
        ).first()
        self.assertIsNotNone(attempt)
    
    def test_tampered_return_fails_signature(self):
        """Test that tampered return parameter fails signature validation."""
        params = self._make_valid_params()
        params = self._sign_params(params)
        params['return'] = 'admin:index'  # Try to redirect to admin
        
        query = '&'.join(f'{k}={v}' for k, v in params.items())
        url = f'/auth/foxpro-launch/?{query}'
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)
        
        attempt = FoxproLaunchAttempt.objects.filter(
            short_name='jsmith',
            failure_reason='INVALID_SIGNATURE'
        ).first()
        self.assertIsNotNone(attempt)
    
    def test_expired_timestamp_fails(self):
        """Test that expired timestamp fails validation."""
        old_time = datetime.now(timezone.utc) - timedelta(seconds=30)
        params = self._make_valid_params({'d': old_time.strftime('%Y%m%d%H%M%S')})
        params = self._sign_params(params)
        
        query = '&'.join(f'{k}={v}' for k, v in params.items())
        url = f'/auth/foxpro-launch/?{query}'
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)
        
        attempt = FoxproLaunchAttempt.objects.filter(
            short_name='jsmith',
            failure_reason='TIMESTAMP_EXPIRED'
        ).first()
        self.assertIsNotNone(attempt)
    
    def test_malformed_timestamp_fails(self):
        """Test that malformed timestamp fails validation."""
        params = self._make_valid_params({'d': 'not-a-timestamp'})
        params = self._sign_params(params)
        
        query = '&'.join(f'{k}={v}' for k, v in params.items())
        url = f'/auth/foxpro-launch/?{query}'
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)
        
        attempt = FoxproLaunchAttempt.objects.filter(
            short_name='jsmith',
            failure_reason='INVALID_TIMESTAMP_FORMAT'
        ).first()
        self.assertIsNotNone(attempt)
    
    def test_invalid_signature_does_not_reserve_nonce(self):
        """Test that invalid signature does NOT reserve the nonce."""
        params = self._make_valid_params()
        params['sig'] = 'V2-0000000000-0000000000-0000000000'  # Wrong signature
        params = self._sign_params(params)
        params['sig'] = 'V2-0000000000-0000000000-0000000000'  # Overwrite with bad sig
        
        query = '&'.join(f'{k}={v}' for k, v in params.items())
        url = f'/auth/foxpro-launch/?{query}'
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)
        
        # Nonce should NOT be reserved
        nonce_hash = hash_nonce(params['nonce'])
        nonce_exists = FoxproLaunchNonce.objects.filter(nonce_hash=nonce_hash).exists()
        self.assertFalse(nonce_exists)
    
    def test_reused_nonce_fails_and_creates_attempt(self):
        """Test that reused nonce fails and creates failed attempt."""
        # First launch should succeed
        url1 = self._make_signed_url({'nonce': 'unique-nonce-12345678901234567890'})
        response1 = self.client.get(url1)
        self.assertEqual(response1.status_code, 302)
        
        # Second launch with same nonce should fail
        url2 = self._make_signed_url({'nonce': 'unique-nonce-12345678901234567890'})
        response2 = self.client.get(url2)
        self.assertEqual(response2.status_code, 400)
        
        # Check that a failed attempt was created for the reuse
        attempt = FoxproLaunchAttempt.objects.filter(
            failure_reason='NONCE_REUSED'
        ).first()
        self.assertIsNotNone(attempt)
    
    def test_unknown_user_fails(self):
        """Test that unknown user fails."""
        params = self._make_valid_params({'n': 'unknown-user'})
        params = self._sign_params(params)
        
        query = '&'.join(f'{k}={v}' for k, v in params.items())
        url = f'/auth/foxpro-launch/?{query}'
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)
        
        attempt = FoxproLaunchAttempt.objects.filter(
            failure_reason='USER_NOT_FOUND'
        ).first()
        self.assertIsNotNone(attempt)
    
    def test_inactive_user_fails(self):
        """Test that inactive user fails."""
        self.user.is_active = False
        self.user.save()
        
        params = self._make_valid_params()
        params = self._sign_params(params)
        
        query = '&'.join(f'{k}={v}' for k, v in params.items())
        url = f'/auth/foxpro-launch/?{query}'
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)
        
        attempt = FoxproLaunchAttempt.objects.filter(
            failure_reason='USER_NOT_FOUND'  # is_active filter returns no user
        ).first()
        self.assertIsNotNone(attempt)
    
    def test_missing_department_fails(self):
        """Test that missing department fails."""
        params = self._make_valid_params({'dp': 'NOTEXIST'})
        params = self._sign_params(params)
        
        query = '&'.join(f'{k}={v}' for k, v in params.items())
        url = f'/auth/foxpro-launch/?{query}'
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)
        
        attempt = FoxproLaunchAttempt.objects.filter(
            failure_reason='DEPT_NOT_FOUND'
        ).first()
        self.assertIsNotNone(attempt)
    
    def test_missing_userdepartment_fails(self):
        """Test that missing UserDepartment membership fails."""
        # Create user without UserDepartment for ACCT
        dept2 = Department.objects.create(dept_code='IT', dept_name='IT', is_active=True)
        user2 = User.objects.create_user(
            username='newuser',
            password='test',
            employee_id='E002',
            is_active=True
        )
        # Note: No UserDepartment for newuser in ACCT
        
        params = self._make_valid_params({'n': 'newuser', 'dp': 'ACCT'})
        params = self._sign_params(params)
        
        query = '&'.join(f'{k}={v}' for k, v in params.items())
        url = f'/auth/foxpro-launch/?{query}'
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)
        
        attempt = FoxproLaunchAttempt.objects.filter(
            failure_reason='DEPT_MEMBERSHIP_MISSING'
        ).first()
        self.assertIsNotNone(attempt)
    
    def test_o_mismatch_logs_audit_but_does_not_change_permissions(self):
        """Test that o mismatch is logged for audit but does not change Django permissions."""
        # User has access_level='STAFF' but FoxPro sends o='DIRECTOR'
        params = self._make_valid_params({'o': 'DIRECTOR'})
        params = self._sign_params(params)
        
        query = '&'.join(f'{k}={v}' for k, v in params.items())
        url = f'/auth/foxpro-launch/?{query}'
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)  # Still succeeds
        
        # Verify user is logged in with original access_level
        attempt = FoxproLaunchAttempt.objects.filter(
            short_name='jsmith',
            success=True
        ).first()
        self.assertIsNotNone(attempt)
        self.assertEqual(attempt.legacy_access_level, 'DIRECTOR')
        
        # Verify user_dept.access_level is still STAFF
        self.user_dept.refresh_from_db()
        self.assertEqual(self.user_dept.access_level, 'STAFF')
    
    def test_unsafe_return_defaults_to_dashboard_after_signature_passes(self):
        """Test that unsafe return URL defaults to dashboard after signature passes.
        
        When FoxPro sends return='admin:index' (which is NOT in ALLOWED_RETURN_PATHS),
        the signature validates successfully (because we signed with admin:index),
        but the redirect goes to 'project_requests:dashboard' because admin:index
        is not in the allowlist.
        """
        # Sign params with return='admin:index' (not in ALLOWED_RETURN_PATHS)
        params = self._make_valid_params({'return': 'admin:index'})
        params = self._sign_params(params)
        
        query = '&'.join(f'{k}={v}' for k, v in params.items())
        url = f'/auth/foxpro-launch/?{query}'
        
        response = self.client.get(url)
        # Signature passes, but redirect goes to dashboard because admin:index not allowed
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('project_requests:dashboard'))
        
        # Verify the launch was successful (not failed)
        attempt = FoxproLaunchAttempt.objects.filter(
            short_name='jsmith',
            success=True
        ).first()
        self.assertIsNotNone(attempt)
    
    def test_employee_id_match_takes_priority_over_username(self):
        """Test that employee_id match takes priority over username fallback."""
        # User has employee_id='E001' and username='jsmith'
        # Passing n='E001' should match by employee_id first
        
        params = self._make_valid_params({'n': 'E001'})
        params = self._sign_params(params)
        
        query = '&'.join(f'{k}={v}' for k, v in params.items())
        url = f'/auth/foxpro-launch/?{query}'
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('project_requests:dashboard'))
    
    def test_username_fallback_works_when_employee_id_not_matched(self):
        """Test that username fallback works when employee_id doesn't match."""
        # Create user with different employee_id
        user2 = User.objects.create_user(
            username='awhite',
            password='test',
            employee_id='E999',  # Different from what will be passed
            is_active=True
        )
        UserDepartment.objects.create(
            user=user2,
            department=self.dept,
            access_level='STAFF',
            is_active=True
        )
        
        # Pass username as n, not employee_id
        params = self._make_valid_params({'n': 'awhite'})
        params = self._sign_params(params)
        
        query = '&'.join(f'{k}={v}' for k, v in params.items())
        url = f'/auth/foxpro-launch/?{query}'
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('project_requests:dashboard'))


class FoxProNonceReplayTestCase(TestCase):
    """Tests for nonce replay protection."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.dept = Department.objects.create(
            dept_code='ACCT',
            dept_name='Accounting',
            is_active=True
        )
        self.user = User.objects.create_user(
            username='jsmith',
            password='test',
            employee_id='E001',
            is_active=True
        )
        UserDepartment.objects.create(
            user=self.user,
            department=self.dept,
            access_level='STAFF',
            is_active=True
        )
        self.secret = 'test-secret-key-for-foxpro-v2'
    
    @override_settings(
        FOXPRO_V2_SECRET='test-secret-key-for-foxpro-v2',
        FOXPRO_LAUNCH_MAX_AGE_SECONDS=15,
        FOXPRO_ALLOWED_IPS=[],
        FOXPRO_ALLOWED_RETURN_PATHS=['project_requests:dashboard'],
    )
    def test_concurrent_nonce_rejection(self):
        """Test that concurrent nonce submissions are rejected."""
        nonce = 'concurrent-nonce-12345678901234567890'
        
        # Create first nonce reservation directly
        from external_auth.signature import hash_nonce
        nonce_hash = hash_nonce(nonce)
        
        nonce1 = FoxproLaunchNonce.objects.create(
            nonce_hash=nonce_hash,
            source_ip='127.0.0.1',
        )
        
        # Second attempt to reserve same nonce should fail
        with self.assertRaises(Exception):  # IntegrityError
            FoxproLaunchNonce.objects.create(
                nonce_hash=nonce_hash,
                source_ip='127.0.0.2',
            )


@override_settings(
    FOXPRO_V2_SECRET='test-secret-key-for-foxpro-v2',
    FOXPRO_LAUNCH_MAX_AGE_SECONDS=15,
    FOXPRO_ALLOWED_IPS=[],
    FOXPRO_ALLOWED_RETURN_PATHS=['project_requests:dashboard'],
    FOXPRO_SIGNATURE_MODE='legacy_v2',  # Required for valid tests
)
class FoxProSignatureModeTestCase(TestCase):
    """Tests for signature mode handling."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.dept = Department.objects.create(
            dept_code='ACCT',
            dept_name='Accounting',
            is_active=True
        )
        self.user = User.objects.create_user(
            username='jsmith',
            password='test',
            employee_id='E001',
            is_active=True
        )
        UserDepartment.objects.create(
            user=self.user,
            department=self.dept,
            access_level='STAFF',
            is_active=True
        )
        self.secret = 'test-secret-key-for-foxpro-v2'
    
    def _make_valid_params(self, overrides=None):
        """Create valid launch parameters."""
        import pytz
        la_tz = pytz.timezone('America/Los_Angeles')
        timestamp = datetime.now(la_tz).strftime('%Y%m%d%H%M%S')
        params = {
            'v': '2',
            'n': 'jsmith',
            'ln': 'John Smith',
            'dp': 'ACCT',
            't': 'Sr. Accountant',
            'o': 'STAFF',
            'd': timestamp,
            'nonce': 'test-nonce-12345678901234567890',
            'return': 'project_requests:dashboard',
        }
        params.update(overrides or {})
        return params
    
    def _sign_params(self, params):
        """Add signature to params."""
        params = params.copy()
        canonical = foxpro_canonical_v2(params)
        params['sig'] = foxpro_sign_v2(canonical, self.secret)
        return params
    
    @override_settings(FOXPRO_SIGNATURE_MODE='hmac_sha256')
    def test_unsupported_signature_mode_returns_400_and_creates_failed_attempt(self):
        """Test that unsupported signature mode returns 400 and creates failed FoxproLaunchAttempt."""
        params = self._make_valid_params()
        params = self._sign_params(params)
        
        query = '&'.join(f'{k}={v}' for k, v in params.items())
        url = f'/auth/foxpro-launch/?{query}'
        
        response = self.client.get(url)
        
        # Should return 400 (generic error)
        self.assertEqual(response.status_code, 400)
        
        # Should create failed attempt record
        attempt = FoxproLaunchAttempt.objects.filter(
            failure_reason='UNSUPPORTED_SIGNATURE_MODE'
        ).first()
        self.assertIsNotNone(attempt)
        self.assertFalse(attempt.success)
        self.assertFalse(attempt.signature_valid)
        self.assertFalse(attempt.timestamp_valid)
        # Nonce should NOT be reserved
        self.assertIsNone(attempt.nonce_reservation)
    
    @override_settings(FOXPRO_SIGNATURE_MODE=None)
    def test_none_signature_mode_returns_400_and_creates_failed_attempt(self):
        """Test that None signature mode returns 400 and creates failed FoxproLaunchAttempt."""
        params = self._make_valid_params()
        params = self._sign_params(params)
        
        query = '&'.join(f'{k}={v}' for k, v in params.items())
        url = f'/auth/foxpro-launch/?{query}'
        
        response = self.client.get(url)
        
        # Should return 400 (generic error)
        self.assertEqual(response.status_code, 400)
        
        # Should create failed attempt record
        attempt = FoxproLaunchAttempt.objects.filter(
            failure_reason='UNSUPPORTED_SIGNATURE_MODE'
        ).first()
        self.assertIsNotNone(attempt)


class FoxProIPHandlingTestCase(TestCase):
    """Tests for IP address handling."""
    
    def test_x_forwarded_for_not_trusted_by_default(self):
        """Test that X-Forwarded-For is NOT trusted by default (FOXPRO_TRUST_X_FORWARDED_FOR=False)."""
        factory = RequestFactory()
        
        # Set REMOTE_ADDR to one value and HTTP_X_FORWARDED_FOR to another
        request = factory.get('/auth/foxpro-launch/')
        request.META['REMOTE_ADDR'] = '192.168.1.100'
        request.META['HTTP_X_FORWARDED_FOR'] = '10.0.0.1, 10.0.0.2'
        
        # get_client_ip should use REMOTE_ADDR when FOXPRO_TRUST_X_FORWARDED_FOR is False
        with override_settings(FOXPRO_TRUST_X_FORWARDED_FOR=False):
            ip = get_client_ip(request)
            self.assertEqual(ip, '192.168.1.100')
    
    def test_x_forwarded_for_trusted_when_setting_is_true(self):
        """Test that X-Forwarded-For IS trusted when FOXPRO_TRUST_X_FORWARDED_FOR=True."""
        factory = RequestFactory()
        
        # Set REMOTE_ADDR to one value and HTTP_X_FORWARDED_FOR to another
        request = factory.get('/auth/foxpro-launch/')
        request.META['REMOTE_ADDR'] = '192.168.1.100'
        request.META['HTTP_X_FORWARDED_FOR'] = '10.0.0.1, 10.0.0.2'
        
        # get_client_ip should use first X-Forwarded-For value when setting is True
        with override_settings(FOXPRO_TRUST_X_FORWARDED_FOR=True):
            ip = get_client_ip(request)
            self.assertEqual(ip, '10.0.0.1')
    
    def test_x_forwarded_for_first_ip_in_chain_used(self):
        """Test that first IP in X-Forwarded-For chain is used."""
        factory = RequestFactory()
        
        request = factory.get('/auth/foxpro-launch/')
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        request.META['HTTP_X_FORWARDED_FOR'] = '203.0.113.195, 70.41.3.18, 150.172.238.178'
        
        with override_settings(FOXPRO_TRUST_X_FORWARDED_FOR=True):
            ip = get_client_ip(request)
            self.assertEqual(ip, '203.0.113.195')


@override_settings(
    FOXPRO_V2_SECRET='test-secret-key-for-foxpro-v2',
    FOXPRO_LAUNCH_MAX_AGE_SECONDS=15,
    FOXPRO_ALLOWED_IPS=[],
    FOXPRO_ALLOWED_RETURN_PATHS=['project_requests:dashboard'],
    FOXPRO_SIGNATURE_MODE='legacy_v2',
    FOXPRO_LAUNCH_TIMEZONE='America/Los_Angeles',
)
class FoxProTimezoneTestCase(TestCase):
    """Tests for timezone handling in timestamp validation."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.dept = Department.objects.create(
            dept_code='ACCT',
            dept_name='Accounting',
            is_active=True
        )
        self.user = User.objects.create_user(
            username='jsmith',
            password='test',
            employee_id='E001',
            is_active=True
        )
        UserDepartment.objects.create(
            user=self.user,
            department=self.dept,
            access_level='STAFF',
            is_active=True
        )
        self.secret = 'test-secret-key-for-foxpro-v2'
    
    def _make_valid_params(self, overrides=None):
        """Create valid launch parameters with LA timezone timestamp."""
        import pytz
        la_tz = pytz.timezone('America/Los_Angeles')
        timestamp = datetime.now(la_tz).strftime('%Y%m%d%H%M%S')
        params = {
            'v': '2',
            'n': 'jsmith',
            'ln': 'John Smith',
            'dp': 'ACCT',
            't': 'Sr. Accountant',
            'o': 'STAFF',
            'd': timestamp,
            'nonce': 'test-nonce-12345678901234567890',
            'return': 'project_requests:dashboard',
        }
        params.update(overrides or {})
        return params
    
    def _sign_params(self, params):
        """Add signature to params."""
        params = params.copy()
        canonical = foxpro_canonical_v2(params)
        params['sig'] = foxpro_sign_v2(canonical, self.secret)
        return params
    
    def test_local_timezone_timestamp_succeeds(self):
        """Test that local timezone (LA) timestamp succeeds with FOXPRO_LAUNCH_TIMEZONE='America/Los_Angeles'."""
        # Generate timestamp in LA timezone
        import pytz
        la_tz = pytz.timezone('America/Los_Angeles')
        now_la = datetime.now(la_tz)
        
        params = self._make_valid_params({
            'd': now_la.strftime('%Y%m%d%H%M%S'),
            'nonce': 'timezone-test-nonce-12345678901234567890',
        })
        params = self._sign_params(params)
        
        query = '&'.join(f'{k}={v}' for k, v in params.items())
        url = f'/auth/foxpro-launch/?{query}'
        
        response = self.client.get(url)
        
        # Should succeed (302 redirect)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('project_requests:dashboard'))
        
        # Verify attempt was created with timestamp_valid=True
        attempt = FoxproLaunchAttempt.objects.filter(
            short_name='jsmith',
            success=True
        ).first()
        self.assertIsNotNone(attempt)
        self.assertTrue(attempt.timestamp_valid)
        self.assertTrue(attempt.signature_valid)
    
    def test_expired_timestamp_in_la_timezone_fails(self):
        """Test that expired timestamp in LA timezone fails validation."""
        import pytz
        la_tz = pytz.timezone('America/Los_Angeles')
        # Create a timestamp 30 seconds in the past (expired with 15s max age)
        old_time_la = datetime.now(la_tz) - timedelta(seconds=30)
        
        params = self._make_valid_params({
            'd': old_time_la.strftime('%Y%m%d%H%M%S'),
            'nonce': 'expired-tz-nonce-12345678901234567890',
        })
        params = self._sign_params(params)
        
        query = '&'.join(f'{k}={v}' for k, v in params.items())
        url = f'/auth/foxpro-launch/?{query}'
        
        response = self.client.get(url)
        
        # Should fail with 400
        self.assertEqual(response.status_code, 400)
        
        # Verify attempt was created with TIMESTAMP_EXPIRED
        attempt = FoxproLaunchAttempt.objects.filter(
            short_name='jsmith',
            failure_reason='TIMESTAMP_EXPIRED'
        ).first()
        self.assertIsNotNone(attempt)