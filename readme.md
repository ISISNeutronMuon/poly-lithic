<!-- NEW DOCS in progress
use old docs in the meantime: [old docs](./readme_old.md) -->

# Table of Contents
  - [Installation](#installation)
  - [Usage](#usage)
  - [Configuration file](#configuration-file-formerly-pv_mappings-files)
  - [Modules](#modules)
    - [Interface](#interface)
      - [Interface Configs](#interface-configs)
        - [p4p sample configuration](#p4p-sample-configuration)
        - [p4p_server sample configuration](#p4p_server-sample-configuration)
        - [k2eg sample configuration](#k2eg-sample-configuration)
    - [Transformer](#transformer)
      - [Transformer Configs](#transformer-configs)
        - [SimpleTransformer sample configuration](#simpletransformer-sample-configuration)
        - [CAImageTransformer sample configuration](#caimagetransformer-sample-configuration)
        - [CompoundTransformer sample configuration](#compoundtransformer-sample-configuration)
        - [PassThroughTransformer sample configuration](#passthroughtransformer-sample-configuration)
    - [Model](#model)
      - [Model Configs](#model-configs)
        - [Example Model - Local Model](#example-model---local-model)
        - [Example Model - MLFLow Model](#example-model---mlflow-model)

  - [Roadmap](#roadmap)
# Poly-Lithic

Poly-Lithic is a package that allows you do deploy any model with an arbitrary number of inputs and outputs, related data transformations and system interfaces. 

Each deployment is defined by a model, typically hosted and retrieved from [MLFlow](https://mlflow.org/) and YAML file that describes the DG (Directed Graph) of model, transformations and interfaces. There are no restrictions on the numbers and types of nodes in the graph, so it may be used for things other than ML models.


## Installation

Python `3.11.x` recommended.

```bash
pip install poly-lithic
```
for development:

```bash
pip install -r reqirements.txt
pip install -e .
```

with docker:

```bash
docker compose -f ./docker/docker_compose.yml up
``` 

## Usage

```python
model_manager --publish -c ./tests/pv_mapping_mlflow.yaml -e ./tests/env.json
```
or
```python
pl --publish -c ./tests/pv_mapping_mlflow.yaml -e ./tests/env.json
```
The env file is a json file that contains the environment variables that are used in the deployment. In this example we are pulling the [torch](./examples/torch_and_generic.ipynb) model and wrapping it with simple transformers and a simple p4p server.  

Reqired variables are:
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET`
- `AWS_DEFAULT_REGION`
- `AWS_REGION`
- `MLFLOW_S3_ENDPOINT_URL`
- `MINIO_ROOT_PASSWORD`
- `MINIO_ROOT_USER`
- `MINIO_SITE_REGION`
- `MLFLOW_TRACKING_URI` 
- `PUBLISH` - set to `true` for the deployment to publish data to the interface. This flag serves as a safety measure to prevent accidental publishing of data to live system. 

See [this](https://mlflow.org/docs/latest/api_reference/python_api/mlflow.environment_variables.html) for explantions of the MLFlow environment variables.

## Configuration file (formerly pv_mappings files)

The configuration file consists of 2 sections `deployment` and `modules`. Former describes deployment type and other setings such as refresh rate. The latter describes the nodes the modules and their connections to each other. 


#### Example configuration file
```yaml
deployment:
  type: "continuous" #type of deployment, continuous is the only one supported at the moment but more will be added
  rate: 0.25 #refresh rate in seconds

modules:
    module1:
        name: "module1"         # name of the module used to identify it in the graph
        type: "type.subtype"    # type of the module, used to identify the module class and subclass 
        pub: "topic1"           # topic the outputs will be published to, similar to MQTT, Kafka, ROS etc 
        sub:                    # topics the module will subscribe to, we listen for and transform data from these topics
        - "update"              # update is a special topic that will trigger an interface module to run get_all method (get_many for all keys)
        - "topic3"              
        module_args: None       # defines what arguments to pass to the module observer, if any this can inform unpacking etc
        config:                 # configuration specific to the module type
            key1: "value1"
            keyn: "valuen"

    module2:
        ...
        pub: "topic2"
        sub:
        - "topic1"
    module3:
        ...
        pub: "topic3"
        sub:
        - "topic2"
```
The graph for the above configuration would look like this:

```mermaid
graph TD;
    every_0.25s --> module1
    module1 --> module2
    module2 --> module3
    module3 --> module1
```

Under the hood we are passing messages in the format:

```json
{
    "topic": "topic1",
    "data": {
        "key1": {"value" : 1},
        "key2": {"value" : [1,2,3]},
        "key3": {"value" : {...}}
    }
}
```
Note that the data is a dictionary of dictionaries.

## Modules

### Interface
Interface modules are used to interact with external data, usually an accelerators control systems but can be anything. They follow the following structure (see [base interface class](./poly-lithic/src/interfaces/BaseInterface.py)):

```python
class BaseInterface(ABC):
    @abstractmethod
    def __init__(self, config):
        pass

    @abstractmethod
    def monitor(self, name, handler, **kwargs): # not used at the moment but will be used to monitor the interface for changes, rather than polling when p4p can monitor more than 4 pv's
        pass

    @abstractmethod
    def get(self, name, **kwargs):              # get a value from the interface
        pass

    @abstractmethod
    def put(self, name, value, **kwargs):       # put a value to the interface
        pass

    @abstractmethod
    def put_many(self, data, **kwargs):         # put many values to the interface
        pass

    @abstractmethod
    def get_many(self, data, **kwargs):         # get many values from the interface
        pass
```
All values are expected to come in as dictionaries of dictionaries with the following format:

```python
# for sigular puts and gets
name = "key1"
value = {"value" : 1, "timestamp": 1234567890, "metadata": "some meta data"}        # note tha the timestamp and metadata are optional and unusued at the moment

# for _many 
data = {
    "key1": {"value" : 1, "timestamp": 1234567890, "metadata": "some meta data"},
    "key2": {"value" : [1,2,3]},
    "key3": {"value" : {...}}
}
```
#### Interface Configs
| Module | Description | YAML configuration | 
| ------ | ----------- | ------------------ | 
| `p4p` | EPICS data source, must have an external EPICS server running. Note that SoftIOCPVA will not work with this module. | [config](#p4p-sample-configuration) |
| `p4p_server` | EPICS data source, host EPICS p4p server for specifed PVs | same [config](#p4p-sample-configuration) as `p4p`|
| `k2eg` | Kafka to EPICS gateway, get data from Kafka and write it to EPICS | [config](#k2eg-sample-configuration) |

##### `p4p` sample configuration
```yaml
deployment:
    ...
modules:
    mymodule:
    ...
    config: 
      EPICS_PVA_NAME_SERVERS: "epics.server.co.uk:5075"
      # other EPICS_CONFIGS can go here
      variables:
        MY_VAR:TEST_A:
          proto: pva
          name: MY_VAR:TEST_A # name here is redundant as the name is the key in the variables dictionary, it will be removed in future versions
        MY_VAR:TEST_B:
          proto: pva
          name: MY_VAR:TEST_B
        MY_VAR:TEST_S:
          proto: pva
          name: MY_VAR:TEST_S
          # default: 0 | [0.0, ... ,0.0] | no defaults for images   optional
          # type: scalar | waverform | image (default scalar)       optional
```

##### `p4p_server` sample configuration
```yaml
    config: 
      EPICS_PVA_NAME_SERVERS: "epics.server.co.uk:5075"
      # other EPICS_CONFIGS can go here
      variables:
        MY_VAR:TEST_A:
          proto: pva
          name: MY_VAR:TEST_A
        MY_VAR:TEST_B:
          proto: pva
          name: MY_VAR:TEST_B
        MY_VAR:TEST_S:
          proto: pva
          name: MY_VAR:TEST_S
          # default: 0 | [0.0, ... ,0.0] | no defaults for images   optional
          # type: scalar | waverform | image (default scalar)       optional
```
Yes, it is identical to p4p, the only difference is that the p4p server will host the PVs for the specified variables.

#### `k2eg` Sample configuration

This module is built on top of SLAC's [k2eg](https://github.com/slaclab/k2eg), it's great because it allows you get data from `pva` and `ca` protocols over Kafka. currently its the only interface that supports `ca` protocol.

> [!CAUTION]
> need some more testing as it was last tested in Q1 2024. 

```yaml
input_data:
  get_method: "k2eg"
  config:
    variables:
      MY_VAR:TEST_A:
        proto: ca # supports ca or pva
        name: MY_VAR:TEST_A
      MY_VAR:TEST_B:
        proto: pva
        name: MY_VAR:TEST_B
```

### Transformer

Transformers are used to transform data from one format to another, they can be used to perform some data processing, aggregation or any other transformation action. They follow the structure (see [base transformer class](./poly-lithic/src/transformers/BaseTransformer.py)):

```python
class BaseTransformer:
    @abstractmethod
    def __init__(self, config: dict):
        """
        config: dict passed from the pv_mappings.yaml files.
        """
        pass

    @abstractmethod
    def transform(self):
        """
        Call transform function to transform the input data, see SimpleTransformer in model_manager/src/transformers/BaseTransformers.py for an example.
        """
        pass

    @abstractmethod
    def handler(self, pv_name: str, value: dict | float | int):
        """
        Handler function to handle the input data, in most cases it initiates the transform function when all the input data is available.
        Handler is the only function exposed to the main loop of the program aside from initial configuration.
        """
        pass
```
#### Transformer Configs
| Module | Description | YAML configuration |
| ------ | ----------- | ------------------ |
| `SimpleTransformer` | Simple transformer that can be used to transform scalar values (ca or pv values that have a `value` field) | [config](#simpletransformer-sample-configuration) |
| `CAImageTransformer` | Transformer that can be used to transform a triplet of an array, x and y ca values into a np array | [config](#caimagetransformer-sample-configuration) |
| `CompoundTransformer` | Compound transformer that can be used to have multiple transformers in parallel | [config](#compoundtransformer-sample-configuration) |
| `PassThroughTransformer` | Transformer that can be used to pass data through without any transformation other than the tag | [config](#passthroughtransformer-sample-configuration) |

##### `SimpleTransformer` Sample configuration
```yaml
modules:
  input_transformer:
    name: "input_transformer"
    type: "transformer.SimpleTransformer"
    pub: "model_input"
    sub:
    - "system_input"
    module_args: None
    config:
      symbols:
        - "LUME:MLFLOW:TEST_B"
        - "LUME:MLFLOW:TEST_A"
      variables:
        x2:
          formula: "LUME:MLFLOW:TEST_B"
        x1: 
          formula: "LUME:MLFLOW:TEST_A"
```

##### `CAImageTransformer` Sample configuration
```yaml
modules:
  image_transformer:
    name: "image_transformer"
    type: "transformer.CAImageTransformer"
    pub: "model_input"
    sub:
    - "update"
    module_args: None
    config:
      variables:
        img_1:
          img_ch: "MY_TEST_CA"
          img_x_ch: "MY_TEST_CA_X"
          img_y_ch: "MY_TEST_CA_Y"
        img_2:
          img_ch: "MY_TEST_C2"
          img_x_ch: "MY_TEST_CA_X2"
          img_y_ch: "MY_TEST_CA_Y2"
```

##### `PassThroughTransformer` Sample configuration
```yaml
modules:
  output_transformer:
    name: "output_transformer"
    type: "transformer.PassThroughTransformer"
    pub: "system_output"
    sub:
    - "model_output"
    module_args: None
    config:
      variables:
        LUME:MLFLOW:TEST_IMAGE: "y_img"
```
##### `CompoundTransformer` Sample configuration
> [!CAUTION]
> This module will be deprecated in the future, pub-sub model means that compound transformers are no longer needed.

```yaml
modules:
  compound_transformer:
    name: "compound_transformer"
    type: "transformer.CompoundTransformer"
    pub: "model_input"
    sub:
    - "update"
    module_args: None
    config:
      transformers:
        transformer_1:
          type: "SimpleTransformer"
          config:
            symbols:
              - "MY_TEST_A"
              - "MY_TEST_B"
            variables:
              x2:
                formula: "MY_TEST_A*2"
              x1: 
                formula: "MY_TEST_B+MY_TEST_A"
        transformer_2:
          type: "CAImageTransformer"
          config:
            variables:
              img_1:
                img_ch: "MY_TEST_CA"
                img_x_ch: "MY_TEST_CA_X"
                img_y_ch: "MY_TEST_CA_Y"
              img_2:
                img_ch: "MY_TEST_C2"
                img_x_ch: "MY_TEST_CA_X2"
                img_y_ch: "MY_TEST_CA_Y2"
```


### Model

Models are the core of the deployment, they can be retrieved locally or from MLFlow and accept data in form of dictionries. By deafault models pivot the dictionry or rather remove the additional keys from messages to simplify the data structure that the model has to process.

All models have to implement the `evaluate` method that takes a dictionary of inputs and returns a dictionary of outputs. 

#### Model Config 

```yaml
model:                              # this is the name of the model module, it is used to identify the model in the graph
    name: "model"                   # name of the model used to identify it in the graph, overrides the name in the module section
    type: "model.SimpleModel"       # type of module, used to identify the model class and subclass, in this case we are saying it a model 
    pub: "model"                    # where the model will publish its outputs, this is the topic that the model will publish to
    sub: "in_transformer"           # topic that the model will subscribe to, this is the topic that the model will listen for inputs
    module_args: None               # defines what arguments to pass to the model observer, if any this can inform unpacking etc
    config:
      type: "modelGetter"           # defines the type of model getter, this is used to identify the model getter class
      args:                         # arguments to pass to the model getter class, in this case we are passing the path to the model definition file

```
See the following examples for usage


###### Example Model - Local Model

```python
  
class SimpleModel(torch.nn.Module):
    def __init__(self):
        super(SimpleModel, self).__init__()
        self.linear1 = torch.nn.Linear(2, 10)
        self.linear2 = torch.nn.Linear(10, 1)

    def forward(self, x): # this is for our benefit, it is not used by poly-lithic
        x = torch.relu(self.linear1(x))
        x = self.linear2(x)
        return x

    # this method is necessary for the model to be evaluated by poly-lithic
    def evaluate(self, x: dict) -> dict:
        # x will be a dicrt of keys and values
        # {"x": x, "y": y}
        input_tensor = torch.tensor([x['x'], x['y']], dtype=torch.float32)
        # you may want to do somethinf more complex here
        output_tensor = self.forward(input_tensor)
        # return a dictionary of keys and values
        return {'output': output_tensor.item()}
  ```

  Lets say we want to retreive the model locally, we need to specify a factory class:

```python
  
class ModelFactory:
    # can do more complex things here but we will just load the model from a locally saved file
    def __init__(self):
        # add this path to python environment
        os.environ['PYTHONPATH'] = os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', '..', '..')
        )
        print('PYTHONPATH set to:', os.environ['PYTHONPATH'])
        self.model = SimpleModel()
        model_path = 'examples/base/local/model.pth'
        if os.path.exists(model_path):
            self.model.load_state_dict(torch.load(model_path))
            print('Model loaded successfully.')
        else:
            print(
                f"Warning: Model file '{model_path}' not found. Using untrained model."
            )
        print('ModelFactory initialized')

    # this method is necessary for the model to be retrieved by poly-lithic
    def get_model(self):
        return self.model
```
The in the config file:

```yaml
...
model:
    name: "model"
    type: "model.SimpleModel"
    pub: "model"
    sub: "in_transformer"
    module_args: None
    config:
      type: "LocalModelGetter"
      args: 
        model_path: "examples/base/local/model_definition.py"           # path to the model definition
        model_factory_class: "ModelFactory"                             # class that you use to create the model
      variables:
        max:
          type: "scalar"
...
```

Then to run the model:
```bash
pl --publish -c examples/base/local/deployment_config.yaml
```
See the [local example notebook](./examples/base/simple_model_local.ipynb) for more details.

#### Example Model - MLFLow Model
See the [MLFlow example notebook](./examples/base/simple_model_mlflow.ipynb) for more details.


## Roadmap

| Feature / Task                                | Timeline     | Priority | Status        |
|-----------------------------------------------|--------------|----------|---------------|
| 🖌️ 🎨 **Make logo**                            | 1–3 Months   | 🥇       | 🚧 In Progress |
| 🧠 🔧 **Lume-Model Integration**               | 1–3 Months   | 🥇       | 🚧 In Progress |
| ⚡ 🔄 **Event driven mode**                    | 1-3 Months   | 🥈       | ⏳ Planned     |
| 📦 🤖 **MLflow 3.x Support**                   | 1–3 Months   | 🥇       | ⏳ Planned     |
| 🌐 🚀 **Move to `gh-pages`**                   | 1–3 Months   | 🥈       | 🚧 In Progress |
| 🔗 🧪 **p4p4isis Interface**                   | 6–12 Months  | 🥉       | ⏳ Planned     |
| 📊 🧭 **Time Series Aggregation**              | 3–6 Months   | 🥉       | ⏳ Planned     |
| 📈 🔍 **Model Evaluator Module**               | 3–6 Months   | 🥉       | ⏳ Planned     |
| 🔁 🔧 **Model Retrainer Module**               | 6–12 Months  | 🥈       | ⏳ Planned     |