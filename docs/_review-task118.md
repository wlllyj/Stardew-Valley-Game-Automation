# task-119 二次 delta 复验：task-118（`9df8c3b`，教训库来源标记 / 名额竞争）

- 验收人：deputy-lead（task-119，owner）
- 对象：**task-118 = `9df8c3b`**（`brain/agentfarm/longrun.py` +24、`brain/agentfarm/planner.py` +83、`tests/test_longrun.py` +127、`tests/test_planner.py` +114；合计 +336/−12）
- 前置：task-115（我）判 **FAIL**，理由是 task-114 只把 `kind/id/类型/文本长度` 钳住、**没钳 `last_seq`/`count`**，而排序键 `(last_seq, severity, count)` 让外部写入者能自抬首位、把真教训挤出 `LESSONS_MAX=20`（A1c 18/20、A2b/A2c/A2d 19/20）。Lead m05415 裁定成立并立 task-118（修）+ task-119（本次复验）。
- 判定：**PASS-WITH-NITS**（三个点名反例全部关掉、防洗白成立、零判定影响与 F2/NIT-1 无回退、范围与全量 0 红；两条非阻塞 NIT 见 §5）

## §1 一句话结论

task-118 的三角修法（`src` 来源标记 + 载入侧 untrusted 判定与钳位 + 排序键 `(trusted, last_seq, severity, count)` + 回写只写可信）**确实关掉了我 task-115 的三个反例**：20 条可信教训在单喂/五类混喂的伪造条目下均 **20/20 存活**，伪造既不进提示词也不占首位；防洗白实测成立（伪造文本不落盘、重载后 `untrusted=0`）；四个形态的判定字段与关闭机制时**逐字相同**。两条 NIT 与名额/洗白无关，不阻塞 0.7.28。

## §2 范围与读数（我亲跑）

| 项 | 结果 |
| --- | --- |
| HEAD | `9df8c3b`；`git status --short` **干净** |
| `git show --stat 9df8c3b` | 恰 4 文件（longrun.py +24 / planner.py +83 / test_longrun.py +127 / test_planner.py +114），合计 +336/−12 |
| 越界扫描（`^mod/`、`^tools/`、`manifest.json`、`bridge.py`、`^logs/`、`00-开发日志`） | **0 命中** |
| SHA256 前 16 | `planner.py B69382C1EBD19D35`、`longrun.py D597A32FCE519144`、`test_planner.py 6D68958B43C54A86`、`test_longrun.py DA0703C6C6818AAF`；未变 `farmwork.py 3D2A9E5AD4B84A7A`、`tools/verify-run3.py 7356D4CBA1D0A1EE`、`tools/compare-runs.py CC86CAEAB38363CF` |
| `py_compile -W error::SyntaxWarning` | exit 0 |
| `tests.test_planner tests.test_longrun` | **Ran 280 / OK**（与作者自报一致） |
| 全量 `discover -s tests` | **Ran 685 / OK / 0 红**（与 Lead 亲核一致） |

## §3 逐条对卡（Lead m05419 的五项）

