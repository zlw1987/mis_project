from django.contrib import admin
from .models import FoxproLaunchAttempt, FoxproLaunchNonce


@admin.register(FoxproLaunchAttempt)
class FoxproLaunchAttemptAdmin(admin.ModelAdmin):
    list_display = ['id', 'short_name', 'dept_code', 'success', 'signature_valid', 
                     'timestamp_valid', 'failure_reason', 'source_ip', 'created_at']
    list_filter = ['success', 'signature_valid', 'timestamp_valid', 'failure_reason', 
                   'short_name', 'dept_code', 'created_at']
    search_fields = ['short_name', 'dept_code', 'source_ip', 'nonce_hash']
    readonly_fields = ['short_name', 'long_name', 'dept_code', 'title', 'legacy_access_level',
                       'nonce_hash', 'source_ip', 'signature_valid', 'timestamp_valid',
                       'return_path', 'raw_params', 'created_at']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']


@admin.register(FoxproLaunchNonce)
class FoxproLaunchNonceAdmin(admin.ModelAdmin):
    list_display = ['id', 'nonce_hash', 'source_ip', 'first_seen_at', 'launch_attempt']
    list_filter = ['first_seen_at']
    search_fields = ['nonce_hash', 'source_ip']
    readonly_fields = ['nonce_hash', 'source_ip', 'first_seen_at', 'launch_attempt']
    date_hierarchy = 'first_seen_at'
    ordering = ['-first_seen_at']