from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Company(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        SUSPENDED = 'SUSPENDED', 'Suspended'
        INACTIVE = 'INACTIVE', 'Inactive'

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    registration_number = models.CharField(max_length=100, blank=True)
    tax_id = models.CharField(max_length=100, blank=True)
    industry = models.CharField(max_length=100, blank=True)
    website = models.URLField(blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    logo = models.ImageField(upload_to='company/logos/', blank=True, null=True)
    default_timezone = models.CharField(max_length=64, default='UTC')
    default_currency = models.CharField(max_length=3, default='USD')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    max_employees = models.PositiveIntegerField(default=50000)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Company'
        verbose_name_plural = 'Companies'

    def __str__(self):
        return self.name

    @property
    def employee_count(self):
        return self.employees.filter(employment_status='ACTIVE').count() if hasattr(self, 'employees') else 0


class Branch(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='branches')
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default='US')
    postal_code = models.CharField(max_length=20, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    timezone = models.CharField(max_length=64, default='UTC')
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    geo_fence_radius_meters = models.PositiveIntegerField(default=100, help_text='Geofence radius for location-based attendance')
    is_headquarters = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['company', 'name']
        unique_together = [('company', 'code')]
        verbose_name = 'Branch'
        verbose_name_plural = 'Branches'

    def __str__(self):
        return f'{self.name} ({self.company.name})'


class Building(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='buildings')
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    total_floors = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['branch', 'name']
        unique_together = [('branch', 'code')]
        verbose_name = 'Building'
        verbose_name_plural = 'Buildings'

    def __str__(self):
        return f'{self.name} ({self.branch.name})'


class Floor(models.Model):
    building = models.ForeignKey(Building, on_delete=models.CASCADE, related_name='floors')
    name = models.CharField(max_length=100)
    level = models.IntegerField(default=0, help_text='Floor level number (can be negative for basement)')
    code = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['building', 'level']
        unique_together = [('building', 'code')]
        verbose_name = 'Floor'
        verbose_name_plural = 'Floors'

    def __str__(self):
        return f'{self.name} - {self.building.name}'


class Department(models.Model):
    """Extended department model linked to organization hierarchy."""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='departments')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='departments')
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=30, blank=True)
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='sub_departments')
    manager = models.ForeignKey(
        'attendance.Employee',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='managed_departments',
    )
    cost_center = models.ForeignKey('CostCenter', on_delete=models.SET_NULL, null=True, blank=True, related_name='departments')
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['company', 'name']
        unique_together = [('company', 'code')]
        verbose_name = 'Department'
        verbose_name_plural = 'Departments'

    def __str__(self):
        return self.name


class Team(models.Model):
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='teams')
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=30, blank=True)
    lead = models.ForeignKey(
        'attendance.Employee',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='led_teams',
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['department', 'name']
        unique_together = [('department', 'code')]
        verbose_name = 'Team'
        verbose_name_plural = 'Teams'

    def __str__(self):
        return f'{self.name} ({self.department.name})'


class CostCenter(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='cost_centers')
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=30)
    description = models.TextField(blank=True)
    budget = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['company', 'code']
        unique_together = [('company', 'code')]
        verbose_name = 'Cost Center'
        verbose_name_plural = 'Cost Centers'

    def __str__(self):
        return f'{self.code} - {self.name}'


class WorkLocation(models.Model):
    """Defines where employees can work from."""
    class LocationType(models.TextChoices):
        OFFICE = 'OFFICE', 'Office'
        REMOTE = 'REMOTE', 'Remote'
        HYBRID = 'HYBRID', 'Hybrid'
        FIELD = 'FIELD', 'Field/On-site Client'
        WFH = 'WFH', 'Work From Home'

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='work_locations')
    name = models.CharField(max_length=150)
    location_type = models.CharField(max_length=20, choices=LocationType.choices, default=LocationType.OFFICE)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='work_locations')
    address = models.TextField(blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    geo_fence_radius_meters = models.PositiveIntegerField(default=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['company', 'name']
        verbose_name = 'Work Location'
        verbose_name_plural = 'Work Locations'

    def __str__(self):
        return f'{self.name} ({self.get_location_type_display()})'
