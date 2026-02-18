from typing import Any

from .p4p_alarm_constants import (
    ALARM_LIMIT_FIELDS,
    ALARM_SEVERITY_FIELDS,
    ALARM_STATUSES,
    CONTROL_FIELDS,
    DEFAULT_ALARM_SEVERITIES,
    DISPLAY_FIELDS,
    SUPPORTED_PV_TYPES,
    VALUE_ALARM_FIELDS,
)


def _copy_optional_dict(
    pv_name: str, field_name: str, value: Any, allowed_keys: set[str]
) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(
            f'{pv_name}.{field_name} must be a dictionary, got {type(value)}'
        )
    unknown_keys = set(value.keys()) - allowed_keys
    if unknown_keys:
        raise ValueError(
            f'{pv_name}.{field_name} contains unknown keys: {sorted(unknown_keys)}'
        )
    return dict(value)


def normalise_variable_settings(pv_name: str, pv_cfg: dict[str, Any]) -> dict[str, Any]:
    pv_type = pv_cfg.get('type', 'scalar')
    if pv_type not in SUPPORTED_PV_TYPES:
        raise TypeError(f'Unknown PV type for {pv_name}: {pv_type}')

    compute_alarm = bool(pv_cfg.get('compute_alarm', False))

    display_cfg = _copy_optional_dict(pv_name, 'display', pv_cfg.get('display'), DISPLAY_FIELDS)
    control_cfg = _copy_optional_dict(pv_name, 'control', pv_cfg.get('control'), CONTROL_FIELDS)
    value_alarm_cfg = _copy_optional_dict(
        pv_name, 'valueAlarm', pv_cfg.get('valueAlarm'), VALUE_ALARM_FIELDS
    )

    if pv_type == 'image' and (display_cfg or control_cfg or value_alarm_cfg):
        raise ValueError(
            f'{pv_name}: image type does not support display/control/valueAlarm config'
        )

    if compute_alarm and pv_type != 'scalar':
        raise ValueError(f'{pv_name}: compute_alarm is only valid for scalar PVs')

    alarm_policy = None
    if compute_alarm:
        if value_alarm_cfg is None:
            raise ValueError(f'{pv_name}: compute_alarm=true requires valueAlarm config')
        if value_alarm_cfg.get('active') is not True:
            raise ValueError(
                f'{pv_name}: compute_alarm=true requires valueAlarm.active=true'
            )

        missing = [field for field in ALARM_LIMIT_FIELDS if field not in value_alarm_cfg]
        if missing:
            raise ValueError(
                f'{pv_name}: compute_alarm requires valueAlarm fields: {missing}'
            )

        limits = {}
        for field in ALARM_LIMIT_FIELDS:
            limits[field] = float(value_alarm_cfg[field])

        if not (
            limits['lowAlarmLimit']
            <= limits['lowWarningLimit']
            <= limits['highWarningLimit']
            <= limits['highAlarmLimit']
        ):
            raise ValueError(
                f'{pv_name}: valueAlarm limits must satisfy '
                'lowAlarmLimit <= lowWarningLimit <= highWarningLimit <= highAlarmLimit'
            )

        severities = {}
        for field in ALARM_SEVERITY_FIELDS:
            severity = int(value_alarm_cfg.get(field, DEFAULT_ALARM_SEVERITIES[field]))
            if severity < 0 or severity > 3:
                raise ValueError(
                    f'{pv_name}: {field} must be in range [0, 3], got {severity}'
                )
            severities[field] = severity

        alarm_policy = {**limits, **severities}

    return {
        'name': pv_name,
        'type': pv_type,
        'is_scalar': pv_type == 'scalar',
        'compute_alarm': compute_alarm,
        'display': display_cfg,
        'control': control_cfg,
        'valueAlarm': value_alarm_cfg,
        'alarm_policy': alarm_policy,
    }


def compute_alarm(value: Any, policy: dict[str, Any]) -> dict[str, Any]:
    value_num = float(value)

    if value_num <= policy['lowAlarmLimit']:
        severity = policy['lowAlarmSeverity']
        status = ALARM_STATUSES['lowAlarm']
        message = 'LOLO'
    elif value_num <= policy['lowWarningLimit']:
        severity = policy['lowWarningSeverity']
        status = ALARM_STATUSES['lowWarning']
        message = 'LOW'
    elif value_num >= policy['highAlarmLimit']:
        severity = policy['highAlarmSeverity']
        status = ALARM_STATUSES['highAlarm']
        message = 'HIHI'
    elif value_num >= policy['highWarningLimit']:
        severity = policy['highWarningSeverity']
        status = ALARM_STATUSES['highWarning']
        message = 'HIGH'
    else:
        severity = 0
        status = ALARM_STATUSES['normal']
        message = ''

    if severity == 0:
        return {'severity': 0, 'status': ALARM_STATUSES['normal'], 'message': ''}

    return {'severity': int(severity), 'status': int(status), 'message': message}
