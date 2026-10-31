#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Author  : Vincent
@Time    : 2026/10/23 15:09
@File    : test_retry.py
@Function :
"""
import asyncio
import backend.core.retry as retry
from backend.core.retry import with_retry
from backend.core.exceptions import LLMAPIError, InvalidInputError

retry.RETRY_DELAYS = [0.0, 0.0]  # 测试时把等待时间清零，不用真等 1s/3s

calls = {"n": 0}


# ── ① 正常成功 ──────────────────────────────────────────────
@with_retry(agent_type="qa")
async def ok():
    return "success"


# ── ② 重试后成功 ────────────────────────────────────────────
@with_retry(agent_type="qa")
async def fail_twice_then_ok():
    calls["n"] += 1
    if calls["n"] < 3:
        raise LLMAPIError("网络抖动")
    return "recovered"


# ── ③ 不可重试异常立即抛出 ──────────────────────────────────
@with_retry(agent_type="qa")
async def non_retryable():
    raise InvalidInputError("输入非法")


# ── ④ 三次全败 + 无降级策略 → 第三层系统兜底 ────────────────
@with_retry(agent_type="")  # 空 agent_type → fallback_map 里找不到 → 直接系统兜底
async def always_fail():
    raise LLMAPIError("一直失败")


# ── ⑤ 三次全败 + 有降级策略 → 第二层 Agent 降级 ─────────────
# 以 qa 为代表；resume / interview / exam_code / exam_subjective 结构完全相同
@with_retry(agent_type="qa")
async def qa_node_always_fail():
    raise LLMAPIError("Milvus 连接超时")


async def main():
    # ①
    print("① 一次成功:", await ok())

    # ②
    print("② 失败2次后第3次成功:", await fail_twice_then_ok(), "| 总调用次数:", calls["n"])

    # ③
    try:
        await non_retryable()
    except InvalidInputError as e:
        print("③ 不可重试异常立即抛出:", e)

    # ④
    r = await always_fail()
    print("④ 全失败→系统兜底: system_fallback =", r.get("system_fallback"),
          "| content =", r["content"][:14], "...")

    # ⑤ 第二层降级（qa 为代表）：三次失败 → _qa_fallback → 返回静态提示
    r2 = await qa_node_always_fail()
    print("\n⑤ 第二层降级（qa）:")
    print("   fallback_used =", r2["fallback_used"])
    print("   content       =", r2["content"])


asyncio.run(main())
