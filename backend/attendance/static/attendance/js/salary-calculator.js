var WEEKS_PER_MONTH = 4.33333;

function SalaryCalculator(formId) {
    this.form = document.getElementById(formId);
    if (!this.form) return;

    this.els = {};
    var self = this;

    this.q = function(sel) { return self.form.querySelector(sel); };
    this.qs = function(sel) { return self.form.querySelectorAll(sel); };

    this.els.paymentType = this.q('select[name="payment_type"], input[name="payment_type"]');
    this.els.monthlyInput = this.q('#id_monthly_salary, input[name="monthly_salary"]');
    this.els.hourlyInput = this.q('#id_hourly_rate, input[name="hourly_rate"]');
    this.els.dailyInput = this.q('#id_daily_rate, input[name="daily_rate"]');
    this.els.daysPerWeek = this.q('#id_days_per_week, input[name="days_per_week"]');
    this.els.hoursPerDay = this.q('#id_expected_daily_hours, input[name="expected_daily_hours"]');
    this.els.breakDuration = this.q('#id_break_duration, input[name="break_duration"]');
    this.els.currency = this.q('#id_currency, select[name="currency"]');
    this.els.taxRuleSet = this.q('#id_tax_rule_set, select[name="tax_rule_set"]');
    this.els.overtimeRuleSet = this.q('#id_overtime_rule_set, select[name="overtime_rule_set"]');
    this.els.pensionEligible = this.q('#id_pension_eligible, input[name="pension_eligible"]');
    this.els.taxCategory = this.q('#id_tax_category, select[name="tax_category"]');
    this.els.transportAllowance = this.q('#id_transport_allowance, input[name="transport_allowance"]');
    this.els.housingAllowance = this.q('#id_housing_allowance, input[name="housing_allowance"]');
    this.els.communicationAllowance = this.q('#id_communication_allowance, input[name="communication_allowance"]');
    this.els.mealAllowance = this.q('#id_meal_allowance, input[name="meal_allowance"]');
    this.els.otherAllowances = this.q('#id_other_allowances, input[name="other_allowances"]');

    this.els.displayHourlyRate = this.q('#displayHourlyRate');
    this.els.displayDailyRate = this.q('#displayDailyRate');
    this.els.displayWeeklySalary = this.q('#displayWeeklySalary');
    this.els.displayMonthlyHours = this.q('#displayMonthlyHours');
    this.els.displayMonthlyHours2 = this.q('#displayMonthlyHours2');
    this.els.displayWeeklyHours = this.q('#displayWeeklyHours');
    this.els.displayAnnualHours = this.q('#displayAnnualHours');
    this.els.displayEffectiveDaily = this.q('#displayEffectiveDaily');

    this.els.summaryMonthly = this.q('#summaryMonthly');
    this.els.summaryDaily = this.q('#summaryDaily');
    this.els.summaryHourly = this.q('#summaryHourly');
    this.els.summaryDays = this.q('#summaryDays');
    this.els.summaryHoursPerDay = this.q('#summaryHoursPerDay');
    this.els.summaryWeeklyHours = this.q('#summaryWeeklyHours');
    this.els.summaryMonthlyHours = this.q('#summaryMonthlyHours');
    this.els.summaryCostPerHour = this.q('#summaryCostPerHour');

    this.els.previewExpectedHours = this.q('#previewExpectedHours');
    this.els.previewWorkedHours = this.q('#previewWorkedHours');
    this.els.previewMissingHours = this.q('#previewMissingHours');
    this.els.previewAttendancePct = this.q('#previewAttendancePct');
    this.els.previewBasicSalary = this.q('#previewBasicSalary');
    this.els.previewAttendanceSalary = this.q('#previewAttendanceSalary');
    this.els.previewHourlyRate = this.q('#previewHourlyRate');
    this.els.previewDailyRate = this.q('#previewDailyRate');
    this.els.previewOvertime = this.q('#previewOvertime');
    this.els.previewOvertimePay = this.q('#previewOvertimePay');
    this.els.previewBonuses = this.q('#previewBonuses');
    this.els.previewAllowances = this.q('#previewAllowances');
    this.els.previewGross = this.q('#previewGross');
    this.els.previewIncomeTax = this.q('#previewIncomeTax');
    this.els.previewPension = this.q('#previewPension');
    this.els.previewGovernmentDed = this.q('#previewGovernmentDed');
    this.els.previewCompanyDed = this.q('#previewCompanyDed');
    this.els.previewNet = this.q('#previewNet');
    this.els.previewLoader = this.q('#previewLoader');
    this.els.previewError = this.q('#previewError');

    this.els.hourlyHidden = this.q('input[name="hourly_rate"]');
    this.els.dailyHidden = this.q('input[name="daily_rate"]');
    this.els.weeklyHoursHidden = this.q('input[name="expected_weekly_hours"]');
    this.els.monthlyHoursHidden = this.q('input[name="expected_monthly_hours"]');

    this.els.advancedToggle = this.q('#advancedToggle');
    this.els.advancedBody = this.q('#advancedBody');
    this.els.collapseIcon = this.q('#collapseIcon');

    this.els.sourceFields = this.qs('.source-field');
    this.els.sourceInputs = {};
    this.els.sourceInputs.MONTHLY = this.q('.source-field[data-payment-type="MONTHLY"] input');
    this.els.sourceInputs.HOURLY = this.q('.source-field[data-payment-type="HOURLY"] input');
    this.els.sourceInputs.DAILY = this.q('.source-field[data-payment-type="DAILY"] input');

    this._previewTimer = null;
}

