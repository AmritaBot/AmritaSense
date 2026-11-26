"""Native 分支／循环的条件位类型约束。

条件在布局里只占一个地址槽（IF 的 call_offset、WHILE 的 condi_offset），
传组合或自编译指令会让后续偏移错位，所以声明处就应该拒绝。
"""

import pytest

from amrita_sense import Node, NodeCompose
from amrita_sense.instructions.native import NATIVE_DO, NATIVE_IF, NATIVE_WHILE


@Node(wrap_to_async=False)
def ret_true() -> bool:
    return True


@Node(wrap_to_async=False)
def body() -> None:
    return None


class TestIfConditionType:
    def test_rejects_plain_callable(self):
        with pytest.raises(TypeError, match="NATIVE_IF condition must be a BaseNode"):
            NATIVE_IF(lambda: True, body)  # type: ignore[arg-type]

    def test_rejects_bool_constant(self):
        with pytest.raises(TypeError, match="NATIVE_IF condition must be a BaseNode"):
            NATIVE_IF(True, body)  # type: ignore[arg-type]

    def test_rejects_compose(self):
        with pytest.raises(TypeError, match="NATIVE_IF condition must be a BaseNode"):
            NATIVE_IF(NodeCompose(ret_true, ret_true), body)  # type: ignore[arg-type]

    def test_rejects_non_node_elif(self):
        with pytest.raises(TypeError, match="ELIF condition must be a BaseNode"):
            NATIVE_IF(ret_true, body).ELIF(lambda: False, body)  # type: ignore[arg-type]

    def test_accepts_node(self):
        NATIVE_IF(ret_true, body)
        NATIVE_IF(ret_true, body).ELIF(ret_true, body)


class TestWhileConditionType:
    def test_rejects_plain_callable(self):
        with pytest.raises(
            TypeError, match="NATIVE_WHILE condition must be a BaseNode"
        ):
            NATIVE_WHILE(lambda: True)  # type: ignore[arg-type]

    def test_rejects_compose(self):
        with pytest.raises(
            TypeError, match="NATIVE_WHILE condition must be a BaseNode"
        ):
            NATIVE_WHILE(NodeCompose(ret_true, ret_true))  # type: ignore[arg-type]

    def test_accepts_node(self):
        NATIVE_WHILE(ret_true).ACTION(body)


class TestDoConditionType:
    def test_rejects_non_node_while(self):
        with pytest.raises(
            TypeError, match=r"NATIVE_DO\.WHILE condition must be a BaseNode"
        ):
            NATIVE_DO(body).WHILE(lambda: True)  # type: ignore[arg-type]

    def test_accepts_node(self):
        comp = NATIVE_DO(body).WHILE(ret_true).extract().render()
        assert comp is not None
