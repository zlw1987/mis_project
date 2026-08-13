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


if __name__ == '__main__':
    unittest.main()
