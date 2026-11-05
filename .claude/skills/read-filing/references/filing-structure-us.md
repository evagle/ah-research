# US SEC Filing Reading Structure

## Assurance Boundary

- 10-Q未经审计；只能说明季度财务报表经过管理层编制及审阅语境，不能替代10-K审计意见。
- 最新季度研究必须同时读取最近10-K审计意见、Critical Audit Matters、财务报表附注和重大重述。
- 10-K/A或10-Q/A只在manifest证明其与同一form family及report period的base filing关系后替代原版本。

## 10-Q Map

1. `Item 1. Financial Statements`:三表、权益变动和附注；先核对report period、CIK和Inline XBRL identity。
2. `Item 2. Management's Discussion and Analysis`:收入、预订、利润率、现金流、季节性、guidance及管理层归因。
3. `Item 3. Quantitative and Qualitative Disclosures About Market Risk`:利率、汇率和投资组合风险。
4. `Item 4. Controls and Procedures`:披露控制、内部控制变化及重大缺陷。
5. `Item 1. Legal Proceedings`和`Item 1A. Risk Factors`:诉讼和风险变化；不得只读“无重大变化”的摘要。
6. `Item 2. Unregistered Sales of Equity Securities and Use of Proceeds`:回购数量、金额及剩余额度。

## 10-K Baseline

读取Business、Risk Factors、MD&A、审计报告、三表、完整附注、Controls and Procedures及回购。季度趋势必须回到10-K核验会计政策、分部、税项、SBC、债务、承诺和审计口径。

## Inline XBRL Rules

- 每个fact保留taxonomy/tag、CIK、unit、contextRef、start/end或instant、form、accession、filed date及artifact SHA-256。
- quarter-only、YTD、TTM和instant是不同context；不得用YTD减法制造未披露季度值。
- 相同tag但unit、period或dimensions不同不得直接比较。
- Inline XBRL与company facts冲突时，仅相关metric进入`Manual review`。
- HTML引用使用真实DOM anchor和逐字quote；无稳定打印页时page为null。
