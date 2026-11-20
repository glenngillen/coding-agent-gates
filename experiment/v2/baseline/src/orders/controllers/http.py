"""Shared response type and request-decoding helpers for controllers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Response:
    status: int
    body: dict[str, Any]


class InvalidRequest(ValueError):
    pass


def bad_request(exc: Exception) -> Response:
    return Response(400, {"error": str(exc)})


def not_found(what: str) -> Response:
    return Response(404, {"error": f"{what} not found"})


def conflict(exc: Exception) -> Response:
    return Response(409, {"error": str(exc)})


def require_str(request: dict[str, Any], field: str) -> str:
    value = request.get(field)
    if not isinstance(value, str) or not value:
        raise InvalidRequest(f"{field} must be a non-empty string")
    return value


def require_positive_int(value: Any, field: str) -> int:
    if type(value) is not int or value < 1:
        raise InvalidRequest(f"{field} must be a positive integer")
    return value


def require_non_negative_int(value: Any, field: str) -> int:
    if type(value) is not int or value < 0:
        raise InvalidRequest(f"{field} must be a non-negative integer")
    return value
