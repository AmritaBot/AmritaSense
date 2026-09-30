#  pyright: reportDeprecated=false
#  Re-exporting the deprecated instruction names below is the whole point of the
#  shim layer; users importing them *do* get the warning.
from ._deprecated import (
    GOTO,
    INTERRUPT,
    INTERRUPT_INTO,
    INTERRUPT_KEEP_CTX,
    INTERRUPT_RET,
    PUSH_AND_GOTO,
    PUSH_STACK,
    RET_FAR,
)
from .alias import ALIAS
from .batch import BATCH_RUN
from .enum import AUTO_PREFIX, AUTO_TAGS, BuiltinTags
from .func_block import FN, FUN_BLOCK, INTER_FN
from .if_clause import IF
from .interrupt import INT, IRET, POP_CONTEXT, PUSH_CONTEXT
from .jump import JMP
from .loop.do_while import DO
from .loop.while_clause import WHILE
from .native import BREAK_LOOP, NATIVE_DO, NATIVE_IF, NATIVE_WHILE
from .ret2 import CALL, PUSH_RET, RET
from .subprogram import ARCHIVED_NODES, INVOKE
from .trigger_event import TRIGGER_EVENT
from .try_catch import Try
from .workfl_ctrl import NOP, RESET, SUSPEND

#  The first import block is the deprecated-name shim layer (see `_deprecated`):
#  the names stay importable so existing code keeps working until 2.0.

__all__ = (
    "ALIAS",
    "ARCHIVED_NODES",
    "AUTO_PREFIX",
    "AUTO_TAGS",
    "BATCH_RUN",
    "BREAK_LOOP",
    "CALL",
    "DO",
    "FN",
    "FUN_BLOCK",
    "GOTO",
    "IF",
    "INT",
    "INTERRUPT",
    "INTERRUPT_INTO",
    "INTERRUPT_KEEP_CTX",
    "INTERRUPT_RET",
    "INTER_FN",
    "INVOKE",
    "IRET",
    "JMP",
    "NATIVE_DO",
    "NATIVE_IF",
    "NATIVE_WHILE",
    "NOP",
    "POP_CONTEXT",
    "PUSH_AND_GOTO",
    "PUSH_CONTEXT",
    "PUSH_RET",
    "PUSH_STACK",
    "RESET",
    "RET",
    "RET_FAR",
    "SUSPEND",
    "TRIGGER_EVENT",
    "WHILE",
    "BuiltinTags",
    "Try",
)
