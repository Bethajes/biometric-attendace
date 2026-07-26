from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, blank=True, unique=True, null=True)
    manager = models.ForeignKey(
        'Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_departments',
    )
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = 'Department'
        verbose_name_plural = 'Departments'

    def __str__(self):
        return self.name


class OfficeLocation(models.Model):
    name = models.CharField(max_length=120, unique=True)
    address = models.CharField(max_length=255, blank=True)
    timezone = models.CharField(max_length=64, default='UTC')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Office Location'
        verbose_name_plural = 'Office Locations'

    def __str__(self):
        return self.name


class Employee(models.Model):
    class EmploymentStatus(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        INACTIVE = 'INACTIVE', 'Inactive'
        ON_LEAVE = 'ON_LEAVE', 'On Leave'
        TERMINATED = 'TERMINATED', 'Terminated'

    organization_id = models.CharField(max_length=50, unique=True) 
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True)
    job_title = models.CharField(max_length=100) 
    fingerprint_id = models.IntegerField(unique=True, null=True, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    office_location = models.ForeignKey(OfficeLocation, on_delete=models.SET_NULL, null=True, blank=True)
    hire_date = models.DateField(null=True, blank=True)
    employment_status = models.CharField(
        max_length=20,
        choices=EmploymentStatus.choices,
        default=EmploymentStatus.ACTIVE,
        db_index=True,
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['organization_id']),
            models.Index(fields=['department', 'employment_status']),
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
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
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
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    WEEKDAY_FIELDS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

    class Meta:
        ordering = ['-effective_start', 'employee__first_name']
        indexes = [
            models.Index(fields=['employee', 'effective_start', 'effective_end']),
            models.Index(fields=['department', 'effective_start']),
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


class Holiday(models.Model):
    name = models.CharField(max_length=160)
    date = models.DateField(db_index=True)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, null=True, blank=True)
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

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leave_requests')
    leave_type = models.CharField(max_length=20, choices=LeaveType.choices, default=LeaveType.ANNUAL)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    days = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0)])
    reason = models.TextField(blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_leave_requests',
    )
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

    class Meta:
        unique_together = [('employee', 'leave_type', 'year')]
        ordering = ['-year', 'leave_type']
        verbose_name = 'Leave Balance'
        verbose_name_plural = 'Leave Balances'

    @property
    def remaining_days(self):
        return self.allocated_days - self.used_days


class AttendanceLog(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    SCAN_TYPES = [
        ('IN', 'Check-In'),
        ('OUT', 'Check-Out'),
    ]
    scan_type = models.CharField(max_length=10, choices=SCAN_TYPES, default='IN')

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

    device_id = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=120)
    serial_port = models.CharField(max_length=120, default='/dev/ttyUSB0')
    baudrate = models.PositiveIntegerField(default=9600)
    mode = models.CharField(max_length=24, choices=Mode.choices, default=Mode.ATTENDANCE)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OFFLINE)
    firmware_version = models.CharField(max_length=80, blank=True)
    template_count = models.PositiveIntegerField(default=0)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Biometric Device'
        verbose_name_plural = 'Biometric Devices'

    def __str__(self):
        return f'{self.name} ({self.device_id})'


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


class Notification(models.Model):
    class Level(models.TextChoices):
        INFO = 'INFO', 'Info'
        WARNING = 'WARNING', 'Warning'
        CRITICAL = 'CRITICAL', 'Critical'

    title = models.CharField(max_length=160)
    message = models.TextField()
    level = models.CharField(max_length=20, choices=Level.choices, default=Level.INFO)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, null=True, blank=True, related_name='notifications')
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
