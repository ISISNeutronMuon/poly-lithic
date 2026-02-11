Configuration Guide
===================

This page explains how to configure your project.

Overview
--------
Configuration is handled through YAML files. Each file has two top-level
sections: ``deployment`` and ``modules``.

Deployment Section
------------------
The ``deployment`` section describes the deployment type and global settings.

.. code-block:: yaml

   deployment:
     type: "continuous"   # deployment type (continuous is the default)
     rate: 0.25           # clock tick interval in seconds

Modules Section
---------------
The ``modules`` section defines all nodes in the processing graph. Each module
has these common fields:

.. list-table::
   :header-rows: 1
   :widths: 15 10 75

   * - Field
     - Type
     - Description
   * - ``name``
     - string
     - Name used to identify the module in the graph
   * - ``type``
     - string
     - Module class identifier, e.g. ``interface.p4p_server``,
       ``transformer.SimpleTransformer``, ``model.SimpleModel``
   * - ``pub``
     - string
     - Topic that the module publishes its outputs to
   * - ``sub``
     - list[string]
     - Topics the module subscribes to for input data. The special topic
       ``update`` (or ``get_all``) triggers an interface to run ``get_many``
       on each clock tick.
   * - ``module_args``
     - any
     - Optional arguments passed to the module observer
   * - ``config``
     - dict
     - Module-specific configuration (see interface, transformer, and model
       docs for details)

Module-specific Configuration
-----------------------------

Interface modules
~~~~~~~~~~~~~~~~~
Each interface type has its own ``config`` block. Refer to the
:doc:`interfaces` guide for details on:

- ``p4p`` / ``p4p_server`` — EPICS PVA variables with ``proto``, ``name``,
  ``type``, ``default`` fields
- ``k2eg`` — Kafka-to-EPICS gateway variables
- ``fastapi_server`` — REST API with ``host``, ``port``, ``start_server``,
  ``input_queue_max``, ``output_queue_max``, ``cors_origins``, and typed
  ``variables`` (with ``mode``, ``type``, ``default``, ``length``,
  ``image_size`` fields)
  (experimental)

Transformer modules
~~~~~~~~~~~~~~~~~~~
See the :doc:`transformers` guide for ``SimpleTransformer``,
``CAImageTransformer``, ``CompoundTransformer``, and
``PassThroughTransformer`` configuration.

Model modules
~~~~~~~~~~~~~
Model config specifies a ``type`` (e.g. ``LocalModelGetter``,
``MLflowModelGetter``) and ``args`` for the model getter class. See the
README for full examples.