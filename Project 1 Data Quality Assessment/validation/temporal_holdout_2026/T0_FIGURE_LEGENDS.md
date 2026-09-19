# T0新期图件合同与图注

两幅均为quantitative grid，Python matplotlib，183 mm宽，Arial、7 pt正文/8 pt面板，开放边框外向刻度，SVG/PDF保留文本，600 dpi TIFF。数据为全部14支通道、7对同源点位和完整108天名义时钟。没有因为图形美观而抽掉通道、低分或缺证据。

## H3 | Frozen structural evidence has a restricted later-period reporting domain

**核心结论：** raw结构分数可计算不意味着可正式report；共享工况OOD和固定L1支持限制新期Full覆盖。

(a) 四个日历片段、逐通道D5正式report小时占名义sensor-hours比例。4月仅14–30日、7月仅1–30日。比例分母包含未评价时段，色阶0–100%，标出的0为真零。(b) D5资格互斥归因，按当前缺观测、context不完整、OOD、L1、report可用、其他的优先级判定。该优先级仅整理缺证据原因，不改分数，也不是因果归因。(c) DQR node Full、Basic及core不可评价的比例，分母同样是名义sensor-hours。

源表：`DQR_monthly_coverage.csv`、`D5_coverage_reasons.csv`；底层D5/DQR逐行parquet。每月同时刻各通道共享工况，不作为独立重复。描述性全量统计，无检验、无CI、无多重比较。14支通道相同覆盖模式不提供14次独立验证。

## H4 | Fixed-core quality and natural low-tail burden under information-time alignment

**核心结论：** 固定core、随证据变化的available和Full条件估计对象必须分开，低分负担需按可评价暴露量定义。

(a,b) node和pair先形成plant-hour通道/点位对算术均值，再形成日时间均值。缺少Full的日不插值跨接；Full不是全部通道总体估计。core、available及Full采用冻结公式；D3仅安全门控，D4仅pair。(c) D2<3与Veto小时数，均除以各通道可评价sensor-hours并乘1,000，量纲一致；标记略作纵向错位以辨认重合值。(d) D4正式可评价范围中D4<3的小时负担，每1,000可评价pair-hours。图为无CI的描述性自然报警结果，不称故障检出率或误报率。

源表：`DQR_daily_quality_coverage.csv`、`channel_burden.csv`；各项nominal/evaluated/low/veto计数可追溯。每日Full可用集合会变，首日受历史末日空值与续接边界影响。新期末端没有满足3分钟延迟的完整D1/D4小时，因此DQR名义网格保留NA。

## 检查

输出画布和可见文字边界程序检查通过，人工检查图例、统一ID、端点、真实零值、缺证据断线和可读性。源静态Nature检查只是工程预检，不代表科学结论或期刊录用保证。H1/H2为历史开盲前审计图，状态文字保留当时含义。
