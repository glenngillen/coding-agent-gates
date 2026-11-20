"""Order service: customers, a product catalogue, stock and orders.

Layers:

- ``orders.controllers``: request decoding and response mapping.
- ``orders.application``: business policy and the only layer that uses storage.
- ``orders.infrastructure``: in-memory storage standing in for a database.
- ``orders.domain``: plain data shared by every layer.
- ``orders.wiring``: the composition root that assembles the layers.
"""