SalaryCalculator.prototype.init = function() {
    if (!this.form) return;
    this.bindEvents();
    this.updateAll();
};

SalaryCalculator.prototype.bindEvents = function() {
    var self = this;

    var radios = this.qs('input[name="payment_type"]');
    if (radios.length) {
        radios.forEach(function(r) {
            r.addEventListener('change', function() { self.onPaymentTypeChange(this.value); });
        });
    }
    if (this.els.paymentType && this.els.paymentType.tagName === 'SELECT') {
        this.els.paymentType.addEventListener('change', function() { self.onPaymentTypeChange(this.value); });
    }

    var inputs = [
        this.els.monthlyInput, this.els.hourlyInput, this.els.dailyInput,
        this.els.daysPerWeek, this.els.hoursPerDay, this.els.breakDuration,
    ];
    inputs.forEach(function(inp) {
        if (inp) {
            inp.addEventListener('input', function() { self.updateAll(); });
            inp.addEventListener('change', function() { self.updateAll(); });
        }
    });

    if (this.els.previewWorkedHours) {
        this.els.previewWorkedHours.addEventListener('input', function() { self.onPreviewChange(); });
    }

    var previewTriggers = [
        this.els.transportAllowance, this.els.housingAllowance,
        this.els.communicationAllowance, this.els.mealAllowance, this.els.otherAllowances,
        this.els.taxRuleSet, this.els.overtimeRuleSet, this.els.pensionEligible, this.els.taxCategory,
        this.els.currency,
    ];
    previewTriggers.forEach(function(el) {
        if (el) {
            el.addEventListener('change', function() { self.onPreviewChange(); });
            if (el.tagName === 'INPUT') {
                el.addEventListener('input', function() { self.onPreviewChange(); });
            }
        }
    });

    if (this.els.advancedToggle) {
        this.els.advancedToggle.addEventListener('click', function() { self.toggleAdvanced(); });
        this.els.advancedToggle.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); self.toggleAdvanced(); }
        });
    }
};

SalaryCalculator.prototype.getPaymentType = function() {
    var radios = this.qs('input[name="payment_type"]:checked');
    if (radios.length) return radios[0].value;
    if (this.els.paymentType && this.els.paymentType.tagName === 'SELECT') return this.els.paymentType.value;
    return 'MONTHLY';
};

SalaryCalculator.prototype.getVal = function(el) {
    if (!el) return 0;
    var v = parseFloat(el.value);
    return isNaN(v) ? 0 : v;
};

SalaryCalculator.prototype.getSelVal = function(el) {
    if (!el) return '';
    return el.value || '';
};

