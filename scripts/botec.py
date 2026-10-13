"""Back-of-the-envelope compute budget for both proposals.

Run with `uv run python scripts/botec.py`. Prices are list prices per million tokens (checked
2026-10-13); token counts are estimates to be replaced with measured values after the first
real-model dev run. See the "Compute Budget Estimate" Google Doc for the write-up.
"""

from __future__ import annotations

from dataclasses import dataclass

# model: (input, output, cache hit, cache write) in $ per million tokens
PRICE = {
    "sonnet": (2.00, 10.00, 0.10, 2.50),
    "opus": (4.00, 20.00, 0.20, 5.00),
    "haiku": (0.10, 0.50, 0.01, 0.125),
    "terra": (2.00, 12.00, 0.20, 2.00),
}
WASTE, CONTINGENCY, BATCH_DISCOUNT = 0.15, 0.25, 0.5
THINK_MULT = 1.0  # sensitivity: 0 = no reasoning, 3 = close to default effort
TOKEN_MULT = 1.0  # sensitivity: 1.5 = all non-reasoning tokens 50% higher


@dataclass(frozen=True)
class Call:
    model: str
    inp: int
    out: int
    think: int

    def cost(self, model: str | None = None) -> float:
        pi, po, *_ = PRICE[model or self.model]
        visible = (self.inp * pi + self.out * po) * TOKEN_MULT
        return (visible + self.think * THINK_MULT * po) / 1e6


AUDITOR = Call("sonnet", 3000, 900, 1500)
ADVOCATE = Call("sonnet", 1800, 600, 1000)
EXECUTOR = Call("sonnet", 2400, 500, 1000)
JUDGE_VIOLATION = Call("terra", 700, 150, 500)
JUDGE_SECRETS = Call("sonnet", 1600, 350, 700)
INTEGRITY = Call("haiku", 500, 20, 0)
GENERATE = (Call("opus", 2500, 3000, 2000), Call("sonnet", 4000, 800, 1000))


def p1_unit(policies=("text", "self", "ctx"), shared=True, model=None) -> float:
    """One scenario, one seed. Shared calls are paid once and cached across policies."""

    def c(call: Call) -> float:
        return call.cost(model)

    total = c(AUDITOR) + c(JUDGE_VIOLATION) + 2 * c(JUDGE_SECRETS) if shared else 0.0
    for policy in policies:
        total += c(JUDGE_VIOLATION) + c(JUDGE_SECRETS)
        if policy in ("self", "ctx"):
            total += c(ADVOCATE) + c(INTEGRITY)
        if policy == "ctx":
            total += c(EXECUTOR)
    return total


def p2_conversation(n=40, redacted=True, model="sonnet", think=300, checkpoints=(5, 10, 20, 40)):
    """One detective conversation with prompt caching on the growing history."""
    case, q, a, det_sys, red_sys = 6000, 80, 300, 600, 500
    pi, po, hit, write = PRICE[model]
    think *= THINK_MULT
    cost = 0.0
    for t in range(n):
        hist = t * (q + a)
        cost += (det_sys + hist) * hit + (q + a) * write + (q + think) * po  # detective
        cost += (case + hist) * hit + q * pi + (a + think) * po  # responder
        if redacted:
            cost += (red_sys + a) * pi + (a + think) * po  # memoryless redactor
    for k in checkpoints:  # MC guesses, explanation and verdict
        cost += 3 * ((det_sys + k * (q + a)) * hit + 200 * pi + (400 + think) * po)
    return cost / 1e6


def p2_short(checkpoints: tuple[int, ...]) -> float:
    """A redacted plus an unredacted conversation of up to 20 questions."""
    return p2_conversation(20, checkpoints=checkpoints) + p2_conversation(
        20, False, checkpoints=checkpoints
    )


def main() -> None:
    gen = sum(call.cost() for call in GENERATE)
    unit = p1_unit()
    mvp_unit = unit - AUDITOR.cost()
    prior = 3 * (800 * 2 + 700 * 10) / 1e6
    judge = 4 * Call("haiku", 1500, 50, 0).cost()
    case = p2_conversation() + p2_conversation(redacted=False) + prior + judge
    r2 = p1_unit(("self", "ctx"), shared=False)
    r3 = p1_unit(("text", "ctx"))
    r5 = (
        AUDITOR.cost()
        + p1_unit(("ctx",), shared=False)
        + JUDGE_VIOLATION.cost()
        + JUDGE_SECRETS.cost()
    )
    r6 = 2 * (EXECUTOR.cost() + JUDGE_VIOLATION.cost() + JUDGE_SECRETS.cost() + INTEGRITY.cost())
    bound = 200 * 2 * (JUDGE_SECRETS.cost("opus") + JUDGE_VIOLATION.cost("opus"))
    opus_detective = (p2_conversation(model="opus") - p2_conversation()) * 0.45
    d3_d7 = 60 * (
        p2_conversation() * 1.45  # D3: redactor reads the whole conversation
        + p2_conversation()
        + 40 * INTEGRITY.cost()  # D4: question monitor
        + case
        + gen  # D5: new case files
        + case  # D6: lab-aligned responder
        + case
        + opus_detective  # D7: Opus detective
    )
    d2 = 60 * (p2_short((5, 10, 20)) + prior + judge)
    # Each item: name, then minimum, expected and maximum cost, then whether it can be batched.
    items = [
        ("Scenario generation (450 attempts)", 450 * gen, 450 * gen, 450 * gen, True),
        ("P1 MVP", 160 * mvp_unit, 160 * mvp_unit, 160 * mvp_unit, False),
        ("Prompt iteration on dev", 800 * unit, 800 * unit, 1200 * unit, False),
        ("Val confirmation", 240 * unit, 240 * unit, 360 * unit, True),
        ("R1 baseline", 720 * unit, 720 * unit, 720 * unit, True),
        ("R2 cover-up", 720 * r2, 720 * r2, 720 * r2, True),
        ("R3 evidence overlap", 0, 240 * gen + 720 * r3, 240 * gen + 720 * r3, True),
        ("Bound check", 0, bound, bound, True),
        ("R4-R6", 0, 0, 189 * r2 / 2 + 720 * r5 + 720 * r6, True),
        ("R7 Opus everywhere", 0, 0, 720 * p1_unit(model="opus"), True),
        ("P2 MVP", 30 * p2_short((5, 20)), 30 * p2_short((5, 20)), 30 * p2_short((5, 20)), False),
        ("P2 D1", 60 * case, 180 * case, 180 * case, False),
        ("P2 D2", 0, d2, d2, False),
        ("P2 D3-D7", 0, 0, d3_d7, False),
        ("Full rerun", 0, 0, 720 * unit + 720 * r2 + 60 * case, True),
    ]
    mult = (1 + WASTE) * (1 + CONTINGENCY)
    print(f"P1 unit ${unit:.3f}; test run ${720 * unit:.0f}; P2 case file ${case:.2f}")
    for name, low, mid, high, _ in items:
        print(f"{name:36s}{low:9.0f}{mid:9.0f}{high:9.0f}")
    for label, use_batch in (("list", False), ("batch", True)):
        totals = [
            mult
            * sum(item[tier] * (BATCH_DISCOUNT if use_batch and item[4] else 1.0) for item in items)
            for tier in (1, 2, 3)
        ]
        print(f"TOTAL ({label}): " + ", ".join(f"${t:,.0f}" for t in totals))


if __name__ == "__main__":
    main()
