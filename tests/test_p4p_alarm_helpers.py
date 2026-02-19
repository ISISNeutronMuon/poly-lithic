# SPDX-FileCopyrightText: Copyright 2025 UK Research and Innovation, Science and Technology Facilities Council, ISIS
#
# SPDX-License-Identifier: BSD-3-Clause

import pytest

from poly_lithic.src.interfaces.p4p_alarm_helpers import normalise_variable_settings


def test_compute_alarm_defaults_valuealarm_active_true_when_missing():
    settings = normalise_variable_settings(
        'PV:TEST',
        {
            'name': 'PV:TEST',
            'proto': 'pva',
            'type': 'scalar',
            'compute_alarm': True,
            'valueAlarm': {
                'lowAlarmLimit': -5.0,
                'lowWarningLimit': -2.0,
                'highWarningLimit': 2.0,
                'highAlarmLimit': 5.0,
            },
        },
    )

    assert settings['compute_alarm'] is True
    assert settings['valueAlarm']['active'] is True
    assert settings['alarm_policy'] is not None


def test_compute_alarm_rejects_explicit_valuealarm_active_false():
    with pytest.raises(
        ValueError, match='compute_alarm=true does not allow valueAlarm.active=false'
    ):
        normalise_variable_settings(
            'PV:TEST',
            {
                'name': 'PV:TEST',
                'proto': 'pva',
                'type': 'scalar',
                'compute_alarm': True,
                'valueAlarm': {
                    'active': False,
                    'lowAlarmLimit': -5.0,
                    'lowWarningLimit': -2.0,
                    'highWarningLimit': 2.0,
                    'highAlarmLimit': 5.0,
                },
            },
        )
