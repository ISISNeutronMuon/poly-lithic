from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Union
from importlib import import_module
from pydantic import (
    BaseModel,
    Field,
    field_validator,
    computed_field,
)
import time
import threading
import collections
from uuid import uuid4
from poly_lithic.src.logging_utils import get_logger
from poly_lithic.src.transformers import BaseTransformer
from poly_lithic.src.interfaces import BaseInterface
from poly_lithic.src.utils.plugin_registry import model_getter_plugin_registry
import os

# from deepdiff import DeepDiff
import hashlib
import psutil

current_process = psutil.Process()
logger = get_logger()


def get_process_tree_cpu(process):
    current = process
    cpu_percent = current.cpu_percent()

    # Add CPU usage from all child processes
    for child in current.children(recursive=True):
        try:
            cpu_percent += child.cpu_percent()
        except psutil.NoSuchProcess:
            pass  # Child process ended

    return cpu_percent


import cProfile


def profileit(func):
    def wrapper(*args, **kwargs):
        start_time = time.time()
        datafn = func.__name__ + '.profile'  # Name the data file sensibly
        prof = cProfile.Profile()
        retval = prof.runcall(func, *args, **kwargs)
        end = time.time()
        if end - start_time > 0.3:
            prof.dump_stats(datafn)
        return retval

    return wrapper


class Message(BaseModel):
    topic: Union[str, list[str]]
    source: str
    ## key: str made a mess of this by including a key, no need to include a key
    value: dict = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)
    # optional
    allow_unsafe: Optional[bool] = False
    # tracing fields
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    parent_trace_ids: list[str] = Field(default_factory=list)

    @field_validator('topic')
    @classmethod
    def check_topic(cls, topic):
        if not isinstance(topic, (str, list)):
            raise ValueError('topic must be a string or list of strings')
        elif isinstance(topic, list):
            t_len = len(topic)
            if t_len == 0 or t_len > 1:
                raise ValueError('topic list must contain one element')
            else:
                return topic[0]
        else:
            return topic

    @field_validator('value')
    @classmethod
    def check_value(cls, value):
        if not isinstance(value, dict):
            if cls.allow_unsafe:
                logger.warning(f'allowing unsafe value {value}')
                return {'value': value}
            else:
                raise ValueError('value must be a dictionary')
        # structs must be
        # {name : {"value": value, "timestamp": timestamp, "metadata": metadata}} value is mandatory, timestamp is optional, metadata is optional
        # can have multiple structs in a dictionary {name1: struct1, name2: struct2}
        for key, struct in value.items():
            if not isinstance(struct, dict):
                raise ValueError('struct must be a dictionary')
            if 'value' not in struct:
                raise ValueError('struct must contain a value')
            if 'timestamp' in struct:
                if not isinstance(struct['timestamp'], (int, float)):
                    raise ValueError('timestamp must be an int or float')
            if 'metadata' in struct:
                if not isinstance(struct['metadata'], dict):
                    raise ValueError('metadata must be a dictionary')
        return value

    @computed_field
    def keys(self) -> list[str]:
        return list(self.value.keys())

    @computed_field
    def values(self) -> list[Any]:
        return list(self.value.values())

    @computed_field
    def uid(self) -> str:
        """return a unique id for the message"""
        items = []
        for key, value in self.value.items():
            value_items = frozenset((k, str(v)) for k, v in value.items())
            items.append((key, value_items))

        return hashlib.md5(str(frozenset(items)).encode()).hexdigest()

    def __str__(self):
        return f'Message(topic={self.topic}, source={self.source}, value={self.value}, timestamp={self.timestamp})'

    def __repr__(self):
        return f'Message(topic={self.topic}, source={self.source}, value={self.value}, timestamp={self.timestamp})'

    def __eq__(self, value):
        # value timestamp source and topic must be the same
        if (
            self.topic == value.topic
            and self.source == value.source
            and self.timestamp == value.timestamp
            and self.value == value.value
        ):
            return True
        else:
            return False


