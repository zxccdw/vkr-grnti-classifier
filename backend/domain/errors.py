from __future__ import annotations


class DomainError(Exception):
    pass


class NodeAlreadyExists(DomainError):
    pass


class NodeNotFound(DomainError):
    pass


class EdgeAlreadyExists(DomainError):
    pass


class EdgeNotFound(DomainError):
    pass


class InvalidDepth(DomainError):
    pass
