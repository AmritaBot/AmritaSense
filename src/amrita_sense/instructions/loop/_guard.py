"""Compile-time guards shared by the `call_sub`-based loop clauses."""

from amrita_sense.node.abc_base import AbstractComposeOriginal


def reject_composition_body(body: object, loop: str) -> None:
    """Reject a multi-node loop body.

    `WHILE` and `DO-WHILE` enter the body through `call_sub`, which executes
    exactly one node.  A composition placed there is entered but never
    advanced, so only its first child would run — silently.  Single nodes
    (including jump-based self-compiled instructions such as `Try`) are fine;
    multi-node bodies belong to `NATIVE_WHILE` / `NATIVE_DO`.
    """
    if isinstance(body, AbstractComposeOriginal):
        raise TypeError(
            f"{loop} body must be a single node, got {type(body).__name__}. "
            "A call_sub-based loop enters its body with a single call, so a "
            "composition would silently run only its first child. "
            "Use NATIVE_WHILE / NATIVE_DO for a multi-node body."
        )