class Observer(ABC):
    @abstractmethod
    def update(self, message: Message) -> Message:
        # all updates should return a message
        pass


class MessageBroker:
    def __init__(self, trace_store=None):
        """initialize the message broker"""
        self._observers: Dict[str, list[Observer]] = {}
        self._stats = {}
        self._stats_cnt = {}
        self.queue = collections.deque()
        self._queue_lock = threading.Lock()
        self.last_update = time.time()
        self.trace_store = trace_store

    def attach(self, observer: Observer, topic: str | list[str]) -> None:
        """add observer to topic"""
        logger.debug(f'attaching {observer} to {topic}')

        if isinstance(topic, list):
            for t in topic:
                if t not in self._observers:
                    self._observers[t] = []
                self._observers[t].append(observer)

        else:
            if topic not in self._observers:
                self._observers[topic] = []
            self._observers[topic].append(observer)

    def detach(self, observer: Observer, topic: str | list[str]) -> None:
        """remove observer from topic, we will probably never use this"""

        if isinstance(topic, list):
            for t in topic:
                if t in self._observers:
                    self._observers[t].remove(observer)
        else:
            self._observers[topic].remove(observer)

    # @profileit
    def notify(self, message: Message) -> None:
        """notify all observers of a message"""
        if self.trace_store is not None:
            self.trace_store.record(message)

        if message.topic in self._observers:
            # logger.debug(f"notifying observers of {message}")

            for observer in self._observers[message.topic]:
                logger.debug(f'notifying {observer}')
                start = time.time()
                result = observer.update(message)
                end = time.time()

                if str(observer) not in self._stats:
                    self._stats[str(observer)] = 0
                    self._stats_cnt[str(observer)] = 0
                self._stats[str(observer)] += (end - start) * 1000
                self._stats_cnt[str(observer)] += 1

                if result is not None:
                    # if list of messages
                    if isinstance(result, list):
                        with self._queue_lock:
                            for r in result:
                                self.queue.append(r)
                    else:
                        with self._queue_lock:
                            self.queue.append(result)

            if time.time() - self.last_update > 1:
                self.last_update = time.time()
                fmt_stats = {k: v / self._stats_cnt[k] for k, v in self._stats.items()}
                '\n\t\n' + '\t\n'.join([
                    f'{k}: {v:.2f}ms' for k, v in fmt_stats.items()
                ])
                # sum all _stats
                sum_time = sum([v for v in self._stats.values()])
                cnt = sum([v for v in self._stats_cnt.values()])
                logger.info(
                    f'real time factor: {sum_time / 1000:.2f} must be less than 1, time spent updating this cycle : {sum_time:.2f}ms, {get_process_tree_cpu(current_process):.2f}% CPU usage'
                )
                # print(self._stats)
                # print(self._stats_cnt)
                self._stats = {}
                self._stats_cnt = {}

        else:
            logger.error(f'no observers for {message.topic}')

    def get_stats(self):
        return self._stats

    def get_all(self) -> None:
        refresh_msg = Message(
            topic='get_all', source='clock', value={'dummy': {'value': 1}}
        )
        self.notify(refresh_msg)
        return None

    def parse_queue(self):
        """parse the queue and notify observers of each message"""
        with self._queue_lock:
            queue_snapshot = list(self.queue)
            self.queue.clear()
        for message in queue_snapshot:
            self.notify(message)
            logger.debug(f'queue length: {len(self.queue)}')


