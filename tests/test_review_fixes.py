# SPDX-FileCopyrightText: Copyright 2025 UK Research and Innovation, Science and Technology Facilities Council, ISIS
#
# SPDX-License-Identifier: BSD-3-Clause

"""Regression tests for the critical/high findings of the code review.

None of these need a network: p4p and k2eg clients are replaced by fakes.
"""

import argparse
import asyncio
import importlib.util
import logging
import os
from types import SimpleNamespace

import h5py
import numpy as np
import pydantic
import pytest
import yaml
from click.testing import CliRunner

from poly_lithic.src.config.config_object import ConfigObject
from poly_lithic.src.config.parser import ConfigParser
from poly_lithic.src.interfaces.BaseInterface import BaseInterface
from poly_lithic.src.interfaces.fastapi_interface import (
    JobInput,
    SimpleFastAPIInterfaceServer,
    VariableStruct,
)
from poly_lithic.src.utils.messaging import (
    InterfaceObserver,
    Message,
    MessageBroker,
    ModelObserver,
    Observer,
)


class MemoryInterface(BaseInterface):
    """In-memory interface; monitor() registers per-PV handlers."""

    supports_monitor = True

    def __init__(self, config=None):
        self.store = dict(config or {'A': 1.0, 'B': 2.0})
        self.handlers = {}
        self.written = {}

    def monitor(self, handler, pv_name=None, **kwargs):
        self.handlers[pv_name] = handler

    def get(self, name, **kwargs):
        return name, {'value': self.store[name]}

    def put(self, name, value, **kwargs):
        self.written[name] = value

    def put_many(self, data, **kwargs):
        self.written.update(data)

    def get_many(self, data, **kwargs):
        return {name: {'value': self.store[name]} for name in data}

    def get_inputs(self):
        return list(self.store)

    def get_outputs(self):
        return list(self.store)


def _fastapi(**variables):
    return SimpleFastAPIInterfaceServer({
        'start_server': False,
        'variables': variables
        or {
            'A': {'mode': 'in', 'type': 'scalar', 'default': 1.0},
            'B': {'mode': 'in', 'type': 'scalar', 'default': 2.0},
            'X': {'mode': 'out', 'type': 'scalar', 'default': 0.0},
        },
    })


def _submit(iface, job_id=None, **values):
    ji = JobInput(
        job_id=job_id,
        variables={k: VariableStruct(value=v) for k, v in values.items()},
    )
    return iface._enqueue_jobs([ji])[0]['job_id']


class SumModel:
    def evaluate(self, inputs):
        return {'X': inputs['A'] + inputs['B']}


def _drain(broker):
    while broker.queue:
        broker.parse_queue()


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------


class TestMessageUid:
    def test_uid_ignores_trace_id(self):
        def msg(tid):
            return Message(
                topic='t',
                source='s',
                value={'A': {'value': 1.0, 'metadata': {'trace': {'trace_id': tid}}}},
            )

        assert msg('one').uid == msg('two').uid

    def test_uid_includes_job_id(self):
        def msg(job):
            trace = {'trace_id': 'x', 'job_id': job}
            return Message(
                topic='t',
                source='s',
                value={'A': {'value': 1.0, 'metadata': {'trace': trace}}},
            )

        assert msg('j1').uid != msg('j2').uid

    def test_unchanged_inputs_do_not_rerun_pipeline(self):
        obs = InterfaceObserver(MemoryInterface(), 'in')
        tick = Message(topic='get_all', source='clock', value={'d': {'value': 1}})
        assert obs.update(tick) is not None
        assert obs.update(tick) is None  # same data, new trace ids
        obs.interface.store['A'] = 5.0
        assert obs.update(tick) is not None


