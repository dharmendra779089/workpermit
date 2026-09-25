from django.contrib import admin
from .models import User, Plant, Area, Equipment, Permit, PermitApproval, PermitAuditLog


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'role', 'badge_number', 'is_active', 'is_staff')
    list_filter = ('role', 'is_active', 'is_staff')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'badge_number')


@admin.register(Plant)
class PlantAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'location')
    search_fields = ('name', 'code', 'location')


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'plant', 'owner')
    list_filter = ('plant',)
    search_fields = ('name', 'code')


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = ('tag_number', 'name', 'area', 'criticality')
    list_filter = ('criticality', 'area__plant')
    search_fields = ('tag_number', 'name')


class PermitApprovalInline(admin.TabularInline):
    model = PermitApproval
    extra = 0
    readonly_fields = ('role_type', 'approver', 'status', 'acted_at', 'comment')


class PermitAuditLogInline(admin.TabularInline):
    model = PermitAuditLog
    extra = 0
    readonly_fields = ('timestamp', 'actor_name', 'actor_role', 'action', 'from_status', 'to_status', 'comment')
    can_delete = False


@admin.register(Permit)
class PermitAdmin(admin.ModelAdmin):
    list_display = ('permit_number', 'title', 'permit_type', 'status', 'requester', 'equipment', 'planned_start', 'planned_end')
    list_filter = ('status', 'permit_type', 'equipment__area__plant')
    search_fields = ('permit_number', 'title', 'contractor_name', 'equipment__tag_number')
    inlines = [PermitApprovalInline, PermitAuditLogInline]
    readonly_fields = ('permit_number', 'created_at', 'updated_at')


@admin.register(PermitApproval)
class PermitApprovalAdmin(admin.ModelAdmin):
    list_display = ('permit', 'role_type', 'approver', 'status', 'acted_at')
    list_filter = ('status', 'role_type')


@admin.register(PermitAuditLog)
class PermitAuditLogAdmin(admin.ModelAdmin):
    list_display = ('permit', 'timestamp', 'actor_name', 'actor_role', 'action', 'from_status', 'to_status')
    list_filter = ('action', 'from_status', 'to_status')
    search_fields = ('permit__permit_number', 'actor_name', 'comment')