| # | 要求 | 结果 | 证据 |
| --- | --- | --- | --- |
| ① | 点名反例逐条自复现：20 条可信 ⇒ 20/20、伪造不进提示词、不占首位 | **PASS** | B1（原 A2b `last_seq=999999`）20/20、`伪造在库内=False`、`rank0=stage_incomplete|g20`、提示词无 `MARKER-EVICT`、`lessons_rejected{untrusted:1, reasons:['clamped:last_seq']}`；B2（A2c `last_seq=21`）/B3（A2d `last_seq=1,count=10**9`）同；B4（卡面五类混喂）20/20、`untrusted=3 dropped=2`、reasons `['truncated:symptom','unknown_kind','id_mismatch','clamped:last_seq']`；**B5（库内只有 5 条可信 + 2 条不可信）** ⇒ 可信 **5/5** 全留、两条不可信只补库内空位且全部排在可信之后（`ids=[g5..g1, encircled|clear_area, unreachable|clear_area]`），注入的前 3 条仍是可信、提示词里不出现外部前缀（补位 ≠ 抢位） |
| ② | 防洗白：回写只持久化可信；重载仍不可信 | **PASS** | W1 回写文件只有 `src=agentfarm` 条目、伪造文本不落盘；W2 重载 `untrusted=0`；W3 journal `lessons{written:2, skipped_untrusted:1}`；W4/W5 当天内存里伪造**可见**但带 `[外部条目·未验证]` 且排在真教训之后 |
| ③ | 零判定影响四形态未回退 | **PASS** | C1 开/关逐字相同 + 退出码相同；C2 合法 schema 篡改（`rejected=[(0,['clamped:last_seq'])]`）、C2b 不合 schema（`rejected=[(1,['unknown_kind'])]`）、C3 坏 JSON（`lessons_load_failed=1`）、C4 复盘抛错——四者判决字段全部逐字相同 |
| ④ | F2 四档丢弃顺序 + NIT-1 真值 evidence 未回退 | **PASS** | 四档 `(lessons,decisions,notes)` = `(T,T,T)/(T,T,F)/(T,F,F)/(F,F,F)`、总长 2042/2041/2040/1947、本体字段四档逐字完整、无半节；D1/D2 `buy_no_space_facts={'free_slots':8,'free_slots_status':'ok','seeds':0,'money':500,'item':'472','price':0}`、教训 evidence=`free_slots=8/ok seeds=0 money=500g item=472`（与实测一致、不含写死的"空格=0"） |
| ⑤ | 范围 + 全量 0 红 | **PASS** | 见 §2 |

## §4 对抗矩阵（38/38 PASS，脚本 `scratch/_t119_probe.py`，原始读数 `scratch/_t119_probe_out.txt`）

### 4.1 B 段：task-115 反例正向化

| 例 | 输入（20 条可信 + 伪造） | 可信存活 | 伪造进提示词 | 伪造在库内 / 首位 | 留痕 |
| --- | --- | --- | --- | --- | --- |
| B1 | `last_seq=999999`（我的 A2b） | **20/20** | 否 | 否 / `g20` | `untrusted=1`、`clamped:last_seq` |
| B2 | `last_seq=21`（我的 A2c） | **20/20** | 否 | 否 / `g20` | `untrusted=1`（21=max(可信)+1，未越界 ⇒ 无 clamped 理由，属预期） |
| B3 | `last_seq=1, count=10**9`（我的 A2d） | **20/20** | 否 | 否 / `g20` | `untrusted=1` |
| B4 | 卡面五类同喂（我的 A1c） | **20/20** | 否 | 否 / `g20` | `untrusted=3`、`dropped=2`（两条走 schema 拒收） |
| B5 | 库内只有 5 条可信 + 2 条不可信 | **5/5** | 否（注入前 3 条全是可信） | 只补库内空位、全部排可信之后 | 库内 7 条；不可信不占首位 |

### 4.2 来源面 / 钳位 / 前缀

- S1 `make_lesson()` 带 `src=agentfarm`；S2 可信+不可信同 id 合并 ⇒ 合并条目**丢掉 `src`**（取最保守，不沾可信身份）；S3 两条都可信 ⇒ 保留 `src`。
- S4 1 条可信 + 2 条不可信 ⇒ 顺序 `[Tfar_dry_given_up|water_far, Uunreachable|clear_area, Uencircled|clear_area]`，不可信 `last_seq` 钳到 6（=max(可信)+1）、`count` 钳到 1,000,000。
- S5 `report={'dropped':0,'reasons':['clamped:last_seq','clamped:last_seq'],'untrusted':2}`；S6 渲染前缀只加在不可信行（`- 可信-干格认输` / `- [外部条目·未验证] MARKER-OUT-1`）。
- S7 旧格式整库无 `src` ⇒ 3 条全部 untrusted、`last_seq` 钳到 1、仍可见且带前缀（不抢位，因为整库无可信条目）。

### 4.3 防洗白与同 id 合并

- W1–W5 见 §3 ②；W6（NIT 取证）单条可信 + 同 id 伪造 ⇒ 跑一天后**持久化库为空**（`saved=[]`）。

### 4.4 未回退回归

- F2 四档、C1–C4 零判定影响、D1/D2 NIT-1：全 PASS（数值见 §3）。

## §5 NIT 表（均不阻塞 0.7.28，与名额竞争/洗白无关）