class TestOneShot:
    def test_one_shot_runs_whole_pipeline(self):
        from poly_lithic.src.cli import model_main

        class Hop(Observer):
            def __init__(self, topic):
                self.topic = topic
                self.seen = []

            def update(self, message):
                self.seen.append(message)
                return Message(topic=self.topic, source='hop', value=message.value)

        class Sink(Observer):
            def __init__(self):
                self.seen = []

            def update(self, message):
                self.seen.append(message)

        # get_all -> a -> b -> c -> sink: four hops, i.e. four parse_queue calls
        broker = MessageBroker()
        broker.attach(Hop('a'), 'get_all')
        broker.attach(Hop('b'), 'a')
        broker.attach(Hop('c'), 'b')
        sink = Sink()
        broker.attach(sink, 'c')

        config = SimpleNamespace(deployment=SimpleNamespace(type='continuous', rate=0))
        args = argparse.Namespace(publish=False, one_shot=True)
        asyncio.run(model_main(args, config, broker))
        assert len(sink.seen) == 1  # reached the last stage before exiting


class TestBuilderModuleArgs:
    def test_module_args_are_keyword_arguments(self, tmp_path):
        from poly_lithic.src.utils.builder import Builder

        cfg = {
            'deployment': {'type': 'continuous', 'rate': 1},
            'modules': {
                'fastapi_server': {
                    'name': 'fastapi_server',
                    'type': 'interface.fastapi_server',
                    'pub': 'in_interface',
                    'sub': ['get_all', 'model'],
                    'module_args': {'sanitise': False},
                    'config': {
                        'start_server': False,
                        'variables': {
                            'A': {'mode': 'in', 'type': 'scalar'},
                            'X': {'mode': 'out', 'type': 'scalar'},
                        },
                    },
                },
                'model': {
                    'name': 'model',
                    'type': 'model.SimpleModel',
                    'pub': 'model',
                    'sub': 'in_interface',
                    'module_args': {'unpack_input': False, 'pack_output': False},
                    'config': {'type': 'mock'},
                },
            },
        }
        path = tmp_path / 'config.yaml'
        path.write_text(yaml.safe_dump(cfg))

        builder = Builder(str(path))
        builder.build()
        model = builder.loaded_observers['model']
        assert model.unpack_input is False
        assert model.pack_output is False
        assert builder.loaded_observers['fastapi_server'].sanitise is False

    def test_unknown_module_args_are_ignored(self, tmp_path, monkeypatch):
        """Generated configs use unpack_data, which no observer accepts."""
        from poly_lithic.src.utils import builder as builder_module

        cfg = yaml.safe_load(open('./tests/pv_mapping.yaml'))
        # only the transformers: the p4p interface needs a network
        cfg['modules'] = {
            name: module
            for name, module in cfg['modules'].items()
            if module['type'].startswith('transformer')
        }
        assert any(
            isinstance(m['module_args'], dict) and 'unpack_data' in m['module_args']
            for m in cfg['modules'].values()
        )
        path = tmp_path / 'config.yaml'
        path.write_text(yaml.safe_dump(cfg))

        # record directly: the shared logger may not propagate to caplog
        warnings = []
        monkeypatch.setattr(builder_module.logger, 'warning', warnings.append)
        builder = builder_module.Builder(str(path))
        builder.build()
        assert set(builder.loaded_observers) == set(cfg['modules'])
        assert any(
            "not accepted by TransformerObserver: ['unpack_data']" in w
            for w in warnings
        )


class TestRoutingGraph:
    def test_visualize_cyclic_pipeline(self, tmp_path):
        config = ConfigParser('./tests/pv_mapping.yaml').parse()
        out = tmp_path / 'graph.png'
        config.save_routing_graph(str(out))
        assert out.exists()

    def test_isolated_modules_are_reported(self, caplog):
        caplog.set_level(logging.WARNING)
        config = ConfigParser('./tests/pv_mapping_isolated_nodes.yaml').parse()
        assert 'output_data_x' in config.isolated_modules()
        assert 'Isolated nodes found' in caplog.text

    def test_continuous_requires_rate(self):
        with pytest.raises(pydantic.ValidationError, match='positive rate'):
            ConfigObject(deployment={'type': 'continuous'}, modules={})
        # event-driven deployments do not need one
        ConfigObject(deployment={'type': 'event_driven'}, modules={})


