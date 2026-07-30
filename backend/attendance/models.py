from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone


class OfficeLocation(models.Model):
    name = models.CharField(max_length=120, unique=True)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default='US')
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    geo_fence_radius_meters = models.PositiveIntegerField(default=100)
    timezone = models.CharField(max_length=64, default='UTC')
    is_headquarters = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Office Location'
        verbose_name_plural = 'Office Locations'

    def __str__(self):
        return self.name


class AttendancePolicy(models.Model):
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    grace_period_minutes = models.PositiveIntegerField(default=5)
    late_threshold_minutes = models.PositiveIntegerField(default=15)
    absent_threshold_minutes = models.PositiveIntegerField(default=120)
    early_checkout_threshold_minutes = models.PositiveIntegerField(default=15)
    overtime_starts_after_minutes = models.PositiveIntegerField(default=30)
    minimum_overtime_minutes = models.PositiveIntegerField(default=30)
    max_overtime_minutes = models.PositiveIntegerField(default=480)
    auto_checkout_enabled = models.BooleanField(default=False)
    auto_checkout_time = models.TimeField(null=True, blank=True)
    duplicate_scan_prevention = models.BooleanField(default=True)
    duplicate_scan_cooldown_seconds = models.PositiveIntegerField(default=60)
    allow_remote_checkin = models.BooleanField(default=False)
    require_location = models.BooleanField(default=False)
    geo_fence_enforcement = models.BooleanField(default=False)
    break_deducted = models.BooleanField(default=True)
    lunch_deducted = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Attendance Policy'
        verbose_name_plural = 'Attendance Policies'

    def __str__(self):
        return self.name


class Employee(models.Model):
    class EmploymentStatus(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        INACTIVE = 'INACTIVE', 'Inactive'
        ON_LEAVE = 'ON_LEAVE', 'On Leave'
        SUSPENDED = 'SUSPENDED', 'Suspended'
        RESIGNED = 'RESIGNED', 'Resigned'
        TERMINATED = 'TERMINATED', 'Terminated'

    class EmploymentType(models.TextChoices):
        FULL_TIME = 'FULL_TIME', 'Full-time'
        PART_TIME = 'PART_TIME', 'Part-time'
        CONTRACT = 'CONTRACT', 'Contract'
        INTERN = 'INTERN', 'Intern'
        TEMPORARY = 'TEMPORARY', 'Temporary'
        CONSULTANT = 'CONSULTANT', 'Consultant'

    class Gender(models.TextChoices):
        MALE = 'MALE', 'Male'
        FEMALE = 'FEMALE', 'Female'
        OTHER = 'OTHER', 'Other'
        PREFER_NOT_TO_SAY = 'PNS', 'Prefer not to say'

    organization_id = models.CharField(max_length=50, unique=True)
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
    address = models.TextField(blank=True)
    emergency_contact_name = models.CharField(max_length=100, blank=True)
    emergency_contact_phone = models.CharField(max_length=30, blank=True)
    department = models.ForeignKey('organizations.Department', on_delete=models.SET_NULL, null=True, blank=True)
    team = models.ForeignKey('organizations.Team', on_delete=models.SET_NULL, null=True, blank=True, related_name='members')
    manager = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='direct_reports')
    job_title = models.CharField(max_length=100)
    employment_type = models.CharField(max_length=20, choices=EmploymentType.choices, default=EmploymentType.FULL_TIME, db_index=True)
    employment_status = models.CharField(max_length=20, choices=EmploymentStatus.choices, default=EmploymentStatus.ACTIVE, db_index=True)
    hire_date = models.DateField(null=True, blank=True)
    contract_start_date = models.DateField(null=True, blank=True)
    contract_end_date = models.DateField(null=True, blank=True)
    resignation_date = models.DateField(null=True, blank=True)
    termination_date = models.DateField(null=True, blank=True)
    office_location = models.ForeignKey(OfficeLocation, on_delete=models.SET_NULL, null=True, blank=True)
    work_location_name = models.CharField(max_length=150, blank=True)
    weekly_working_days = models.PositiveIntegerField(default=5, validators=[MinValueValidator(1), MaxValueValidator(7)])
    expected_weekly_hours = models.DecimalField(max_digits=5, decimal_places=2, default=40)
    expected_monthly_hours = models.DecimalField(max_digits=7, decimal_places=2, default=176)
    attendance_policy = models.ForeignKey(AttendancePolicy, on_delete=models.SET_NULL, null=True, blank=True, related_name='employees')
    fingerprint_id = models.IntegerField(unique=True, null=True, blank=True)
    face_profile = models.ImageField(upload_to='employees/faces/', blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['organization_id']),
            models.Index(fields=['department', 'employment_status']),
            models.Index(fields=['team', 'employment_status']),
            models.Index(fields=['manager', 'employment_status']),
            models.Index(fields=['employment_type', 'employment_status']),
        ]
        ordering = ['first_name', 'last_name']
        verbose_name = 'Employee'
        verbose_name_plural = 'Employees'

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.organization_id})"

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'.strip()

    @property
    def face_enrolled(self):
        return bool(self.fingerprint_id)

    @property
    def is_contract_ending_soon(self):
        if self.contract_end_date:
            return self.contract_end_date <= timezone.localdate() + timedelta(days=30)
        return False

    def get_absolute_url(self):
        return reverse('employee_detail', kwargs={'pk': self.pk})