class TransformerObserver(Observer):
    def __init__(
        self, transformer: BaseTransformer, topic: str, unpack_output: bool = False
    ):
        """wraps around the transformer.handler method"""
        self.transformer = transformer
        self.topic = topic
        self.unpack_output = unpack_output

    def update(self, message: Message) -> Message | list[Message]:
        # Snapshot input metadata before transformer strips it
        input_meta = {}
        for k, v in message.value.items():
            if isinstance(v, dict) and 'metadata' in v:
                input_meta[k] = v['metadata']

        for key, value in message.value.items():
            self.transformer.handler(key, value)

        if self.transformer.updated:
            values = self.transformer.latest_transformed
            message_dict = {}
            for key, value in values.items():
                if isinstance(value, dict) and 'value' in value:
                    # Shallow-copy to avoid mutating transformer's internal
                    # state (latest_input_struct) during trace injection.
                    message_dict[key] = {**value}
                    if 'metadata' in value:
                        message_dict[key]['metadata'] = {**value['metadata']}
                else:
                    message_dict[key] = {'value': value}
                # Re-attach input metadata if this key had it
                if key in input_meta:
                    existing_meta = message_dict[key].get('metadata', {})
                    existing_meta.update(input_meta[key])
                    message_dict[key]['metadata'] = existing_meta

            self.transformer.updated = False

            # Aggregate trace_ids from ALL contributing inputs,
            # not just the triggering message.
            parent_ids = {message.trace_id}
            input_structs = getattr(self.transformer, 'latest_input_struct', {})
            for struct in (input_structs or {}).values():
                if isinstance(struct, dict):
                    trace_info = (struct.get('metadata') or {}).get('trace') or {}
                    tid = trace_info.get('trace_id')
                    if tid:
                        parent_ids.add(tid)

            out_msg = Message(
                topic=self.topic,
                source=str(self),
                value=message_dict,
                parent_trace_ids=list(parent_ids),
            )
            # Inject trace_id into each variable struct metadata
            for key in out_msg.value:
                if isinstance(out_msg.value[key], dict):
                    meta = out_msg.value[key].setdefault('metadata', {})
                    meta['trace'] = {'trace_id': out_msg.trace_id}
            return out_msg


