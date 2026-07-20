from rest_framework import serializers
from .models import AttendanceLog, AttendanceRecord, Employee

class EmployeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = '__all__'

class AttendanceLogSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    
    class Meta:
        model = AttendanceLog
        fields = ['id', 'employee', 'employee_name', 'timestamp', 'scan_type']


class AttendanceRecordSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)

    class Meta:
        model = AttendanceRecord
        fields = '__all__'
