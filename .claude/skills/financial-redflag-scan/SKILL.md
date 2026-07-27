---
name: financial-redflag-scan
description: Use when a user asks to scan a Shanghai/Shenzhen A-share or HK filing for财报排雷,financial red flags,earnings-quality problems,or fraud indicators,including "排雷600519.SH","检查收入造假信号",or "/redflag-scan 0700.HK".
---

# Financial Red-Flag Scan Skill

本 skill 是 value-profile 主 skill 的子 skill, 专门负责"财报排雷 + 造假高危模式扫描"。结构分三层: **§1原则 → §2规则 → §3流程**。

**覆盖边界**:港股仅支持当前上市发行人;已退市港股发行人不在当前下载器与官方目录适配范围内。

**上市资料绑定**:所有带`--listing-date <official-listing-date>`的下载命令必须同时传`--listing-profile-bundle <actual-official-query-bundle-path>`,该路径必须是采集器stdout返回的真实bundle路径。source preflight要求年报manifest与事件manifest的listing_profile路径和SHA-256一致;不一致立即abort。

## §0运行模式

### Mode A — Standalone

- **Invocation**:`/redflag-scan <ticker> [--as-of YYYY-MM-DD] [--resume|--start-fresh] [--counterpart-filing-manifest <exchange>:<absolute-json-path>]... [--auto|--interactive]`/`财报排雷 <ticker>`/`排雷 <ticker>`。Mode A默认`--auto`
- **行为**: 子 skill 独立完成 ticker 验证 + filings audit + PDF 抽取 + 派子 agent 扫29项 + 6项高危附加检查 + 主 agent 复核 + 写 standalone 报告
- **依赖失败**:年报目录、监管事件、上市资料或live revalidation任一失败时,Mode A持久化`dependency_failure`及具体原因,阻断发布完成态;临时年报manifest复核通过后,只允许执行Step 5列出的提升命令,不得手工复制或改写
- **Output path**:`profiles/<ticker>-redflags-<YYYY-MM-DD>[-vN].md`—self-contained报告,约150-250行
- **典型场景**: 用户对某 ticker 做快速排雷扫描, 发现风险直接剔除, 不需要完整 value-profile

### Mode B — As-subroutine

- **Invocation**:主value-profile skill在Step 5遇到Part 4 §4.5排雷时delegate,传参`--target-profile PATH --section part4/§4.5 --as-of AS_OF --filing-manifest <absolute-json-path> --event-manifest <absolute-json-path> [--counterpart-filing-manifest <exchange>:<absolute-json-path>]... --auto|--interactive`
- **行为**:读取两个canonical manifest,重新校验选中版本和截止日、文件路径及SHA-256;校验通过后跳过重复下载,从Step 3开始
- **Output**:仅返回`draft_section`和结构化flags,父skill是唯一写入者;本skill不直接修改`<target-profile>`
- **确认归属**:Mode B始终只返回草稿;父skill独占`accept/edit/research more`,本skill不显示菜单、不接受草稿也不落盘。
- **典型场景**: 用户跑 `/value-profile <ticker>`, 主 skill 推进到 §4.5时自动调用本 skill

### Invocation 解析

- 参数只有 ticker → Mode A (Standalone)
- 参数含`--target-profile PATH`→Mode B（As-subroutine）,必须同时提供`--as-of AS_OF --filing-manifest <absolute-json-path> --event-manifest <absolute-json-path>`并继承调用方的`--auto`或`--interactive`;A+H发行人还必须为每个counterpart重复传`--counterpart-filing-manifest <exchange>:<absolute-json-path>`,任一缺失时报契约错误
- Mode A可显式传`--as-of YYYY-MM-DD`;未传时按Step 1从目标完整年报首次有效披露日初始化
- Mode A的`--resume`与`--start-fresh`互斥;显式指定时按原值执行,未指定时按Step 1的持久状态选择
- Mode A未传模式时按`--auto`;Mode A的`--interactive`才显示确认菜单。Mode B无论继承`--auto`还是`--interactive`都不显示菜单,只返回父skill确认
- Ticker验证:沪深A股使用`\d{6}\.(SH|SZ)`,HK使用`\d{1,5}\.HK`,与下载器一致。港股代码立即左补零为五位,后续路径、manifest、查询参数和输出只使用canonical ticker

### 运行时必读 reference

本skill的**深度操作手册**在`references/fraud-library.md`:风险10项（§1）+三表勾稽4条（§2）+造假5维度（§3）+pattern A1/A2/A3叙述（§4）+书中补充质检信号（§5）。跨skill共享阈值和市场基准的唯一来源是`references/thresholds.yaml`。派子agent前,主agent必须读取这两个文件,再按exchange读取`../read-filing/references/filing-structure-cn.md`或`filing-structure-hk.md`,并把适用阈值、严重度和语义章节写入prompt。附注12项原始数据由`statement-reading.md §3`产出。

---

## §1排雷原则

精炼5条。

### §1.1年报正文是管理层 PR, 真相在附注

董事会报告/经营情况讨论是管理层美化口径, 读快扫即可。**风险的真正藏身处是附注**: 应交税费/关联交易/对外担保/其他应收款明细/存货构成/商誉减值测试假设/金融资产4分类。正文不读则已, 读也只用来对比附注是否在说同一件事。

### §1.2三表勾稽不一致即风险

资产负债表/利润表/现金流量表必须互相对得上。任一表的数字不能被另两张表交叉验证 → 疑点。关键公式（见 references/fraud-library.md §2）必须跑完4条, 不过的项目直接标 `需人工`。

### §1.3造假6类高危模式 → profile 降级

商誉/其他应收/在建工程/经营现金流/生物资产/管理层道德风险, 任一触发 → 即使 §1-§3生意模式再好, profile 整体降级或弃权。高危模式的优先级高于好生意判断。

### §1.4排雷是强制步骤, 不是可选

每份profile（或standalone报告）**必须**跑完29项清单+6项高危附加检查+三表勾稽4条+8类补充质检+造假识别5个维度。交互模式的确认节点不接受`defer/skip`;自动子流程通过复核后直接返回,也不能跳过任何检查。

### §1.5排雷是定量, 不要靠感觉

量化项必须给阈值+页码+实际值;定性项必须给事件、日期、主体和文书。禁"看起来商誉有点高"这类主观判断。

---

## §2排雷规则

### §2.1 29项清单逐项扫（§1.4推出）