class InterfaceObserver(Observer):
    def __init__(self, interface: BaseInterface, topic: str, sanitise: bool = True):
        """wraps around the interface.put_many method"""
        self.interface: BaseInterface = interface
        self.topic: str = topic
        self.sanitise = sanitise
        self.last_get_all = None

    def update(self, message: Message) -> Message | list[Message]:
        if message.topic == 'get_all':
            messages = self.get_all()
            # compare to last_get_all if not None
            if self.last_get_all is not None:
                # compare uid for each message
                diff = False
                for m in messages:
                    if m.uid not in [msg.uid for msg in self.last_get_all]:
                        diff = True
                        break
                # print(self.last_get_all, messages)
                if diff:
                    self.last_get_all = messages
                    return messages
                else:
                    logger.debug('no diff')
                    return None
            else:
                self.last_get_all = messages
                return messages

            return messages
        else:
            # check if os.environ['PUBLISH'] exists and is True
            if 'PUBLISH' not in os.environ:
                os.environ['PUBLISH'] = 'False'

            logger.debug(f'updating {self}')
            if os.environ['PUBLISH'] == 'True':
                # Strip internal metadata before writing to the interface
                # (e.g. p4p NTScalar doesn't have a 'metadata' field)
                clean = {}
                for k, v in message.value.items():
                    if isinstance(v, dict) and 'metadata' in v:
                        clean[k] = {fk: fv for fk, fv in v.items() if fk != 'metadata'}
                    else:
                        clean[k] = v
                self.interface.put_many(clean)
            else:
                logger.warning(
                    'PUBLISH is set to False, this will not publish to the interface'
                )

    def get(self, message: Message) -> list[Message]:
        """get a single variable from the interface"""
        messages = []
        for key in message.keys:
            key, value = self.interface.get(key)
            messages.append(
                Message(topic=self.topic, source=str(self), value={key: value})
            )
        return messages

    def get_all(self) -> list[Message]:
        """get all variables from the interface based on internal variable list"""
        messages = []
        output_dict = {}

        self.interface.get_many(self.interface.get_inputs())
        # print(f"values: {values}")
        for key in self.interface.get_inputs():
            key, value = self.interface.get(key)
            if value is not None:
                output_dict[key] = value

        msg = Message(topic=self.topic, source=str(self), value=output_dict)
        # Inject trace_id into each variable struct metadata (origin — no parent)
        for key in msg.value:
            if isinstance(msg.value[key], dict):
                meta = msg.value[key].setdefault('metadata', {})
                meta['trace'] = {'trace_id': msg.trace_id}
        messages.append(msg)
        return messages

        # if self.last_get_all is not None:
        #     diff = DeepDiff(self.last_get_all, output_dict)
        #     self.last_get_all = output_dict
        #     if diff:
        #         messages.append(
        #             Message(topic=self.topic, source=str(self), value=output_dict)
        #         )
        #     else:
        #         logger.debug("no diff")
        # else:
        #     self.last_get_all = output_dict
        #     messages.append(
        #         Message(topic=self.topic, source=str(self), value=output_dict)
        #     )
        # return messages

    def get_many(self, message: Message) -> list[Message]:
        """get many variables from the interface"""
        keys, values = self.interface.get_many(message.value)

        messages = []
        for key, value in values.items():
            messages.append(
                Message(topic=self.topic, source=str(self), value={key: value})
            )
        return messages

    def put(self, message: Message) -> None:
        """put a single variable into the interface"""
        if not isinstance(message.value, dict):
            raise ValueError('message value must be a dictionary')

        for key, value in zip(message.keys, message.values):
            self.interface.put(key, value)

    def put_many(self, message: Message) -> None:
        """put many variables into the interface"""
        if not isinstance(message.value, dict):
            raise ValueError('message value must be a dictionary')
        self.interface.put_many(message.value)

    def start_monitors(self, broker, min_interval: float = 0.0, on_change_only: bool = False):
        """Start PV monitors that push updates into the broker queue (event-driven mode).

        Args:
            broker: MessageBroker instance to push messages into.
            min_interval: Minimum seconds between updates per PV (throttle).
            on_change_only: When True, skip updates where the value hasn't changed.
        """
        last_fire_time = {}
        last_value = {}
        self._monitors = []

        def _make_handler(pv_name):
            def handler(value):
                now = time.time()
                # Throttle
                if min_interval > 0:
                    if pv_name in last_fire_time and (now - last_fire_time[pv_name]) < min_interval:
                        return
                # Dedup
                if on_change_only:
                    if pv_name in last_value and last_value[pv_name] == value:
                        return
                    last_value[pv_name] = value

                last_fire_time[pv_name] = now
                val_struct = {'value': value}
                msg = Message(
                    topic=self.topic,
                    source=str(self),
                    value={pv_name: val_struct},
                )
                val_struct.setdefault('metadata', {})['trace'] = {'trace_id': msg.trace_id}
                with broker._queue_lock:
                    broker.queue.append(msg)
            return handler

        for pv_name in self.interface.get_inputs():
            mon = self.interface.monitor(_make_handler(pv_name), pv_name)
            self._monitors.append(mon)


class MockModel:
    def __init__(self):
        """placeholder for model"""

    def evaluate(self, value):
        """placeholder for model prediction"""
        return {'not_initialized': {'value': -99999999999}}


