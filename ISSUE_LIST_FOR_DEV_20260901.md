# 问题清单（移交开发者修复）

- 生成日期：2026-09-01
- 生成方式：全仓代码审查 + 完整测试套件复跑验证（`118 passed in 43.13s`）+ 数据库自省
- 验证环境：Python 3.12 venv（`.venv`），Windows，pytest 118 例 / 31 个文件
- 适用对象：量化资产监控系统（`d:\量化资产监控系统`）

> 说明：本清单所有结论均基于源码复读与复跑实测，不含推测性描述。每条问题给出文件路径、根因、证据与建议修复方向，可直接按优先级派单。

## 问题汇总表

| 编号 | 级别 | 类别 | 主题 | 状态 |
|------|------|------|------|------|
| P0-1 | P0 | 可追溯性 | git 不可用导致 `code_version` 降级，运行记录无法关联 commit | 待修复 |
| P0-2 | P0 | 稳定性 | 单测间歇性失败（PermissionError），间歇复现 | 需加日志/隔离复现 |
| P1-1 | P1 | 死代码 | `domain/exceptions.py` 全仓零引用，且与 `ProviderError` 重名 | 待确认后清理 |
| P1-2 | P1 | 死代码 | `backtest/full_model.py` 重复定义 `FullModelStrategy` 且未被使用 | 待确认后清理 |
| P2-1 | P2 | 基线过期 | QA 基线 108 passed vs 当前 118，未随测试新增更新 | 待重新生成 |
| P2-2 | P2 | 工程卫生 | 根目录堆积 16+ 个 `.pytest-tmp*` 目录，清理受 Windows 文件锁阻塞 | 待清理+治理 |
| P2-3 | P2 | 环境一致性 | QA 基线记录 git 模式哈希，但当前环境 git 不可用 | 待统一 |
| P3-1 | P3 | 数据状态 | DB `observations=0`，`wind_evidence_staging=189,768` 未进入正式链路 | 数据准入阻塞 |
| P3-2 | P3 | 数据状态 | Wind 生产准入 PARTIAL（LEGAL/STABILITY UNKNOWN） | 外部依赖 |
| P3-3 | P3 | 数据状态 | FRED ALFRED 因 vintage 超限停止，宏观数据 PARTIAL | 外部依赖 |

---

## 一、环境与可复现性（P0）

### P0-1 git 不可用，`code_version` 降级，运行可追溯性问题

- **文件**：`src/cross_asset/storage/provenance.py`（第 31-37 行，`code_version()`）
- **现象**：本机 `git` 不在 PATH（`git --version` 报 CommandNotFoundException）。`code_version()` 在 `subprocess` 调用失败后降级返回 `no_commit+source_tree:{hash}`，不携带任何 commit 引用。
- **证据**：
  - DB 中 `model_runs` 记录的 `code_version` 均为 `no_commit+source_tree:...` 格式，多次运行哈希各不相同且无法关联到具体代码版本。
  - 对照 `artifacts/qa/latest.json`：其 `code_version` 为 git 模式哈希（`ddad1d97569a0dc1290fe1d9c4f49c21a4e236ce`），说明基线生成时 git 可用，与环境现状不一致（见 P2-3）。
- **影响**：模型运行结果的 provenance 无法指向确定 commit，审计链条断裂，违背项目 PIT/可溯源纪律。
- **建议修复方向**：
  1. 统一开发/CI 环境：在 PATH 中提供 git，或将 `.git` 纳入必须依赖；`pyproject.toml` 或 CI 配置中显式声明前置条件。
  2. 增强 `code_version()` 的鲁棒性：当 git 不可用时，将降级原因（异常信息脱敏）写入输出并告警，而不是静默降级。
  3. 在仓库根添加环境检查脚本/文档，明确"无 git 不可生成可验证 provenance"。

### P0-2 单测间歇性失败（PermissionError），无法稳定复现

- **文件**：`tests/unit/test_evidence_shadow.py`（第 73-105 行，`test_local_experiment_persistence_is_idempotent_and_explainable`）
- **现象**：完整套件运行曾出现 `117 passed, 1 failed`，失败测试报 PermissionError；单独重跑仍失败。但本次验证中，单独重跑通过（1 passed in 1.51s），随后完整套件复跑 **118 passed in 43.13s** 全部通过。
- **证据**：
  - 本测试会在 tmp duckdb 中写入 `wind_evidence_staging` 后调用 `local_experiment(persist=True, project_root=".")`，两次运行断言 `run_id` 相同、`first.reused=False`、`second.reused=True`。
  - 失败窗口与 Windows 文件锁、`.pytest-tmp*` 目录残留（见 P2-2）时间上相关，但本次无法稳定复现，**根因未确认**。