class TestFastAPIJobs:
    def _pipeline(self, iface):
        broker = MessageBroker()
        interface_obs = InterfaceObserver(iface, 'in')
        broker.attach(interface_obs, ['get_all', 'model'])
        broker.attach(ModelObserver(model=SumModel(), topic='model'), 'in')
        return broker, interface_obs

    def test_event_driven_job_completes_with_one_run(self, monkeypatch):
        monkeypatch.setenv('PUBLISH', 'True')
        iface = _fastapi()
        broker, interface_obs = self._pipeline(iface)
        interface_obs.start_monitors(broker)

        jid = _submit(iface, A=10.0, B=5.0)
        # the whole job arrives as one message, so the model runs once
        assert len(broker.queue) == 1
        assert set(broker.queue[0].value) == {'A', 'B'}
        assert iface._jobs[jid]['status'] == 'running'

        _drain(broker)
        job = iface._jobs[jid]
        assert job['status'] == 'completed'
        assert job['outputs']['X']['value'] == 15.0
        assert not iface._queued

    def test_continuous_job_is_completed_by_its_own_outputs(self, monkeypatch):
        monkeypatch.setenv('PUBLISH', 'True')
        iface = _fastapi()
        broker, _ = self._pipeline(iface)
        first = _submit(iface, A=1.0, B=1.0)
        second = _submit(iface, A=2.0, B=2.0)

        broker.get_all()  # promotes the first job
        _drain(broker)
        broker.get_all()  # promotes the second job
        _drain(broker)

        assert iface._jobs[first]['outputs']['X']['value'] == 2.0
        assert iface._jobs[second]['outputs']['X']['value'] == 4.0

    def test_resubmitting_same_values_still_completes(self, monkeypatch):
        monkeypatch.setenv('PUBLISH', 'True')
        iface = _fastapi()
        broker, _ = self._pipeline(iface)
        jobs = [_submit(iface, A=1.0, B=1.0) for _ in range(2)]
        for _ in jobs:
            broker.get_all()
            _drain(broker)
        assert all(iface._jobs[j]['status'] == 'completed' for j in jobs)

    def test_put_many_without_job_id_is_ambiguous_with_two_running(self):
        iface = _fastapi()
        a = _submit(iface, A=1.0)
        b = _submit(iface, A=2.0)
        iface.get_many(['A'])
        iface.get_many(['A'])  # both running now
        iface.put_many({'X': {'value': 3.0}})
        assert iface._jobs[a]['status'] == 'running'
        assert iface._jobs[b]['status'] == 'running'

        iface.put_many({'X': {'value': 3.0, 'metadata': {'trace': {'job_id': b}}}})
        assert iface._jobs[b]['status'] == 'completed'
        assert iface._jobs[a]['status'] == 'running'


class TestMonitorDedup:
    def test_on_change_only_handles_arrays(self):
        iface = MemoryInterface({'W': np.zeros(3)})
        broker = MessageBroker()
        InterfaceObserver(iface, 'in').start_monitors(broker, on_change_only=True)
        handler = iface.handlers['W']

        handler(np.array([1.0, 2.0, 3.0]))
        handler(np.array([1.0, 2.0, 3.0]))  # unchanged: dropped
        handler(np.array([1.0, 2.0, 4.0]))
        assert len(broker.queue) == 2

    def test_dedup_is_not_fooled_by_in_place_mutation(self):
        iface = MemoryInterface({'W': np.zeros(3)})
        broker = MessageBroker()
        InterfaceObserver(iface, 'in').start_monitors(broker, on_change_only=True)
        arr = np.array([1.0, 2.0, 3.0])
        iface.handlers['W'](arr)
        arr[0] = 9.0
        iface.handlers['W'](arr)
        assert len(broker.queue) == 2


# ---------------------------------------------------------------------------
# Interfaces
# ---------------------------------------------------------------------------


