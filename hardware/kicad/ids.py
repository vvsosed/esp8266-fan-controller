"""Deterministic UUIDs for the generated KiCad files, so a regeneration changes nothing it needn't."""
import uuid

ROOT = uuid.UUID("5e1f9c84-7f0a-4b2e-8d31-0fa0c0a7e01a")     # the root sheet


def sym(ref):
    """UUID of the schematic symbol with this reference."""
    return str(uuid.uuid5(ROOT, "sym:" + ref))


def path(ref):
    """The KIID path a footprint carries to link it to its symbol."""
    return f"/{ROOT}/{sym(ref)}"


def other(kind, i):
    """UUID for the i-th wire, label, junction or other item of a kind."""
    return str(uuid.uuid5(ROOT, f"{kind}:{i}"))