SalaryCalculator.prototype.setVal = function(el, val) {
    if (!el) return;
    el.value = val;
};

SalaryCalculator.prototype.show = function(el) { if (el) el.style.display = ''; };
SalaryCalculator.prototype.hide = function(el) { if (el) el.style.display = 'none'; };

SalaryCalculator.prototype.formatMoney = function(val, currency) {
    var cur = currency || 'ETB';
    if (typeof val !== 'number') return '—';
    return cur + ' ' + val.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
};

SalaryCalculator.prototype.formatNum = function(val) {
    if (typeof val !== 'number') return '—';
    return val.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
};

SalaryCalculator.prototype.formatPct = function(val) {
    if (typeof val !== 'number') return '—';
    return val.toFixed(1) + '%';
};

SalaryCalculator.prototype.onPaymentTypeChange = function(type) {
    var self = this;
    this.els.sourceFields.forEach(function(f) { self.hide(f); });
    var active = this.q('.source-field[data-payment-type="' + type + '"]');
    if (active) this.show(active);

    var options = this.qs('.pt-option');
    options.forEach(function(o) {
        var inp = o.querySelector('input');
        if (inp && inp.value === type) { o.classList.add('active'); }
        else { o.classList.remove('active'); }
    });
    this.updateAll();
};

SalaryCalculator.prototype.computeHours = function(hoursPerDay, daysPerWeek, breakMinutes) {
    var breakHours = (breakMinutes || 0) / 60;
    var effectiveDaily = Math.max(0, hoursPerDay - breakHours);
    var weekly = effectiveDaily * daysPerWeek;
    var monthly = weekly * WEEKS_PER_MONTH;
    var annual = weekly * 52;
    return { effectiveDaily: effectiveDaily, weekly: weekly, monthly: monthly, annual: annual };
};

SalaryCalculator.prototype.computeAll = function() {
    var paymentType = this.getPaymentType();
    var monthlyVal = this.getVal(this.els.monthlyInput);
    var hourlyVal = this.getVal(this.els.hourlyInput);
    var dailyVal = this.getVal(this.els.dailyInput);
    var daysPerWeek = this.getVal(this.els.daysPerWeek) || 5;
    var hoursPerDay = this.getVal(this.els.hoursPerDay) || 8;
    var breakMin = this.getVal(this.els.breakDuration) || 0;
    var currency = this.els.currency ? (this.els.currency.value || 'ETB') : 'ETB';

    var h = this.computeHours(hoursPerDay, daysPerWeek, breakMin);
    var hourly = 0, daily = 0, weekly = 0, monthly = 0, monthlyHours = h.monthly;

    if (paymentType === 'MONTHLY') {
        monthly = monthlyVal;
        if (h.monthly > 0) hourly = monthly / h.monthly;
        if (daysPerWeek > 0) {
            daily = monthly / (daysPerWeek * WEEKS_PER_MONTH);
            weekly = daily * daysPerWeek;
        }
    } else if (paymentType === 'HOURLY') {
        hourly = hourlyVal;
        daily = hourly * h.effectiveDaily;
        weekly = daily * daysPerWeek;
        monthly = weekly * WEEKS_PER_MONTH;
    } else if (paymentType === 'DAILY') {
        daily = dailyVal;
        hourly = h.effectiveDaily > 0 ? daily / h.effectiveDaily : 0;
        weekly = daily * daysPerWeek;
        monthly = weekly * WEEKS_PER_MONTH;
    }

    this.setVal(this.els.hourlyHidden, hourly.toFixed(2));
    this.setVal(this.els.dailyHidden, daily.toFixed(2));
    this.setVal(this.els.weeklyHoursHidden, h.weekly.toFixed(2));
    this.setVal(this.els.monthlyHoursHidden, h.monthly.toFixed(2));

    return {
        monthly: monthly, daily: daily, hourly: hourly, weekly: weekly,
        weeklyHours: h.weekly, monthlyHours: h.monthly, annualHours: h.annual,
        effectiveDaily: h.effectiveDaily, daysPerWeek: daysPerWeek, hoursPerDay: hoursPerDay,
        currency: currency, paymentType: paymentType,
    };
};