class ModelObserver(Observer):
    def __init__(
        self,
        model=None,
        config=None,
        topic: str = 'model',
        unpack_input: bool = True,
        pack_output: bool = True,
    ):
        """wraps around the model.predict method"""
        self.model = model
        self.topic = topic
        self.config = config
        self.unpack_input = unpack_input
        self.pack_output = pack_output

        if self.model is None and self.config is not None:
            self.model = self.__get_model()
            # if not hasattr(self.model, 'evaluate'): # mlflow wierdness doesnt let me check the attribute, it always comes back false
            #     raise ValueError('model must have a .evaluate() method')
        elif self.model is not None:
            self.model = model
        else:
            raise ValueError('model must be provided or a config to load a model')

    def __get_model(self):
        """load the model from the config"""
        model_type = self.config['type']
        if model_type == 'mock':
            return MockModel()
        model_getter_class = self.__resolve_model_getter_class(model_type)
        model_getter = model_getter_class(self.config['args'])
        model = model_getter.get_model()
        if model_type == 'MlflowModelGetterLegacy' and model is None:
            raise ValueError('model is None')
        return model

    @staticmethod
    def __resolve_model_getter_class(model_type: str):
        builtins = {
            'MlflowModelGetterLegacy': (
                'poly_lithic.src.model_utils.MlflowModelGetter',
                'MLflowModelGetterLegacy',
            ),
            'mlflow_legacy': (
                'poly_lithic.src.model_utils.MlflowModelGetter',
                'MLflowModelGetterLegacy',
            ),
            'MlflowModelGetter': (
                'poly_lithic.src.model_utils.MlflowModelGetter',
                'MLflowModelGetter',
            ),
            'mlflow': (
                'poly_lithic.src.model_utils.MlflowModelGetter',
                'MLflowModelGetter',
            ),
            'LocalModelGetter': (
                'poly_lithic.src.model_utils.LocalModelGetter',
                'LocalModelGetter',
            ),
            'local': (
                'poly_lithic.src.model_utils.LocalModelGetter',
                'LocalModelGetter',
            ),
        }
        if model_type in builtins:
            module_name, class_name = builtins[model_type]
            return getattr(import_module(module_name), class_name)

        # External model getter plugins are discovered via entry points and loaded on demand.
        if model_getter_plugin_registry.has_plugin(model_type):
            return model_getter_plugin_registry.get(model_type)

        raise ValueError(f'model type not recognised: {model_type}')

    def update(self, message: Message) -> list[Message]:
        messages = []
        logger.debug(f'updating {self}')

        # Snapshot input metadata before unpacking
        input_meta = {}
        for k, v in message.value.items():
            if isinstance(v, dict) and 'metadata' in v:
                input_meta[k] = v['metadata']

        if self.unpack_input:
            # logger.debug(f"unpacking input: {message.value}")
            value = {v: message.value[v]['value'] for v in message.value}
        else:
            # logger.debug(f"not unpacking input passign raw: {message.value}")
            value = message.value
        pred = self.model.evaluate(value)
        output = {}

        if self.pack_output:
            # logger.debug(f"packing output: {pred}")
            for key, value in pred.items():
                # If model already returns a full value struct, preserve it.
                if isinstance(value, dict) and 'value' in value:
                    output[key] = value
                else:
                    output[key] = {'value': value}
        else:
            # logger.debug(f"not packing output passign raw: {pred}")
            output = pred

        # Aggregate trace_ids from ALL input variables, not just
        # the triggering message.
        parent_ids = {message.trace_id}
        for meta in input_meta.values():
            trace_info = (meta.get('trace') or {})
            tid = trace_info.get('trace_id')
            if tid:
                parent_ids.add(tid)

        out_msg = Message(
            topic=self.topic,
            source=str(self),
            value=output,
            parent_trace_ids=list(parent_ids),
        )
        # Inject trace_id and merge input metadata into each output variable struct
        for key in out_msg.value:
            if isinstance(out_msg.value[key], dict):
                meta = out_msg.value[key].setdefault('metadata', {})
                meta['trace'] = {'trace_id': out_msg.trace_id}
        messages.append(out_msg)

        return messages


# class GenericObserver(Observer):
#     def __init__(self, callback):
#         """wraps around the callback method, a catch all observer"""
#         self.callback = callback

#     def update(self, message: Message) -> None:
#         self.callback(message)
