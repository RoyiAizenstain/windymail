"""What a check returns: a finding ID from the catalog plus optional detail values."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    id: str
    # Normalized technical values only (ADR-017); the engine drops anything else.
    values: tuple[str, ...] = ()