class Shift(models.Model):
    name = models.CharField(max_length=120, unique=True)
    start_time = models.TimeField()
    end_time = models.TimeField()
    grace_period_minutes = models.PositiveIntegerField(default=5)
    late_threshold_minutes = models.PositiveIntegerField(default=15)
    absent_threshold_minutes = models.PositiveIntegerField(default=120)
    early_checkout_threshold_minutes = models.PositiveIntegerField(default=15)
    overtime_starts_after_minutes = models.PositiveIntegerField(default=30)
    minimum_overtime_minutes = models.PositiveIntegerField(default=30)
    is_overnight = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['start_time', 'name']
        verbose_name = 'Shift'
        verbose_name_plural = 'Shifts'

    def __str__(self):
        return self.name

    @property
    def planned_minutes(self):
        today = timezone.localdate()
        start = timezone.datetime.combine(today, self.start_time)
        end = timezone.datetime.combine(today, self.end_time)
        if self.is_overnight or end <= start:
            end += timedelta(days=1)
        return int((end - start).total_seconds() // 60)


class EmployeeSchedule(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='schedules')
    department = models.ForeignKey('organizations.Department', on_delete=models.SET_NULL, null=True, blank=True)
    shift = models.ForeignKey(Shift, on_delete=models.PROTECT, related_name='employee_schedules')
    effective_start = models.DateField(db_index=True)
    effective_end = models.DateField(null=True, blank=True, db_index=True)
    monday = models.BooleanField(default=True)
    tuesday = models.BooleanField(default=True)
    wednesday = models.BooleanField(default=True)
    thursday = models.BooleanField(default=True)
    friday = models.BooleanField(default=True)
    saturday = models.BooleanField(default=False)
    sunday = models.BooleanField(default=False)
    is_flexible = models.BooleanField(default=False)
    flexible_start_time = models.TimeField(null=True, blank=True)
    flexible_end_time = models.TimeField(null=True, blank=True)
    rotation_group = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    WEEKDAY_FIELDS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

    class Meta:
        ordering = ['-effective_start', 'employee__first_name']
        indexes = [
            models.Index(fields=['employee', 'effective_start', 'effective_end']),
            models.Index(fields=['department', 'effective_start']),
            models.Index(fields=['rotation_group']),
        ]
        verbose_name = 'Employee Schedule'
        verbose_name_plural = 'Employee Schedules'

    def __str__(self):
        return f'{self.employee.full_name} - {self.shift.name}'

    def clean(self):
        if self.effective_end and self.effective_end < self.effective_start:
            raise ValidationError('Effective end date cannot be earlier than start date.')
        if self.is_flexible and bool(self.flexible_start_time) != bool(self.flexible_end_time):
            raise ValidationError('Flexible schedules require both start and end times.')

    def works_on(self, date):
        return getattr(self, self.WEEKDAY_FIELDS[date.weekday()])


class ScheduleTemplate(models.Model):
    class TemplateType(models.TextChoices):
        WEEKLY = 'WEEKLY', 'Weekly'
        ROTATING = 'ROTATING', 'Rotating'
        NIGHT = 'NIGHT', 'Night Shift'
        SPLIT = 'SPLIT', 'Split Shift'
        FLEXIBLE = 'FLEXIBLE', 'Flexible'

    name = models.CharField(max_length=150)
    template_type = models.CharField(max_length=20, choices=TemplateType.choices, default=TemplateType.WEEKLY)
    shift = models.ForeignKey(Shift, on_delete=models.PROTECT, related_name='templates')
    monday = models.BooleanField(default=True)
    tuesday = models.BooleanField(default=True)
    wednesday = models.BooleanField(default=True)
    thursday = models.BooleanField(default=True)
    friday = models.BooleanField(default=True)
    saturday = models.BooleanField(default=False)
    sunday = models.BooleanField(default=False)
    is_flexible = models.BooleanField(default=False)
    flexible_start_time = models.TimeField(null=True, blank=True)
    flexible_end_time = models.TimeField(null=True, blank=True)
    rotation_pattern = models.JSONField(default=list, blank=True)
    split_shifts = models.JSONField(default=list, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Schedule Template'
        verbose_name_plural = 'Schedule Templates'

    def __str__(self):
        return f'{self.name} ({self.get_template_type_display()})'


class Holiday(models.Model):
    name = models.CharField(max_length=160)
    date = models.DateField(db_index=True)
    department = models.ForeignKey('organizations.Department', on_delete=models.CASCADE, null=True, blank=True)
    office_location = models.ForeignKey(OfficeLocation, on_delete=models.CASCADE, null=True, blank=True)
    is_paid = models.BooleanField(default=True)

    class Meta:
        ordering = ['date', 'name']
        unique_together = [('name', 'date', 'department', 'office_location')]
        verbose_name = 'Holiday'
        verbose_name_plural = 'Holidays'

    def __str__(self):
        return f'{self.name} ({self.date})'


class LeaveRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'
        CANCELLED = 'CANCELLED', 'Cancelled'

    class LeaveType(models.TextChoices):
        ANNUAL = 'ANNUAL', 'Annual'
        SICK = 'SICK', 'Sick'
        PERSONAL = 'PERSONAL', 'Personal'
        UNPAID = 'UNPAID', 'Unpaid'
        MATERNITY = 'MATERNITY', 'Maternity'
        PATERNITY = 'PATERNITY', 'Paternity'
        BEREAVEMENT = 'BEREAVEMENT', 'Bereavement'
        COMPOFF = 'COMPOFF', 'Comp-off'

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leave_requests')
    leave_type = models.CharField(max_length=20, choices=LeaveType.choices, default=LeaveType.ANNUAL)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    days = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0)])
    reason = models.TextField(blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_leave_requests')
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['employee', 'start_date', 'end_date']),
            models.Index(fields=['status', 'start_date']),
        ]
        verbose_name = 'Leave Request'
        verbose_name_plural = 'Leave Requests'

    def __str__(self):
        return f'{self.employee.full_name} {self.leave_type} ({self.start_date} - {self.end_date})'

    def clean(self):
        if self.end_date < self.start_date:
            raise ValidationError('Leave end date cannot be earlier than start date.')


