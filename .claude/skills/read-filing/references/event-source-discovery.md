# 监管事件官方数据源发现

事件query plan不能凭记忆填写。每次首次使用或官方接口契约变化时，必须从实际官方请求建立source contract；没有经过验证的contract就停止，不能把接口缺失写成`未检出`。

## 发现流程

1. 打开对应监管机构或交易所的官方检索页，确认浏览器地址属于`build_event_manifest.py`允许的官方域名。
2. 在浏览器网络面板执行一次最窄的真实查询，记录实际官方请求的URL、HTTP方法、请求编码、请求头要求、查询参数和原始响应。不得猜测接口、参数名或默认分页。
3. 分别执行“有结果”和“无结果”查询；若支持多页，再执行至少2页。由实际响应确定结果数组、官方总数、当前页、总页数和下一页参数等分页字段。
4. 从实际响应逐字段建立`response_adapter`，覆盖发行人代码、主体ID、事件标题、发生日期、发布时间、状态、违法类型、法律效力、发生时角色、发行人关系和官方文书URL。固定值只能来自该官方类别的公开语义，不能用来掩盖响应缺字段。
5. 保存listing profile和历史主体名册的实际官方请求，覆盖上市日期、上市状态、退市日期、完整主体列表、任期和审计机构。主体名册不能从当前年报人工拼接冒充官方历史响应。
6. 对每个source contract执行collector和builder的dry run，再用同一请求直接重取并比较官方结果总数、全部分页、响应哈希和标准化结果。只有两次结果一致才可写入版本化query plan。

## 已验证的HKEX上市资料契约

以下contract已于2026-07-29通过两次独立普通HTTP会话验证。港股当前上市发行人的listing profile优先直接复用，不得每次打开Chrome或CDP重新发现:

```json
{
  "source_url": "https://www1.hkex.com.hk/hkexwidget/data/getequityquote",
  "http_method": "GET",
  "request_encoding": "query",
  "query_params": {"issuer_code": "09992"},
  "response_schema": "canonical_listing_profile_v1",
  "request_bootstrap": {
    "type": "hkex_equity_quote_token_v1",
    "page_url": "https://www.hkex.com.hk/Market-Data/Securities-Prices/Equities/Equities-Quote"
  }
}
```

将`issuer_code`替换为五位canonical港股代码。collector会在同一cookie会话中获取quote页面,从`LabCI.getToken()`提取动态token,先URL解码再由请求库编码,随后调用官方quote API。token和实时价格字段不落盘;证据文件只保存由同一官方响应提取的稳定身份字段,包括发行人代码、上市日期、上市状态、`issuer_name`、`listing_category`和`chairman`。不得把token硬编码进query plan或skill。

只有自动bootstrap明确报`LabCI.getToken`缺失、JSONP结构变化、非`EQTY`、身份不匹配或官方host/path变化时,才按上面的发现流程重新打开浏览器网络面板。普通403先检查是否错误地对HTML中的`%2f`再次编码为`%252f`,不得直接转人工或把403解释为无记录。

## 失败关闭

- 官方页面没有可重复调用的结构化请求、需要未获授权的凭证、字段不能映射、分页无法证明完整或官方域名校验失败时立即abort。
- abort时返回缺失的source ID、官方检索页URL、已尝试请求和缺失字段，进入`manual_review`；不得改用搜索引擎摘要、第三方数据库或人工猜测的空响应。
- 已验证contract后续返回schema变化、总数不一致或新字段时视为contract失效，保留旧证据并重新执行本流程。
