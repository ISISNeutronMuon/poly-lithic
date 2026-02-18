SUPPORTED_PV_TYPES = {'scalar', 'waveform', 'array', 'image'}
DISPLAY_FIELDS = {'limitLow', 'limitHigh', 'description', 'format', 'units'}
CONTROL_FIELDS = {'limitLow', 'limitHigh', 'minStep'}
VALUE_ALARM_FIELDS = {
    'active',
    'lowAlarmLimit',
    'lowWarningLimit',
    'highWarningLimit',
    'highAlarmLimit',
    'lowAlarmSeverity',
    'lowWarningSeverity',
    'highWarningSeverity',
    'highAlarmSeverity',
    'hysteresis',
}

ALARM_STATUSES = {
    'normal': 0,  # NO_ALARM
    'highAlarm': 3,  # HIHI
    'highWarning': 4,  # HIGH
    'lowAlarm': 5,  # LOLO
    'lowWarning': 6,  # LOW
}

ALARM_SEVERITY_FIELDS = (
    'lowAlarmSeverity',
    'lowWarningSeverity',
    'highWarningSeverity',
    'highAlarmSeverity',
)

DEFAULT_ALARM_SEVERITIES = {
    'lowAlarmSeverity': 2,
    'lowWarningSeverity': 1,
    'highWarningSeverity': 1,
    'highAlarmSeverity': 2,
}

ALARM_LIMIT_FIELDS = (
    'lowAlarmLimit',
    'lowWarningLimit',
    'highWarningLimit',
    'highAlarmLimit',
)
