from django.core.management.base import BaseCommand, CommandError

from payroll.models import PayrollPeriod
from payroll.services.payroll_engine import PayrollEngine, PayrollEngineError
from payroll.services.payslip_generator import PayslipGenerator


class Command(BaseCommand):
    help = 'Calculate payroll for a period (by id) and optionally generate payslips'

    def add_arguments(self, parser):
        parser.add_argument('period_id', type=int)
        parser.add_argument('--payslips', action='store_true', help='Also generate payslips')

    def handle(self, *args, **options):
        try:
            period = PayrollPeriod.objects.get(pk=options['period_id'])
        except PayrollPeriod.DoesNotExist as exc:
            raise CommandError(f'Period {options["period_id"]} not found') from exc

        try:
            results = PayrollEngine().calculate_period(period)
        except PayrollEngineError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f'Calculated {len(results)} payrolls for {period}'))

        if options['payslips']:
            slips = PayslipGenerator().generate_for_period(period)
            self.stdout.write(self.style.SUCCESS(f'Generated {len(slips)} payslips'))
