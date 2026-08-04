"""
Payroll approval workflow:

  Draft → HR Review → Finance Review → Approved → Locked → Paid

Locked/Paid payrolls cannot be modified unless unlocked by an authorized admin.
"""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from payroll.models import Payroll, PayrollApproval, PayrollPeriod
from payroll.services.audit import log_payroll_action
from payroll.services.payslip_generator import PayslipGenerator


WORKFLOW = [
    Payroll.Status.DRAFT,
    Payroll.Status.HR_REVIEW,
    Payroll.Status.FINANCE_REVIEW,
    Payroll.Status.APPROVED,
    Payroll.Status.LOCKED,
    Payroll.Status.PAID,
]

PERIOD_WORKFLOW = [
    PayrollPeriod.Status.DRAFT,
    PayrollPeriod.Status.HR_REVIEW,
    PayrollPeriod.Status.FINANCE_REVIEW,
    PayrollPeriod.Status.APPROVED,
    PayrollPeriod.Status.LOCKED,
    PayrollPeriod.Status.PAID,
]


class ApprovalService:
    def advance_payroll(self, payroll: Payroll, actor, comments='', request=None) -> Payroll:
        if payroll.status == Payroll.Status.PAID:
            raise ValidationError('Paid payroll cannot be advanced further.')
        if payroll.status == Payroll.Status.CANCELLED:
            raise ValidationError('Cancelled payroll cannot be advanced.')

        idx = WORKFLOW.index(payroll.status) if payroll.status in WORKFLOW else -1
        if idx < 0 or idx >= len(WORKFLOW) - 1:
            raise ValidationError(f'Cannot advance from status {payroll.status}.')

        next_status = WORKFLOW[idx + 1]
        return self._set_payroll_status(
            payroll, next_status, actor, PayrollApproval.Decision.APPROVE, comments, request
        )

    def submit_for_hr(self, payroll, actor, comments='', request=None):
        return self._require_and_set(
            payroll, Payroll.Status.DRAFT, Payroll.Status.HR_REVIEW,
            actor, PayrollApproval.Decision.SUBMIT, comments, request,
        )

    def hr_approve(self, payroll, actor, comments='', request=None):
        return self._require_and_set(
            payroll, Payroll.Status.HR_REVIEW, Payroll.Status.FINANCE_REVIEW,
            actor, PayrollApproval.Decision.APPROVE, comments, request,
        )

    def finance_approve(self, payroll, actor, comments='', request=None):
        payroll = self._require_and_set(
            payroll, Payroll.Status.FINANCE_REVIEW, Payroll.Status.APPROVED,
            actor, PayrollApproval.Decision.APPROVE, comments, request,
        )
        payroll.approved_at = timezone.now()
        payroll.save(update_fields=['approved_at', 'updated_at'])
        return payroll

    def lock_payroll(self, payroll, actor, comments='', request=None):
        if payroll.status not in {Payroll.Status.APPROVED, Payroll.Status.FINANCE_REVIEW}:
            raise ValidationError('Only approved payroll can be locked.')
        payroll = self._set_payroll_status(
            payroll, Payroll.Status.LOCKED, actor, PayrollApproval.Decision.LOCK, comments, request
        )
        PayslipGenerator().generate(payroll, actor=actor, request=request)
        return payroll

    def unlock_payroll(self, payroll, actor, comments='', request=None):
        if not self._can_unlock(actor):
            raise PermissionDenied('Only authorized administrators may unlock payroll.')
        if payroll.status not in {Payroll.Status.LOCKED, Payroll.Status.APPROVED}:
            raise ValidationError('Only locked/approved payroll can be unlocked.')
        return self._set_payroll_status(
            payroll, Payroll.Status.DRAFT, actor, PayrollApproval.Decision.UNLOCK, comments, request
        )

    def mark_paid(self, payroll, actor, comments='', request=None):
        if payroll.status not in {Payroll.Status.LOCKED, Payroll.Status.APPROVED}:
            raise ValidationError('Payroll must be approved/locked before marking paid.')
        payroll = self._set_payroll_status(
            payroll, Payroll.Status.PAID, actor, PayrollApproval.Decision.MARK_PAID, comments, request
        )
        payroll.paid_at = timezone.now()
        payroll.save(update_fields=['paid_at', 'updated_at'])
        return payroll

    def reject(self, payroll, actor, comments='', request=None):
        if payroll.status in {Payroll.Status.LOCKED, Payroll.Status.PAID}:
            raise ValidationError('Cannot reject locked or paid payroll. Unlock first.')
        return self._set_payroll_status(
            payroll, Payroll.Status.DRAFT, actor, PayrollApproval.Decision.REJECT, comments, request
        )

    def advance_period(self, period: PayrollPeriod, actor, comments='', request=None) -> PayrollPeriod:
        mapping = {
            PayrollPeriod.Status.OPEN: PayrollPeriod.Status.DRAFT,
            PayrollPeriod.Status.PROCESSING: PayrollPeriod.Status.DRAFT,
            PayrollPeriod.Status.DRAFT: PayrollPeriod.Status.HR_REVIEW,
            PayrollPeriod.Status.HR_REVIEW: PayrollPeriod.Status.FINANCE_REVIEW,
            PayrollPeriod.Status.FINANCE_REVIEW: PayrollPeriod.Status.APPROVED,
            PayrollPeriod.Status.APPROVED: PayrollPeriod.Status.LOCKED,
            PayrollPeriod.Status.LOCKED: PayrollPeriod.Status.PAID,
        }
        if period.status not in mapping:
            raise ValidationError(f'Cannot advance period from {period.status}.')
        next_status = mapping[period.status]
        return self._set_period_status(period, next_status, actor, comments, request)

    def unlock_period(self, period: PayrollPeriod, actor, comments='', request=None) -> PayrollPeriod:
        if not self._can_unlock(actor):
            raise PermissionDenied('Only authorized administrators may unlock payroll periods.')
        return self._set_period_status(
            period, PayrollPeriod.Status.DRAFT, actor, comments, request, decision='UNLOCK'
        )

    def _require_and_set(self, payroll, required, target, actor, decision, comments, request):
        if payroll.status != required:
            raise ValidationError(f'Payroll must be in {required} status (currently {payroll.status}).')
        return self._set_payroll_status(payroll, target, actor, decision, comments, request)

    @transaction.atomic
    def _set_payroll_status(self, payroll, status, actor, decision, comments, request):
        before = {'status': payroll.status}
        payroll.status = status
        payroll.save(update_fields=['status', 'updated_at'])
        PayrollApproval.objects.create(
            payroll=payroll,
            period=payroll.period,
            stage=status,
            decision=decision,
            actor=actor if actor and getattr(actor, 'is_authenticated', False) else None,
            comments=comments,
        )
        log_payroll_action(
            action='APPROVE' if decision == PayrollApproval.Decision.APPROVE else decision,
            summary=f'Payroll {payroll.pk} → {status} ({decision})',
            actor=actor,
            entity_type='Payroll',
            entity_id=payroll.pk,
            period=payroll.period,
            payroll=payroll,
            before_data=before,
            after_data={'status': status},
            request=request,
        )
        return payroll

    @transaction.atomic
    def _set_period_status(self, period, status, actor, comments, request, decision='APPROVE'):
        before = {'status': period.status}
        period.status = status
        update_fields = ['status', 'updated_at']
        if status == PayrollPeriod.Status.LOCKED:
            period.locked_at = timezone.now()
            period.locked_by = actor if actor and getattr(actor, 'is_authenticated', False) else None
            update_fields += ['locked_at', 'locked_by']
            # Lock all payrolls + generate payslips
            for payroll in period.payrolls.exclude(status=Payroll.Status.CANCELLED):
                if payroll.status != Payroll.Status.LOCKED:
                    payroll.status = Payroll.Status.LOCKED
                    payroll.save(update_fields=['status', 'updated_at'])
                    PayslipGenerator().generate(payroll, actor=actor, request=request)
        if status == PayrollPeriod.Status.PAID:
            period.paid_at = timezone.now()
            update_fields.append('paid_at')
            period.payrolls.exclude(status=Payroll.Status.CANCELLED).update(
                status=Payroll.Status.PAID, paid_at=timezone.now()
            )
        if status == PayrollPeriod.Status.APPROVED:
            period.payrolls.filter(
                status__in=[Payroll.Status.DRAFT, Payroll.Status.HR_REVIEW, Payroll.Status.FINANCE_REVIEW]
            ).update(status=Payroll.Status.APPROVED, approved_at=timezone.now())
        if decision == 'UNLOCK':
            period.locked_at = None
            period.locked_by = None
            update_fields += ['locked_at', 'locked_by']
            period.payrolls.filter(status=Payroll.Status.LOCKED).update(status=Payroll.Status.DRAFT)

        period.save(update_fields=update_fields)
        PayrollApproval.objects.create(
            period=period,
            stage=status,
            decision=decision,
            actor=actor if actor and getattr(actor, 'is_authenticated', False) else None,
            comments=comments,
        )
        log_payroll_action(
            action='UNLOCK' if decision == 'UNLOCK' else 'APPROVE',
            summary=f'Period {period} → {status}',
            actor=actor,
            entity_type='PayrollPeriod',
            entity_id=period.pk,
            period=period,
            before_data=before,
            after_data={'status': status},
            request=request,
        )
        return period

    @staticmethod
    def _can_unlock(actor) -> bool:
        if actor is None or not getattr(actor, 'is_authenticated', False):
            return False
        if actor.is_superuser or actor.is_staff:
            return True
        return actor.has_perm('payroll.unlock_payroll')
