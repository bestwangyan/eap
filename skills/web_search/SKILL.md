---
name: web_search
description: 互联网搜索技能，使用搜索引擎获取最新信息
version: 1.0.0
author: EAP Team
tools:
  - web_search
  - fetch_webpage
tags:
  - search
  - research
---

# Web Search Skill

## 触发条件
当用户提问涉及以下场景时使用：
- 需要最新新闻或实时信息
- 需要查找互联网上的公开资料
- 需要比较不同来源的信息

## 执行步骤
1. 使用 web_search 工具执行搜索
2. 对搜索结果进行相关性评估
3. 如有必要，使用 fetch_webpage 获取详细内容
4. 综合多源信息，给出有引用的回答

## 约束
- 最多执行 3 次搜索
- 标明信息来源 URL
