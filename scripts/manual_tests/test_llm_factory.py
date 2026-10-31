#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Author  : Vincent
@Time    : 2026/10/23 11:25
@File    : test_llm_factory.py
@Function :
"""
# test_llm_factory.py（项目根目录）
from pydantic import BaseModel, Field
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable
from backend.core.llm_factory import LLMFactory

# ① 按类型拿到模型实例
llm = LLMFactory.get_llm("qa")
print("① 是 BaseChatModel:", isinstance(llm, BaseChatModel), "|", type(llm).__name__)

# ② 相同参数有缓存，返回同一实例
print("② 缓存命中(同一实例):", LLMFactory.get_llm("qa") is llm)

# ③ 未知 agent_type 会报错
try:
    LLMFactory.get_llm("not_exist")
except ValueError as e:
    print("③ 未知类型报错:", str(e)[:38], "...")


# ④ 结构化输出：绑定 Pydantic，返回 Runnable
class Demo(BaseModel):
    name: str = Field(description="姓名")


print("④ 结构化模型是 Runnable:", isinstance(LLMFactory.get_structured_llm("resume", Demo), Runnable))

# ⑤ 清空缓存
LLMFactory.clear_cache()
print("⑤ clear_cache 后缓存为空:", len(LLMFactory._instances) == 0)
