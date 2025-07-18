from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Union
from pydantic import (
    BaseModel,
    Field,
    field_validator,
    computed_field,
)
import time
from poly_lithic.src.logging_utils import get_logger
from poly_lithic.src.transformers import BaseTransformer
from poly_lithic.src.interfaces import BaseInterface
from poly_lithic.src.model_utils import registered_model_getters
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
    def __init__(self):
        """initialize the message broker"""
        self._observers: Dict[str, list[Observer]] = {}
        self._stats = {}
        self._stats_cnt = {}
        self.queue = []
        self.last_update = time.time()

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
                        for r in result:
                            self.queue.append(r)
                    else:
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
        queue_snapshot = self.queue.copy()
        for message in queue_snapshot:
            self.notify(message)
            self.queue.remove(message)
            logger.debug(f'queue length: {len(self.queue)}')
            # logger.debug(f"queue: {self.queue}")


class TransformerObserver(Observer):
    def __init__(
        self, transformer: BaseTransformer, topic: str, unpack_output: bool = False
    ):
        """wraps around the transformer.handler method"""
        self.transformer = transformer
        self.topic = topic
        self.unpack_output = unpack_output

    def update(self, message: Message) -> Message | list[Message]:
        for key, value in message.value.items():
            self.transformer.handler(key, value)

        if self.transformer.updated:
            values = self.transformer.latest_transformed
            message_dict = {}
            for key, value in values.items():
                message_dict[key] = {'value': value}

            self.transformer.updated = False
            return Message(topic=self.topic, source=str(self), value=message_dict)


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
            logger.debug(f'updating {self}')
            if os.environ['PUBLISH'] == 'True':
                self.interface.put_many(message.value)
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

        self.interface.get_many(self.interface.variable_list)
        # print(f"values: {values}")
        for key in self.interface.variable_list:
            key, value = self.interface.get(key)
            if value is not None:
                output_dict[key] = value

        messages.append(Message(topic=self.topic, source=str(self), value=output_dict))
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
        if self.config['type'] == 'mock':
            return MockModel()
        if self.config['type'] == 'MlflowModelGetterLegacy':
            model_getter = registered_model_getters['mlflow_legacy'](
                self.config['args']
            )  # legacy name well make it consistent across the board in the future
            model = model_getter.get_model()
            # check model is not None
            if model is None:
                raise ValueError('model is None')
            return model
        elif self.config['type'] == 'MlflowModelGetter':
            model_getter = registered_model_getters['mlflow'](self.config['args'])
            model = model_getter.get_model()
            return model
        elif self.config['type'] == 'LocalModelGetter':
            model_getter = registered_model_getters['local'](self.config['args'])
            model = model_getter.get_model()
            return model

        else:
            raise ValueError(f'model type not recognised: {self.config["type"]}')

    def update(self, message: Message) -> list[Message]:
        messages = []
        logger.debug(f'updating {self}')

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
                output[key] = {'value': value}
        else:
            # logger.debug(f"not packing output passign raw: {pred}")
            output = pred

        messages.append(Message(topic=self.topic, source=str(self), value=output))

        return messages


# class GenericObserver(Observer):
#     def __init__(self, callback):
#         """wraps around the callback method, a catch all observer"""
#         self.callback = callback

#     def update(self, message: Message) -> None:
#         self.callback(message)