- **§2.1.1清单来源**:完整29项位于主template`.claude/skills/value-profile/template-zh.md`,必须按标题定位`### §4.5负面清单 — 排雷风险（29项）`,读取到下一个同级标题为止。禁止依赖行号。派子agent时把29项inline嵌入prompt。
- **§2.1.2每项格式**:`看哪里|触发条件|应采取动作|状态+严重度+证据`
- **§2.1.3结果值域**: `是 / 否 / 不适用 / 需人工` — 4选1, 每项必答
- **§2.1.4严重度映射**:适用于29项、6项、三表勾稽、8类补充质检和造假识别5个维度。29项/6项的`否/不适用`→`无`,`需人工`→`待定`;未明示高风险或一票否决的`是`统一映射为`预警`,只有模板或`thresholds.yaml`明确命中高风险阈值才写`高风险`。三表勾稽的`通过/不适用`→`无`,`异常`→`预警`,`需人工`→`待定`。8类补充质检的`未见异常/不适用`→`无`,`异常`→`预警`,`需人工`→`待定`。5个维度的`未见异常/不适用`→`无`,`沾边`→`预警`,`需人工`→`待定`;若直接命中高风险或一票否决事实,按更高等级覆盖。保留意见、无法表示或否定意见为`一票否决`;强调事项段本身不改变无保留意见,只按其底层事项适用的独立阈值定严重度。正式财务造假处罚和管理层道德否决为`一票否决`。不得省略严重度或自行改名。
- **§2.1.5行内聚合**:一行包含多个指标时取最高严重度,并逐个保留实际值、适用性和证据;不得用正常子项抵消异常或缺证子项。

### §2.2 6项高危附加检查（§1.3推出）

即使不在29项清单中, 以下6项必须显式 flag:

1. **商誉/归母净资产≥20%**→预警并深查减值假设;**>30%**→高风险。归母净资产≤0时比例无定义,直接标高风险并列出商誉和负净资产金额。两档严重度来自`thresholds.yaml`,不得互换
2. **其他应收款/流动资产≥10%**或单一关联方长年挂账→仅触发预警和深查;分母固定为流动资产。继续核查交易对手、关联关系、账龄、形成原因、资金流向和可收回性,不得据此认定股东占款。只有年报附注、审计结论、监管文书或资金流向等直接证据证明股东或关联方非经营性占用资金时,才认定占款并按§2.5升级
3. **在建工程长期不转固**（≥3年）→挂账操纵折旧
4. **经营现金流/归母净利润<50%连续2年**→利润真实性风险,可能应收膨胀。归母净利润≤0时不计算该比率,改列经营现金流和归母净利润符号、金额及连续亏损年数;该子项统一写`不适用/无`,归母净利润为负本身不得把该比率行写`需人工/待定`,但连续亏损可由其他适用检查独立评估
5. **生物资产可审计性**:按`thresholds.yaml:checks.biological_asset_auditability`判断。存在重大生物资产先写`是/预警`并核查数量、权属、死亡率和第三方盘点;重大余额且数量或权属无法独立验证才写`是/高风险`;无生物资产为`不适用/无`,字段缺失为`需人工/待定`
6. **管理层道德风险**（正式财务造假或财务虚假陈述处罚/已证实股东利益输送）→直接大幅降级。非财务造假处罚不得直接升级,按底层事项独立阈值处理

### §2.3三表勾稽4条必跑（§1.2推出）

**银行排雷替代bundle（银行10行替代bundle）**:识别为银行后,29项仍逐行保留以维持输出契约,但不适用行写`不适用/无`并说明银行口径。银行不使用销售收现、CFO/NI、存货、毛利率或普通企业杠杆阈值;三表勾稽4条全部写`不适用/无`,逐条注明“银行资金即产品,改由银行10行替代bundle覆盖”,不得与银行10行重复计分。固定10行检查:①不良率与关注类迁徙②逾期90天以上贷款③拨备覆盖率与拨贷比④信用成本⑤净息差⑥核心一级资本充足率⑦风险加权资产增速⑧流动性覆盖率与净稳定资金比例⑨存款集中度与同业融资依赖⑩关联授信与大额风险暴露。银行10行按`bank_bundle_severity`映射:低于`regulatory_minima`中的对应CN/HK监管下限或高于`regulatory_maxima`中的对应监管上限=`高风险`;按每项`directions`方向,当前值同时劣于前3年中位数和同交易所同银行子类型同业中位数=`预警`;信用成本、拨备覆盖率和风险加权资产增速分别使用`credit_cost_matrix`、`provision_coverage_matrix`和`rwa_growth_matrix`,不套单向高低规则。信用成本矩阵中的升降统一比较当前财年与紧邻前一可比财年,信用成本和不良率变化达到1个基点才分别算上升或下降,绝对变化小于1个基点算稳定;矩阵命中后不再叠加历史/同业方向规则。缺失完成判断所需证据=`待定`;其余=`无`。核心一级资本充足率先取得机构适用核心一级资本监管最低要求,只在实际值低于该披露或监管要求时判高风险;适用要求不可得时写待定且不得判定监管违规,通用市场基线只作后备比较。A股大额风险暴露先按交易对手类型选择注册表分档:非同业单一客户15%、非同业关联客户组20%、同业单一客户或关联客户组25%;无法确定类型时写`待定`,不得统一套25%。A股拨备覆盖率监管要求为120%-150%的差异化区间;只有取得该机构披露或监管适用下限后,实际值低于该适用值才写监管违规高风险,适用值不可得时走历史与同业比较并写证据限制,不得固定以150%判违规。拨备覆盖率>500%写`预警`,检查利润平滑或损失确认延迟,不得按“越高越好”直接判正常。存款集中度的分子范围和分母必须与历史及同业完全同口径;最大单一存款人、前十大存款人或其他范围不得混比,口径不一致且无法还原时写`待定`。同业证据必须具备`peer_evidence_required_fields`全部字段且披露日≤AS_OF。没有统一法定阈值的指标不得伪称违反监管阈值,只走历史+同业比较。一行包含多个指标时取最高严重度。所有适用行均须给状态、严重度、实际值、适用监管下限或上限、历史/同业基准、页码和动作;`不适用/无`按§2.4.3a提供适用性证据,不得伪造数值或阈值。

**保险公司替代bundle（保险10行替代bundle）**:识别为保险公司后保留29项结构,普通企业不适用行写`不适用/无`并给适用性证据;另严格按`thresholds.yaml:checks.insurer_bundle`的10个metrics输出。每行必须包含metric、期间、实际值、单位、分子、分母、计算口径、机构适用监管要求、前3年中位数、同交易所同险种同业中位数、来源、页码或URL、严重度和动作。低于机构适用监管最低要求、重大准备金不足或已证实关联利益输送为`高风险`;无统一法定阈值的行只有同时劣于历史和同业才为`预警`;完成判断字段缺失为`需人工/待定`,不得凭通用市场数字判监管违规。

**银行与保险字段契约**:`status`与`severity`是两个独立字段。银行`status`只允许`正常/预警/高风险/不适用/需人工`,保险`status`只允许`是/否/不适用/需人工`;两者`severity`只允许`无/预警/高风险/待定`。保险10行还必须包含`thresholds.yaml:checks.insurer_bundle.required_output_fields`中的全部字段,不得把status藏在severity或自然语言结论中。

