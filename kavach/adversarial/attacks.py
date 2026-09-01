from dataclasses import dataclass


@dataclass(frozen=True)
class Attack:
    attack_id: str
    name: str
    mechanism: str
    blocked_by: tuple[str, ...]


ATTACKS = (
    Attack("A-1", "Direct injection in description", "Instruction text in product description", ("GR-1", "GR-2")),
    Attack("A-2", "Injection in negotiation reply", "Instruction text in seller counter-offer", ("GR-1", "GR-2")),
    Attack("A-3", "Bait and switch", "Cheap at discovery, higher at checkout", ("GR-9",)),
    Attack("A-4", "False spec claim", "Description claims a constraint that structured attributes deny", ("GR-7",)),
    Attack("A-5", "Budget extraction", "Seller probes for the buyer ceiling", ("GR-1", "GR-2")),
    Attack("A-6", "Sybil review flood", "Synthetic five-star reviews", ("GR-2", "GR-7")),
    Attack("A-7", "Cart injection", "Adds a product never discovered", ("GR-8",)),
    Attack("A-8", "Loop exhaustion", "Infinite counter-offers", ("GR-11",)),
)
