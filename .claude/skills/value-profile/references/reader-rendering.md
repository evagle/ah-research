# Reader Rendering Contract

本文件定义`value-profile`完成研究内容之后的最终读者输出层。研究事实、证据、数字和
投资判断在进入本层前已经生成；本层不继续研究，也不补写缺失结论。

## 1. 固定流水线

处理顺序不可交换：

```text
完整研究Markdown
-> 读者语气编辑
-> 确定性reader projection
-> 负向检查与自动删除
-> 删除后复检
-> 纯HTML renderer
-> 内存终检
-> 原子写入HTML
```

HTML renderer是最后一层。未完成projection和负向复检时不得开始HTML转换。

## 2. 输入和输出

- 输入是已经保存成功的完整profile Markdown。
- Markdown是唯一可编辑、可恢复的研究源文件，继续保留机器引用、证据字段、回执、
  指纹、研究账本状态和恢复信息。
- 输出是同名HTML阅读版，只包含面向研究员和投资者的内容。
- 不创建或保存`.reader.md`中间文件。
- HTML不进入CAS或run-store，不能反向覆盖Markdown。

## 3. 读者语气编辑

主skill在研究生成完成后、调用确定性渲染命令前执行一次读者语气编辑。它只优化已经
形成的表达：

- 使用自然、简洁的中文，删除重复限制说明和研究过程叙述。
- 调整标题、段落和表格前后的阅读顺序，使读者先看到关键事实和商业含义。
- 合并同一证据缺口的重复说明；只在最相关章节保留一次。
- 删除只是在提醒AI如何处理资料的句子。

该步骤不得新增事实或预测，不得改变任何数字、时间、单位、比较口径、限定词、风险
强度或投资结论。无法在不改变含义的情况下润色时保留原文。内容是否足够由用户判断，
渲染层不设置篇幅或完整度门槛。

## 4. 确定性读者投影

运行：

```bash
uv run python scripts/render_profile_html.py <profile-path>
```

CLI先调用`scripts/profile_reader_projection.py`，再调用纯
`scripts/profile_html_renderer.py`。projection自动删除：

- HTML注释内的机器引用、回执和恢复数据；
- `引用`、`置信度`、`管理层口径校核`及其续行；
- 指纹、长哈希、schema版本和内部字段名；
- claim、role、route及ledger/run-store状态和路径；
- 已尝试来源、下一路由和accepted/exhausted等研究工作流叙述；
- 只服务AI审计或恢复的整张表、整段或空标题。

表格按完整Markdown块删除，不能只删部分单元格留下破损表。删除后清理空标题、重复
分隔线和多余空行，但不得改写正常投资正文或财务表。

## 5. 删除报告

识别出的机器内容直接删除，不因删除而阻止输出。每次删除写到stderr，stdout继续只
输出最终HTML路径：

```text
[reader-projection] removed machine-table lines 312-326: 角色 / 状态 / 路由终态
[reader-projection] removed reader-metadata line 418: 置信度
[reader-projection] removed 7 machine-only blocks
```

控制台报告只用于定位上游泄漏，不写入HTML。

## 6. 负向检查和失败条件

projection删除后必须再次扫描reader Markdown。若仍识别到机器字段，继续删除包含它
的最小完整Markdown块并报告；复检通过后才可调用HTML renderer。

HTML在内存中生成后、写盘前再做一次机器字段断言。以下技术错误才停止并保留原HTML：

- 源文件不可读；
- 删除后正文完全为空；
- 删除会造成无法解析的Markdown；
- 复检仍发现无法安全定位的机器字段；
- HTML生成或原子写入失败。

不得因为篇幅较短、某项公开数据缺失或研究结论偏保守而阻止渲染。

## 7. 纯renderer边界

`scripts/profile_html_renderer.py`只负责Markdown到HTML、目录、标题锚点、表格容器、
样式和响应式布局。它不得：

- 读取年报、研报、网页或manifest；
- 判断证据是否充分；
- 删除或补写研究内容；
- 改变数字、口径、风险或投资判断；
- 处理claim、role、route或ledger状态。

任何新过滤规则都应加入reader projection，而不是放回HTML renderer。
