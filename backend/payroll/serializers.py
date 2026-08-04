"""
DRF serializers for future API / mobile / ERP integrations.
Not wired to ViewSets yet — UI uses Django CBVs.
"""

from rest_framework import serializers

from .models import (
    Bonus,
    Deduction,
    Payroll,
    PayrollItem,
    PayrollPeriod,
    Payslip,
    SalaryProfile,
)


class SalaryProfileSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)

    class Meta:
        model = SalaryProfile
        fields = '__all__'


class PayrollPeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollPeriod
        fields = '__all__'


class PayrollItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollItem
        fields = '__all__'


class PayrollSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    items = PayrollItemSerializer(many=True, read_only=True)

    class Meta:
        model = Payroll
        fields = '__all__'


class PayslipSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payslip
        fields = '__all__'


class BonusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bonus
        fields = '__all__'


class DeductionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Deduction
        fields = '__all__'