- **影响**：CI 偶发红盘，干扰"通过=健康"的判断，掩盖真实回归。
- **建议修复方向**：
  1. 排查失败时的运行上下文（是否与其他测试/并行进程共享 `project_root="."` 下的持久化文件）：
     - 检查 `local_experiment` 写入目标（DB 文件、artifacts 目录）在测试间是否被并发打开。
     - 确认 `project_root="."` 传参是否会在测试并发下彼此干扰。
  2. 为测试增加隔离：全部 I/O 指向 `tmp_path`，不触碰仓库根的工作文件。
  3. 复现策略：以 `pytest -x -k local_experiment` 循环压力运行（如 50 次）采集失败现场，定位具体被锁文件。
  4. 短期缓解：CI 中为 pytest 设置独立 basetemp，并在任务间清理。

---

## 二、死代码与命名冲突（P1）

### P1-1 `domain/exceptions.py` 全仓零引用，且 `ProviderError` 重名

- **文件**：`src/cross_asset/domain/exceptions.py`（第 1-14 行，定义 `CrossAssetError`、`ConfigurationError`、`DataUnavailableError`、`ProviderError`）
- **现象**：全仓（`src/` + `tests/`）无任何 `import` 引用这 4 个异常类（grep 全仓仅命中定义行自身）。
- **证据**：
  - grep `domain.exceptions|CrossAssetError|ConfigurationError` 全仓：仅命中 `exceptions.py` 内部 4 行定义。
  - 同时存在同名类：`src/cross_asset/providers/base.py` 第 14 行定义 `class ProviderError(RuntimeError)`，且被本模块第 41 行使用——两套 `ProviderError` 语义不同（一个继承 `CrossAssetError`，一个继承 `RuntimeError`），容易引发误导入/混淆。
- **影响**：死代码增加维护成本；同名异常类增加误用风险（捕获异常时可能 catch 错层级）。
- **建议修复方向**：
  1. 确认业务侧是否有意使用 `domain.exceptions`：若无，删除该文件。
  2. 若需保留统一异常体系：将 `providers/base.py` 的 `ProviderError` 改为继承/复用 `domain.exceptions.ProviderError`，消除重名。
  3. 补充 lint 规则（如 `vulture` / `ruff` F401 之外的未使用检测），阻止死代码回流。

### P1-2 `backtest/full_model.py` 重复定义 `FullModelStrategy` 且未被使用

- **文件**：`src/cross_asset/backtest/full_model.py`（第 7-23 行，`class FullModelStrategy`）
- **现象**：仓库中另有一份真正被使用的同名类：`src/cross_asset/backtest/replay.py` 第 115 行 `class FullModelStrategy`，被 `golden.py`、`ingestion/live_run.py`、`tests/unit/backtest/test_replay_acceptance.py` 引用。`full_model.py` 中的该类无任何引用。
- **证据**：
  - grep `FullModelStrategy` 全仓：引用全部指向 `replay.py`；`full_model.py` 仅命中定义行本身。
  - `full_model.py` 内部引用的 `ASSET_SERIES` / `STRATEGIC` 来源与 `allocation.yml` 权重体系不同，若被误用会产生与当前策略不同的结果，属隐患。
- **影响**：同名双实现易被误 import；死代码维护成本；策略引用混乱风险。
- **建议修复方向**：
  1. 确认 `full_model.py` 是否为历史遗留实验脚本：若是，删除或移入 `scripts/`（且确认不被 `source_tree_hash` 之外的任务依赖）。
  2. 若 `replay.py` 的 `FullModelStrategy` 为唯一权威实现，删除 `full_model.py` 时同步清理其 import 关系。
  3. 建议全仓建立"符号唯一性"检查（如自定义 pytest 插件或 CI grep），防止重复类名再次引入。

---

## 三、工程卫生与基线管理（P2）

### P2-1 QA 基线过期：记录 108 通过，当前 118 通过

- **文件**：`artifacts/qa/latest.json`（`pytest.passed_count: 108`，`generated_at: 2026-09-01T03:38:13Z`）
- **现象**：当前完整套件实测 `118 passed in 43.13s`，与基线 108 相差 10 个用例；基线未随新增测试重新生成。
- **影响**：基线失去"回归参照"作用，无法判断新增测试是否引入异常。
- **建议修复方向**：修复完 P0/P1 后重新运行 `qa_baseline` 生成新基线；建议在测试数量变更时自动触发基线更新或至少产生告警。

### P2-2 根目录 `.pytest-tmp*` 目录堆积且清理受阻