class LeaveBalance(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leave_balances')
    leave_type = models.CharField(max_length=20, choices=LeaveRequest.LeaveType.choices)
    year = models.PositiveIntegerField()
    allocated_days = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    used_days = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    carried_over = models.DecimalField(max_digits=6, decimal_places=2, default=0)

    class Meta:
        unique_together = [('employee', 'leave_type', 'year')]
        ordering = ['-year', 'leave_type']
        verbose_name = 'Leave Balance'
        verbose_name_plural = 'Leave Balances'

    @property
    def remaining_days(self):
        return self.allocated_days + self.carried_over - self.used_days


class AttendanceLog(models.Model):
    class ScanSource(models.TextChoices):
        BIOMETRIC = 'BIOMETRIC', 'Biometric Device'
        MANUAL = 'MANUAL', 'Manual Entry'
        MOBILE = 'MOBILE', 'Mobile App'
        API = 'API', 'API'
        SELF_SERVICE = 'SELF_SERVICE', 'Self Service'

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    scan_type = models.CharField(max_length=10, choices=[('IN', 'Check-In'), ('OUT', 'Check-Out')], default='IN')
    device = models.ForeignKey('BiometricDevice', on_delete=models.SET_NULL, null=True, blank=True)
    source = models.CharField(max_length=20, choices=ScanSource.choices, default=ScanSource.BIOMETRIC, db_index=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_within_geofence = models.BooleanField(null=True, blank=True)

    class Meta:
        verbose_name = 'Attendance Log'
        verbose_name_plural = 'Attendance Logs'

    def __str__(self):
        return f"{self.employee.first_name} - {self.scan_type} at {self.timestamp.strftime('%H:%M')}"


class AttendanceRecord(models.Model):
    class Status(models.TextChoices):
        PRESENT = 'PRESENT', 'Present'
        LATE = 'LATE', 'Late'
        ABSENT = 'ABSENT', 'Absent'
        HOLIDAY = 'HOLIDAY', 'Holiday'
        WEEKEND = 'WEEKEND', 'Weekend'
        ON_LEAVE = 'ON_LEAVE', 'On Leave'
        EARLY_LEAVE = 'EARLY_LEAVE', 'Early Leave'
        OVERTIME = 'OVERTIME', 'Overtime'
        UNEXPECTED = 'UNEXPECTED', 'Unexpected Attendance'
        REMOTE = 'REMOTE', 'Remote Work'
        ON_SITE = 'ON_SITE', 'Site Visit'

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField(db_index=True)
    schedule = models.ForeignKey(EmployeeSchedule, on_delete=models.SET_NULL, null=True, blank=True)
    shift = models.ForeignKey(Shift, on_delete=models.SET_NULL, null=True, blank=True)
    first_check_in = models.DateTimeField(null=True, blank=True)
    last_check_out = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, db_index=True)
    minutes_late = models.PositiveIntegerField(default=0)
    minutes_early_leave = models.PositiveIntegerField(default=0)
    overtime_minutes = models.PositiveIntegerField(default=0)
    worked_minutes = models.PositiveIntegerField(default=0)
    break_minutes = models.PositiveIntegerField(default=0)
    lunch_minutes = models.PositiveIntegerField(default=0)
    remote_minutes = models.PositiveIntegerField(default=0)
    site_visit_minutes = models.PositiveIntegerField(default=0)
    total_attendance_minutes = models.PositiveIntegerField(default=0)
    auto_checkout = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    calculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('employee', 'date')]
        ordering = ['-date', 'employee__first_name']
        indexes = [
            models.Index(fields=['date', 'status']),
            models.Index(fields=['employee', 'date']),
        ]
        verbose_name = 'Attendance Record'
        verbose_name_plural = 'Attendance Records'

    def __str__(self):
        return f'{self.employee.full_name} - {self.date} - {self.get_status_display()}'