SalaryCalculator.prototype.updateAll = function() {
    var d = this.computeAll();
    this.updateComputedRates(d);
    this.updateSummary(d);
    this.onPreviewChange();
};

SalaryCalculator.prototype.updateComputedRates = function(d) {
    var c = d.currency;
    if (this.els.displayHourlyRate) this.els.displayHourlyRate.textContent = this.formatMoney(d.hourly, c);
    if (this.els.displayDailyRate) this.els.displayDailyRate.textContent = this.formatMoney(d.daily, c);
    if (this.els.displayWeeklySalary) this.els.displayWeeklySalary.textContent = this.formatMoney(d.weekly, c);
    if (this.els.displayMonthlyHours) this.els.displayMonthlyHours.textContent = this.formatNum(d.monthlyHours) + ' h';
    if (this.els.displayWeeklyHours) this.els.displayWeeklyHours.textContent = this.formatNum(d.weeklyHours) + ' h';
    if (this.els.displayMonthlyHours2) this.els.displayMonthlyHours2.textContent = this.formatNum(d.monthlyHours) + ' h';
    if (this.els.displayAnnualHours) this.els.displayAnnualHours.textContent = this.formatNum(d.annualHours) + ' h';
    if (this.els.displayEffectiveDaily) this.els.displayEffectiveDaily.textContent = this.formatNum(d.effectiveDaily) + ' h';
};

SalaryCalculator.prototype.updateSummary = function(d) {
    var c = d.currency;
    if (this.els.summaryMonthly) this.els.summaryMonthly.textContent = this.formatMoney(d.monthly, c);
    if (this.els.summaryDaily) this.els.summaryDaily.textContent = this.formatMoney(d.daily, c);
    if (this.els.summaryHourly) this.els.summaryHourly.textContent = this.formatMoney(d.hourly, c);
    if (this.els.summaryDays) this.els.summaryDays.textContent = this.formatNum(d.daysPerWeek);
    if (this.els.summaryHoursPerDay) this.els.summaryHoursPerDay.textContent = this.formatNum(d.effectiveDaily);
    if (this.els.summaryWeeklyHours) this.els.summaryWeeklyHours.textContent = this.formatNum(d.weeklyHours) + ' h';
    if (this.els.summaryMonthlyHours) this.els.summaryMonthlyHours.textContent = this.formatNum(d.monthlyHours) + ' h';
    if (this.els.summaryCostPerHour) {
        var cph = d.monthlyHours > 0 ? d.monthly / d.monthlyHours : 0;
        this.els.summaryCostPerHour.textContent = this.formatMoney(cph, c);
    }
};

SalaryCalculator.prototype.getPreviewUrl = function() {
    var base = this.form.getAttribute('data-preview-url') || '/payroll/preview/';
    return base;
};

SalaryCalculator.prototype.collectPreviewParams = function() {
    var d = this.computeAll();
    var worked = this.getVal(this.els.previewWorkedHours);
    var allowances = this.getVal(this.els.transportAllowance)
        + this.getVal(this.els.housingAllowance)
        + this.getVal(this.els.communicationAllowance)
        + this.getVal(this.els.mealAllowance)
        + this.getVal(this.els.otherAllowances);
    var defaultOtMult = '1.50';
    var taxExempt = this.getSelVal(this.els.taxCategory) === 'EXEMPT';

    var params = new URLSearchParams();
    params.set('basic_salary', d.monthly.toFixed(2));
    params.set('worked_hours', worked.toFixed(2));
    params.set('expected_hours', d.monthlyHours.toFixed(2));
    params.set('hourly_rate', d.hourly.toFixed(4));
    params.set('daily_rate', d.daily.toFixed(2));
    params.set('overtime_hours', '0');
    params.set('overtime_multiplier', defaultOtMult);
    params.set('total_bonuses', '0');
    params.set('total_allowances', allowances.toFixed(2));
    params.set('total_company_deductions', '0');
    params.set('attendance_deductions', '0');
    params.set('currency', this.getSelVal(this.els.currency) || 'ETB');
    params.set('pension_eligible', this.els.pensionEligible ? (this.els.pensionEligible.checked ? 'true' : 'false') : 'true');
    params.set('tax_exempt', taxExempt ? 'true' : 'false');

    var taxId = this.getSelVal(this.els.taxRuleSet);
    if (taxId) params.set('tax_rule_set_id', taxId);

    var otId = this.getSelVal(this.els.overtimeRuleSet);
    if (otId) params.set('overtime_rule_set_id', otId);

    return params;
};

