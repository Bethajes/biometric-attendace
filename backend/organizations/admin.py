from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Branch,
    Building,
    Company,
    CostCenter,
    Department,
    Floor,
    Team,
    WorkLocation,
)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'industry', 'status', 'employee_count_display', 'is_active')
    list_filter = ('status', 'is_active', 'industry')
    search_fields = ('name', 'slug', 'registration_number')
    readonly_fields = ('created_at', 'updated_at')
    prepopulated_fields = {'slug': ('name',)}
    list_per_page = 25
    fieldsets = (
        ('Basic Info', {'fields': ('name', 'slug', 'industry', 'status', 'is_active')}),
        ('Registration', {'fields': ('registration_number', 'tax_id', 'website', 'email', 'phone')}),
        ('Location', {'fields': ('address',)}),
        ('Configuration', {'fields': ('default_timezone', 'default_currency', 'max_employees')}),
        ('Branding', {'fields': ('logo',), 'classes': ('collapse',)}),
        ('Metadata', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    def employee_count_display(self, obj):
        return obj.employee_count
    employee_count_display.short_description = 'Employees'


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'code', 'city', 'country', 'is_headquarters', 'is_active')
    list_filter = ('company', 'is_headquarters', 'is_active', 'country')
    search_fields = ('name', 'code', 'city')
    autocomplete_fields = ('company',)
    list_per_page = 25
    fieldsets = (
        ('Basic Info', {'fields': ('company', 'name', 'code', 'is_active', 'is_headquarters')}),
        ('Address', {'fields': ('address', 'city', 'state', 'country', 'postal_code')}),
        ('Contact', {'fields': ('phone', 'email')}),
        ('Configuration', {'fields': ('timezone', 'latitude', 'longitude', 'geo_fence_radius_meters')}),
    )


@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):
    list_display = ('name', 'branch', 'code', 'total_floors', 'is_active')
    list_filter = ('branch', 'is_active')
    search_fields = ('name', 'code')
    autocomplete_fields = ('branch',)


@admin.register(Floor)
class FloorAdmin(admin.ModelAdmin):
    list_display = ('name', 'building', 'level', 'code', 'is_active')
    list_filter = ('building', 'is_active')
    search_fields = ('name', 'code')
    autocomplete_fields = ('building',)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'company', 'branch', 'parent', 'manager', 'is_active')
    list_filter = ('company', 'branch', 'is_active')
    search_fields = ('name', 'code')
    autocomplete_fields = ('company', 'branch', 'parent', 'manager', 'cost_center')
    list_per_page = 25
    fieldsets = (
        ('Basic Info', {'fields': ('company', 'name', 'code', 'description', 'is_active')}),
        ('Hierarchy', {'fields': ('parent', 'manager', 'cost_center')}),
        ('Location', {'fields': ('branch',)}),
    )


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'department', 'lead', 'is_active')
    list_filter = ('department__company', 'department', 'is_active')
    search_fields = ('name', 'code')
    autocomplete_fields = ('department', 'lead')


@admin.register(CostCenter)
class CostCenterAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'company', 'budget', 'is_active')
    list_filter = ('company', 'is_active')
    search_fields = ('name', 'code')
    autocomplete_fields = ('company',)


@admin.register(WorkLocation)
class WorkLocationAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'location_type', 'branch', 'is_active')
    list_filter = ('company', 'location_type', 'is_active')
    search_fields = ('name',)
    autocomplete_fields = ('company', 'branch')