class TestControlLimits:
    def test_min_step_rounding_cannot_exceed_limit(self):
        from poly_lithic.src.interfaces.p4p_alarm_helpers import (
            enforce_control_limits,
        )

        control = {'limitLow': 0.0, 'limitHigh': 1.0, 'minStep': 0.6}
        assert enforce_control_limits(0.95, control) <= 1.0
        assert enforce_control_limits(0.2, control) == 0.0

    def test_arrays_are_clipped(self):
        from poly_lithic.src.interfaces.p4p_alarm_helpers import (
            enforce_control_limits,
        )

        out = enforce_control_limits(
            np.array([-5.0, 5.0, 50.0]), {'limitLow': 0.0, 'limitHigh': 10.0}
        )
        np.testing.assert_array_equal(out, [0.0, 5.0, 10.0])

    def _pva(self, pv_cfg):
        from poly_lithic.src.interfaces.p4p_alarm_helpers import (
            normalise_variable_settings,
        )
        from poly_lithic.src.interfaces.p4p_interface import SimplePVAInterface

        iface = SimplePVAInterface.__new__(SimplePVAInterface)
        iface.variable_settings = {'PV': normalise_variable_settings('PV', pv_cfg)}
        return iface

    def test_enforced_without_compute_alarm(self):
        iface = self._pva({
            'proto': 'pva',
            'name': 'PV',
            'control': {'limitLow': 0.0, 'limitHigh': 10.0},
            'enforce_control_limits': True,
        })
        payload, has_alarm = iface._prepare_write_payload('PV', {'value': 50.0})
        assert payload['value'] == 10.0
        assert has_alarm is False
        payload, _ = iface._prepare_write_payload('PV', -5.0)
        assert payload == 0.0


class TestP4PClient:
    def test_name_server_config_applies_to_client(self, monkeypatch):
        from poly_lithic.src.interfaces import p4p_interface

        seen = {}

        class FakeContext:
            def __init__(self, *args, **kwargs):
                seen['name_servers'] = os.environ.get('EPICS_PVA_NAME_SERVERS')

        monkeypatch.delenv('EPICS_PVA_NAME_SERVERS', raising=False)
        monkeypatch.setattr(p4p_interface, 'Context', FakeContext)
        p4p_interface.SimplePVAInterface({
            'EPICS_PVA_NAME_SERVERS': 'gateway:5075',
            'variables': {},
        })
        assert seen['name_servers'] == 'gateway:5075'

    def test_get_many_skips_failed_pvs(self):
        from poly_lithic.src.interfaces.p4p_interface import SimplePVAInterface

        iface = SimplePVAInterface.__new__(SimplePVAInterface)
        iface.ctxt = SimpleNamespace(
            get=lambda names, throw: [TimeoutError('PV:A'), {'value': 2.0}]
        )
        assert iface.get_many(['PV:A', 'PV:B']) == {'PV:B': {'value': 2.0}}

    def test_get_all_skips_unreadable_variables(self):
        class Flaky(MemoryInterface):
            def get_many(self, data, **kwargs):
                return {'B': {'value': self.store['B']}}

            def get(self, name, **kwargs):
                raise TimeoutError(name)

        messages = InterfaceObserver(Flaky(), 'in').get_all()
        assert list(messages[0].value) == ['B']


class TestK2EG:
    def test_per_pv_monitor(self):
        from poly_lithic.src.interfaces.k2eg_interface import K2EGInterface

        registered = {}
        iface = K2EGInterface.__new__(K2EGInterface)
        iface.reverse_url_lookup = {'X': 'pva://X'}
        iface.client = SimpleNamespace(
            monitor=lambda url, h, timeout: registered.setdefault(url, h)
        )
        received = []
        iface.monitor(received.append, 'X')  # as InterfaceObserver.start_monitors
        registered['pva://X']('X', {'value': 3.0})
        assert received == [3.0]

    def test_init_failure_reports_real_error(self, monkeypatch):
        from poly_lithic.src.interfaces import k2eg_interface

        def boom(*args, **kwargs):
            raise ConnectionError('broker unreachable')

        monkeypatch.setattr(k2eg_interface.k2eg, 'dml', boom)
        with pytest.raises(ConnectionError, match='broker unreachable'):
            k2eg_interface.K2EGInterface({'variables': {}})