- **§2.3.1应有销售收现勾稽**:`应有销售收现≈营业收入×(1+有效VAT税率)−Δ应收账款账面余额−Δ应收票据账面余额+Δ合同负债+Δ预收款项（新收入准则前口径）−本期核销±汇兑影响±合并范围变动/合并处置影响±重分类调整−本期票据贴现−非现金抵账+收回已核销坏账`。所有非经营滚动调整按附注披露方向代入,不得默认取0。有效VAT税率按各业务适用税率×对应含税前收入占比加权,税率从会计政策/税项附注取得;香港本地无VAT的收入税率为0,内地子公司按其披露税率。无法取得收入权重时给出披露税率范围的敏感性结果并标`需人工`,不得猜统一税率。将结果与现金流量表"销售商品、提供劳务收到的现金"比较,背离>5%时继续检查票据背书转让和口径差异。该公式只做收现勾稽,不得直接推断收入真实性。
- **§2.3.2销售收现比**:`销售商品、提供劳务收到的现金/(营业收入×(1+有效VAT税率))`。≥1.0通常表示收现较完整;<1连续2年才进入深查,并结合票据背书、非现金结算、行业收款模式解释。阈值和5%勾稽容差来自`thresholds.yaml`。
- **港股披露替代**:港股未单列销售商品、提供劳务收到的现金时,§2.3.1和§2.3.2写`不适用—披露口径缺失`,引用现金流量表页码;改查应收账款、合同负债、分部收入和经营现金流桥,不伪造毛额收现值,也不因两项不适用而判风险。
- **清单第4项唯一公式**:`max(同业中位数−公司收益率,0)/abs(同业中位数)`。结果≥50%才触发收益率异常偏低;同业中位数≤0时写`需人工/待定`,不得改用公司收益率作分母或把异常偏高也算作该项风险。
- **清单第6项港股替代**:港股未披露"其他货币资金"科目时,必须从现金及银行结余、流动资产和受限资产附注逐项查`受限制银行存款`、`质押存款`、`保证金存款`和`非现金等价物定期存款`,按经济实质去重汇总。以现金及银行结余和上述存款去重后的总额为分母;受限或非现金等价物存款合计占比>30%且无用途说明时写`是/预警`,占比未超过阈值或用途解释充分时写`否/无`,字段或口径无法取得时写`需人工/待定`。证据必须列四类项目各自金额、合计占比、用途说明和年报页码;不得因港股科目名称不同而跳过
- **清单第9项港股替代**:清单第9、10、18项只有营收增长率>0且应收、存货或预付增长率为可比正值时才计算增长倍数;营收增长率≤0时不计算增长倍数,改比较应收/营收、存货/营收、预付/营收、周转天数和绝对额方向,不得因负分母自动触发。港股不使用缺失的毛额销售收现。正增长可比口径下应收增幅未超过营收1.5倍时写`否/无`;超过时改查应收周转天数、合同负债、分部收入和CFO/收入,仅当应收周转恶化且至少一项替代信号同向恶化时写`是/预警`,证据不足写`需人工/待定`
- **清单第12项港股替代**:毛额销售收现子项写`不适用/无`,经营现金流/归母净利润子项按正归母净利润规则独立判断;归母净利润≤0时该子项也写`不适用/无`,并列出经营现金流与归母净利润金额
- **§2.3.3净利润→CFO桥**:以合并净利润为起点,使用`fraud-library.md`§2.3的完整间接法桥,不得把归母净利润与合并现金流混用。桥接残差/`max(|CFO|,|合并净利润|)`≤`thresholds.yaml`的5%为勾稽通过;超过后先补齐所有非现金及营运资本项目,仍超才标`需人工`。
- **§2.3.4维持性CapEx近似**:`维持性CapEx≈折旧摊销×(1+通胀系数)`;`自由现金流≈CFO−维持性CapEx`。通胀系数使用报告期CPI同比（主要经营地官方全年平均）;跨地区时按收入权重加权,权重缺失则列敏感性区间。维持性CapEx是估算值,不存在报表真值容差;完整披露输入、假设和敏感性即为完成,不得把估算差异当勾稽失败。
- **§2.3.5非正或零分母**:清单第12项中归母净利润≤0时不计算经营现金流/归母净利润,只列符号、金额和连续亏损年数。清单第23项利息费用≤0时不计算利息保障倍数,区分无有息负债与利息披露缺失。清单第25项归母净利润≤0时不计算资本化研发/归母净利润,仍可独立检查研发资本化率。勾稽分母为0时不得输出百分比残差,改列绝对残差并标`需人工`;任何检查都不得对非正分母套比例阈值。

### §2.4引用 + 证据规则（§1.5推出）

- **§2.4.1量化检查证据**:涉及金额、比例、增速或年限的`是/需人工`必须给`金额或实际值+阈值对比+年报页码`。例:`是|商誉42亿/净资产180亿=23%>20%阈值[年报-2024.pdf p.87]|追查商誉减值假设`。
- **§2.4.2定性检查证据**:审计意见、处罚历史、生物资产可审计性、管理层道德等定性项给`事件/主体/日期/文书或原文依据+页码或URL+动作`;没有适用金额时不得为了满足格式伪造数字。
- **§2.4.3不接受"根据经验"**:触发后的建议或父级请求必须具体,不能留空或写"待补充"。Mode A只记录建议动作,不得声称已修改投资池、profile或估值;Mode B返回类型化`action_requests`,类型只允许`deepen_research/lower_confidence/block_valuation/management_review/valuation_route_review/rebuild_evidence`,由父skill执行并持久化。canonical citation ID定义为对`source_type`、绝对artifact路径、artifact哈希、page或null、规范化quote及适用时的document URL和content哈希组成的确定性JSON计算SHA-256;生成请求前按ID排序。每项请求必须含稳定`request_id`、`target_section_id`、`requested_confidence`、`execution_status`和`execution_result`:子skill以`sha256(type|target_section_id|reason|canonical-citation-ids)`生成`request_id`,返回时`execution_status=pending`且`execution_result=null`;父skill执行后在同一次CAS中把状态改为`completed/failed`并填写结果。相同请求重试复用同一ID,不得重复执行;未知ID或目标section拒绝保存。
- **§2.4.3a所有终态证据**:`否/不适用/通过/未见异常`也必须有证据。适用的量化行至少给实际值、阈值和页码;定性行至少给检索对象、覆盖期间、文书或原文依据及页码/URL。`不适用/无`不要求伪造实际值或阈值,但必须给出适用性依据和页码或URL。无证据不得聚合为`无重大风险`。
- **§2.4.4重试耗尽例外**:只有自动重派2次后仍客观无法取得字段时,`需人工/待定`行的证据改为`已查来源+检索词+未取得字段+最后错误`;不再要求不存在的实际值,但必须写下一步人工动作和估值阻断。

