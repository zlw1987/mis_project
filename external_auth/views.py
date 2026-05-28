"""
FoxPro External Authentication Views

Implements the FoxPro v2 signed launch URL validation.
"""

import logging
import secrets
from datetime import datetime, timezone

from django.conf import settings
from django.contrib.auth import login, get_user_model
from django.http import HttpResponseForbidden, HttpResponseBadRequest
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View
from django.template.loader import render_to_string

from .models import FoxproLaunchAttempt, FoxproLaunchNonce
from .signature import (
    foxpro_norm, foxpro_canonical_v2, foxpro_sign_v2,
    validate_timestamp, parse_timestamp, hash_nonce, is_ip_allowed
)

logger = logging.getLogger(__name__)
User = get_user_model()

# User-facing error message (generic to avoid information disclosure)
GENERIC_ERROR_MESSAGE = 'Unable to launch. Please contact IT support.'


def get_client_ip(request):
    """Extract client IP from request, considering X-Forwarded-For header based on setting."""
    trust_x_forwarded_for = getattr(settings, 'FOXPRO_TRUST_X_FORWARDED_FOR', False)
    if trust_x_forwarded_for:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            # Take the first IP in the chain (original client)
            return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def render_error_response(request, error_message=GENERIC_ERROR_MESSAGE):
    """Render a generic error response."""
    return HttpResponseBadRequest(error_message)