class TestMlflowVersions:
    def _getter(self, version=None, uri=None):
        from poly_lithic.src.model_utils.MlflowModelGetter import MLflowModelGetter

        calls = []
        getter = MLflowModelGetter.__new__(MLflowModelGetter)
        getter.model_name, getter.model_version, getter.model_uri = 'm', version, uri
        getter.client = SimpleNamespace(
            get_model_version=lambda n, v: (
                calls.append(('version', v)) or SimpleNamespace(source=f'src/{v}')
            ),
            get_model_version_by_alias=lambda n, a: (
                calls.append(('alias', a)) or SimpleNamespace(source=f'src/{a}')
            ),
        )
        getter.mlflow = SimpleNamespace(
            artifacts=SimpleNamespace(download_artifacts=lambda uri: uri)
        )
        return getter, calls

    def test_alias(self):
        getter, calls = self._getter(version='champion')
        assert getter.get_requirements() == 'src/champion/requirements.txt'
        assert calls == [('alias', 'champion')]

    def test_number(self):
        getter, calls = self._getter(version=2)
        assert getter.get_requirements() == 'src/2/requirements.txt'
        assert calls == [('version', '2')]

    def test_model_uri(self):
        getter, _ = self._getter(uri='models:/m/3/')
        assert getter.get_requirements() == 'models:/m/3/requirements.txt'


class TestFileInterface:
    def test_save_and_load(self, tmp_path):
        from poly_lithic.src.interfaces.file_interface import h5dfInterface

        path = tmp_path / 'data.h5'
        h5py.File(path, 'w').close()
        iface = h5dfInterface({'path': str(path)})
        iface.save({'ab': np.arange(3)})
        iface.save({'cd': np.ones(2)})  # appends, keeps 'ab'
        loaded = dict(iface.load())
        np.testing.assert_array_equal(loaded['ab'], [0, 1, 2])
        np.testing.assert_array_equal(loaded['cd'], [1.0, 1.0])


# ---------------------------------------------------------------------------
# CLI and templates
# ---------------------------------------------------------------------------


def _mock_model_config(tmp_path, model_config):
    cfg = {
        'deployment': {'type': 'continuous', 'rate': 1},
        'modules': {
            'model': {
                'name': 'model',
                'type': 'model.SimpleModel',
                'pub': 'model',
                'sub': 'in',
                'config': model_config,
            }
        },
    }
    path = tmp_path / 'config.yaml'
    path.write_text(yaml.safe_dump(cfg))
    return str(path)


class TestCli:
    def test_group_accepts_run_options(self, tmp_path, monkeypatch):
        from poly_lithic.src import cli as cli_module

        calls = []
        monkeypatch.setattr(
            cli_module.subprocess, 'run', lambda cmd, check: calls.append(cmd)
        )
        path = _mock_model_config(
            tmp_path,
            {
                'type': 'local',
                'args': {
                    'model_path': 'unused.py',
                    'model_factory_class': 'Unused',
                    'requirements': ['numpy'],
                },
            },
        )
        result = CliRunner().invoke(
            cli_module.cli, ['--config', path, '--requirements']
        )
        assert result.exit_code == 0, result.output
        # requirements were installed without building (or loading) the model
        assert calls and calls[0][-3:] == ['pip', 'install', 'numpy']

    def test_requirements_file(self, tmp_path, monkeypatch):
        from poly_lithic.src import cli as cli_module

        reqs = tmp_path / 'requirements.txt'
        reqs.write_text('numpy\n')
        calls = []
        monkeypatch.setattr(
            cli_module.subprocess, 'run', lambda cmd, check: calls.append(cmd)
        )
        path = _mock_model_config(
            tmp_path,
            {
                'type': 'local',
                'args': {
                    'model_path': 'unused.py',
                    'model_factory_class': 'Unused',
                    'requirements': str(reqs),
                },
            },
        )
        result = CliRunner().invoke(cli_module.cli, ['run', '-c', path, '-r'])
        assert result.exit_code == 0, result.output
        assert calls[0][-2:] == ['-r', str(reqs)]