class AttendanceBreak(models.Model):
    class BreakType(models.TextChoices):
        BREAK = 'BREAK', 'Break'
        LUNCH = 'LUNCH', 'Lunch'
        PERSONAL = 'PERSONAL', 'Personal'

    attendance_record = models.ForeignKey(AttendanceRecord, on_delete=models.CASCADE, related_name='breaks')
    break_type = models.CharField(max_length=20, choices=BreakType.choices, default=BreakType.BREAK)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['start_time']
        verbose_name = 'Attendance Break'
        verbose_name_plural = 'Attendance Breaks'

    def __str__(self):
        return f'{self.get_break_type_display()} - {self.duration_minutes}min'

    def save(self, *args, **kwargs):
        if self.start_time and self.end_time:
            self.duration_minutes = max(0, int((self.end_time - self.start_time).total_seconds() // 60))
        super().save(*args, **kwargs)


class OvertimeRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='overtime_requests')
    date = models.DateField()
    requested_minutes = models.PositiveIntegerField()
    approved_minutes = models.PositiveIntegerField(default=0)
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_overtime_requests')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date']
        verbose_name = 'Overtime Request'
        verbose_name_plural = 'Overtime Requests'

    def __str__(self):
        return f'{self.employee.full_name} - {self.date} ({self.requested_minutes}min)'


class SiteVisit(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='site_visits')
    date = models.DateField()
    location_name = models.CharField(max_length=200)
    purpose = models.TextField(blank=True)
    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        verbose_name = 'Site Visit'
        verbose_name_plural = 'Site Visits'

    def __str__(self):
        return f'{self.employee.full_name} - {self.location_name} ({self.date})'


