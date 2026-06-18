# App 监控多商店化改造计划

> **目标**：把「App 详情监控」这条链路——被追踪 App 的增删改查 + 每日快照（`app_snapshots`）+ 告警（`alerts`）+ 同步（`sync_app_now`）+ 监控页展示——从写死 `google_play` 升级为按四元组 `(platform, app_id, country, lang)` 真正多商店，接入已存在的 `AppStoreService`。
>
> **基线**：`v1.2.0`（改造前稳定版，随时可 `git checkout v1.2.0` 回退）。建议在独立分支（如 `v2-dev`）开发，避免半成品经 `publish-code-patch` 热更新推给现有用户。
>
> **来源**：本文档 = 初版计划 + GPT‑5.5（codex 只读评审）交叉评审 + 逐条源码核实。

---

## 0. 现状

`identity` 名义上是四元组 `(platform, app_id, country, lang)`，但 App 监控链路把 `platform` 钉死成 `google_play`：

- `repositories.add_app` 硬编码 `platform="google_play"`（`app/db/repositories.py:904`）
- `list_apps` 查全表、不带 platform（`app/db/repositories.py:954`）；`remove_app`/`update_sync_time`/`record_app_failure`/`record_app_success` 用三元组 where
- 快照仓储 `upsert_for_day`/`previous_distinct_day`/`get_history`/`latest_two_bulk` 用三元组 key
- 告警 bulk `latest_by_app`/`unread_count_bulk` 用纯 `app_id` 列表
- `sync_app_now` 永远调 `google_play_service.app_detail`（`app/services/tracking_service.py:495`）；`monitor_overview` 用三元组组 `app_keys`（`:247`）

## 1. 已确认的利好（降低工作量）

1. `AppStoreService` 与 `GooglePlayService` 接口已对齐（都有 `app_detail/search/reviews/chart/similar`）——同步分派只需按 platform 选 service。
2. pydantic schema 已带 `platform` 字段（默认 `google_play`）。
3. 除 `alerts` 外，相关表（`apps`/`app_snapshots`/`tracked_apps`/`reviews`/各快照表）都已有 `platform` 列。

## 2. 关键风险与硬伤（开工前必读，均已核实源码）

| # | 硬伤 | 证据 | 对策 |
|---|---|---|---|
| 1 | **App Store `app_id` 身份分裂**：`app_detail` 输入可为 bundleId 或 trackId，但**返回的 `AppDetail.app_id` 优先取 iTunes `trackId`** | `app/services/app_store_service.py:74-79`、`:196` | 入库前先 resolve detail，统一用 `detail.app_id`（trackId 字符串）当 key，**禁止写用户输入的 bundleId**。详见 §3 |
| 2 | **存在第二套 QML UI，且显式拦截非 GP**：`_guard_google_play_only` 在 App 监控/快照/榜单/权限处拦截 | `app/ui/qml_bridge.py:348`、`:489/:514/:649/:688/:706/:724` | 改造范围含 QML 与 widgets 两套；按 platform 放开 guard |
| 3 | **`alerts` 表根本不是四元组**：只有 `app_id`，无 `platform`/`country`/`lang` | `app/db/models.py:306` | `alerts` 加 `platform + country + lang` 三列；bulk/过滤/cleanup 全部带 identity |
| 4 | **`sync_app_now` 会触发评论监控，而 `ReviewService` 是 GP-only**：首日同步后调 `_monitor_reviews` | `app/services/tracking_service.py:552`、`review_service.py` | `ReviewService` 平台分派；App Store 初期可先跳过评论监控 |
| 5 | **榜单线其实也没 platform 化**（不能当参照系）：`add_chart_app` 不带 platform | `app/db/repositories.py:1262` | 视范围决定是否一并处理；至少不要误以为「已隔离」 |