### §2.5管理层道德风险 = 一票否决（§1.3推出）

历史正式财务造假或财务虚假陈述处罚记录、已证实的股东利益输送或违规资金占用→直接大幅降级并阻断估值,Mode A报告结论写`剔除`,Mode B返回对应阻断请求。风险结论和证据置信度分开:官方处罚窗口完整、文书逐字节复核且归因闭合时,即使结论为`剔除`,证据置信度保持`高`;不得为了表达风险严重而强制降为低。与财务造假无关的其他处罚按底层事项和独立阈值定严重度,不得据此一票否决。

### §2.6 summary 段落写法

- **§2.6.1结果不是简单列表**:29项扫完后按模板原字段名写`**发现的风险小结:**`1-2段,聚焦`是/需人工`项,说明①雷是什么②为何对本ticker重要③交叉验证的下一步;随后填写`**引用:**`并把小结中的叙述数字逐条映射到页码或独立来源。
- **§2.6.2无重大风险前提**:29项、6项、三表勾稽4条、8类补充质检和造假识别5个维度的全部适用行均为`无`,且不存在`待定/需人工`,才可写"本次扫描未发现重大风险";任何层异常均进入§2.6.3聚合。
- **§2.6.3结论聚合**:触发任一`一票否决`→`剔除`;存在任一`预警/高风险/待定`→`有保留`;其余为`无重大风险`。pattern只能解释已触发风险,不得单独升级为剔除;3个不同的29项清单ID指向同一模式时,模式综合严重度至少为`高风险`,但最终结论仍按行级最高严重度聚合。同一事实跨层出现只计1次;6项、三表勾稽、8类补充质检和5个维度不增加29项计数,只提供严重度覆盖或解释证据。销售收现和CFO桥按各自容差判断;维持性CapEx按输入与敏感性完整性判断。任一高风险、一票否决或结论为`剔除`时,§4.5写`**估值阻断:**是—<原因>`并返回`valuation_blocked=true`;任一`需人工`或`待定`写`**估值阻断:**是—证据需人工`并返回`valuation_blocked=true`;只有全部适用检查证据闭合且无上述信号时才写`否`。
- **§2.6.4证据置信度固定映射**:`高`=完整官方窗口且无代理口径,所有适用行可复算;`中`=官方窗口完整但存在已披露且不影响阈值方向的代理口径;`低`=关键结论仅有二级来源或窗口不足;`需人工`=存在待定、证据冲突或终端质量失败。取所有关键结论中的最低档,不得凭主观上调。

### §2.7确认策略（§1.4推出）

`bootstrap取证菜单`只属于Mode A `--interactive`,提供`yes/no/show-command`;其中`no/show-command`保留同一骨架报告的可恢复状态。`终稿确认菜单`只属于Mode A `--interactive`,提供`accept/edit/research more`。Mode B不显示菜单,无论auto或interactive都只返回草稿,由父skill唯一确认。任何终稿确认都不提供`defer/skip`。

---

## §3分析流程（Step 1-5）

### Step 1 — Bootstrap与上游事实

Mode B跳过Step 1的1-6项,但必须执行第7项,使用自身调用read-filing Mode B取得并复核`facts/citations/warnings`;不得依赖调用方未传入的内存事实。

1. **Validate ticker**:沪深A股使用`\d{6}\.(SH|SZ)`,港股使用`\d{1,5}\.HK`。港股代码立即左补零为五位。失败abort。
2. **先选择resume或start-fresh并确定截止日**:查找`profiles/<ticker>-redflags-*.md`,读取`运行状态`、AS_OF和报告路径。显式flag优先;未传时,普通未完成报告默认resume,已完成报告默认start-fresh。`manual_review`不属于可自动resume的未完成状态;`output_quality_failure`不属于可自动resume的未完成状态。最近报告为任一上述终态时必须先显示`[edit/research more/start-fresh/exit]`,未显式选择前不得派发或自动重试,选择exit后保留原终态。多个可resume的未完成报告按报告日期降序、`-vN`中的N降序（base文件按v1处理）和完整路径稳定排序后只选最新一个,不得合并。证据阶段为未建立时允许manifest路径和SHA-256写`待建立`,resume必须回到Step 1.3继续取证;只有证据阶段为已绑定时才验证路径和SHA-256。证据已绑定时resume逐项验证已持久化manifest路径和SHA-256;路径或哈希不一致时不得resume,须保留旧报告并重新构建证据。resume沿用报告内AS_OF,显式`--as-of`冲突时abort;start-fresh优先采用显式`--as-of`,否则先只查询交易所官方目录,以选中目标完整年报首次有效披露日初始化并持久化AS_OF。上市日期必须来自交易所官方发行人资料并记录来源和响应哈希;后续下载命令追加`--listing-date <official-listing-date>`。初始化并持久化AS_OF后立即写入骨架报告。`初始化并持久化AS_OF`和骨架报告必须在任何年报下载命令、PDF下载或事件查询之前完成。必须在构造manifest之前完成选择,不得先下载后询问。
   **人工终态门槛**:上述菜单未显式选择时退出;不得把`manual_review`或`output_quality_failure`送入普通resume路径。