| # | 现象 | 行号 | 影响 | 建议 |
| --- | --- | --- | --- | --- |
| NIT-1 | `count` 钳位只在载入侧**逐条**生效，`prune_lessons` 合并时累加可越过 `LESSON_COUNT_MAX`（实测两条 10^6 合并 ⇒ **2,000,000**） | `planner.py:_sanitize_lesson`（钳位）、`planner.py:prune_lessons`（合并累加） | `count` 是排序键第 4 位且**只在同信任级内**比较 ⇒ 抢不到可信名额，无白过通道；仅是"上限不是不变量" | 合并后再 `min(count, LESSON_COUNT_MAX)`（一行） |
| NIT-2 | 可信条目与外部同 `id` 条目合并后 `src` 被摘掉（S2 设计如此）⇒ 该 id **不再回写**，真教训从持久化库消失（W6 `saved=[]`） | `planner.py:prune_lessons` 的 `cur.pop("src", None)` + `save_lessons_file` 只写可信 | 有损（学习素材丢失），但伪造文本同样不落盘（W1/W2）⇒ 不是洗白也不是抢名额；且威胁模型里"能写教训库文件"本就等于可整库删除 ⇒ 不额外扩大能力 | 合并时若 `cur` 原本可信则保留 `src`（或在 flush 前把可信条目单独落盘） |
| INFO-1 | 卡面五类里 `unknown_kind`/`id_mismatch` 走 `dropped`，另三类走 `untrusted` ⇒ `untrusted=3 dropped=2` | `longrun.py:_lessons_load` / `planner.py:load_lessons_file` | 字段语义与卡面一致（拒收 vs 收下但降级），非缺陷 | 无需动作 |
| INFO-2 | 作者新增 `lessons_rejected.untrusted`、`lessons.written`/`skipped_untrusted`、渲染前缀属**新字段**（Lead 已另派小卡给 analyzer） | `longrun.py` | 不影响判定 | 由 analyzer 卡收 |
| INFO-3 | **「完整内容模板校验留 0.7.29（task-117）」的影响面再确认**：本次最小版把**无 `src`** 的外部条目收窄为"不抢名额、不进注入前 3 条、带前缀可见"，且可信条目的 `last_seq` 只由 agentfarm 自己写、不再被外部抬高；残余面 = **能伪造 `src="agentfarm"` 的写入者**仍可用自由文本占最高优先级 | `planner.py:_sanitize_lesson`/`render_lessons` | 与本次判定无关；对"只能写库文件、不知 `src` 约定"的敌意写入者已被基本封死 | 同意仍留 0.7.29，task-117 动机句可改写为"能伪造 src 的写入者" |

## §6 复跑命令

```powershell
$py = "C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$env:PYTHONUTF8 = "1"; $env:PYTHONPATH = "D:\Deepseek Harness Workspace\星露谷游戏自动化\brain"
Set-Location "D:\Deepseek Harness Workspace\星露谷游戏自动化"
& $py "scratch\_t119_probe.py" 2>&1 | Out-File -Encoding utf8 "scratch\_t119_probe_out.txt"
& $py -m unittest tests.test_planner tests.test_longrun 2>&1 | Out-File -Encoding utf8 "scratch\_t119_targeted.txt"
& $py -m unittest discover -s tests 2>&1 | Out-File -Encoding utf8 "scratch\_t119_full.txt"
# 两条 NIT 的最小复现：
#  NIT-1：库里放两条同 id、count=LESSON_COUNT_MAX 的无 src 条目 ⇒ 载入后 merged count = 2*10**6
#  NIT-2：库里放一条可信 + 一条同 id 无 src 条目 ⇒ 跑一天后 lessons 文件为空
```

## §7 结论与建议

- task-118 **达成了 task-115 的点名要求**：外部条目不再能抢可信教训的名额、不再能进次日提示词、不再能占据首位；回写只写可信条目、不可信条目在内存中可见但被显式标注。
- 零判定影响、F2 丢弃顺序、NIT-1 真值 evidence 全部未回退；范围干净、全量 685 OK / 0 红。
- 建议：**0.7.28 可放行**；两条 NIT 归 0.7.29（与 task-117「完整内容模板校验」同批，卡面可加一句"合并后 count 重新钳位""同 id 合并不得让可信条目掉出持久化库"）。
- 本次不改判 task-115 的 FAIL 结论：那条 FAIL 针对的是 task-114，本卡（task-118）是它的修复，判定为 PASS-WITH-NITS。
