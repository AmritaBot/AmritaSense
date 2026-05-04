from amrita_core.hook.matcher import Depends

from amrita_sense.runtime.workflow import WorkflowPC


def _ptr_dp(pt: WorkflowPC):
    return pt


POINTER_DEPENDS = Depends(_ptr_dp)

__all__ = ("POINTER_DEPENDS",)
