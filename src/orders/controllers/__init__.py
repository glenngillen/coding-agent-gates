"""HTTP-style controllers: decode requests, call the application service, map responses.

Architecture rule (enforced by the import contract in ``.importlinter``):
controller modules must not import ``orders.infrastructure`` directly.
"""
