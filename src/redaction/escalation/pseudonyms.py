"""Stand-ins for confidential values: consistent pseudonyms, or one marker per type.

Consistent pseudonyms give each distinct value its own stand-in (Customer A, Customer B), so a
reader can still tell two redacted customers apart. Markers give every value of a type the same
text, which erases that identity. Used by the marker ablation and the pseudonymized
text-redaction policy.
"""

from __future__ import annotations

from typing import Final

from redaction.core.models import Scenario, SecretType
from redaction.core.registry import redaction_marker

PSEUDONYMS: Final[dict[SecretType, str]] = {
    SecretType.LR_SCHEDULE: "schedule S1",
    SecretType.DATA_MIX: "mix M1",
    SecretType.CUSTOMER_NAME: "Customer A",
    SecretType.EMPLOYEE_NAME: "Employee A",
    SecretType.OPTIMIZER: "optimizer O1",
    SecretType.PARAMETER_SCALE: "size S1",
    SecretType.ARCHITECTURE: "architecture A1",
    SecretType.DATA_VENDOR: "Vendor A",
    SecretType.CODENAME: "Project A",
    SecretType.DELIBERATION: "the decision recorded in minutes M1",
    SecretType.COMPUTE_FOOTPRINT: "allocation C1",
    SecretType.RELEASE_DATE: "release window R1",
}


def nth_pseudonym(secret_type: SecretType, k: int) -> str:
    """The k-th distinct stand-in for a type: Customer A, Customer B; allocation C1, C2."""
    base = PSEUDONYMS[secret_type]
    if k == 0:
        return base
    if base[-1].isdigit():
        return f"{base[:-1]}{int(base[-1]) + k}"
    return f"{base[:-1]}{chr(ord(base[-1]) + k)}"


def stand_ins(scenario: Scenario, *, consistent: bool) -> dict[str, str]:
    """Replacement text per confidential value.

    Consistent stand-ins give each distinct value of a type its own pseudonym, so two customers
    stay two customers. Markers are not consistent: every value of a type gets the same marker.
    """
    seen: dict[SecretType, int] = {}
    out: dict[str, str] = {}
    for secret in scenario.redactable():
        k = seen.get(secret.secret_type, 0)
        seen[secret.secret_type] = k + 1
        out[secret.value] = (
            nth_pseudonym(secret.secret_type, k)
            if consistent
            else redaction_marker(secret.secret_type)
        )
    return out