**额外遗漏**（一并纳入）：`set_app_enabled`/`set_app_frequency`/`set_app_tag`/`toggle_app` 仍三元组；跨页跳转 `open_app_detail`/`open_history`/`open_reviews` 丢 platform（`app/ui/main_window.py:237`）；`MonitorCard` 回调只有 app_id（`app/ui/widgets/monitor_card.py:25`）；History/Export 三元组（`history_page.py`、`export_service.py`）；retention `cleanup` 跨商店；migration 目前只 backfill 了 keyword 两表（`app/db/migrations.py:77`）；`CREATE INDEX IF NOT EXISTS` 不会更新旧索引定义（`app/db/migrations.py:17`）。

## 3. Identity 规范化（地基，最先做）

新增中心化 helper：`normalize_identity(platform, app_id, country, lang) -> (platform, app_id, country, lang)`，所有入库/查询前统一走它：

- **country**：统一 `lower()` 的 ISO‑2。
- **lang**：Google Play 保留规范化后的 `lang`；**App Store 当前实现忽略 lang → 统一成哨兵值 `"default"`**（UI 显示「商店默认语言」）。
  - ⚠️ **禁止 NULL/空**：SQLite 的 `UNIQUE` 对 NULL 放过重复，且多处调用点 `or "en"` 会把空值又变回 `en`。
- **app_id**：App Store **入库前先 resolve `app_detail`、取 `detail.app_id`（trackId 字符串）**；详情页「加入监控/保存快照」用 `current_detail.app_id`，不是输入框原值。
- **不回写历史**：helper 只在 `platform == "app_store"` 时改 lang/app_id 规则，对既有 Google Play 数据零副作用。

## 4. 分阶段实施

> 通用向后兼容约定：所有新增 `platform` 参数一律 **kw-only、默认 `"google_play"`**，避免旧 positional 调用与旧测试错位；新查询对历史 NULL 行用 `COALESCE(platform, 'google_play')` 兜底。

### 阶段 0 — Identity helper + 常量 + 回归测试
最终签名（**纯函数：不联网、不 resolve bundleId**）：
```python
def normalize_identity(*, platform: str, app_id: str, country: str = "us", lang: str = "en") -> tuple[str, str, str, str]:
    # app_id.strip()；platform/country 统一 lower；platform == "app_store" 时强制 lang = "default"；未知 platform 抛 ValueError
```
- 放 `app/utils/identity.py`，常量 `GOOGLE_PLAY` / `APP_STORE` / `PLATFORMS` / `APP_STORE_LANG_SENTINEL = "default"`。
- ⚠️ **bundleId→trackId 解析不放进 helper**（需联网调 `app_detail`，会破坏纯函数性）。App Store 入库前先 fetch detail、用 `detail.app_id`（trackId）再调 helper。
- 纯函数单测：GP/App Store 各 locale、app_id trim、App Store lang 强制 `default`、未知 platform 抛错。

### 阶段 A — 数据层（models + migrations）
- `AlertModel` 加 `platform`/`country`/`lang` 列（`app/db/models.py:306`）。
- `migrations.py`：给 `tracked_apps`/`app_snapshots`/`reviews`/`alerts`/`tracked_chart_apps`/`chart_rank_snapshots` 的 NULL/空 `platform` backfill 为 `google_play`；alerts 旧行 `country/lang` backfill 为 `us/en`（或从 `payload_json` 尽力提取）。
- **新增带 platform 的索引，且换新名**（旧 `ix_*` 不会被 `IF NOT EXISTS` 更新）：`ix_app_snapshots_platform_lookup(platform, app_id, country, lang, captured_at)`、`ix_alerts_platform_app_created(platform, app_id, created_at)` 等。

