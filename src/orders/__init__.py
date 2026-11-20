"""Order service: the agent-editable application code checked by the architecture contract.

Layers:

- ``orders.controllers``: request decoding and response mapping only.
- ``orders.application``: business policy (pricing, discount eligibility) and
  the only layer that talks to repositories.
- ``orders.infrastructure``: storage. Here, an in-memory repository.
- ``orders.domain``: plain data shared by every layer.
- ``orders.wiring``: the composition root that assembles the layers.

The rule the sensor enforces: controller modules may not import infrastructure
modules directly. Controller -> application service -> repository is legal.
"""