class FoxProLaunchView(View):
    """
    Handle FoxPro v2 signed launch URL validation.
    
    Validation order:
    1. Check method GET only
    2. Check source IP if FOXPRO_ALLOWED_IPS configured
    3. Validate required params: v, n, ln, dp, t, d, nonce, return, sig (o optional)
    4. Require v == "2"
    5. Validate timestamp format YYYYMMDDHHMMSS
    6. Validate timestamp max age
    7. Build canonical string from decoded request.GET values
    8. Compute v2 signature with FOXPRO_V2_SECRET
    9. Compare expected signature and received sig using secrets.compare_digest
    10. If signature mismatch: create failed FoxproLaunchAttempt, do NOT reserve nonce
    11. If signature valid: atomically reserve nonce_hash in FoxproLaunchNonce
    12. If nonce reused: create failed FoxproLaunchAttempt with NONCE_REUSED
    13. Validate return named route allowlist (default to project_requests:dashboard)
    14. Map user (employee_id first, fallback username)
    15. Validate active Department
    16. Validate active UserDepartment
    17. Compare FoxPro o to UserDepartment.access_level for audit only
    18. login(request, user)
    19. Create success FoxproLaunchAttempt linked to nonce reservation
    20. Redirect via reverse(return_name)
    """
    
    def get(self, request):
        """Handle GET request to /auth/foxpro-launch/"""
        
        # Step 1: Check method GET only
        if request.method != 'GET':
            return render_error_response(request)
        
        params = request.GET
        source_ip = get_client_ip(request)
        
        # Step 0: Check signature mode
        signature_mode = getattr(settings, 'FOXPRO_SIGNATURE_MODE', None)
        if signature_mode != 'legacy_v2':
            logger.warning(f"FoxPro launch blocked - unsupported signature mode: {signature_mode}")
            return render_error_response(request)
        
        # Initialize tracking variables
        short_name = foxpro_norm(params.get('n'))
        long_name = foxpro_norm(params.get('ln'))
        dept_code = foxpro_norm(params.get('dp'))
        title = foxpro_norm(params.get('t'))
        legacy_access_level = foxpro_norm(params.get('o'))
        timestamp_str = foxpro_norm(params.get('d'))
        nonce = foxpro_norm(params.get('nonce'))
        return_route = foxpro_norm(params.get('return'))
        sig = foxpro_norm(params.get('sig'))
        version = foxpro_norm(params.get('v'))
        
        # Helper to create failed attempt record
        def create_failed_attempt(failure_reason, signature_valid=False, timestamp_valid=False,
                                   nonce_reserved=False, nonce_reservation=None):
            attempt = FoxproLaunchAttempt.objects.create(
                short_name=short_name,
                long_name=long_name,
                dept_code=dept_code,
                title=title,
                legacy_access_level=legacy_access_level,
                return_path=return_route,
                nonce_hash=hash_nonce(nonce) if nonce else '',
                source_ip=source_ip,
                signature_valid=signature_valid,
                timestamp_valid=timestamp_valid,
                success=False,
                failure_reason=failure_reason,
                nonce_reservation=nonce_reservation if nonce_reserved else None,
                raw_params={
                    'n': short_name,
                    'ln': long_name,
                    'dp': dept_code,
                    't': title,
                    'o': legacy_access_level,
                    'd': timestamp_str,
                    'nonce_hash': hash_nonce(nonce) if nonce else '',
                    'return': return_route,
                },
            )
            return attempt
        
        # Step 2: Check source IP if FOXPRO_ALLOWED_IPS configured
        allowed_ips = getattr(settings, 'FOXPRO_ALLOWED_IPS', [])
        if allowed_ips and not is_ip_allowed(source_ip, allowed_ips):
            logger.warning(f"FoxPro launch blocked - IP not in allowlist: {source_ip}")
            create_failed_attempt(FoxproLaunchAttempt.FailureReason.IP_BLOCKED)
            return render_error_response(request)
        
        # Step 3: Validate required params
        required_params = ['v', 'n', 'ln', 'dp', 't', 'd', 'nonce', 'return', 'sig']
        for param in required_params:
            if not params.get(param):
                logger.warning(f"FoxPro launch failed - missing param: {param}")
                create_failed_attempt(FoxproLaunchAttempt.FailureReason.MISSING_PARAMS)
                return render_error_response(request)
        
        # Step 4: Require v == "2"
        if version != '2':
            logger.warning(f"FoxPro launch failed - invalid version: {version}")
            create_failed_attempt(FoxproLaunchAttempt.FailureReason.INVALID_VERSION)
            return render_error_response(request)
        
        # Step 5: Validate timestamp format YYYYMMDDHHMMSS
        if not validate_timestamp(timestamp_str):
            logger.warning(f"FoxPro launch failed - invalid timestamp format: {timestamp_str}")
            create_failed_attempt(FoxproLaunchAttempt.FailureReason.INVALID_TIMESTAMP_FORMAT)
            return render_error_response(request)
        
        # Step 6: Validate timestamp max age
        timestamp = parse_timestamp(timestamp_str)
        if timestamp:
            # Parse FoxPro timestamp in the configured timezone (LA)
            import pytz
            launch_tz = pytz.timezone(getattr(settings, 'FOXPRO_LAUNCH_TIMEZONE', 'America/Los_Angeles'))
            timestamp_aware = launch_tz.localize(timestamp)  # Make it aware in LA timezone
            # Convert to UTC for comparison with current UTC time
            timestamp_utc = timestamp_aware.astimezone(timezone.utc)
            now_utc = datetime.now(timezone.utc)
            max_age = getattr(settings, 'FOXPRO_LAUNCH_MAX_AGE_SECONDS', 15)
            age = (now_utc - timestamp_utc).total_seconds()
            
            if abs(age) > max_age:
                logger.warning(f"FoxPro launch failed - timestamp expired: {timestamp_str} (age={age}s)")
                create_failed_attempt(FoxproLaunchAttempt.FailureReason.TIMESTAMP_EXPIRED,
                                     timestamp_valid=True)
                return render_error_response(request)
        
        # Step 7 & 8: Build canonical string and compute v2 signature
        try:
            canonical = foxpro_canonical_v2(params)
            secret = getattr(settings, 'FOXPRO_V2_SECRET', '')
            expected_sig = foxpro_sign_v2(canonical, secret)
        except Exception as e:
            logger.error(f"FoxPro signature computation failed: {e}")
            create_failed_attempt(FoxproLaunchAttempt.FailureReason.UNKNOWN_ERROR,
                                 timestamp_valid=True)
            return render_error_response(request)
        
        # Step 9: Compare signatures using secrets.compare_digest (constant-time)
        if not secrets.compare_digest(expected_sig, sig):
            logger.warning(f"FoxPro launch failed - invalid signature")
            # Note: Do NOT reserve nonce for invalid signature
            create_failed_attempt(FoxproLaunchAttempt.FailureReason.INVALID_SIGNATURE,
                                 timestamp_valid=True)
            return render_error_response(request)
        
        # Signature is valid
        nonce_hash = hash_nonce(nonce)
        
        # Step 10 & 11: Atomically reserve nonce
        nonce_reservation = None
        from django.db import transaction
        try:
            with transaction.atomic():
                nonce_reservation = FoxproLaunchNonce.objects.create(
                    nonce_hash=nonce_hash,
                    source_ip=source_ip,
                )
        except Exception:
            # Nonce already exists (unique constraint violation)
            logger.warning(f"FoxPro launch failed - nonce reused: {nonce_hash[:12]}...")
            create_failed_attempt(FoxproLaunchAttempt.FailureReason.NONCE_REUSED,
                                 signature_valid=True, timestamp_valid=True)
            return render_error_response(request)
        
        # Step 12: If we get here, nonce is reserved (signature was valid)
        
        # Step 13: Validate return named route allowlist
        allowed_returns = getattr(settings, 'FOXPRO_ALLOWED_RETURN_PATHS',
                                  ['project_requests:dashboard'])
        if return_route not in allowed_returns:
            logger.warning(f"FoxPro launch - return route not allowed, using default: {return_route}")
            return_route = 'project_requests:dashboard'
        
        # Step 14: Map user (employee_id first, then username)
        normalized_n = foxpro_norm(params.get('n')).lower()
        
        # Try employee_id first
        user = User.objects.filter(
            employee_id__iexact=normalized_n,
            is_active=True
        ).first()
        
        # Fallback to username
        if not user:
            user = User.objects.filter(
                username__iexact=normalized_n,
                is_active=True
            ).first()
        
        if not user:
            logger.warning(f"FoxPro launch failed - user not found: {normalized_n}")
            create_failed_attempt(FoxproLaunchAttempt.FailureReason.USER_NOT_FOUND,
                                 signature_valid=True, timestamp_valid=True,
                                 nonce_reserved=True, nonce_reservation=nonce_reservation)
            return render_error_response(request)
        
        # Step 15: Validate active Department
        from accounts.models import Department
        department = Department.objects.filter(
            dept_code__iexact=dept_code,
            is_active=True
        ).first()
        
        if not department:
            logger.warning(f"FoxPro launch failed - department not found: {dept_code}")
            create_failed_attempt(FoxproLaunchAttempt.FailureReason.DEPT_NOT_FOUND,
                                 signature_valid=True, timestamp_valid=True,
                                 nonce_reserved=True, nonce_reservation=nonce_reservation)
            return render_error_response(request)
        
        # Step 16: Validate active UserDepartment
        from accounts.models import UserDepartment
        user_dept = UserDepartment.objects.filter(
            user=user,
            department=department,
            is_active=True
        ).first()
        
        if not user_dept:
            logger.warning(f"FoxPro launch failed - department membership missing: {user.username} in {dept_code}")
            create_failed_attempt(FoxproLaunchAttempt.FailureReason.DEPT_MEMBERSHIP_MISSING,
                                 signature_valid=True, timestamp_valid=True,
                                 nonce_reserved=True, nonce_reservation=nonce_reservation)
            return render_error_response(request)
        
        # Step 17: Compare FoxPro o to UserDepartment.access_level for audit only
        # Do NOT change Django permissions based on FoxPro o
        if legacy_access_level and legacy_access_level != user_dept.access_level:
            logger.warning(
                f"FoxPro access level mismatch for {user.username}: "
                f"FoxPro o={legacy_access_level}, Django access_level={user_dept.access_level}"
            )
            # Log only - do not change permissions
        
        # Step 18: login(request, user)
        login(request, user)
        
        # Step 19: Create success FoxproLaunchAttempt
        attempt = FoxproLaunchAttempt.objects.create(
            short_name=short_name,
            long_name=long_name,
            dept_code=dept_code,
            title=title,
            legacy_access_level=legacy_access_level,
            return_path=return_route,
            nonce_hash=nonce_hash,
            source_ip=source_ip,
            signature_valid=True,
            timestamp_valid=True,
            user=user,
            success=True,
            failure_reason='',
            nonce_reservation=nonce_reservation,
            raw_params={
                'n': short_name,
                'ln': long_name,
                'dp': dept_code,
                't': title,
                'o': legacy_access_level,
                'd': timestamp_str,
                'nonce_hash': nonce_hash,
                'return': return_route,
            },
        )
        
        # Update nonce reservation with link to successful attempt
        nonce_reservation.launch_attempt = attempt
        nonce_reservation.save(update_fields=['launch_attempt'])
        
        # Step 20: Redirect via reverse(return_route)
        logger.info(f"FoxPro launch success: {user.username} -> {return_route}")
        return redirect(reverse(return_route))


# Function-based view for URL routing
foxpro_launch = FoxProLaunchView.as_view()