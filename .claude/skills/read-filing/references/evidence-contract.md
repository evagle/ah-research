# 财务研究共享证据契约

本文件是`value-profile`、`read-filing`、`product-analysis`、`management-analysis`和`financial-redflag-scan`的证据绑定唯一规范。各skill可以增加业务完成条件，不得重新定义本文件的公共字段、哈希比较、引用类型、Mode B写入权或证据漂移语义。

## 目录

1.身份与截止日；2.Manifest绑定；3.Mode B只读与写入权；4.引用；5.终态；6.证据漂移。

## 1.身份与截止日

每次运行绑定以下身份：

```text
canonical ticker
exchange
target_fiscal_year
AS_OF
target_section（Mode B）
```

- 沪深A股ticker为`\d{6}\.(SH|SZ)`。
- 港股ticker为`\d{1,5}\.HK`，立即左补零为五位。
- `target_fiscal_year`是完整财务报告期结束日所在公历年。
- 显式AS_OF原样贯穿全部来源；任何事实、事件或引用的披露时间不得晚于AS_OF。
- Mode B的身份必须与target profile Part 0及manifest逐项一致，不能从文件名猜测。

## 2.Manifest绑定

公共证据集合包括：

- annual filing manifest。
- event manifest。
- A+H发行人的全部counterpart filing manifests。

每个绑定同时保存真实绝对路径和文件SHA-256。A+H的counterpart法域键集合必须与Part 0完全相等，不得缺键、多键或跨法域代用。

所有带`--listing-date <official-listing-date>`的下载命令必须同时传`--listing-profile-bundle <actual-official-query-bundle-path>`。该路径只能使用采集器stdout返回的真实bundle路径。

source preflight至少验证：

1. ticker、exchange、AS_OF和查询发行人代码。
2. 官方目录候选集合、选中版本、替代关系和披露时间。
3. 选中PDF绝对路径及SHA-256。
4. event manifest来源矩阵、查询参数、响应哈希和事件内容哈希。
5. annual manifest与event manifest的listing profile路径及SHA-256一致。
6. counterpart路径、法域键和SHA-256与Part 0一致。

任一绑定字段不一致时fail closed，不得使用同名canonical文件或本地旧PDF代替。

## 3.Mode B只读与写入权

- Mode B只读取父skill已经绑定的证据，不发布或改绑canonical manifest。
- Mode B不得创建、删除或替换持久化抽取cache。
- Mode B不得直接修改target profile，也不得显示第二套确认菜单。
- Mode B只返回目标section草稿、事实、引用、warnings、findings、未决事项和manifest哈希。
- 父skill是target profile的唯一写入者。父skill完成Schema、业务门槛、引用、身份和哈希复核后，才可执行CAS原子写入。
- 子skill需要扩窗、重抽取或补充官方来源时返回`dependency_failure`和`rebuild_evidence`，由父skill在Mode B之外处理。

## 4.引用

公共引用类型只有：

```text
filing_text
filing_pdf
event_document
```

所有引用包含：

```text
section_id
jurisdiction
source_type
artifact_path
artifact_sha256
page
quote
```

`filing_text`和`filing_pdf`追加`source_pdf_sha256`，page必须为正整数。`event_document`追加`event_manifest_sha256/document_url/content_sha256`，HTML文书page可以为null。

`artifact_path`必须指向最终持久证据的绝对路径。引用不得指向临时抽取目录。canonical citation ID按字段规范化JSON计算SHA-256；相同证据重复使用时复用同一ID。

每条可供判断层复用的事实或事件还必须生成`canonical_evidence_id`。该ID只由规范化来源身份、文档哈希、页码或事件ID和原文quote决定，不包含下游skill、严重度或判断文字。同一底层证据被公司财务、管理层或产品判断复用时保持相同ID。

## 5.终态

公共终态语义：

|终态|语义|草稿|
|---|---|---|
|`success`或专题兼容值`completed`|当前目标通过Schema和业务完成门槛|必须满足专题契约|
|`pending`或专题兼容值`manual_review`|已有可复核草稿，但存在真实未决证据|可以返回，父skill保存为需人工|
|`failure`|本次处理失败且没有可保存草稿|不得返回可保存草稿|
|`dependency_failure`|证据绑定、前置section或live revalidation失败|不得返回可保存草稿|
|`output_quality_failure`|结构、枚举、Schema或证据结论一致性失败|不得伪装成证据缺失|

子skill可以保留现有兼容状态名称，但必须在自身Schema中给出唯一映射。证据不足与输出质量失败不得互换。

## 6.证据漂移

形成否定性结论、保存草稿或写最终终态前，按manifest保存的真实请求契约执行live revalidation：

1. 重放官方目录及事件来源请求。
2. 比较响应哈希、结果总数、候选或事件集合。
3. 重新下载选中官方PDF并比较远端、本地和manifest三方SHA-256。
4. 重算annual、event及全部counterpart manifest文件SHA-256。
5. 父skill在CAS中把所有绑定manifest作为guard。

任一证据发生变化时返回`dependency_failure`和`rebuild_evidence`。父skill先重建证据、原子改绑并使受影响section失效，再重新调用子skill；不得把漂移降级为普通pending。
