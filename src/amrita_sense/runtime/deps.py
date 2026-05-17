from amrita_sense.runtime.workflow import WorkflowInterpreter
from amrita_sense.types import PointerVector


def POINTER_DEPENDS(pt: WorkflowInterpreter):
    """Dependency factory that returns the current WorkflowInterpreter instance.

    This function is designed to be used with Depends() to inject the current
    workflow interpreter into a node function parameter. It allows nodes to
    access the runtime context and perform operations like jumping, calling
    subroutines, or accessing workflow state.

    Args:
        pt: The WorkflowInterpreter instance (automatically provided by dependency injection)

    Returns:
        The same WorkflowInterpreter instance passed as input

    Example:
        ```python
        @Node()
        def my_node(pc: WorkflowInterpreter = Depends(POINTER_DEPENDS)):
            # Use pc to interact with the workflow runtime
            pass
        ```
    """
    return pt


def FAR_OFFSET(where: str):
    """Creates a dependency factory for calculating multi-dimensional offset vectors.

    This function returns a factory that computes the far offset (multi-dimensional
    pointer vector difference) between the current execution pointer and a target
    node identified by its alias. The result can be used for complex navigation
    in nested workflow structures.

    Args:
        where: The alias string of the target node to calculate offset from

    Returns:
        A factory function that returns PointerVector when called with WorkflowInterpreter

    Example:
        ```python
        @Node()
        def my_node(offset: PointerVector = Depends(FAR_OFFSET("target_alias"))):
            # offset contains the multi-dimensional vector difference
            pass
        ```
    """

    def inner(pc: WorkflowInterpreter) -> PointerVector:
        now_addr = pc._pointer
        return now_addr - PointerVector(pc.find_addr_alias(where))

    return inner


def NEAR_OFFSET(where: str):
    """Creates a dependency factory for calculating single-level offset integers.

    This function returns a factory that computes the near offset (single integer
    difference) between the current execution pointer and a target node within
    the same scope level. It validates that both addresses are at the same
    nesting level and raises RuntimeError if they are not.

    Args:
        where: The alias string of the target node to calculate offset from

    Returns:
        A factory function that returns int when called with WorkflowInterpreter

    Raises:
        RuntimeError: If the target node is not at the same nesting level as current pointer

    Example:
        ```python
        @Node()
        def my_node(offset: int = Depends(NEAR_OFFSET("target_alias"))):
            # offset is the relative position within the current chunk
            pass
        ```
    """

    def inner(pc: WorkflowInterpreter) -> int:
        now_addr = pc._pointer
        delta = now_addr - PointerVector(pc.find_addr_alias(where))
        if not all(i == 0 for idx, i in enumerate(delta) if idx < (len(delta) - 1)):
            raise RuntimeError(f"Far offset {delta} is not assign able to near offset")
        return delta[-1]

    return inner


def ADDR(where: str):
    """Creates a dependency factory for retrieving absolute address vectors.

    This function returns a factory that provides the absolute address (PointerVector)
    of a target node identified by its alias. This is useful when you need to
    store or reference the complete address path to a specific node in the workflow.

    Args:
        where: The alias string of the target node to get address for

    Returns:
        A factory function that returns PointerVector when called with WorkflowInterpreter

    Example:
        ```python
        @Node()
        def my_node(address: PointerVector = Depends(ADDR("target_alias"))):
            # address contains the full absolute path to the target node
            pass
        ```
    """

    def inner(pc: WorkflowInterpreter) -> PointerVector:
        return PointerVector(pc.find_addr_alias(where))

    return inner


__all__ = ("ADDR", "FAR_OFFSET", "NEAR_OFFSET", "POINTER_DEPENDS")