3. **保存下载前基线和骨架报告**:resume若已有canonical年报或事件manifest,在运行年报下载器之前分别复制为只读不可变snapshot并记录旧SHA-256;start-fresh若同一AS_OF的canonical文件已被旧报告引用,也执行相同快照并把旧报告改为引用snapshot。下载或live查询不得先覆盖该基线。随后按Step 2的Mode A骨架报告立即原子写入`进行中`状态、AS_OF和当前manifest路径;下载失败、用户选择no/show-command或进程中断都更新同一骨架报告,不得等取证成功后才创建状态。
3.5. **先采集官方查询bundle**:在任何`download_filings.py`命令前生成符合`../read-filing/references/event-query-plan.schema.json`的query plan。A+H发行人逐交易所保存`查询发行人代码映射[source_exchange]`,listing profile与subject roster保存完整请求契约,上市代码与日期只从官方响应取得。运行`uv run python scripts/collect_event_evidence.py --plan <absolute-query-plan.json> --bundle-out <absolute-official-query-bundle.json> --evidence-dir <absolute-immutable-evidence-dir>`并验证后,读取采集器stdout返回的真实bundle路径;后续下载器和构建器只使用该真实路径。失败时持久化原因并停止。
4. **Audit`data/filings/<ticker>/`**:准备最近10个财年年报,用于3/5/10年窗口。公司上市≥10年但文件不足时使用`uv run python scripts/download_filings.py <ticker> --years 10 --end-year <latest-required-fiscal-year> --as-of AS_OF --listing-date <official-listing-date> --listing-profile-bundle <actual-official-query-bundle-path> --manifest-out <temporary-annual-manifest-path>`。`--auto`自动执行下载;下载成功后重新audit,再重建两个manifest并执行完整source preflight;临时manifest与快照比较后才发布canonical路径。下载失败则持久化`需人工`终态并退出。只有`--interactive`显示`yes/no/show-command`;选择yes后执行,选择no或show-command后保留可恢复状态。上市历史不足10年时使用上市以来全部年报和可取得的官方上市文件历史数据,逐项标`上市历史不足,实际窗口N年`,不得把短窗口写成10年结论。
5. **建立canonical evidence**:只使用Step 2已持久化的AS_OF。Audit和任何下载结束后,按read-filing完整目录和版本规则发布`annual-reports-<AS_OF>.json`或内容变化时的`annual-reports-<AS_OF>-<content-sha256>.json`内容寻址版本;实际发布路径和SHA-256为唯一绑定依据。事件证据必须先采集后构建:query plan按`../read-filing/references/event-source-discovery.md`从实际官方请求发现来源,不得猜测接口;A+H发行人必须按两地官方代码和官方上市日期覆盖两地监管源。使用Step 3.5中采集器stdout返回的真实bundle路径运行`uv run python scripts/build_event_manifest.py --bundle <actual-official-query-bundle-path> --out <canonical-event-manifest-path>`。读取构建器stdout返回的真实发布路径,并把报告正文、失效集合、manifest路径和SHA-256通过CAS原子改绑;同一AS_OF证据变化时旧manifest保持不可变。每类事件覆盖全部适用官方来源,每类保存`source_count`和`sources`,逐source保存HTTP方法、请求编码和响应schema,并保存请求头、查询参数、响应和文书;构建器逐类在线重取全部事件分页,同类内再逐source与保存响应逐页一致。命中文书的本地路径单独放在`document_files`,不得混入官方响应;构建器重新下载每个官方文书URL并与本地文书逐字节哈希一致。临时事件manifest复核必须执行官方域名白名单、解析全部分页响应、分别校验`occurrence_date`和`publication_time`,并要求每个事件具备`offense_type`、`legal_effect`、`subject_role_at_occurrence`和`issuer_connection`,验证发行人/管理层/实控人/审计机构主体覆盖并限制状态枚举。主体名册必须保存官方URL、查询参数、原始响应和结果总数;构建器必须重请求主体名册的官方URL和查询参数,并逐项比较实时响应哈希、结果总数和完整主体列表;任一不一致立即abort。顶层`live_revalidation_required`必须为`true`;形成任何否定性结论前,按每个source保存的请求契约重新请求全部分页并复核响应与内容哈希。与Step 3快照逐字段比较,再执行与Mode B相同的source preflight,且必须覆盖其全部检查。source preflight成功后,把证据阶段从`未建立`原子转换为`已绑定`,同一次写入两个manifest路径和SHA-256;任一字段写入失败则全部保持`未建立`。证据阶段不是`已绑定`时不得进入完成终态或开始扫描。
6. **PDF预抽取cache**:所有参与窗口计算的PDF都调用`extract_pdf.py`以校验source_sha256;哈希不符自动重抽取。
7. **建立上游事实层**:主agent读取`references/thresholds.yaml`和`references/fraud-library.md`§1-§5。Mode A调用`read-filing` Mode A并追加`--complete-facts`;Mode B调用`read-filing` Mode B并追加`--complete-facts`,消费`facts/citations/warnings`。该模式触发L1-L3也继续完成排雷事实层。两种模式只有上游成功且manifest哈希一致时才能继续。

### Step 2 — 模式判定 + Output 准备

1. **解析 invocation**:
   - 无 `--target-profile` → Mode A
   - 有`--target-profile <path> --section part4/§4.5 --auto|--interactive`→Mode B

2. **Mode A 准备**:resume时加载所选报告并迁移缺失的运行字段,存在则加载并迁移,不得覆盖原文;start-fresh才新建`profiles/<ticker>-redflags-<YYYY-MM-DD>.md`,start-fresh遇到同日路径冲突时使用最小可用`-vN`后缀:

   ```markdown
   # <中英文公司名> 财报排雷 — <ticker>

   **研究者:** <git config user.name>
   **报告日期:** <today>
   **信息截止日（AS_OF）:** <AS_OF>
   **证据阶段:** [未建立/已绑定]
   **年报manifest:** <absolute-json-path>
   **年报manifest SHA-256:** <sha256>
   **监管事件manifest:** <absolute-json-path>
   **监管事件manifest SHA-256:** <sha256>
   **counterpart filing manifests:** <exchange>:<absolute-json-path>:<sha256>或无
   **基于年报:** 年报-<latest>.pdf (p.XX-YY)
   **模式:** standalone
   **运行状态:** [进行中/需人工/已完成/output_quality_failure]
   **终态:** [未终结/completed/manual_review/output_quality_failure]
   **依赖终态:** [无/dependency_failure]
   **manual_review_required:** [false/true]
   **失败原因:** [无/<具体错误>]
   **人工处理清单:** [无/逐项列出]

   ## §4.5.1 29项完整清单
   [表格: 项号 | 看哪里 | 触发条件 | 应采取动作 | 状态+严重度+证据]

   ## §4.5.2 6项高危附加检查
   [逐项填写状态+严重度+证据与动作]

   ## §4.5.3 三表勾稽4条
   [逐条公式+实际数+状态+严重度+证据与结论]

   ## §4.5.4 8类补充质检信号
   [逐项填写状态+严重度+证据与动作]

   ## §4.5.5造假识别5个维度
   [收入端/成本端/现金端/利润端/结构端逐项填写状态+严重度+证据与动作,再写综合结论]

	   ## §4.5.6银行10行替代bundle（仅银行）
	   [固定10行逐项填写状态+严重度+实际值+监管或历史/同业基准+页码+动作]

	   ## §4.5.7保险10行替代bundle（仅保险公司）
	   [按thresholds.yaml固定10行逐项填写状态+严重度+实际值+口径+监管或历史/同业基准+页码+动作]

   **发现的风险小结:**[1-2段]

   **引用:**
   - [小结中的叙述数字逐条映射到页码或独立来源]

   **估值阻断:**[否/是—原因]

   **结论:**[无重大风险/有保留/剔除]

   **置信度:**[高/中/低/需人工]
   ```

