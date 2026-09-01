from .attacks import ATTACKS

POPULATIONS = [
    {"name": "clean", "attack_id": None},
    *[{"name": attack.name.lower().replace(" ", "_"), "attack_id": attack.attack_id} for attack in ATTACKS],
]

__all__ = ["POPULATIONS"]
