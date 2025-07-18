## Purpose and Idea
The purpose of the model manager is to allow for easy deployment of models from MLflow, local model defintion or other sources. 
The package is in an early stage and right now is tightly coupled with MLflow. The goal is to make it more general and allow for easy deployment of models from other sources as well.

The idea is to divide model deployment into 3 layers:

### System level 
In this stage we get the data from X system (in our case EPICS), this is where we are "relaxed" about the definition of the data format. We just want to get the data and store it as a dictionary And supply it to a handler function.

Example
```python
my_data_getter.get(name:str) -> Tuple(key: str, value: Dict[str, Any])
```
or get many
```python
my_data_getter.get_many(names:List[str]) -> List[Tuple(key: str, value: Dict[str, Any])]
```
Note: this is only partially implemeted thats why `main()` uses `.get()` instead of `.get_many()`

Since we are focused on continuous data we also usually have a monitor that calls a callback function when new data is available:

```python
my_data_getter.monitor(callback: Callable[[Dict[str, Any]], None])
```

### Transformation level
This is where we transform the data into a format that the model can understand; it is where we are stricter about the data format.

Again since the initial focus was on continuous data, the transformer supplies a callback function that is called from the system level monitor function.

```python
my_transformer.handle(data: Dict[str, Any]) -> Dict[str, Any]
```
Now internally the model tracks the late input data, on each call to `handle` it updates the internal state and returns the transformed data.

Example:
```python
# my pretend system has 3 inputs it provides, the inputs need some adjustments before they can be fed to the model
config = {
    "variables": {
        "x1": {
            "formula": "LUME:MLFLOW:TEST_A"
        },
        "x2": {
            "formula": "LUME:MLFLOW:TEST_B"
        },
        "x3": {
            "formula": "LUME:MLFLOW:TEST_C + LUME:MLFLOW:TEST_B"
        }
    },
    "symbols": ["LUME:MLFLOW:TEST_A", "LUME:MLFLOW:TEST_B", "LUME:MLFLOW:TEST_C"]
}

transformer = SimpleTransformer(config) # all variables intialy set to None

# now manually call the handle function
transformer.handle("LUME:MLFLOW:TEST_A", 1) # this should update the internal state but internal update should only happen once all variables are updated
transformer.handle("LUME:MLFLOW:TEST_B", 2) # still no update
transformer.handle("LUME:MLFLOW:TEST_C", 3) # now the internal state should be updated

transformer.updated # should be True

x = transformer.latest_transformed
# x should be a dictionary with the transformed data, ready to be fed to the model
# {
#     "x1": 1,
#     "x2": 2,
#     "x3": 5
# }

```
### Model level
This is where a lume model is used to make predictions. The model should be able to handle the transformed data and return a prediction.

```python

output = some_lume_model.evaluate(data: Dict[str, Any]) -> Dict[str, Any]
# say output is:
# {
#     "y": 0.5
# }
```
and done, now we follow the same pattern as before, the model calls the callback function when new data is available.

```python

config = {
    "variables": {
        "LUME:MLFLOW:TEST_Y": {
            "formula": "y"
        }
    },
    "symbols": ["LUME:MLFLOW:TEST_Y"]
}

reverse_transformer = ReverseTransformer(config) # all variables intialy set to None

reverse_transformer.handle("y", 0.5) 

reverse_transformer.updated # should be True

y = reverse_transformer.latest_transformed

# should return
# {
#     "LUME:MLFLOW:TEST_Y": 0.5
# }
```
Then we pass the data to the system level and we are done.
```python
my_data_outputter.put(data: Dict[str, Any])
```
or many
```python
my_data_outputter.put_many(data: List[Dict[str, Any]])
```

To summarise the data flow is as follows:
```
System level -> Transformation level -> Model level -> Transformation level -> System level
```
All of this happens in the `main()` function in `model_manager/src/cli.py` under `setup()` and `model_main()` methods.

## Available modules

### System
Purpose of the system module is to provide a way to get data from a system. The system can be anything from a database to a file or a live data source like EPICS, kafka, etc.