- **文件**：项目根目录残留 16 个 `.pytest-tmp*` 目录（含 `.pytest-tmp-qa`、`.pytest-tmp-fullmodel*`、`.pytest-tmp-final-audit*` 等，时间跨度 2026-08-30 ~ 2026-09-01）；`src/cross_asset/operations/qa_baseline.py` 第 20 行固定使用 `--basetemp .pytest-tmp-qa`。
- **现象**：
  - 多次运行 pytest（显式 `--basetemp` 与默认模式）在根目录留下大量临时目录。
  - 清理时批量 `Remove-Item` 报 Access denied（Windows 文件锁，进程句柄未释放）。
- **影响**：仓库根目录污染；`source_tree_hash` 虽已排除临时目录（仅扫 `src/`、`scripts/`、`pyproject.toml`、`uv.lock`），但残留文件仍占用磁盘与干扰人工排查；文件锁可能关联 P0-2 的 PermissionError。
- **建议修复方向**：
  1. 将 pytest 临时目录统一收敛到系统临时目录（如 `%TEMP%\ca-pytest-tmp`）或 `.gitignore` 明确排除。
  2. 在 CI/脚本中加入前置清理（先杀残留 python 进程再删目录）。
  3. 为 `qa_baseline.py` 的 basetemp 增加时间戳或运行 id 后缀，避免固定目录被复用导致锁冲突。

### P2-3 QA 基线 code_version 与环境现状不一致

- **文件**：`artifacts/qa/latest.json`（`code_version: ddad1d97569a0dc1290fe1d9c4f49c21a4e236ce`，git 模式）
- **现象**：该哈希是 git commit 模式产出，但当前环境 git 不可用（见 P0-1），且当前运行实测为 `no_commit+source_tree:...` 格式。
- **影响**：基线产物无法在当前环境复现/核验，provenance 对不上。
- **建议修复方向**：随 P0-1 一并处理：统一环境后重新生成基线；`code_version` 输出中增加"生成环境标记"（git 可用 / 不可用）。

---

## 四、数据链路状态（P3，外部依赖/阻塞项，非代码缺陷）

> 以下为数据准入与外部数据源的状态，不构成代码 bug，但阻塞整体交付（`DATA_BLOCKED`），需要开发/数据侧跟进。

### P3-1 DB 正式观测数据为空

- **现状**：`observations` 表 0 行；`wind_evidence_staging` 189,768 行（Wind 导入 staging 已完成但未进入 canonical 链路）；`wind_evidence_staging` 来源含 CSV 113,012 行 + XLSX 76,756 行（见 `artifacts/wind_import/WIND_IMPORT_REPORT_20260901.md`）。
- **影响**：模型链在空观测数据上运行，allocator 输出（如 CN_EQ 38.18% / HK_EQ 14.92% / CN_BOND 30.72% / CASH 16.18%）在数据落地前不具备落地意义。
- **建议**：完成 canonical series 的 staging→正式表 数据过渡后重跑模型链并重出报告。

### P3-2 Wind 生产准入 PARTIAL

- **现状**：9 条候选 series 技术/PIT 检查 PASS、Grade C，但 LEGAL/STABILITY 为 UNKNOWN（见 `artifacts/production_admission/wind_candidates/SUMMARY.json` 与 `artifacts/production_admission/WIND_PRODUCTION_ADMISSION_STATUS_20260901.md`）。
- **建议**：补齐 Wind 许可与稳定性证据（授权范围、数据变更公告、重发机制），达到准入标准后再切换生产源。

### P3-3 FRED 宏观数据 PARTIAL

- **现状**：FRED Public CSV 证据已采集；ALFRED（vintage 修订库）因重定向后 vintage 数据超限停止，宏观 series 仍 PARTIAL（对应 `CALENDAR_BLOCKED` / 4 markets UNKNOWN 状态）。
- **建议**：确认 ALFRED 请求参数（校订范围/时间窗）后继续采集，或明确接受 Public CSV 作为宏观数据源并更新准入记录。

---

## 附：验证命令（供修复后回归）

```powershell
# 完整测试套件
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .pytest-tmp-fix-verify2

# 间歇性失败用例压力复现
.venv\Scripts\python.exe -m pytest tests/unit/test_evidence_shadow.py::test_local_experiment_persistence_is_idempotent_and_explainable -q --count=50

# 重生成 QA 基线
.venv\Scripts\python.exe -m cross_asset.operations.qa_baseline
```

## 修复优先级建议

1. 先处理 P0-2（间歇性失败）与 P0-1（git/provenance），二者都影响 CI 可信度。
2. 再清理 P1 死代码（消除重名类，防误用）。
3. P2 随上述修复一并落地（重新生成基线、收敛 pytest 临时目录、统一环境）。
4. P3 为数据侧独立工作线，可与代码修复并行推进。