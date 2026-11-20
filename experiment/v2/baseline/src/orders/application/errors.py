"""Errors raised by application services and mapped to responses by controllers."""


class NotFound(LookupError):
    """The requested entity does not exist."""


class OrderNotFound(NotFound):
    """No order exists with the requested id."""


class CustomerNotFound(NotFound):
    """No customer exists with the requested id."""


class ProductNotFound(NotFound):
    """No product exists with the requested SKU."""


class Conflict(ValueError):
    """The request is valid but conflicts with the current state."""