SalaryCalculator.prototype.onPreviewChange = function() {
    var self = this;
    if (this._previewTimer) clearTimeout(this._previewTimer);
    this._previewTimer = setTimeout(function() { self.fetchPreview(); }, 300);
};

SalaryCalculator.prototype.fetchPreview = function() {
    if (this.els.previewLoader) this.els.previewLoader.style.display = 'inline-block';
    if (this.els.previewError) this.els.previewError.style.display = 'none';

    var params = this.collectPreviewParams();
    var url = this.getPreviewUrl() + '?' + params.toString();

    var self = this;
    var xhr = new XMLHttpRequest();
    xhr.open('GET', url, true);
    xhr.onload = function() {
        if (self.els.previewLoader) self.els.previewLoader.style.display = 'none';
        if (xhr.status === 200) {
            try {
                var resp = JSON.parse(xhr.responseText);
                if (resp.success) {
                    self.renderPreview(resp.data);
                    return;
                }
            } catch(e) {}
        }
        if (self.els.previewError) {
            self.els.previewError.style.display = 'block';
            self.els.previewError.textContent = 'Preview unavailable';
        }
    };
    xhr.onerror = function() {
        if (self.els.previewLoader) self.els.previewLoader.style.display = 'none';
        if (self.els.previewError) {
            self.els.previewError.style.display = 'block';
            self.els.previewError.textContent = 'Network error';
        }
    };
    xhr.send();
};

SalaryCalculator.prototype.renderPreview = function(data) {
    var c = data.currency || 'ETB';

    function setText(el, val) {
        if (!el) return;
        el.textContent = val;
    }

    setText(this.els.previewExpectedHours, data.expected_hours + ' h');
    setText(this.els.previewMissingHours, data.missing_hours + ' h');
    setText(this.els.previewAttendancePct, this.formatPct(parseFloat(data.attendance_percent)));
    setText(this.els.previewBasicSalary, this.formatMoney(parseFloat(data.basic_salary), c));
    setText(this.els.previewAttendanceSalary, this.formatMoney(parseFloat(data.attendance_salary), c));
    setText(this.els.previewHourlyRate, this.formatMoney(parseFloat(data.hourly_rate), c));
    setText(this.els.previewDailyRate, this.formatMoney(parseFloat(data.daily_rate), c));
    setText(this.els.previewOvertime, data.overtime_hours + ' h');
    setText(this.els.previewOvertimePay, this.formatMoney(parseFloat(data.overtime_amount), c));
    setText(this.els.previewBonuses, this.formatMoney(parseFloat(data.total_bonuses), c));
    setText(this.els.previewAllowances, this.formatMoney(parseFloat(data.total_allowances), c));
    setText(this.els.previewGross, this.formatMoney(parseFloat(data.gross_salary), c));
    setText(this.els.previewIncomeTax, this.formatMoney(parseFloat(data.income_tax), c));
    setText(this.els.previewPension, this.formatMoney(parseFloat(data.pension_employee), c));
    setText(this.els.previewGovernmentDed, this.formatMoney(parseFloat(data.total_government_deductions), c));
    setText(this.els.previewCompanyDed, this.formatMoney(parseFloat(data.total_company_deductions) + parseFloat(data.attendance_deductions), c));
    setText(this.els.previewNet, this.formatMoney(parseFloat(data.net_salary), c));
};

SalaryCalculator.prototype.toggleAdvanced = function() {
    var body = this.els.advancedBody;
    var icon = this.els.collapseIcon;
    if (!body) return;
    var isOpen = body.style.display !== 'none';
    body.style.display = isOpen ? 'none' : '';
    if (icon) icon.innerHTML = isOpen ? '\u25B2' : '\u25BC';
};
