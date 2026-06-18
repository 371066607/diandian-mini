"""身份四元组 (platform, app_id, country, lang) 的规范化工具。

几乎每个实体都按这个四元组定位。``normalize_identity`` 是入库 / 查询前唯一的
收口点：把四元组规范成统一形态，使同一个逻辑 App 不会因大小写或 locale 差异
裂成两行（参见 docs/multistore-monitoring.md §3）。

这是一个**纯函数**：不联网、不访问 DB。特别地，它**不**把 App Store 的
bundleId 解析成 iTunes trackId —— 那需要一次实时 ``app_detail`` 调用。调用方
必须先 fetch detail、再用 ``detail.app_id`` 传进来。
"""

from __future__ import annotations

GOOGLE_PLAY = "google_play"
APP_STORE = "app_store"
PLATFORMS = frozenset({GOOGLE_PLAY, APP_STORE})

# App Store 的 app_detail / search / reviews 当前都不真正按 lang 取数据。用一个
# 固定哨兵占住四元组里的 lang 位，避免伪 locale，也避免 NULL/空值破坏 SQLite
# 唯一约束（NULL 在 UNIQUE 中不去重）。切勿改成 None 或 ""。
APP_STORE_LANG_SENTINEL = "default"


def normalize_identity(
    *,
    platform: str,
    app_id: str,
    country: str = "us",
    lang: str = "en",
) -> tuple[str, str, str, str]:
    """规范化身份四元组，返回 ``(platform, app_id, country, lang)``。

    - ``platform`` / ``country`` 去空白并统一小写；``country`` 为空回退 ``"us"``。
    - ``app_id`` 仅去首尾空白（**不**解析 bundleId→trackId，见模块说明）。
    - App Store 强制 ``lang = APP_STORE_LANG_SENTINEL``（忽略传入值）；其余平台
      ``lang`` 去空白小写、为空回退 ``"en"``。
    - 未知 ``platform`` 抛 ``ValueError``（fail fast，避免静默写脏数据）。

    仅限关键字参数调用，避免与历史三元组 positional 调用混淆。
    """
    platform = (platform or "").strip().lower()
    if platform not in PLATFORMS:
        raise ValueError(f"未知 platform: {platform!r}（支持 {sorted(PLATFORMS)}）")

    app_id = (app_id or "").strip()
    if not app_id:
        raise ValueError("app_id 不能为空")

    country = (country or "").strip().lower() or "us"

    if platform == APP_STORE:
        lang = APP_STORE_LANG_SENTINEL
    else:
        lang = (lang or "").strip().lower() or "en"

    return platform, app_id, country, lang
