from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Department, UserDepartment, AccessLevel


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin for custom User model."""
    list_display = ('username', 'display_name', 'employee_id', 'email', 'is_staff', 'is_active')
    list_filter = ('is_staff', 'is_active')
    search_fields = ('username', 'display_name', 'employee_id', 'email')
    ordering = ('username',)

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('display_name', 'employee_id', 'first_name', 'last_name', 'email')}),
        # Fix 6: Include is_superuser in Permissions fieldset
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('date_joined',)}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2', 'display_name', 'employee_id'),
        }),
    )


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    """Admin for Department model."""
    list_display = ('dept_code', 'dept_name', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('dept_code', 'dept_name')
    ordering = ('dept_code',)


@admin.register(UserDepartment)
class UserDepartmentAdmin(admin.ModelAdmin):
    """Admin for UserDepartment model."""
    list_display = ('user', 'department', 'access_level', 'is_primary', 'is_active', 'can_approve')
    list_filter = ('access_level', 'is_primary', 'is_active', 'can_approve')
    search_fields = ('user__username', 'user__display_name', 'department__dept_code', 'department__dept_name')
    raw_id_fields = ('user', 'department')