class TestDeploymentTemplates:
    def _generate(self, tmp_path, **kwargs):
        from poly_lithic.src.utils.model_introspector import ModelMetadata
        from poly_lithic.src.utils.project_generator import (
            ReadyModelProjectGenerator,
        )

        metadata = ModelMetadata(
            input_variables=[
                {'name': 'img', 'type': 'image', 'image_size': {'x': 4, 'y': 3}},
                {'name': 'wave', 'type': 'waveform', 'length': 5},
                {'name': 'a', 'type': 'scalar'},
            ],
            output_variables=[{'name': 'out', 'type': 'scalar'}],
        )
        path = ReadyModelProjectGenerator().generate(
            name='proj',
            interface_type='fastapi',
            output_dir=str(tmp_path),
            metadata=metadata,
            **kwargs,
        )
        config = yaml.safe_load((path / 'deployment_config.yaml').read_text())
        return path, config['modules']['fastapi_server']['config']

    def test_fastapi_defaults_only_where_supported(self, tmp_path):
        _, cfg = self._generate(tmp_path)
        variables = cfg['variables']
        assert 'default' not in variables['PROJ:img']
        assert 'default' not in variables['PROJ:wave']
        assert variables['PROJ:a']['default'] == 0.0
        # the generated variables are accepted by the interface
        SimpleFastAPIInterfaceServer({**cfg, 'start_server': False})

    def test_config_updater_defaults(self):
        from poly_lithic.src.utils.config_updater import ConfigUpdater

        assert ConfigUpdater._default_entry({'type': 'image'}, fastapi=True) == {}
        assert ConfigUpdater._default_entry({'type': 'waveform'}, fastapi=True) == {}
        assert ConfigUpdater._default_entry({'type': 'scalar'}, fastapi=True) == {
            'default': 0.0
        }
        assert ConfigUpdater._default_entry({'type': 'scalar'}, fastapi=False) == {}

    def test_local_run_binds_loopback(self, tmp_path):
        _, cfg = self._generate(tmp_path)
        assert cfg['host'] == '127.0.0.1'

    def test_container_deployment(self, tmp_path):
        path, cfg = self._generate(
            tmp_path, include_docker=True, include_kubernetes=True
        )
        assert cfg['host'] == '0.0.0.0'
        compose = yaml.safe_load((path / 'docker' / 'compose.yaml').read_text())
        assert compose['services']['proj']['ports'] == ['8000:8000']
        k8s = yaml.safe_load((path / 'k8s' / 'deployment.yaml').read_text())
        image = k8s['spec']['template']['spec']['containers'][0]['image']
        assert image == 'proj:latest'

    def test_kubernetes_alone_includes_dockerfile(self, tmp_path):
        path, _ = self._generate(tmp_path, include_kubernetes=True)
        assert (path / 'docker' / 'Dockerfile').exists()


class TestPluginTemplate:
    def _generate(self, tmp_path):
        from poly_lithic.src.utils.plugin_generator import PluginGenerator

        return PluginGenerator().generate(name='my-plugin', output_dir=str(tmp_path))

    def test_license(self, tmp_path):
        path = self._generate(tmp_path)
        assert (
            'license = {text = "BSD-3-Clause"}' in (path / 'pyproject.toml').read_text()
        )

    def test_generated_classes_work(self, tmp_path):
        path = self._generate(tmp_path)
        spec = importlib.util.spec_from_file_location(
            'generated_plugins', path / 'my_plugin' / 'plugins.py'
        )
        plugins = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(plugins)

        iface = plugins.CustomInterface({'variables': {'A': {}, 'B': {}}})
        assert iface.get_inputs() == ['A', 'B']
        assert iface.get_outputs() == ['A', 'B']

        getter = plugins.CustomModelGetter({'requirements': ['numpy']})
        assert getter.get_requirements() == ['numpy']

        transformer = plugins.CustomTransformer({'scale': 2.0})
        transformer.handler('A', {'value': 3.0})
        assert transformer.updated is True
        assert transformer.latest_transformed == {'A': 6.0}
