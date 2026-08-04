"""
Payroll audit helper — every sensitive payroll mutation should call log_payroll_action.
"""

from payroll.models import PayrollAudit


def get_client_ip(request) -> str | None:
    if request is None:
        return None
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def log_payroll_action(
    *,
    action: str,
    summary: str,
    actor=None,
    entity_type: str = '',
    entity_id: int | None = None,
    period=None,
    payroll=None,
    before_data: dict | None = None,
    after_data: dict | None = None,
    request=None,
) -> PayrollAudit:
    ip = None
    ua = ''
    if request is not None:
        ip = get_client_ip(request)
        ua = (request.META.get('HTTP_USER_AGENT') or '')[:255]
        if actor is None and getattr(request, 'user', None) and request.user.is_authenticated:
            actor = request.user

    return PayrollAudit.objects.create(
        actor=actor if actor and getattr(actor, 'is_authenticated', True) else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        period=period,
        payroll=payroll,
        summary=summary[:255],
        before_data=before_data or {},
        after_data=after_data or {},
        ip_address=ip,
        user_agent=ua,
    )
