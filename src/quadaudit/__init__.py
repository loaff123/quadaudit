"""Auditable, exact-reference quadrature experiments (research preview)."""

__version__ = "0.1.0a1"
from .model import Case, Segment
from .oracle import Reference, adjudicate

__all__ = ["Case", "Segment", "Reference", "adjudicate"]