3. **Mode B准备**:读取`<target-profile>`和两个绝对路径manifest。两个manifest及全部counterpart manifest的路径和SHA-256必须与Part 0持久化路径及SHA-256映射一致;counterpart参数键集合必须完全相等,不得缺键、多键或跨法域代用。逐一运行`download_filings.py --revalidate`并在返回前再次计算文件哈希;任一漂移返回`dependency_failure`和`rebuild_evidence`。顶层`ticker`、`exchange`、`AS_OF`和`查询发行人代码`逐项等于target-profile的Part 0,查询参数中的发行人也必须一致。主体名册按持久化`source_url/http_method/request_encoding/request_headers/query_params/response_schema/response_adapter`重放,不得假定GET、query编码或固定分页字段;复核实时响应哈希、结果总数和完整主体列表,任一变化都abort并要求父skill重建。重新请求年报manifest的官方目录查询URL和参数,复核响应哈希、结果总数和完整候选集合;发现新增更正、撤销或替代版本时abort。逐类重新请求监管事件manifest的官方查询URL和参数,复核响应哈希、结果总数和逐事件内容哈希;漂移返回`dependency_failure`并请求`rebuild_evidence`。按精确标题定位§4.5,从标题和文件名解析ticker、exchange和report_date;英文公司名从Part 0元数据表读取,缺失时查交易所发行人官方名称,元数据缺失或冲突时报契约错误。逐行校验29行+6行+4行+8行+5行的状态、严重度、证据和触发后的实际动作;银行10行替代bundle和保险公司替代bundle按适用性追加,任一缺失不得判定完成。逐行按证据和thresholds.yaml重算状态与严重度,同步重算实际动作,不得保留与新状态矛盾的`无需动作`;重算结果与持久化值一致后才视为完成。再校验`发现的风险小结/造假维度综合结论/结论/置信度/估值阻断/建议动作/父级动作请求/排雷终态/排雷失败原因`和至少一条非占位机器引用;仅有层级标题不算完成。行业上下文只解释风险和动作,不得覆盖thresholds.yaml固定严重度。

### Step 3 — 派 subagent 排雷

**Mode B身份映射补充**:annual manifest标量`查询发行人代码`必须等于Part 0查询发行人代码映射[exchange];event manifest的查询发行人代码映射完整相等。不得把标量与整张映射直接比较。

派 ONE `general-purpose` 子 agent, prompt 英文, 强制中文输出。**必须包含**:

- ticker, 中英文公司名, exchange, report_date
- `AS_OF证据截止日`和event manifest绝对路径;监管、处罚、公告和财务证据都不得使用AS_OF之后发布或发生的证据
- **使用extracted cache时**:每个cache路径必须由annual manifest选中PDF路径派生,即按manifest选中PDF路径派生`<pdf-parent>/_extracted/<pdf-stem>/text.md`,不得按可变文件名或年份猜测。传入主年报及最近10个财年或上市以来全部可用年报的extracted绝对路径,并说明含`<!-- page N -->`markers
- **使用raw PDF时**:传入主年报和全部历史输入的raw PDF绝对路径,要求直接按PDF页码引用;不得同时声称使用不存在的extracted cache
- **29项完整清单**:按标题定位主template的§4.5 block并inline到prompt中（看哪里/触发条件/应采取动作三列+要求子agent填结果列）
- **6项高危附加检查**: 即使不在29项里也必须 flag; 阈值见 §2.2
- **8类补充质检信号**:按`fraud-library.md`§5逐项判断`异常/未见异常/不适用/需人工`并映射严重度,作为解释层,不擅自增加硬阈值
- **三表勾稽4条**: §2.3, 必跑, 给出实际数字 + 年报页码
- **造假识别5个维度**:按`fraud-library.md`§3逐项判断收入端/成本端/现金端/利润端/结构端,输出`沾边/未见异常/不适用/需人工`+严重度+证据,最后给出维度综合结论
- **银行10行替代bundle**:识别为银行时按§2.3固定10行逐项输出状态、严重度、实际值、基准、页码和动作;任一缺失不得判定完成
- **保险公司替代bundle**:识别为保险公司时保留29项行结构并把普通企业不适用项写`不适用/无`,另按`thresholds.yaml:checks.insurer_bundle.metrics`逐项输出固定10行及全部`required_output_fields`;缺证据写`需人工/待定`
- **每项回答**:量化检查按§2.4.1;定性检查按§2.4.2;触发时写出实际动作
- **禁用 "根据经验"**: 所有判断必须带页码或 URL
- **终态字段**:子agent输出末尾严格依次填写`**发现的风险小结:**`、`**引用:**`、`**估值阻断:**`、`**结论:**`和`**置信度:**`;小结为1-2段

子 agent 必读附注（对应 §4.5 29项高覆盖）:
- 货币资金受限/应收账款5大客户 + 账龄/应收票据银票 vs 商票/预付账款对象/其他应收款关联方/存货分项 + 跌价/在建工程转固/商誉减值假设/合同负债占营收/应付账款议价权/长投 + 金融资产分类/有息负债结构

### Step 4 — 主 agent 复核

读子 agent 产出。**驳回并 re-dispatch**若任一:

- 任一量化检查的`是/需人工`缺实际值、阈值或页码→退回;任一定性检查缺事件/主体/日期/文书或原文依据→退回;`否/不适用/通过/未见异常`也必须有证据,不满足§2.4.3a即退回
- 引用AS_OF之后的证据,或未用event manifest证明监管事件窗口→退回并按截止日重查
- 29项少答/跳答 → 退回补齐
- 6项高危附加检查未显式 flag → 退回重扫
- 8类补充质检信号少答/跳答→退回补齐
- 三表勾稽4条漏跑 → 退回补
- 造假识别5个维度少答/跳答→退回补齐
- 29项、6项、三表勾稽、8类补充信号和5个维度任一严重度缺失→退回补齐
- 识别为银行时,银行10行替代bundle任一行缺失或任一适用行缺状态、严重度、实际值、基准、页码或动作→退回;`不适用/无`行缺适用性依据和页码或URL也退回,任一缺失不得判定完成
- 识别为保险公司时,保险公司替代bundle任一行缺失或缺`required_output_fields`任一字段→退回;不得用普通企业CFO/存货或毛利率行替代
- 主agent逐行按触发条件和thresholds.yaml重算状态与严重度;`否/无`但证据命中阈值、`是/预警`但命中明确高风险阈值,或状态、严重度、证据、动作彼此矛盾时覆盖为重算结果并重新聚合
- 无论子agent是否已填写结论,主agent都按§2.6.3强制重算;不一致时覆盖为重算结果。无证据不得聚合为`无重大风险`
- 置信度缺失或与证据窗口不一致→按复核结果补齐或覆盖
- 风险小结空洞/仅列表,或`**引用:**`未覆盖小结中的叙述数字→退回改写§2.6.1格式
- Mode B 子 agent 填了主 profile §4.5以外的 section → 退回

自动复核失败时最多重派2次,每次只补明确缺口并保留已完成行。重试耗尽后不得无限重派:只有客观字段不可得时按§2.4.4填写缺失项的`需人工/待定`搜索日志证据和人工动作。若字段已经存在但输出缺行、枚举非法、JSON不可解析或结论与行级证据冲突,终态写`output_quality_failure`,置信度写`需人工`,并阻断估值;不得把输出格式失败伪装成字段客观不可得。交互模式的`research more`由用户显式触发,不计入自动重派次数。

