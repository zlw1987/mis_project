"""
Tests for pilot runtime settings (config/settings_pilot.py).

Uses unittest and subprocess to test settings loading in clean Python processes.
"""

import os
import subprocess
import sys
import unittest


class PilotSettingsTestCase(unittest.TestCase):
    """Test pilot settings with subprocess isolation."""

    def run_subprocess_test(self, env_overrides, test_code):
        """Run a test in a subprocess with specified environment variables."""
        env = os.environ.copy()
        
        for key in [
            'DJANGO_SETTINGS_MODULE',
            'DJANGO_SECRET_KEY',
            'DJANGO_ALLOWED_HOSTS',
            'FOXPRO_V2_SECRET',
            'FOXPRO_ALLOWED_IPS',
            'FOXPRO_SIGNATURE_MODE',
            'FOXPRO_LAUNCH_MAX_AGE_SECONDS',
            'FOXPRO_LAUNCH_TIMEZONE',
            'FOXPRO_TRUST_X_FORWARDED_FOR',
            'MIS_DB_NAME',
            'MIS_DB_USER',
            'MIS_DB_PASSWORD',
            'MIS_DB_HOST',
            'MIS_DB_PORT',
        ]:
            env.pop(key, None)
        
        env.update(env_overrides)
        
        result = subprocess.run(
            [sys.executable, "-c", test_code],
            env=env,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result


class PilotSettingsDiscoveryTests(PilotSettingsTestCase):
    """Test 1: valid pilot configuration loads successfully."""

    def test_valid_pilot_configuration(self):
        """Test that valid pilot configuration loads successfully."""
        test_code = """
import os
import sys
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'

import django
django.setup()
print('SUCCESS: Settings loaded')
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertEqual(result.returncode, 0, f"Expected success, got: {result.stderr}")
        self.assertIn("SUCCESS", result.stdout)


class PilotSettingsDebugTest(PilotSettingsTestCase):
    """Test 2: pilot DEBUG is False."""

    def test_pilot_debug_is_false(self):
        """Test that pilot DEBUG is False."""
        test_code = """
import os
import sys
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'

import django
django.setup()
from django.conf import settings
assert settings.DEBUG is False, f"DEBUG should be False, got {settings.DEBUG}"
print('SUCCESS: DEBUG is False')
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertEqual(result.returncode, 0, f"Expected success, got: {result.stderr}")
        self.assertIn("SUCCESS", result.stdout)


class PilotSettingsSecretKeyTests(PilotSettingsTestCase):
    """Tests 3-4: missing and blank DJANGO_SECRET_KEY fail closed."""

    def test_missing_django_secret_key_fails(self):
        """Test that missing DJANGO_SECRET_KEY fails closed."""
        test_code = """
import os
import sys
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'

import django
django.setup()
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertNotEqual(result.returncode, 0, "Expected failure for missing SECRET_KEY")
        self.assertIn("ImproperlyConfigured", result.stderr)

    def test_blank_django_secret_key_fails(self):
        """Test that blank DJANGO_SECRET_KEY fails closed."""
        test_code = """
import os
import sys
os.environ['DJANGO_SECRET_KEY'] = '   '
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'

import django
django.setup()
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertNotEqual(result.returncode, 0, "Expected failure for blank SECRET_KEY")
        self.assertIn("ImproperlyConfigured", result.stderr)


class PilotSettingsAllowedHostsTests(PilotSettingsTestCase):
    """Tests 5-7: DJANGO_ALLOWED_HOSTS validation."""

    def test_missing_django_allowed_hosts_fails(self):
        """Test that missing DJANGO_ALLOWED_HOSTS fails closed."""
        test_code = """
import os
import sys
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'

import django
django.setup()
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertNotEqual(result.returncode, 0, "Expected failure for missing ALLOWED_HOSTS")
        self.assertIn("ImproperlyConfigured", result.stderr)

    def test_blank_django_allowed_hosts_fails(self):
        """Test that blank/effectively-empty DJANGO_ALLOWED_HOSTS fails closed."""
        test_code = """
import os
import sys
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = '   '
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'

import django
django.setup()
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertNotEqual(result.returncode, 0, "Expected failure for blank ALLOWED_HOSTS")
        self.assertIn("ImproperlyConfigured", result.stderr)

    def test_comma_separated_hosts_trimmed(self):
        """Test that comma-separated hosts are trimmed and empty items removed."""
        test_code = """
import os
import sys
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = ' localhost , , 127.0.0.1 ,  '
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'

import django
django.setup()
from django.conf import settings
assert 'localhost' in settings.ALLOWED_HOSTS
assert '127.0.0.1' in settings.ALLOWED_HOSTS
print('SUCCESS: Hosts trimmed correctly')
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertEqual(result.returncode, 0, f"Expected success, got: {result.stderr}")
        self.assertIn("SUCCESS", result.stdout)


class PilotSettingsFoxproV2SecretTests(PilotSettingsTestCase):
    """Tests 8-9: FOXPRO_V2_SECRET validation."""

    def test_missing_foxpro_v2_secret_fails(self):
        """Test that missing FOXPRO_V2_SECRET fails closed."""
        test_code = """
import os
import sys
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'

import django
django.setup()
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertNotEqual(result.returncode, 0, "Expected failure for missing FOXPRO_V2_SECRET")
        self.assertIn("ImproperlyConfigured", result.stderr)

    def test_short_foxpro_v2_secret_fails(self):
        """Test that short FOXPRO_V2_SECRET fails closed."""
        test_code = """
import os
import sys
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'short-secret'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'

import django
django.setup()
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertNotEqual(result.returncode, 0, "Expected failure for short secret")
        self.assertIn("ImproperlyConfigured", result.stderr)


class PilotSettingsFoxproAllowedIpsTests(PilotSettingsTestCase):
    """Tests 10-12: FOXPRO_ALLOWED_IPS validation."""

    def test_missing_foxpro_allowed_ips_fails(self):
        """Test that missing FOXPRO_ALLOWED_IPS fails closed."""
        test_code = """
import os
import sys
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'

import django
django.setup()
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertNotEqual(result.returncode, 0, "Expected failure for missing FOXPRO_ALLOWED_IPS")
        self.assertIn("ImproperlyConfigured", result.stderr)

    def test_blank_foxpro_allowed_ips_fails(self):
        """Test that blank/effectively-empty FOXPRO_ALLOWED_IPS fails closed."""
        test_code = """
import os
import sys
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '   '
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'

import django
django.setup()
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertNotEqual(result.returncode, 0, "Expected failure for blank ALLOWED_IPS")
        self.assertIn("ImproperlyConfigured", result.stderr)

    def test_comma_separated_ips_trimmed(self):
        """Test that comma-separated IP/CIDR values are trimmed and empty items removed."""
        test_code = """
import os
import sys
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = ' 127.0.0.1 , , ::1 ,  '
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'

import django
django.setup()
from django.conf import settings
assert '127.0.0.1' in settings.FOXPRO_ALLOWED_IPS
assert '::1' in settings.FOXPRO_ALLOWED_IPS
print('SUCCESS: IPs trimmed correctly')
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertEqual(result.returncode, 0, f"Expected success, got: {result.stderr}")
        self.assertIn("SUCCESS", result.stdout)


class PilotSettingsDefaultValuesTests(PilotSettingsTestCase):
    """Tests 13-19: Default values for configurable settings."""

    def test_default_foxpro_signature_mode(self):
        """Test that default FOXPRO_SIGNATURE_MODE is legacy_v2."""
        test_code = """
import os
import sys
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'

import django
django.setup()
from django.conf import settings
assert settings.FOXPRO_SIGNATURE_MODE == 'legacy_v2'
print('SUCCESS: Default signature mode is legacy_v2')
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertEqual(result.returncode, 0, f"Expected success, got: {result.stderr}")
        self.assertIn("SUCCESS", result.stdout)

    def test_default_foxpro_launch_max_age(self):
        """Test that default FOXPRO_LAUNCH_MAX_AGE_SECONDS is 15."""
        test_code = """
import os
import sys
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'

import django
django.setup()
from django.conf import settings
assert settings.FOXPRO_LAUNCH_MAX_AGE_SECONDS == 15
print('SUCCESS: Default max age is 15')
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertEqual(result.returncode, 0, f"Expected success, got: {result.stderr}")
        self.assertIn("SUCCESS", result.stdout)

    def test_default_foxpro_launch_timezone(self):
        """Test that default FOXPRO_LAUNCH_TIMEZONE is America/Los_Angeles."""
        test_code = """
import os
import sys
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'

import django
django.setup()
from django.conf import settings
assert settings.FOXPRO_LAUNCH_TIMEZONE == 'America/Los_Angeles'
print('SUCCESS: Default timezone is America/Los_Angeles')
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertEqual(result.returncode, 0, f"Expected success, got: {result.stderr}")
        self.assertIn("SUCCESS", result.stdout)

    def test_default_foxpro_trust_x_forwarded_for(self):
        """Test that default FOXPRO_TRUST_X_FORWARDED_FOR is False."""
        test_code = """
import os
import sys
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'

import django
django.setup()
from django.conf import settings
assert settings.FOXPRO_TRUST_X_FORWARDED_FOR is False
print('SUCCESS: Default trust_x_forwarded_for is False')
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertEqual(result.returncode, 0, f"Expected success, got: {result.stderr}")
        self.assertIn("SUCCESS", result.stdout)


class PilotSettingsFoxproLaunchMaxAgeTests(PilotSettingsTestCase):
    """Tests 15-16: FOXPRO_LAUNCH_MAX_AGE_SECONDS validation including zero and negative."""

    def test_invalid_foxpro_launch_max_age_fails(self):
        """Test that invalid FOXPRO_LAUNCH_MAX_AGE_SECONDS fails closed."""
        test_code = """
import os
import sys
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['FOXPRO_LAUNCH_MAX_AGE_SECONDS'] = 'invalid'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'

import django
django.setup()
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertNotEqual(result.returncode, 0, "Expected failure for invalid max age")
        self.assertIn("ImproperlyConfigured", result.stderr)

    def test_zero_max_age_fails(self):
        """Test that zero FOXPRO_LAUNCH_MAX_AGE_SECONDS fails closed."""
        test_code = """
import os
import sys
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['FOXPRO_LAUNCH_MAX_AGE_SECONDS'] = '0'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'

import django
django.setup()
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertNotEqual(result.returncode, 0, "Expected failure for zero max age")
        self.assertIn("ImproperlyConfigured", result.stderr)

    def test_negative_max_age_fails(self):
        """Test that negative FOXPRO_LAUNCH_MAX_AGE_SECONDS fails closed."""
        test_code = """
import os
import sys
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['FOXPRO_LAUNCH_MAX_AGE_SECONDS'] = '-5'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'

import django
django.setup()
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertNotEqual(result.returncode, 0, "Expected failure for negative max age")
        self.assertIn("ImproperlyConfigured", result.stderr)


class PilotSettingsFoxproLaunchTimezoneTests(PilotSettingsTestCase):
    """Test 18: explicit blank timezone fails closed."""

    def test_explicit_blank_timezone_fails(self):
        """Test that explicit blank timezone fails closed."""
        test_code = """
import os
import sys
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['FOXPRO_LAUNCH_TIMEZONE'] = '   '
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'

import django
django.setup()
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertNotEqual(result.returncode, 0, "Expected failure for blank timezone")
        self.assertIn("ImproperlyConfigured", result.stderr)


class PilotSettingsFoxproTrustXForwardedForTests(PilotSettingsTestCase):
    """Tests 20-21: FOXPRO_TRUST_X_FORWARDED_FOR boolean parsing."""

    def test_true_value_parsed_as_true(self):
        """Test that 'true' environment value parses as True."""
        test_code = """
import os
import sys
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['FOXPRO_TRUST_X_FORWARDED_FOR'] = 'true'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'

import django
django.setup()
from django.conf import settings
assert settings.FOXPRO_TRUST_X_FORWARDED_FOR is True
print('SUCCESS: true parsed as True')
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertEqual(result.returncode, 0, f"Expected success, got: {result.stderr}")
        self.assertIn("SUCCESS", result.stdout)

    def test_true_case_insensitive(self):
        """Test that 'TRUE' (uppercase) parses as True."""
        test_code = """
import os
import sys
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['FOXPRO_TRUST_X_FORWARDED_FOR'] = 'TRUE'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'

import django
django.setup()
from django.conf import settings
assert settings.FOXPRO_TRUST_X_FORWARDED_FOR is True
print('SUCCESS: TRUE parsed as True')
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertEqual(result.returncode, 0, f"Expected success, got: {result.stderr}")
        self.assertIn("SUCCESS", result.stdout)

    def test_one_parsed_as_true(self):
        """Test that '1' environment value parses as True."""
        test_code = """
import os
import sys
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['FOXPRO_TRUST_X_FORWARDED_FOR'] = '1'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'

import django
django.setup()
from django.conf import settings
assert settings.FOXPRO_TRUST_X_FORWARDED_FOR is True
print('SUCCESS: 1 parsed as True')
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertEqual(result.returncode, 0, f"Expected success, got: {result.stderr}")
        self.assertIn("SUCCESS", result.stdout)

    def test_false_value_parsed_as_false(self):
        """Test that 'false' environment value parses as False."""
        test_code = """
import os
import sys
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['FOXPRO_TRUST_X_FORWARDED_FOR'] = 'false'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'

import django
django.setup()
from django.conf import settings
assert settings.FOXPRO_TRUST_X_FORWARDED_FOR is False
print('SUCCESS: false parsed as False')
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertEqual(result.returncode, 0, f"Expected success, got: {result.stderr}")
        self.assertIn("SUCCESS", result.stdout)

    def test_false_case_insensitive(self):
        """Test that 'FALSE' (uppercase) parses as False."""
        test_code = """
import os
import sys
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['FOXPRO_TRUST_X_FORWARDED_FOR'] = 'FALSE'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'

import django
django.setup()
from django.conf import settings
assert settings.FOXPRO_TRUST_X_FORWARDED_FOR is False
print('SUCCESS: FALSE parsed as False')
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertEqual(result.returncode, 0, f"Expected success, got: {result.stderr}")
        self.assertIn("SUCCESS", result.stdout)

    def test_zero_parsed_as_false(self):
        """Test that '0' environment value parses as False."""
        test_code = """
import os
import sys
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['FOXPRO_TRUST_X_FORWARDED_FOR'] = '0'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'

import django
django.setup()
from django.conf import settings
assert settings.FOXPRO_TRUST_X_FORWARDED_FOR is False
print('SUCCESS: 0 parsed as False')
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertEqual(result.returncode, 0, f"Expected success, got: {result.stderr}")
        self.assertIn("SUCCESS", result.stdout)

    def test_invalid_trust_x_forwarded_for_fails(self):
        """Test that invalid FOXPRO_TRUST_X_FORWARDED_FOR value fails closed."""
        test_code = """
import os
import sys
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['FOXPRO_TRUST_X_FORWARDED_FOR'] = 'maybe'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'

import django
django.setup()
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertNotEqual(result.returncode, 0, "Expected failure for invalid trust_x_forwarded_for")
        self.assertIn("ImproperlyConfigured", result.stderr)


class PilotSettingsExternalModuleOverrideTest(PilotSettingsTestCase):
    """Test 22: externally supplied DJANGO_SETTINGS_MODULE=config.settings_pilot loads correctly."""

    def test_external_django_settings_module_overrides(self):
        """Test that externally supplied DJANGO_SETTINGS_MODULE successfully loads pilot settings."""
        test_code = """
import os
import sys

os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'

import subprocess
result = subprocess.run(
    [sys.executable, 'manage.py', 'check'],
    env=os.environ,
    capture_output=True,
    text=True,
    timeout=30
)
assert result.returncode == 0, f"manage.py check failed: {result.stderr}"
print('SUCCESS: External DJANGO_SETTINGS_MODULE works')
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertEqual(result.returncode, 0, f"Expected success, got: {result.stderr}")
        self.assertIn("SUCCESS", result.stdout)


class PilotSettingsDefaultSQLiteTest(PilotSettingsTestCase):
    """Test 23: Default settings still use SQLite without MIS_DB_* variables."""

    def test_default_settings_use_sqlite(self):
        """Test that default config.settings uses SQLite and doesn't require MIS_DB_*."""
        test_code = """
import os
import sys
os.environ.pop('MIS_DB_NAME', None)
os.environ.pop('MIS_DB_USER', None)
os.environ.pop('MIS_DB_PASSWORD', None)
os.environ.pop('MIS_DB_HOST', None)
os.environ.pop('MIS_DB_PORT', None)
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'

import django
django.setup()
from django.conf import settings
assert settings.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3'
assert str(settings.DATABASES['default']['NAME']).endswith('db.sqlite3')
print('SUCCESS: Default settings use SQLite')
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertEqual(result.returncode, 0, f"Expected success, got: {result.stderr}")
        self.assertIn("SUCCESS", result.stdout)


class PilotSettingsPilotDoesNotInheritSQLite(PilotSettingsTestCase):
    """Test 24: Pilot settings do not silently inherit SQLite."""

    def test_pilot_settings_override_sqlite(self):
        """Test that pilot settings use MySQL, not SQLite."""
        test_code = """
import os
import sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['MIS_DB_HOST'] = 'localhost'
os.environ['MIS_DB_PORT'] = '3306'

import django
django.setup()
from django.conf import settings
assert settings.DATABASES['default']['ENGINE'] == 'django.db.backends.mysql'
assert settings.DATABASES['default']['ENGINE'] != 'django.db.backends.sqlite3'
print('SUCCESS: Pilot settings use MySQL, not SQLite')
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertEqual(result.returncode, 0, f"Expected success, got: {result.stderr}")
        self.assertIn("SUCCESS", result.stdout)


class PilotSettingsDatabaseEngineTest(PilotSettingsTestCase):
    """Test 25: Pilot database engine is exactly django.db.backends.mysql."""

    def test_pilot_database_engine_is_mysql(self):
        """Test that pilot database engine is exactly django.db.backends.mysql."""
        test_code = """
import os
import sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['MIS_DB_HOST'] = 'localhost'
os.environ['MIS_DB_PORT'] = '3306'

import django
django.setup()
from django.conf import settings
assert settings.DATABASES['default']['ENGINE'] == 'django.db.backends.mysql'
print('SUCCESS: Database engine is mysql')
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertEqual(result.returncode, 0, f"Expected success, got: {result.stderr}")
        self.assertIn("SUCCESS", result.stdout)


class PilotSettingsDatabaseValidationTests(PilotSettingsTestCase):
    """Tests 26-34: Database environment variable validation."""

    def test_missing_mis_db_name_fails(self):
        """Test that missing MIS_DB_NAME fails closed."""
        test_code = """
import os
import sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'

import django
django.setup()
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertNotEqual(result.returncode, 0, "Expected failure for missing MIS_DB_NAME")
        self.assertIn("ImproperlyConfigured", result.stderr)

    def test_blank_mis_db_name_fails(self):
        """Test that blank MIS_DB_NAME fails closed."""
        test_code = """
import os
import sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['MIS_DB_NAME'] = '   '
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'

import django
django.setup()
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertNotEqual(result.returncode, 0, "Expected failure for blank MIS_DB_NAME")
        self.assertIn("ImproperlyConfigured", result.stderr)

    def test_missing_mis_db_user_fails(self):
        """Test that missing MIS_DB_USER fails closed."""
        test_code = """
import os
import sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'

import django
django.setup()
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertNotEqual(result.returncode, 0, "Expected failure for missing MIS_DB_USER")
        self.assertIn("ImproperlyConfigured", result.stderr)

    def test_blank_mis_db_user_fails(self):
        """Test that blank MIS_DB_USER fails closed."""
        test_code = """
import os
import sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = '   '
os.environ['MIS_DB_PASSWORD'] = 'testpass123'

import django
django.setup()
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertNotEqual(result.returncode, 0, "Expected failure for blank MIS_DB_USER")
        self.assertIn("ImproperlyConfigured", result.stderr)

    def test_missing_mis_db_password_fails(self):
        """Test that missing MIS_DB_PASSWORD fails closed."""
        test_code = """
import os
import sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'

import django
django.setup()
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertNotEqual(result.returncode, 0, "Expected failure for missing MIS_DB_PASSWORD")
        self.assertIn("ImproperlyConfigured", result.stderr)

    def test_empty_mis_db_password_fails(self):
        """Test that empty MIS_DB_PASSWORD fails closed."""
        test_code = """
import os
import sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = ''

import django
django.setup()
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertNotEqual(result.returncode, 0, "Expected failure for empty MIS_DB_PASSWORD")
        self.assertIn("ImproperlyConfigured", result.stderr)

    def test_mis_db_password_preserved_exactly(self):
        """Test that MIS_DB_PASSWORD is preserved exactly without stripping."""
        test_code = """
import os
import sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = '  password_with_spaces  '

import django
django.setup()
from django.conf import settings
assert settings.DATABASES['default']['PASSWORD'] == '  password_with_spaces  '
print('SUCCESS: Password preserved exactly')
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertEqual(result.returncode, 0, f"Expected success, got: {result.stderr}")
        self.assertIn("SUCCESS", result.stdout)

    def test_default_mis_db_host_is_localhost(self):
        """Test that default MIS_DB_HOST is localhost."""
        test_code = """
import os
import sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'

import django
django.setup()
from django.conf import settings
assert settings.DATABASES['default']['HOST'] == 'localhost'
print('SUCCESS: Default host is localhost')
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertEqual(result.returncode, 0, f"Expected success, got: {result.stderr}")
        self.assertIn("SUCCESS", result.stdout)

    def test_explicit_blank_mis_db_host_fails(self):
        """Test that explicit blank MIS_DB_HOST fails closed."""
        test_code = """
import os
import sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['MIS_DB_HOST'] = '   '

import django
django.setup()
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertNotEqual(result.returncode, 0, "Expected failure for blank MIS_DB_HOST")
        self.assertIn("ImproperlyConfigured", result.stderr)

    def test_default_mis_db_port_is_3306(self):
        """Test that default MIS_DB_PORT is 3306."""
        test_code = """
import os
import sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'

import django
django.setup()
from django.conf import settings
assert settings.DATABASES['default']['PORT'] == 3306
print('SUCCESS: Default port is 3306')
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertEqual(result.returncode, 0, f"Expected success, got: {result.stderr}")
        self.assertIn("SUCCESS", result.stdout)

    def test_non_integer_mis_db_port_fails(self):
        """Test that non-integer MIS_DB_PORT fails closed."""
        test_code = """
import os
import sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['MIS_DB_PORT'] = 'invalid'

import django
django.setup()
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertNotEqual(result.returncode, 0, "Expected failure for non-integer port")
        self.assertIn("ImproperlyConfigured", result.stderr)

    def test_zero_mis_db_port_fails(self):
        """Test that zero MIS_DB_PORT fails closed."""
        test_code = """
import os
import sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['MIS_DB_PORT'] = '0'

import django
django.setup()
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertNotEqual(result.returncode, 0, "Expected failure for zero port")
        self.assertIn("ImproperlyConfigured", result.stderr)

    def test_negative_mis_db_port_fails(self):
        """Test that negative MIS_DB_PORT fails closed."""
        test_code = """
import os
import sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['MIS_DB_PORT'] = '-1'

import django
django.setup()
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertNotEqual(result.returncode, 0, "Expected failure for negative port")
        self.assertIn("ImproperlyConfigured", result.stderr)

    def test_mis_db_port_over_65535_fails(self):
        """Test that MIS_DB_PORT > 65535 fails closed."""
        test_code = """
import os
import sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'
os.environ['MIS_DB_PORT'] = '65536'

import django
django.setup()
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertNotEqual(result.returncode, 0, "Expected failure for port > 65535")
        self.assertIn("ImproperlyConfigured", result.stderr)


class PilotSettingsEnvironmentIsolationTest(PilotSettingsTestCase):
    """Test 46: verify all 14 pilot environment variables are sanitized from inherited environment."""

    EXPECTED_SANITIZATION_KEYS = [
        'DJANGO_SETTINGS_MODULE',
        'DJANGO_SECRET_KEY',
        'DJANGO_ALLOWED_HOSTS',
        'FOXPRO_V2_SECRET',
        'FOXPRO_ALLOWED_IPS',
        'FOXPRO_SIGNATURE_MODE',
        'FOXPRO_LAUNCH_MAX_AGE_SECONDS',
        'FOXPRO_LAUNCH_TIMEZONE',
        'FOXPRO_TRUST_X_FORWARDED_FOR',
        'MIS_DB_NAME',
        'MIS_DB_USER',
        'MIS_DB_PASSWORD',
        'MIS_DB_HOST',
        'MIS_DB_PORT',
    ]

    def setUp(self):
        """Set up synthetic sentinel values for ALL 14 pilot-related environment variables."""
        self.original_env = {}
        for key in self.EXPECTED_SANITIZATION_KEYS:
            self.original_env[key] = os.environ.get(key)
            os.environ[key] = 'inherited_sentinel_' + key

    def tearDown(self):
        """Restore parent environment."""
        for key in self.EXPECTED_SANITIZATION_KEYS:
            if self.original_env[key] is not None:
                os.environ[key] = self.original_env[key]
            else:
                os.environ.pop(key, None)

    def test_all_pilot_env_vars_sanitized_from_subprocess(self):
        """Test that all inherited parent environment variables are removed in subprocess."""
        test_code = """
import os
import sys

# Check that none of the expected keys have their inherited sentinel values
for key in [
    'DJANGO_SETTINGS_MODULE',
    'DJANGO_SECRET_KEY',
    'DJANGO_ALLOWED_HOSTS',
    'FOXPRO_V2_SECRET',
    'FOXPRO_ALLOWED_IPS',
    'FOXPRO_SIGNATURE_MODE',
    'FOXPRO_LAUNCH_MAX_AGE_SECONDS',
    'FOXPRO_LAUNCH_TIMEZONE',
    'FOXPRO_TRUST_X_FORWARDED_FOR',
    'MIS_DB_NAME',
    'MIS_DB_USER',
    'MIS_DB_PASSWORD',
    'MIS_DB_HOST',
    'MIS_DB_PORT',
]:
    value = os.environ.get(key)
    if value and 'sentinel' in value:
        sys.stderr.write(f"Inherited value leaked: {key}={value}\\n")
        sys.exit(1)

# Now set up valid pilot settings to verify subprocess can load
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['MIS_DB_NAME'] = 'testdb'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'

import django
django.setup()
print('SUCCESS: All inherited env vars sanitized and pilot settings loaded')
"""
        result = self.run_subprocess_test({}, test_code)
        self.assertEqual(result.returncode, 0, f"Expected success, got: {result.stderr}")
        self.assertIn("SUCCESS", result.stdout)

    def test_env_overrides_applied_after_sanitize(self):
        """Test that explicit env_overrides override any remaining parent values."""
        test_code = """
import os
import sys

# Check that MIS_DB_NAME has the child override, not the inherited sentinel
mis_db_name = os.environ.get('MIS_DB_NAME')
if mis_db_name == 'inherited_sentinel_MIS_DB_NAME':
    sys.stderr.write(f"Sentinel leaked, expected override: {mis_db_name}\\n")
    sys.exit(1)
if mis_db_name != 'synthetic_child_override':
    sys.stderr.write(f"Wrong value for MIS_DB_NAME: {mis_db_name}\\n")
    sys.exit(1)

# Verify other required vars are still sanitized
for key in ['DJANGO_SETTINGS_MODULE', 'DJANGO_SECRET_KEY', 'DJANGO_ALLOWED_HOSTS',
            'FOXPRO_V2_SECRET', 'FOXPRO_ALLOWED_IPS']:
    if os.environ.get(key) and 'sentinel' in os.environ.get(key, ''):
        sys.stderr.write(f"Key not sanitized: {key}\\n")
        sys.exit(1)

os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_pilot'
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-32chars-long-for-testing'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'localhost,127.0.0.1'
os.environ['FOXPRO_V2_SECRET'] = 'test-foxpro-secret-minimum-32-chars'
os.environ['FOXPRO_ALLOWED_IPS'] = '127.0.0.1,::1'
os.environ['MIS_DB_USER'] = 'testuser'
os.environ['MIS_DB_PASSWORD'] = 'testpass123'

import django
django.setup()
print('SUCCESS: Overrides applied after sanitization')
"""
        result = self.run_subprocess_test({'MIS_DB_NAME': 'synthetic_child_override'}, test_code)
        self.assertEqual(result.returncode, 0, f"Expected success, got: {result.stderr}")
        self.assertIn("SUCCESS", result.stdout)


if __name__ == '__main__':
    unittest.main()
