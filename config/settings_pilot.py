"""
Django pilot runtime settings for config project.

This module provides fail-closed configuration for pilot deployment.
Use with: DJANGO_SETTINGS_MODULE=config.settings_pilot

All sensitive settings MUST be provided via environment variables.
Missing or invalid values will raise ImproperlyConfigured.
"""

import os

from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F403


def get_env_required(name: str) -> str:
    """Get required environment variable or raise ImproperlyConfigured."""
    value = os.environ.get(name)
    if value is None:
        raise ImproperlyConfigured(f"Required environment variable {name} is not set")
    return value


def get_env_trimmed(name: str) -> str:
    """Get and trim environment variable value."""
    value = os.environ.get(name)
    if value is not None:
        return value.strip()
    return None


def get_env_required_trimmed(name: str) -> str:
    """Get required environment variable with trimming."""
    value = get_env_trimmed(name)
    if value is None or value == "":
        raise ImproperlyConfigured(
            f"Required environment variable {name} is blank or not set"
        )
    return value


# SECURITY WARNING: keep the secret key used in production secret!
# Read from environment; fail closed if missing or blank
SECRET_KEY = get_env_required_trimmed("DJANGO_SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

# ALLOWED_HOSTS must be provided via environment
# Comma-separated list of hostnames
allowed_hosts_raw = get_env_required_trimmed("DJANGO_ALLOWED_HOSTS")
allowed_hosts_list = [
    h.strip()
    for h in allowed_hosts_raw.split(",")
    if h.strip()
]
if not allowed_hosts_list:
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS is blank or contains no valid hostnames"
    )
ALLOWED_HOSTS = allowed_hosts_list

# FoxPro V2 secret - required, minimum 32 characters
foxpro_secret = get_env_required_trimmed("FOXPRO_V2_SECRET")
if len(foxpro_secret) < 32:
    raise ImproperlyConfigured(
        "FOXPRO_V2_SECRET must be at least 32 characters long"
    )
FOXPRO_V2_SECRET = foxpro_secret

# FoxPro allowed IPs - comma-separated list of IPs or CIDR
allowed_ips_raw = get_env_required_trimmed("FOXPRO_ALLOWED_IPS")
allowed_ips_list = [
    ip.strip()
    for ip in allowed_ips_raw.split(",")
    if ip.strip()
]
if not allowed_ips_list:
    raise ImproperlyConfigured(
        "FOXPRO_ALLOWED_IPS is blank or contains no valid IP addresses"
    )
FOXPRO_ALLOWED_IPS = allowed_ips_list

# FoxPro signature mode - optional, defaults to legacy_v2
FOXPRO_SIGNATURE_MODE = os.environ.get(
    "FOXPRO_SIGNATURE_MODE", "legacy_v2"
).strip()
if FOXPRO_SIGNATURE_MODE == "":
    raise ImproperlyConfigured(
        "FOXPRO_SIGNATURE_MODE cannot be blank"
    )

# FoxPro launch max age in seconds - strict integer, must be > 0
max_age_str = os.environ.get("FOXPRO_LAUNCH_MAX_AGE_SECONDS")
if max_age_str is not None:
    max_age_str = max_age_str.strip()
    if max_age_str == "":
        raise ImproperlyConfigured(
            "FOXPRO_LAUNCH_MAX_AGE_SECONDS cannot be blank"
        )
    try:
        FOXPRO_LAUNCH_MAX_AGE_SECONDS = int(max_age_str)
    except ValueError:
        raise ImproperlyConfigured(
            "FOXPRO_LAUNCH_MAX_AGE_SECONDS must be a valid integer"
        )
else:
    FOXPRO_LAUNCH_MAX_AGE_SECONDS = 15

if FOXPRO_LAUNCH_MAX_AGE_SECONDS <= 0:
    raise ImproperlyConfigured(
        "FOXPRO_LAUNCH_MAX_AGE_SECONDS must be greater than 0"
    )

# FoxPro launch timezone - defaults to America/Los_Angeles
FOXPRO_LAUNCH_TIMEZONE = os.environ.get(
    "FOXPRO_LAUNCH_TIMEZONE", "America/Los_Angeles"
).strip()
if FOXPRO_LAUNCH_TIMEZONE == "":
    raise ImproperlyConfigured(
        "FOXPRO_LAUNCH_TIMEZONE cannot be blank"
    )

# FoxPro trust X-Forwarded-For - strict boolean parsing
trust_xff_raw = os.environ.get("FOXPRO_TRUST_X_FORWARDED_FOR")
if trust_xff_raw is not None:
    trust_xff_raw = trust_xff_raw.strip().lower()
    if trust_xff_raw == "":
        raise ImproperlyConfigured(
            "FOXPRO_TRUST_X_FORWARDED_FOR cannot be blank"
        )
    if trust_xff_raw in ("true", "1"):
        FOXPRO_TRUST_X_FORWARDED_FOR = True
    elif trust_xff_raw in ("false", "0"):
        FOXPRO_TRUST_X_FORWARDED_FOR = False
    else:
        raise ImproperlyConfigured(
            "FOXPRO_TRUST_X_FORWARDED_FOR must be true/false or 1/0"
        )
else:
    FOXPRO_TRUST_X_FORWARDED_FOR = False