class RemoteWorkLog(models.Model):
    class Status(models.TextChoices):
        PLANNED = 'PLANNED', 'Planned'
        ACTIVE = 'ACTIVE', 'Active'
        COMPLETED = 'COMPLETED', 'Completed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='remote_work_logs')
    date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED, db_index=True)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    hours_worked = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    task_description = models.TextField(blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        verbose_name = 'Remote Work Log'
        verbose_name_plural = 'Remote Work Logs'

    def __str__(self):
        return f'{self.employee.full_name} - Remote ({self.date})'


class EnrollmentRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        DISPATCHED = 'DISPATCHED', 'Dispatched'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='enrollment_requests')
    fingerprint_id = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    device = models.ForeignKey('BiometricDevice', on_delete=models.SET_NULL, null=True, blank=True, related_name='enrollment_requests')
    progress_message = models.CharField(max_length=255, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['-requested_at']
        verbose_name = 'Enrollment Request'
        verbose_name_plural = 'Enrollment Requests'

    def __str__(self):
        return f"Enrollment {self.fingerprint_id} for {self.employee.organization_id} ({self.status})"


class BiometricDevice(models.Model):
    class Mode(models.TextChoices):
        ATTENDANCE = 'ATTENDANCE', 'Attendance Mode'
        ENROLLMENT = 'ENROLLMENT', 'Fingerprint Enrollment Mode'
        DELETION = 'DELETION', 'Fingerprint Deletion Mode'
        MAINTENANCE = 'MAINTENANCE', 'Maintenance Mode'
        OFFLINE = 'OFFLINE', 'Offline'

    class Status(models.TextChoices):
        ONLINE = 'ONLINE', 'Online'
        OFFLINE = 'OFFLINE', 'Offline'
        BUSY = 'BUSY', 'Busy'
        ERROR = 'ERROR', 'Error'

    class DeviceType(models.TextChoices):
        ENTRY_GATE = 'ENTRY_GATE', 'Entry Gate'
        EXIT_GATE = 'EXIT_GATE', 'Exit Gate'
        RECEPTION = 'RECEPTION', 'Reception'
        WAREHOUSE = 'WAREHOUSE', 'Warehouse'
        OFFICE = 'OFFICE', 'Office Entrance'
        FLOOR = 'FLOOR', 'Floor Access'
        LABORATORY = 'LABORATORY', 'Laboratory'
        SERVER_ROOM = 'SERVER_ROOM', 'Server Room'
        OTHER = 'OTHER', 'Other'

    device_id = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=120)
    device_type = models.CharField(max_length=20, choices=DeviceType.choices, default=DeviceType.OFFICE)
    serial_port = models.CharField(max_length=120, default='/dev/ttyUSB0')
    baudrate = models.PositiveIntegerField(default=9600)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    mac_address = models.CharField(max_length=17, blank=True)
    office_location = models.ForeignKey(OfficeLocation, on_delete=models.SET_NULL, null=True, blank=True, related_name='devices')
    building_name = models.CharField(max_length=150, blank=True)
    floor_number = models.IntegerField(null=True, blank=True)
    assigned_branch = models.CharField(max_length=150, blank=True)
    mode = models.CharField(max_length=24, choices=Mode.choices, default=Mode.ATTENDANCE)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OFFLINE)
    firmware_version = models.CharField(max_length=80, blank=True)
    template_count = models.PositiveIntegerField(default=0)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    health_check_interval = models.PositiveIntegerField(default=60)
    last_health_check = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Biometric Device'
        verbose_name_plural = 'Biometric Devices'

    def __str__(self):
        return f'{self.name} ({self.device_id})'

    @property
    def is_healthy(self):
        if not self.last_seen_at:
            return False
        return (timezone.now() - self.last_seen_at).total_seconds() < self.health_check_interval * 3


