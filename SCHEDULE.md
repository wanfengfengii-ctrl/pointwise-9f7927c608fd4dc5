# 周期巡检日程

白班工艺员在一个固定计划上登记循环日程。夜班按日程号签发长期占用，排班员按报告号领取原件。现有规程登记、计划冻结、比例核账、静态报告和运行方式见 `README.md`。

## 调用与返回值

| 新入口 | 返回 |
| --- | --- |
| `plan.freeze.freeze_schedule(archive, plan_id, stages)` | 日程号 `str` |
| `publication.issue.issue_schedule_report(archive, schedule_id, *, before_commit=None)` | `(report, receipt)` |
| `publication.read.read_schedule_report(archive, report_id)` | 按报告号读取已保存的 `(report, receipt)` |

`archive` 使用现有 `HandoverArchive`。`stages` 是非空有序集合，每项为 `(name, ratio, steps)` 三元组。阶段名为非空白字符串，在该日程内唯一，保留原字符串及位置。比例在闭区间 [0, 1] 内，接受 V1 的 `Fraction`、整数和精确有理字符串。步数为非布尔正整数。日程冻结固定计划号和规范化后的有序阶段，随后修改输入集合不影响该日程。

报告通过 `report_id`、`schedule_id`、`plan_id`、`stations`、`stages`、`stage_occupations` 和 `round_occupation` 属性交付。`stations` 为计划原序工位名元组，`stages` 为原序三元组的元组，比例规范为 `Fraction`。`stage_occupations` 为按阶段原序排列的向量元组，`round_occupation` 为整轮向量。所有占用向量以工位原序排列，元素均为 `Fraction`。回执沿用 `publication.receipt.IssueReceipt`，其报告号和计划号与报告相同。重开后的读回值与签发返回值相等。

## 占用口径

原计划开工分布位于首阶段第一步之前。各阶段按冻结顺序执行各自步数，依 V1 路线和留驻规则取该阶段比例下的逐步转移，末阶段结束后接续首阶段。每一步归入执行该步的阶段，并记录执行之前的工位分布。各阶段向量是从开工起、跨重复轮次对该阶段所有步前分布取长期算术平均。整轮向量是所有执行步的长期平均，因此各阶段以实际步数加权。整轮存在多个闭类或轮间周期时仍使用指定开工分布。允许全量重算。

## 归档与失败

更正源规程、移开源库并重开归档后，按原日程号仍可签发。读取使用报告和回执的已存结果，不重新计算占用。非法业务输入抛 `ValueError`，格式合法但在相应入口未知的编号抛 `KeyError`。沿用 V1 的非空白编号约定和异常传播。冻结失败无新日程。签发时报告和回执同次提交，`before_commit` 是在两件暂存后、提交前运行的可选无参回调，按 V1 约定观察或抛出异常。失败后无新报告或回执，旧件可继续领取，同一日程可重试。

## 手算样例

`schedule_examples.py` 用原接口准备固定计划，并可直接运行核对示例规程的 V1 数据。`prepare_swap_plan` 固定 A、B 两工位及从 A 开工的计划，两条换位路线的逐步概率均为比例本身。下列向量顺序均为 `(A, B)`。

| 阶段输入 | 阶段向量 | 整轮向量 |
| --- | --- | --- |
| `ABA`，比例依次为 1、1、0，每段一步 | `((1,0), (0,1), (1,0))` | `(2/3, 1/3)` |
| `ABB`，比例依次为 1、0、1，每段一步 | `((1,0), (0,1), (0,1))` | `(1/3, 2/3)` |
| `WEIGHTED`，比例依次为 1、1、0，步数为 1、1、2 | `((1,0), (0,1), (1,0))` | `(3/4, 1/4)` |
| `SINGLE_SWAP`，比例 1，持续一步 | `((1/2,1/2),)` | `(1/2, 1/2)` |
| `DOUBLE_SWAP`，比例 1，持续两步 | `((1/2,1/2),)` | `(1/2, 1/2)` |

`prepare_split_plan` 固定 `(A, B, C)`，从 A 开工。比例 0 下，A 每步以 `1/4` 到 B，以 `1/2` 到 C，其余留在 A；B、C 在比例 0 下留驻。`ZERO_SPLIT` 的每阶段及整轮均应为 `(0, 1/3, 2/3)`。

实现新增入口后，可按以下方式重现白班登记、源规程更正和夜班签读。

```python
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

from archive.catalog import HandoverArchive
from plan.freeze import freeze_schedule
from publication.issue import issue_schedule_report
from publication.read import read_schedule_report
from routing.intake import record_revision
from routing.revision_store import RevisionStore
from schedule_examples import ABA, ABB, SWAP_ROUTES, prepare_swap_plan

with TemporaryDirectory() as directory:
    source_path = Path(directory) / 'routing.sqlite'
    archive_path = Path(directory) / 'handover.sqlite'
    with RevisionStore(source_path) as source, HandoverArchive.open(archive_path) as archive:
        plan_id = prepare_swap_plan(source, archive)
        first = freeze_schedule(archive, plan_id, ABA)
        second = freeze_schedule(archive, plan_id, ABB)
        record_revision(source, ('A', 'B'), (0, 1), SWAP_ROUTES)
    source_path.rename(source_path.with_suffix('.offline'))
    with HandoverArchive.open(archive_path) as archive:
        issued = [issue_schedule_report(archive, schedule_id) for schedule_id in (first, second)]
    with HandoverArchive.open(archive_path) as archive:
        for (report, receipt), expected in zip(issued, (Fraction(2, 3), Fraction(1, 3)), strict=True):
            assert report.round_occupation == (expected, 1 - expected)
            assert read_schedule_report(archive, report.report_id) == (report, receipt)
            print(report.schedule_id, report.report_id, report.stage_occupations, report.round_occupation)
```

沿用 `.pointwise-runtime.json` 的 V1 `cli` 清单。`setup` 保存准备命令的 argv 列表，`verify` 和 `demo` 各保存一条命令的 argv。接通原回归及新增联合核验，验证失败保留非零退出码。演示展示两份日程在断源后签发的阶段占用和整轮占用，以及重开后的报告和回执领取。