### 阶段 B — 仓储层（四元组化）
- `tracked_apps`：`add_app`（去硬编码）、`list_apps`、`remove_app`、`update_sync_time`、`record_app_failure`、`record_app_success`、`set_app_enabled`、`set_app_frequency`、`set_app_tag`、`toggle_app` 全部带 platform。
- 快照：`upsert_for_day`/`previous_distinct_day`/`get_history`/`latest_two_bulk`/**`cleanup`(retention partition 含 platform)** 四元组化。
- 告警：`latest_by_app`/`unread_count_bulk` 接 **full identity keys**（不是只接 app_ids）；`create`/写入落 `platform/country/lang`。

### 阶段 C — 服务层（分派 + 装配 + 评论耦合）
- `TrackingService` 注入 `app_store_service` + `_service_for(platform)` 分派；**同步改 `app/composition.py`**（目前创建了 `AppStoreService` 但没传进 Tracking，见 `:41/:56`）。
- `add_app`/`remove_app`/`list_apps`/`sync_app_now`/`sync_all_apps`/`get_history`/`history_with_diffs`/`monitor_overview` 加 platform；`monitor_overview` 的 `app_keys` 四元组、bulk key 同步。
- `AlertService.create_snapshot_alerts`/`record_fetch_failure`/`record_fetch_recovered` 写入 alert 的 `platform/country/lang`。
- 评论耦合：`_monitor_reviews` 按 platform 分派 `ReviewService`，或 App Store 阶段先短路跳过。

### 阶段 D — UI（widgets + QML 两套）
- 监控树 `app/ui/pages/tracking_page.py:280`：`list_apps()` 结果按商店分组或加商店徽标。
- 拆 `qml_bridge._guard_google_play_only` 的相关拦截，按 platform 放开 App 监控/快照。
- 跨页跳转 `open_app_detail`/`open_history`/`open_reviews` 带 platform（`app/ui/main_window.py:237`）；`MonitorCard` 回调带 platform；`history_page`/`export_service`/`dashboard_page` 四元组化。
- 「添加监控」让用户选商店（或继承搜索页当前 platform）。

## 5. 测试 / PoC

**纵切 PoC（无网络、可断言的服务层测试）**：
1. fake `AppStoreService.app_detail()` 返回 `AppDetail(platform="app_store", app_id="310633997")`。
2. 同 `app_id/country/lang` 下同时建 `google_play` 与 `app_store` 两条监控，断言同步、快照、告警、`monitor_overview`、history/export **完全隔离**。
3. bundleId 输入测试：传 bundleId，同步后 tracked row 与 snapshot 都落 canonical trackId。
4. 失败测试：App Store fetch 失败只增加 App Store 那条 `tracked_app` 的 failure，并写带平台 identity 的 alert。
5. 跑 `python main.py --smoke-test` 验 migration/装配；最后才做 UI 路径（App Store 搜索结果加入监控 → 同步 → 详情页历史可见）。

## 6. 决策（已定案 — 经 GPT‑5.5 两轮评审 + 源码核实）

- ✅ **App Store `lang` = `"default"`**（禁 NULL/空）。⚠️ 坑：多处 `lang or "en"` 会把 `"default"` 污染回 `"en"`，需全局排查。
- ✅ **App Store 评论监控首期短路跳过**，二期再做。⚠️ 必须在**服务层** `sync_app_now`/`_monitor_reviews` 按 platform 短路，**不能只禁 UI 入口**——`ReviewService` 仅注入 GP，`ReviewRepository` 的 `existing_review_ids`/`list_by_app`/`cleanup` 仍按 app_id 维度。
- ✅ **榜单线 `tracked_chart_apps` 本次不动**，只做 App 详情监控。`add_chart_app` 仍硬编码 `platform="google_play"`（`app/db/repositories.py:1274`）；⚠️ 不要顺手在迁移/cleanup 里改一半，形成「模型像多商店、服务仍 GP-only」的半升级。

## 7. 落地顺序

阶段 0 → **0.5（身份契约测试）** → A → B → C → **PoC 验证** → D。

> **第 0.5 步（GPT‑5.5 强调，优先于铺迁移）**：helper 完成后立刻加一个无网络的服务层契约测试——用 fake `AppStoreService.app_detail()` 验证「输入 bundleId，最终 `tracked_apps` row 与 `app_snapshots` 都落 canonical trackId + `lang="default"`」。这比马上铺迁移更能锁住最危险的 #1 身份分裂。（该测试依赖阶段 B/C 的最小落地，归入 PoC 任务 #5 的首要断言。）

先把 §2 的 #1（app_id 规范化）与 #3/#4（alerts 四元组 + 评论耦合）消化掉，再横向铺开，否则后续返工。
