"""
FoxPro External Authentication Models

FoxproLaunchAttempt: Records every launch attempt for audit purposes.
FoxproLaunchNonce: Stores nonce reservations for replay prevention.
"""

from django.conf import settings
from django.db import models
from django.contrib.auth import get_user_model


class FoxproLaunchAttempt(models.Model):
    """Records every FoxPro launch attempt for audit purposes.
    
    All fields that could contain sensitive data are stored for audit/logging.
    The success field indicates whether the launch completed successfully.
    """
    
    class FailureReason(models.TextChoices):
        IP_BLOCKED = 'IP_BLOCKED', 'IP Blocked'
        MISSING_PARAMS = 'MISSING_PARAMS', 'Missing Parameters'
        INVALID_VERSION = 'INVALID_VERSION', 'Invalid Version'
        INVALID_TIMESTAMP_FORMAT = 'INVALID_TIMESTAMP_FORMAT', 'Invalid Timestamp Format'
        TIMESTAMP_EXPIRED = 'TIMESTAMP_EXPIRED', 'Timestamp Expired'
        INVALID_SIGNATURE = 'INVALID_SIGNATURE', 'Invalid Signature'
        NONCE_REUSED = 'NONCE_REUSED', 'Nonce Reused'
        UNSUPPORTED_SIGNATURE_MODE = 'UNSUPPORTED_SIGNATURE_MODE', 'Unsupported Signature Mode'
        USER_NOT_FOUND = 'USER_NOT_FOUND', 'User Not Found'
        USER_INACTIVE = 'USER_INACTIVE', 'User Inactive'
        DEPT_NOT_FOUND = 'DEPT_NOT_FOUND', 'Department Not Found'
        DEPT_MEMBERSHIP_MISSING = 'DEPT_MEMBERSHIP_MISSING', 'Department Membership Missing'
        UNKNOWN_ERROR = 'UNKNOWN_ERROR', 'Unknown Error'
    
    # Identity hints from FoxPro URL params (NOT used for authorization)
    short_name = models.CharField(
        max_length=150,
        help_text='Employee short name from launch URL (identity hint only)'
    )
    long_name = models.CharField(
        max_length=255,
        blank=True, default='',
        help_text='Employee long name from launch URL (display/audit only)'
    )
    dept_code = models.CharField(
        max_length=20,
        blank=True, default='',
        help_text='Department code from launch URL'
    )
    title = models.CharField(
        max_length=150,
        blank=True, default='',
        help_text='Employee title from launch URL'
    )
    legacy_access_level = models.CharField(
        max_length=10,
        blank=True, default='',
        help_text='FoxPro o param - audit only, NOT used for Django authorization'
    )
    return_path = models.CharField(
        max_length=255,
        blank=True, default='',
        help_text='Requested return path (named route)'
    )
    
    # Security-related fields
    nonce_hash = models.CharField(
        max_length=64,
        help_text='SHA-256 hash of nonce from launch URL (for audit)'
    )
    source_ip = models.GenericIPAddressField(
        null=True, blank=True,
        help_text='Client IP address'
    )
    signature_valid = models.BooleanField(
        default=False,
        help_text='Signature passed validation'
    )
    timestamp_valid = models.BooleanField(
        default=False,
        help_text='Timestamp within max age'
    )
    
    # User mapping result
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='foxpro_launch_attempts',
        help_text='Mapped Django user (null if no match)'
    )
    
    # Launch result
    success = models.BooleanField(
        default=False,
        help_text='Launch succeeded (user found, session created)'
    )
    failure_reason = models.CharField(
        max_length=50,
        choices=FailureReason.choices,
        blank=True, default='',
        help_text='Short failure reason code'
    )
    
    # Nonce reservation link (null if nonce not reserved, e.g., invalid signature case)
    nonce_reservation = models.OneToOneField(
        'FoxproLaunchNonce',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='attempt',
        help_text='Link to nonce reservation record'
    )
    
    # Raw params snapshot (safe fields only - no secret stored)
    raw_params = models.JSONField(
        null=True, blank=True,
        help_text='Snapshot of all decoded params (secret not included)'
    )
    
    # Timestamp
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'external_auth_foxpro_launch_attempt'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['nonce_hash'], name='idx_attempt_nonce'),
            models.Index(fields=['short_name', 'dept_code', 'created_at'], 
                        name='idx_attempt_name_dept'),
            models.Index(fields=['source_ip', 'created_at'], 
                        name='idx_attempt_ip_time'),
        ]
    
    def __str__(self):
        status = 'SUCCESS' if self.success else f'FAILED({self.failure_reason})'
        return f"Launch {self.id}: {self.short_name} @ {self.dept_code} - {status}"


class FoxproLaunchNonce(models.Model):
    """Stores nonce reservations for replay prevention.
    
    Separate from FoxproLaunchAttempt to allow logging all replay attempts
    (both successful and failed). Only valid signatures reserve nonces.
    """
    
    nonce_hash = models.CharField(
        max_length=64,
        unique=True,
        help_text='SHA-256 hash of the nonce (unique constraint prevents replay)'
    )
    source_ip = models.GenericIPAddressField(
        null=True, blank=True,
        help_text='IP that first presented this nonce'
    )
    first_seen_at = models.DateTimeField(auto_now_add=True)
    launch_attempt = models.OneToOneField(
        FoxproLaunchAttempt,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='nonce_reserved',
        help_text='Link to successful launch attempt'
    )
    
    class Meta:
        db_table = 'external_auth_foxpro_launch_nonce'
        ordering = ['-first_seen_at']
        indexes = [
            models.Index(fields=['first_seen_at'], name='idx_nonce_time'),
        ]
    
    def __str__(self):
        return f"Nonce {self.nonce_hash[:12]}... from {self.source_ip}"