class DeviceCommand(models.Model):
    class Command(models.TextChoices):
        ENROLL = 'ENROLL', 'Enroll'
        DELETE = 'DELETE', 'Delete'
        VERIFY = 'VERIFY', 'Verify'
        DEVICE_STATUS = 'DEVICE_STATUS', 'Device Status'
        RESTART = 'RESTART', 'Restart'
        MAINTENANCE = 'MAINTENANCE', 'Maintenance'
        ATTENDANCE_MODE = 'ATTENDANCE_MODE', 'Attendance Mode'

    class Status(models.TextChoices):
        QUEUED = 'QUEUED', 'Queued'
        SENT = 'SENT', 'Sent'
        ACKNOWLEDGED = 'ACKNOWLEDGED', 'Acknowledged'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    device = models.ForeignKey(BiometricDevice, on_delete=models.CASCADE, related_name='commands')
    employee = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='device_commands')
    enrollment_request = models.ForeignKey(EnrollmentRequest, on_delete=models.SET_NULL, null=True, blank=True, related_name='device_commands')
    command = models.CharField(max_length=32, choices=Command.choices)
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED, db_index=True)
    raw_command = models.CharField(max_length=255, blank=True)
    response = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['device', 'status', 'created_at']),
            models.Index(fields=['employee', 'created_at']),
        ]
        verbose_name = 'Device Command'
        verbose_name_plural = 'Device Commands'

    def __str__(self):
        return f'{self.command} for {self.device.device_id} ({self.status})'


class DeviceEvent(models.Model):
    class EventType(models.TextChoices):
        ENROLL_PROGRESS = 'ENROLL_PROGRESS', 'Enrollment Progress'
        ENROLL_SUCCESS = 'ENROLL_SUCCESS', 'Enrollment Success'
        DELETE_SUCCESS = 'DELETE_SUCCESS', 'Deletion Success'
        ATTENDANCE_EVENT = 'ATTENDANCE_EVENT', 'Attendance Event'
        DEVICE_STATUS = 'DEVICE_STATUS', 'Device Status'
        COMMAND_ACK = 'COMMAND_ACK', 'Command Acknowledgement'
        ERROR = 'ERROR', 'Error'
        RAW = 'RAW', 'Raw Message'
        HEALTH_CHECK = 'HEALTH_CHECK', 'Health Check'

    device = models.ForeignKey(BiometricDevice, on_delete=models.CASCADE, related_name='events')
    employee = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='device_events')
    command = models.ForeignKey(DeviceCommand, on_delete=models.SET_NULL, null=True, blank=True, related_name='events')
    enrollment_request = models.ForeignKey(EnrollmentRequest, on_delete=models.SET_NULL, null=True, blank=True, related_name='events')
    event_type = models.CharField(max_length=32, choices=EventType.choices, db_index=True)
    status = models.CharField(max_length=40, blank=True)
    message = models.TextField(blank=True)
    fingerprint_id = models.PositiveIntegerField(null=True, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['device', 'created_at']),
            models.Index(fields=['event_type', 'created_at']),
        ]
        verbose_name = 'Device Event'
        verbose_name_plural = 'Device Events'

    def __str__(self):
        return f'{self.device.device_id} {self.event_type} {self.created_at:%Y-%m-%d %H:%M:%S}'


class AuditLog(models.Model):
    class ActionType(models.TextChoices):
        CREATE = 'CREATE', 'Create'
        UPDATE = 'UPDATE', 'Update'
        DELETE = 'DELETE', 'Delete'
        LOGIN = 'LOGIN', 'Login'
        LOGOUT = 'LOGOUT', 'Logout'
        APPROVE = 'APPROVE', 'Approve'
        REJECT = 'REJECT', 'Reject'
        EXPORT = 'EXPORT', 'Export'
        OVERRIDE = 'OVERRIDE', 'Override'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=20, choices=ActionType.choices, db_index=True)
    model_name = models.CharField(max_length=100, db_index=True)
    object_id = models.CharField(max_length=50, blank=True)
    object_repr = models.CharField(max_length=255, blank=True)
    field_changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'

    def __str__(self):
        return f'{self.user} - {self.action} - {self.model_name} ({self.timestamp})'


class Notification(models.Model):
    class Level(models.TextChoices):
        INFO = 'INFO', 'Info'
        WARNING = 'WARNING', 'Warning'
        CRITICAL = 'CRITICAL', 'Critical'

    title = models.CharField(max_length=160)
    message = models.TextField()
    level = models.CharField(max_length=20, choices=Level.choices, default=Level.INFO)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, null=True, blank=True, related_name='notifications')
    link = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'

    def __str__(self):
        return self.title


class SystemSetting(models.Model):
    key = models.CharField(max_length=120, unique=True)
    value = models.TextField(blank=True)
    description = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['key']
        verbose_name = 'System Setting'
        verbose_name_plural = 'System Settings'

    def __str__(self):
        return self.key