Acceptable后写中文终稿。

### Step 5 — 写 summary + Output

Mode A使用全局`## 机器引用清单`;Mode B每个draft section使用模板内`**机器引用清单:**`。每条列`dependent_check_ids`,每个canonical check ID使用`checklist/1..29`、`high-risk/<id>`、`reconciliation/1..4`、`supplemental/1..8`、`bank/<id>`、`insurer/<id>`或`dimension/<id>`命名空间。联合类型均含最终持久证据的绝对`artifact_path`;`source_type=filing_text/filing_pdf`还含`source_pdf_sha256/artifact_sha256/page/quote`,`source_type=event_document`还含`event_manifest_sha256/document_url/content_sha256/artifact_sha256/page/quote`;HTML文书page可为null。action_requests.citations复用同一联合类型。resume时逐条复核机器引用并失效全部依赖ID。

**Mode A**:
- 最终发布前运行`uv run python scripts/download_filings.py --revalidate <bound-annual-manifest-path>`和`uv run python scripts/build_event_manifest.py --revalidate <bound-event-manifest-path>`,A+H还要逐一重验证全部counterpart manifest;再运行`uv run python scripts/publish_text_cas.py --source <draft-path> --target <final-report-path> --expected-sha256 <baseline-report-sha256> --guard <bound-annual-manifest-path>:<sha256> --guard <bound-event-manifest-path>:<sha256> --guard <counterpart-filing-manifest-path>:<sha256>`,非A+H省略最后一类guard;任一漂移或冲突不得覆盖
- 任一证据依赖获取或live revalidation失败时持久化`dependency_failure`、具体`failure_reason`和`manual_review_required=true`,不得发布`completed`;临时年报manifest只有通过复核并执行`scripts/download_filings.py --promote <temporary-annual-manifest-path> --canonical-out <canonical-annual-manifest-path>`后才能绑定
- 原子写入Step 2选定的报告路径;同步保存正文、运行状态、终态、依赖终态、`manual_review_required`、失败原因和人工处理清单。固定映射为:`已完成`→`completed/无`,`需人工`→`manual_review/<具体证据缺口>`,`output_quality_failure`→`output_quality_failure/<具体格式或一致性错误>`,`dependency_failure`→`需人工/未终结/dependency_failure/<具体依赖错误>`;对应`manual_review_required`依次为`false/true/true/true`。运行状态=进行中时终态固定写未终结,失败原因写无;未终结不是完成终态,不得参与成功聚合。中断恢复后按当前证据重算终态,不得写占位符
- 严格填写`**发现的风险小结:**`、`**引用:**`、`**估值阻断:**`、`**结论:**`和`**置信度:**`;结论3选1:`无重大风险/有保留/剔除`
- Mode A只记录建议动作;报告不得声称已执行父profile修改、估值阻断持久化或投资池操作
- 按§2.6.3持久化估值阻断。客观证据缺失重试耗尽时写`**运行状态:**需人工`、`**终态:**manual_review`、`**失败原因:**<具体证据缺口>`、`**置信度:**需人工`、`**估值阻断:**是—证据需人工`,保存搜索日志证据和人工动作。字段存在但输出缺行、枚举非法、JSON不可解析或证据结论冲突时写`**运行状态:**output_quality_failure`、`**终态:**output_quality_failure`、`**失败原因:**<具体格式或一致性错误>`、`**置信度:**需人工`和`**估值阻断:**是—输出质量失败`;两类终态不得互换或伪装成已完成
- 若结论=剔除,加`> 本ticker触发<风险列表>,建议不进入投资池;主value-profile若正在进行,应写Part 0 **估值阻断:**是—<风险原因>.`

**Mode B**:
- Mode B不直接写target-profile;仅返回精确定位的Part 4 §4.5 `draft_section`,保留heading和HTML注释,并返回`valuation_blocked`、`manual_review_required`、`failure_reason`、`filing_manifest_sha256`、`event_manifest_sha256`和完整`counterpart_filing_manifest_sha256s`供父skill原子保存。Mode B返回类型化`action_requests`,每项包含`request_id/type/reason/target_section_id/requested_confidence/execution_status/execution_result/citations`,由父skill复核和执行
- 按§2.6.3在draft中填写`**估值阻断:**`;结论为`剔除`时必须写`是`并返回`valuation_blocked=true`
- `--auto`通过主agent复核且无`需人工/待定`后直接返回调用方;重试耗尽时在draft保留搜索日志证据,置信度写`需人工`,返回`manual_review_required=true`和`valuation_blocked=true`,不得标`已完成`
- Mode B不显示菜单;存在`需人工/待定`时返回人工终态,不能伪装为已完成
- Mode B输出质量失败时返回`terminal_status=output_quality_failure`和具体`failure_reason`,并保持`manual_review_required=true/valuation_blocked=true`;不得降格为普通manual_review

**确认节点**:Mode A的`--interactive`终稿显示`[accept/edit/research more]`;`edit`→应用修改后重新复核并保存,`research more`→附加hint重新派发。Mode A的`--auto`复核通过后直接保存;Mode B的`--auto`复核通过后直接返回草稿,Mode B的`--interactive`也只返回草稿,由父skill决定是否保存。任何终稿确认都不提供`defer/skip`。

---

## §4 Policy

- **中文输出**: 填写区/引用/置信度 / summary / 结论均中文
- **中文空格规则**:只禁止两个中文字符之间出现不恰当空格;不禁止中文与英文或数字之间为可读性保留正常空格
- **引用必带页码**: `(年报-YYYY.pdf p.NN)` 格式
- **子 agent 输出禁空话**: "财务稳健/经营规范/无重大风险" 无具体数字 → 退回
- **不大段拷贝年报**: 抽取关键数字 + 金额 + 页码; 原话仅在疑点场景做1-2句引用

---

## §5 MUST NOT

- MUST NOT 编造数字/金额/页码。无来源写 `证据不足, 需人工补充`
- MUST NOT 跑 `git commit`——用户自 commit
- MUST NOT Mode B 下改主 profile 的 §4.5之外的其他 section
- MUST NOT Mode A 下把生意模式/估值/管理层写进本 skill 输出——本 skill 仅管排雷
- MUST NOT 接受 `defer` / `skip`——排雷强制
- MUST NOT 用英文写 profile 内容
- MUST NOT在没有可读filing时开扫。Mode A优先extracted cache;Mode B若父skill选择skip extraction,允许使用raw PDF并保留页码,但必须在prompt标明数据源。extracted和raw PDF都不存在才报错

---

## §6 References — 共享自 value-profile 主 skill