| Module | Description | YAML configuration | Compatible with: |
| ------ | ----------- | ------------------ | --------------- |
| `p4p` | EPICS data source, must have an external EPICS server running. Note that SoftIOCPVA will not work with this module. | [config](#p4p-sample-configuration) | `SimpleTransformer`, `CompoundTransformer` |
| `p4p_server` | EPICS data source, host EPICS p4p server for specifed PVs | same [config](#p4p-sample-configuration) as `p4p`| `SimpleTransformer`, `CompoundTransformer` |
| `k2eg` | Kafka to EPICS gateway, get data from Kafka and write it to EPICS | [config](#k2eg-sample-configuration) | `SimpleTransformer`, `CompoundTransformer` , `CAImageTransformer`* |


*`CAImageTransformer` untested, but compatible with `k2eg` ca protocol only


#### `p4p` Sample configuration
```yaml
input_data:
  get_method: "p4p"
  config:
    EPICS_PVA_NAME_SERVERS: "134.79.151.21:5169" # can be a space separated list
    variables:
      LUME:MLFLOW:TEST_B:
        proto: pva # supports pva only
        name: LUME:MLFLOW:TEST_B
      LUME:MLFLOW:TEST_A:
        proto: pva
        name: LUME:MLFLOW:TEST_A
      ### in p4p_server you can specify type as well, if not specified it will be assumed to be scalar
      LUME:MLFLOW:TEST_C:
        proto: pva
        name: LUME:MLFLOW:TEST_C
        type: "image"
       
```
Available types are `scalar` and `image`. The `image` type expects an np array as the value. See `examples/image_model/pv_mapping.yaml` or run 
```bash
model_manager -n "image_model" -v "16" -e cred.json -c ./local_test/pv_mapping.yaml -p -d"
```
to see an example of how to use the `image` type.

#### `k2eg` Sample configuration
```yaml
input_data:
  get_method: "k2eg"
  config:
    variables:
      LUME:MLFLOW:TEST_B:
        proto: ca # supports ca or pva
        name: LUME:MLFLOW:TEST_B
      LUME:MLFLOW:TEST_A:
        proto: pva
        name: LUME:MLFLOW:TEST_A
```

### Transformation

Purpose of the transformation module is to provide a way to transform the data into a format that the model can understand. Minor transformation operations like scaling, normalizing, etc. can be done here.

| Module | Description | YAML configuration | Compatible with: |
| ------ | ----------- | ------------------ | --------------- |
| `SimpleTransformer` | Simple transformer that can be used to transform scalar values (ca or pv values that have a `value` field) | [config](#simpletransformer-sample-configuration) | `p4p`,`p4p_server`, `k2eg`|
| `CAImageTransformer` | Transformer that can be used to transform a triplet of an array, x and y ca values into a np array | [config](#caimagetransformer-sample-configuration) | `k2eg` ca only|
| `CompoundTransformer` | Compound transformer that can be used to have multuple transformers in parallel | [config](#compoundtransformer-sample-configuration) | `p4p`,`p4p_server`, `k2eg`|
`PassThroughTransformer` | Transformer that can be used to pass data through without any transformation | [config](#passthroughtransformer-sample-configuration) | `p4p`,`p4p_server`, `k2eg`|

#### `SimpleTransformer` Sample configuration
```yaml
input_data_to_model:
  type: "SimpleTransformer"
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
Two keywords expected in the configuration are `varaibles` where one must sepcify the a list of output variables of the transformer and their associated `formula`s (in the example its `x1` and `x2`). The formulas tell us how to transform the input data from the providers to get the model input. `symbols` will be variables gathered from one of the compatible system data providers. All are intialised as `None` and are populated first via `.get()` then `.monitor()` methods of the providers. On each change a transform is executed and the transfomer provides a dictonary of model inputs for example `{'x1':1.2,'x2':3.2}`. `formula` can be any valid [SymPy](https://www.sympy.org/en/index.html) expression.

#### `CAImageTransformer` Sample configuration
```yaml
input_data_to_model:
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
The above provides a way to transform a triplet of an array, x and y ca values into a np array. The `img_ch` is the channel for the image array, `img_x_ch` is the x channel and `img_y_ch` is the y channel. The transformer will wait for all three channels to be updated before transforming the data. The output will be a dictionary with the keys being the `img_ch` and the values being the np array. The x and y channels are not returned `{img_1: np.array, img_2: np.array}`. where `np.array` is a 2D numpy array with shape `(x,y)`.

#### `CompoundTransformer` Sample configuration
```yaml
input_data_to_model:
  type: "CompoundTransformer"
  config:
    transformers:
      transformer_1:
        type: "SimpleTransformer"
        config:
          symbols:
            - "LUME:MLFLOW:TEST_B"
            - "LUME:MLFLOW:TEST_A"
          variables:
            x2:
              formula: "LUME:MLFLOW:TEST_B"
            x1: 
              formula: "LUME:MLFLOW:TEST_A"
      transformer_2:
        type: "CAImageTransfomer"
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
Combines multiple transformers in parallel. The output will be a combined dictionary og model outputs . Example: `{'x1':1.2,'x2':3.2, img_1: np.array, img_2: np.array}`

#### `PassThroughTransformer` Sample configuration
```yaml
output_model_to_data:
  type: "PassThroughTransformer"
  config:
    variables:
      LUME:MLFLOW:TEST_IMAGE: "y_img"
```

### Model
Model layer is compatible with [lume-model](https://github.com/slaclab/lume-model). Currently of `TorchModule` and `BaseModel` are supported. All models have to come from MLflow, with local models coming soon.

See an example notebook containing both `TorchModule` and `BaseModel` being uploaded and registered to MLflow [here](/examples/sample_workflow.ipynb).

## Example YAML configurations

### Example 1
```yaml
deployment:
  type: "continuous" # doesnt do anything at the moment, but will be used to determine the type of deployment
  # other configurations
input_data:
  get_method: "k2eg"
  config:
    variables:
      LUME:MLFLOW:TEST_B:
        proto: pva
        name: LUME:MLFLOW:TEST_B
      LUME:MLFLOW:TEST_A:
        proto: pva
        name: LUME:MLFLOW:TEST_A

input_data_to_model:
  type: "SimpleTransformer"
  config:
    symbols:
      - "LUME:MLFLOW:TEST_B"
      - "LUME:MLFLOW:TEST_A"
    variables:
      x2:
        formula: "LUME:MLFLOW:TEST_B"
      x1: 
        formula: "LUME:MLFLOW:TEST_A"

outputs_model:
  config:
    variables:
      y:
        type: "scalar" # doesnt do anything at the moment, but will be used to determine the type of output

output_model_to_data:
  type: "SimpleTransformer"
  config:
    symbols:
      - "y"
    variables:
      LUME:MLFLOW:TEST_G:
        formula: "y"

output_data_to:
  put_method: "k2eg"
  config:
    variables:
      LUME:MLFLOW:TEST_G:
        proto: pva
        name: LUME:MLFLOW:TEST_G
```

### Example 2
```yaml
deployment:
  type: "continuous"
input_data:
  get_method: "k2eg"
  config:
    variables:
      SOLN:IN20:121:BACT:
        proto: ca
        name: SOLN:IN20:121:BACT
      QUAD:IN20:121:BACT:
        proto: ca
        name: QUAD:IN20:121:BACT
      QUAD:IN20:122:BACT:
        proto: ca
        name: QUAD:IN20:122:BACT
      ACCL:IN20:300:L0A_PDES:
        proto: ca
        name: ACCL:IN20:300:L0A_PDES
      ACCL:IN20:400:L0B_PDES:
        proto: ca
        name: ACCL:IN20:400:L0B_PDES
      ACCL:IN20:300:L0A_ADES:
        proto: ca
        name: ACCL:IN20:300:L0A_ADES
      ACCL:IN20:400:L0B_ADES:
        proto: ca
        name: ACCL:IN20:400:L0B_ADES
      QUAD:IN20:361:BACT:
        proto: ca
        name: QUAD:IN20:361:BACT
      QUAD:IN20:371:BACT:
        proto: ca
        name: QUAD:IN20:371:BACT
      QUAD:IN20:425:BACT:
        proto: ca
        name: QUAD:IN20:425:BACT
      QUAD:IN20:441:BACT:
        proto: ca
        name: QUAD:IN20:441:BACT
      QUAD:IN20:511:BACT:
        proto: ca
        name: QUAD:IN20:511:BACT
      QUAD:IN20:525:BACT:
        proto: ca
        name: QUAD:IN20:525:BACT
      FBCK:BCI0:1:CHRG_S:
        proto: ca
        name: FBCK:BCI0:1:CHRG_S
      CAMR:IN20:186:XRMS:
        proto: ca
        name: CAMR:IN20:186:XRMS
      CAMR:IN20:186:YRMS:
        proto: ca
        name: CAMR:IN20:186:YRMS

input_data_to_model:
  type: "SimpleTransformer"
  config:
    symbols:
      - CAMR:IN20:186:XRMS
      - CAMR:IN20:186:YRMS
      - SOLN:IN20:121:BACT
      - QUAD:IN20:121:BACT
      - QUAD:IN20:122:BACT
      - ACCL:IN20:300:L0A_PDES
      - ACCL:IN20:400:L0B_PDES
      - ACCL:IN20:300:L0A_ADES
      - ACCL:IN20:400:L0B_ADES
      - QUAD:IN20:361:BACT
      - QUAD:IN20:371:BACT
      - QUAD:IN20:425:BACT
      - QUAD:IN20:441:BACT
      - QUAD:IN20:511:BACT
      - QUAD:IN20:525:BACT
      - FBCK:BCI0:1:CHRG_S
    variables:
      distgen:t_dist:length:value:
          formula: "1.8550514181818183" # constant
      distgen:r_dist:sigma_xy:value: 
        formula: "(CAMR:IN20:186:XRMS**2 + CAMR:IN20:186:YRMS**2)**(1/2)" 
      SOL1:solenoid_field_scale:
        formula: "SOLN:IN20:121:BACT" # no transformation just pass the value
      CQ01:b1_gradient:
        formula: "QUAD:IN20:121:BACT"
      SQ01:b1_gradient:
        formula: "QUAD:IN20:122:BACT"
      L0A_phase:dtheta0_deg:
        formula: "ACCL:IN20:300:L0A_PDES"
      L0B_phase:dtheta0_deg:
        formula: "ACCL:IN20:400:L0B_PDES"
      L0A_scale:voltage:
        formula: "ACCL:IN20:300:L0A_ADES"
      L0B_scale:voltage:
        formula: "ACCL:IN20:400:L0B_ADES"
      QA01:b1_gradient:
        formula: "QUAD:IN20:361:BACT"
      QA02:b1_gradient:
        formula: "QUAD:IN20:371:BACT"
      QE01:b1_gradient:
        formula: "QUAD:IN20:425:BACT"
      QE02:b1_gradient:
        formula: "QUAD:IN20:441:BACT"
      QE03:b1_gradient:
        formula: "QUAD:IN20:511:BACT"
      QE04:b1_gradient:
        formula: "QUAD:IN20:525:BACT"
      distgen:total_charge:value:
        formula: "FBCK:BCI0:1:CHRG_S"

outputs_model:
  config:
    variables:
      sigma_x:
        type:"scalar"
      sigma_y:
        type:"scalar"
      sigma_z:
        type:"scalar"
      norm_emit_x:
        type:"scalar"
      norm_emit_y:
        type:"scalar"

output_model_to_data:
  type: "SimpleTransformer"
  config:
    symbols:
      - sigma_x
      - sigma_y
      - sigma_z
      - norm_emit_x
      - norm_emit_y
    variables:
      LUME:MLFLOW:SIGMA_X:
        type: ca
        formula: "sigma_x"
      LUME:MLFLOW:SIGMA_Y:
        type: ca
        formula: "sigma_y"
      LUME:MLFLOW:SIGMA_Z:
        type: ca
        formula: "sigma_z"
      LUME:MLFLOW:NORM_EMIT_X:
        type: ca
        formula: "norm_emit_x"
      LUME:MLFLOW:NORM_EMIT_Y:
        type: ca
        formula: "norm_emit_y"
      LUME:MLFLOW:EXAMPLE:COMBINED:
        type: ca
        formula: "(sigma_x**2 + sigma_y**2)**(1/2)"
    
output_data_to:
  put_method: "k2eg"
  config:
    variables:
      LUME:MLFLOW:SIGMA_X:
        proto: pva
        name: LUME:MLFLOW:SIGMA_X
      LUME:MLFLOW:SIGMA_Y:
        proto: pva
        name: LUME:MLFLOW:SIGMA_Y
      LUME:MLFLOW:SIGMA_Z:
        proto: pva
        name: LUME:MLFLOW:SIGMA_Z
      LUME:MLFLOW:NORM_EMIT_X:
        proto: pva
        name: LUME:MLFLOW:NORM_EMIT_X
      LUME:MLFLOW:NORM_EMIT_Y:
        proto: pva
        name: LUME:MLFLOW:NORM_EMIT_Y
      LUME:MLFLOW:EXAMPLE:COMBINED:
        proto: pva
        name: LUME:MLFLOW:EXAMPLE:COMBINED
```
This example is a working deployment for [lcls-cu-in-nn](https://github.com/t-bz/lcls_cu_injector_nn_model) model. The output channels are live and can be inspected using `pvget` or `pvmonitor` commands.

### Example 3
This is based on the image example 
```yaml
deployment:
  type: "continuous"
  # other configurations
input_data:
  get_method: "k2eg"
  config:
    variables:
      CAMR:IN20:186:IMAGE:
        proto: ca
        name: CAMR:IN20:186:IMAGE
      CAMR:IN20:186:N_OF_ROW:
        proto: ca
        name: CAMR:IN20:186:N_OF_ROW
      CAMR:IN20:186:N_OF_COL:
        proto: ca
        name: CAMR:IN20:186:N_OF_COL
      
input_data_to_model:
      type: "CAImageTransfomer"
      config:
        variables:
          image:
            img_ch: CAMR:IN20:186:IMAGE
            img_x_ch: CAMR:IN20:186:N_OF_COL
            img_y_ch: CAMR:IN20:186:N_OF_ROW
outputs_model:
  config:
    variables:
      y_max:
        type: "scalar"
      y_min:
        type: "scalar"
      y_mean:
        type: "scalar"
      y_std:
        type: "scalar"
      y_img:
        type: "image"
output_model_to_data:
  type: "CompoundTransformer"
  config:
    transformers:
      t_1:
        type: "SimpleTransformer"
        config:
          symbols:
            - "y_max"
            - "y_min"
            - "y_mean"
            - "y_std"
          variables:
            LUME:MLFLOW:TEST_Y_MAX:
              formula: "y_max"
            LUME:MLFLOW:TEST_Y_MIN:
              formula: "y_min"
            LUME:MLFLOW:TEST_Y_MEAN:
              formula: "y_mean"
            LUME:MLFLOW:TEST_Y_STD:
              formula: "y_std"
      t_2:
        type: "PassThroughTransformer"
        config:
          variables:
            LUME:MLFLOW:TEST_IMAGE: "y_img"

output_data_to:
  put_method: "p4p_server"
  config:
    variables:
      LUME:MLFLOW:TEST_Y_MAX:
        proto: pva
        name: LUME:MLFLOW:TEST_Y_MAX
      LUME:MLFLOW:TEST_Y_MIN:
        proto: pva
        name: LUME:MLFLOW:TEST_Y_MIN
      LUME:MLFLOW:TEST_Y_MEAN:
        proto: pva
        name: LUME:MLFLOW:TEST_Y_MEAN
      LUME:MLFLOW:TEST_Y_STD: # implicitly type: "scalar"
        proto: pva
        name: LUME:MLFLOW:TEST_Y_STD
      LUME:MLFLOW:TEST_IMAGE:
        type: "image"
        image_size:
          x: 640
          y: 480
        proto: pva
        name: LUME:MLFLOW:TEST_IMAGE
```

Then running from command line rather than deplyment:
```bash
model_manager -n "image_model" -v "16" -e cred.json -c ./examples/image/pv_mapping.yaml -p"
```
![gif example of the terminal result](/images/terminal_example.gif)

and viewing the result in pydm using (image.ui):

![model output](/images/result.gif)

## Installation

Python `3.11.x` recommended.

```bash
pip install -r reqirements.txt
cd model_manager
pip install .
```
for development:

```bash
pip install -r reqirements.txt
cd model_manager
pip install -e .
```

Or conda environment:

```bash
conda env create -f mlflow_env.yml
conda activate mlflow
 
cd model_manager
pip install . # or pip install -e .
```

## Usage

```bash
model_manager -n <model_name> -v <model_version> -e <env.json> -c <configs.yaml>
```
Where:

- `model_name` is the name of the registered model in MLflow
- `model_version` is the version of the model to be used
- `env.json` is a json file containing the environment variables for the model, optional
- `pv_mappings.yaml` is a yaml file containing the full configuration for the system, transformation and model layers, optional, provided that the registered model has a `pv_mappings.yaml` file in the MLflow model directory.

For non-mlflow models:

```bash
model_manager -l /path/to/model_and_factory -e <env.json> -c <configs.yaml>
```
See image example for how to set up model factory and model for local use.

#### List of flags:
- `-n` or `--model_name` : Name of the model in MLflow
- `-v` or `--model_version` : Version of the model in MLflow
- `-e` or `--env` : Path to the env.json file
- `-c` or `--configs` : Path to the configs.yaml file
- `-p` or `--publish` : Publish data to output module, off by default.
- `-d` or `--debug` : Debug mode, off by default.
- `-l` or `--local` : Local mode, you need to supply a model path and a model factory class. Alternative to using MLflow. you need to provide a `-c` config as well. 

`env.json` is a json file containing the environment variables for the model. The file should look like this:
```json
{
    "MLFLOW_TRACKING_USERNAME": "username",
    "MLFLOW_TRACKING_PASSWORD": "password",
    "MLFLOW_ENABLE_SYSTEM_METRICS_LOGGING": "true",
    "AWS_DEFAULT_REGION": "eu-west-3",
    "AWS_REGION": "eu-west-3",
    "AWS_ACCESS_KEY_ID": "key-id",
    "AWS_SECRET_ACCESS_KEY": "secret-key"
    "MLFLOW_S3_ENDPOINT_URL": "http://my-s3-endpoint:myport",
    "MLFLOW_TRACKING_URI": "http://my-mlflow-server"
    "K2EG_PYTHON_CONFIGURATION_PATH_FOLDER" : "/path/to/k2eg/config_folder"
}
```
This is optional and all of the above can be set as environment variables. But working on windows can be a pain so this is a workaround.

If you are using mlflow locally, you dont have to set anything just run mlflow ui in the terminal and the model manager will use the local server.

## Deployment

This section outlines how to deploy the model on various systems.

### General Notes and Pre-flight checks

- [ ] Model is `LUMEBaseModel`, `TorchModule` or a custom model type that is compatible with the model manager. i.e. The model registered using pyfunc wrapper has a `.get_model()` method and the model itself has a `.evaluate()` method. See `examples/image_examples.ipynb` for an example of a custom model.
- [ ] Model is in MLflow
- [ ] Model is registered in MLflow
- [ ] `pv_mappings.yaml` file is in the MLflow model_name directory.
- [ ] Test configuration locally using `model_manager -n <model_name> -v <model_version> -e <env.json> -c <configs.yaml> -d`
     - If not working check if you have valid PV names and that your interfaces are in contact with the PV servers
     - Check on multiple machines if possible, you may also test inside `matindocker/lumeservicesdeployment:latest` container.

Note: when the model is registered you have to ensure that you have a valid `pv_mappings.yaml` file in a directory with the __same name as your registered model name__! .i.e if your model is named `my_model` then the directory should be `my_model` and the `pv_mappings.yaml` file should be in that directory. As shown in figure below: 
![mlflow](/images/capture_1.PNG)

### SLAC/S3DF

At SLAC the models can be deployed directly from the MLflow web UI. Once a model has been registered and saved to the MLflow server it can be deployed by setting the registered models tag `deployment_type` to `prod` or `continuous` (latter is becoming legacy). Within a minute the model will be deployed to the S3DF kubernates container and will be available for use. Additional fields relating to the deployment will be populated as shown below: 
![deployment info](/images/capture_2.PNG)
Note the timestamp is in UTC.

In order to terminate a deployment the `deployment_terminate` tag should be set to `true`. This will terminate the deployment and the model will no longer be available for use.
The model page should update to reflect that the model is no longer deployed: 
![deployment info](/images/capture_3.PNG)

### ISIS

TODO

### Local/Daemon (recommended for evaluation and testing)

Deploying on local machines as is as simple as running 

```bash
model_manager -n <model_name> -v <model_version> -e <env.json>
# optionaly you might wanna specify -c <configs.yaml> locally
# -p flag is optional, it will publish the output to the output module
```
Using local model getter is also possible, but not recommended for production deployments. 

```bash
model_manager -l /path/to/model_and_factory -e <env.json> -c <configs.yaml>
```

You can append `&` to the end of the command to run it in the background.

### Known issues

- [ ] ~~`p4p_server` cannot be an input to the transformation layer.~~ Fix implemented needs more testing to tick off.
- [ ] `k2eg` will not work correctly if the PVs or CAs are not available.
- [ ] `p4p_server` does not publish out of s3df, so deployments using it have to be local or daemon ones. Such as the image example untill this is addressed.

### Future work
- [ ] Batch processing for models that require it.
- [x] Local model getter for easier testing, specific deployment.
- [ ] Rate limiting for live deployments.
- [ ] Visualisation of the data flow and data webpages.
- [ ] Slack bot for deployment status and workflow building help. As well as help with spinning up and terminating deployments.
- [ ] Better abstract classes for the system, transformation and model layers.
- [ ] Compound interfaces for the system layer.




