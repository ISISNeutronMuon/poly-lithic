Transformers Guide
==================

This page explains how to use transformers in your project.

Overview
--------
Transformers convert message payloads from one shape to another before model
evaluation or interface publication.

All transformer modules follow the
:class:`~poly_lithic.src.transformers.BaseTransformer.BaseTransformer` contract
and expose:

- ``handler(pv_name, value)`` to receive incoming struct data
- ``transform()`` to produce output values

Available Transformers
----------------------

- :class:`~poly_lithic.src.transformers.BaseTransformers.SimpleTransformer`
- :class:`~poly_lithic.src.transformers.BaseTransformers.CAImageTransfomer`
- :class:`~poly_lithic.src.transformers.BaseTransformers.PassThroughTransformer`
- :class:`~poly_lithic.src.transformers.CompoundTransformer.CompoundTransformer`

Transformer Configs
-------------------

.. list-table::
   :header-rows: 1
   :widths: 24 46 30

   * - Module
     - Description
     - YAML reference
   * - ``SimpleTransformer``
     - Scalar/array formula transform from input symbols to output variables
     - See sample below
   * - ``CAImageTransformer``
     - Reconstruct image arrays from flattened channel + X + Y inputs
     - See sample below
   * - ``PassThroughTransformer``
     - Relabel and forward values without numeric transformation
     - See sample below
   * - ``CompoundTransformer``
     - Run multiple transformers in one module
     - See sample below

Metadata Propagation
--------------------

Transformer outputs may be either plain values or structured payloads with
``value`` and additional fields:

- ``PassThroughTransformer`` preserves non-``value`` fields (for example
  ``alarm``, ``timestamp``, ``metadata``) when they are present in input
  structs.
- ``SimpleTransformer`` preserves non-``value`` fields only for direct-symbol
  formulas (for example ``OUT = IN``). Computed formulas emit value-only output.
- ``TransformerObserver`` forwards structured outputs unchanged and wraps plain
  outputs as ``{"value": ...}``.

This makes direct pass-through paths suitable for carrying alarm payloads across
transformer stages.

``SimpleTransformer`` Sample Configuration
------------------------------------------

.. code-block:: yaml

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

``CAImageTransformer`` Sample Configuration
-------------------------------------------

.. code-block:: yaml

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

``PassThroughTransformer`` Sample Configuration
-----------------------------------------------

.. code-block:: yaml

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

``CompoundTransformer`` Sample Configuration
--------------------------------------------

.. caution::

   This module may be deprecated in the future because the pub-sub model can
   replace most compound-transformer use cases.

.. code-block:: yaml

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