本 skill **引用**以下 reference（不复制内容）:

- `references/fraud-library.md` — **必读**, 本 skill 的深度操作手册:
  - §1风险10项（6项高危附加检查的阈值来源）
  - §2三表勾稽4条公式（§2.3的公式来源）
  - §3造假5维度（收入端/成本端/现金端/利润端/结构端）
  - §4 pattern 叙述 A1/A2/A3（channel stuffing / inventory hiding / vendor squeeze）
  - §5书中补充质检信号（员工薪酬/配套费用/现金流/治理/交易对手）
- `references/thresholds.yaml` — 跨skill共享阈值、市场基准、分母和严重度的唯一来源
- `../read-filing/references/statement-reading.md` §3 — 必读附注12项（对应29项清单的附注原始数据来源 — 由上游 read-filing 产出）
- `../read-filing/references/statement-reading.md` §6 — 特殊场景加读清单（商誉 > 20% / 有息负债 > 净资产/金融资产 > 营收等）
- `.claude/skills/value-profile/references/moat-framework.md` — 了解生意模型以判断某些风险的严重性（例: 消费品行业商誉20% 严重, 周期行业可能只是并购周期）

派子 agent 时, 若需更深操作手册, 在 prompt 里明确告知 "reference 路径 = `.claude/skills/financial-redflag-scan/references/fraud-library.md` 第 N 节"。附注12项原始数据路径: `.claude/skills/read-filing/references/statement-reading.md §3`。

---

## §7主 skill 调用契约（Mode B）

主 value-profile skill Step 5遇 §4.5时如下 delegate:

```

`risk_counts按最终行严重度计数`:每个canonical check ID按最终最高严重度进入一个桶,同一行只计数一次;综合维度和同一事实的多条引用不另增计数。
子 skill: financial-redflag-scan
传参: --target-profile profiles/<ticker>-<date>.md --section part4/§4.5 --as-of AS_OF --filing-manifest <absolute-json-path> --event-manifest <absolute-json-path> --auto|--interactive
期望:子skill填完§4.5 block（29项清单+6项高危附加检查+三表勾稽4条+造假识别5个维度+8类补充质检信号+`**发现的风险小结:**`+`**引用:**`+`**估值阻断:**`+`**结论:**`+`**置信度:**`）后交还控制
```

子skill返回主skill Step 5时区分两类终态:证据闭合且复核通过时,`--auto`或`--interactive`接受后派生控制台状态`已完成`;自动重试耗尽且仍有未决证据时,置信度写`需人工`,返回`manual_review_required=true`,加入人工处理清单并阻断估值,不得标`已完成`。`--interactive`选择research more时把hint附加后重新派发Step 3子agent。

Mode B只返回以下版本化JSON schema,不得增加并行顶层形态:

```json
{
  "schema_version": "1.0",
  "terminal_status": "completed",
  "failure_reason": null,
  "draft_section": "<part4/§4.5完整草稿>",
  "risk_counts": {"warning": 0, "high_risk": 0, "veto": 0, "pending": 0},
  "valuation_blocked": false,
  "manual_review_required": false,
  "filing_manifest_sha256": "<sha256>",
  "event_manifest_sha256": "<sha256>",
  "counterpart_filing_manifest_sha256s": {},
  "action_requests": [{"request_id": "<sha256>", "type": "deepen_research", "reason": "...", "target_section_id": "part4/§4.5", "requested_confidence": "medium", "execution_status": "pending", "execution_result": null, "citations": []}],
  "confidence": "high"
}
```

`terminal_status`只允许`completed/manual_review/output_quality_failure/dependency_failure`;只有`completed`时`failure_reason=null`,其余必须给具体原因。preflight或live revalidation漂移时返回`dependency_failure`,令`draft_section=""`、`manual_review_required=true`、`valuation_blocked=true`,并给`action_requests=[{"type":"rebuild_evidence",...}]`请求父skill重建,不得映射为输出质量失败。`action_requests.type`只允许`deepen_research/lower_confidence/block_valuation/management_review/valuation_route_review/rebuild_evidence`;`confidence`只允许`high/medium/low/manual_review`并与§2.6.4映射一致。父skill原子保存前不得把任何草稿字段视为已持久化。

子skill若发现§2.5管理层道德风险→同步建议主skill写Part 0`**估值阻断:**是—管理层道德风险`,主skill下一步应联动调用management-analysis子skill深查§4。

---

## §A 造假模式叙述库（子 agent prompt 附加深度上下文）

29项硬清单是**数字触发**; 以下3个**模式叙述** 帮子 agent 理解**为什么**数字异常 = 真实造假信号。主 agent 派 subagent 时作为 "pattern library" 附在 prompt 里, 不进29项计分, 但触发时必须在笔记中引用。

### A1客户塞货 (channel stuffing)
- **信号组合**: AR 增速 > 营收增速 ≥ 20pp **且** 存货增速 > 营收增速 ≥ 20pp **且** 应付账款 (AP) 增速趋缓/压缩
- **为什么**: 公司把货硬压给经销商, 确认营收; 经销商卖不动导致 AR 积压 + 自家存货同步膨胀; 同时供应商也知道销售疲软, 不再给信用期, AP 不增反降
- **典型场景**: 白酒/消费品渠道库存周期顶部; 集采前夕的医药公司

### A2库存减值掩盖 (inventory obsolescence hiding)
- **信号组合**: 存货周转天数翻倍以上 **且** 毛利率保持稳定 **且** 存货跌价计提/存货比值10年不升反降
- **为什么**: 存货占用资金翻倍 = 滞销; 正常情况毛利率应下降 (降价清库) 但却稳定 = 没做减值; 跌价计提比例反而走低 = 故意压缩减值以保利润
- **典型场景**: 周期股晚期 (钢铁/煤炭/猪); 电子/家电 technology refresh 前夕

### A3供应商融资压力 (vendor squeeze)
- **信号组合**: 应付账款天数 (AP days) 从正常60-90天被压缩到30-40天 **且** 营收加速 **且** 资产端现金仍在紧张
- **为什么**: 供应商担心公司经营不稳, 要求提前付款或缩短账期; 公司被迫动用现金流保供应链, 即便营收看起来在增长, 实际经营现金流承压
- **典型场景**: 高杠杆地产/扩张期互联网/大宗商品暴跌后的 commodity 公司; 也是破产前2-4季度的 early warning

---

**用法**:
- 上述3模式**不纳入29项计分**, 属于**深度解释层**; 若29项触发任一项, 且可对号入座到 A1/A2/A3, 在报告"发现的风险 summary" 段落明确引用并加注 "模式 A<N>"
- 主agent复核时,3个以上不同29项清单ID指向同一pattern时标`系统性造假高风险`,但pattern不得单独升级为剔除;只有行级`一票否决`可以把结论升级为`剔除`
