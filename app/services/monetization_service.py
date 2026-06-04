from __future__ import annotations

from app.schemas.app_schema import AppDetail


class MonetizationService:
    def score(
        self,
        detail: AppDetail,
        grossing_rank: int | None = None,
        review_growth_rate: float | None = None,
    ) -> dict:
        score = 0
        signals: list[str] = []

        if detail.has_iap:
            score += 20
            signals.append("应用包含内购")
        if detail.free is False:
            score += 10
            signals.append("应用为付费下载")

        installs = detail.min_installs or 0
        if installs >= 100_000_000:
            score += 25
            signals.append("安装量达到 1 亿+")
        elif installs >= 10_000_000:
            score += 20
            signals.append("安装量达到 1000 万+")
        elif installs >= 1_000_000:
            score += 15
            signals.append("安装量达到 100 万+")
        elif installs >= 100_000:
            score += 8
            signals.append("安装量达到 10 万+")

        rating = detail.rating or 0
        if rating >= 4.5:
            score += 10
            signals.append("评分高于 4.5")
        elif rating >= 4.0:
            score += 6
            signals.append("评分高于 4.0")
        elif rating >= 3.5:
            score += 3
            signals.append("评分高于 3.5")

        ratings_count = detail.ratings_count or 0
        if ratings_count >= 1_000_000:
            score += 15
            signals.append("评分数达到 100 万+")
        elif ratings_count >= 100_000:
            score += 10
            signals.append("评分数达到 10 万+")
        elif ratings_count >= 10_000:
            score += 5
            signals.append("评分数达到 1 万+")

        if grossing_rank is not None:
            if grossing_rank <= 10:
                score += 25
                signals.append("畅销榜前 10")
            elif grossing_rank <= 50:
                score += 18
                signals.append("畅销榜前 50")
            elif grossing_rank <= 100:
                score += 12
                signals.append("畅销榜前 100")
            elif grossing_rank <= 200:
                score += 6
                signals.append("畅销榜前 200")

        if review_growth_rate is not None:
            if review_growth_rate >= 0.1:
                score += 10
                signals.append("评论增长率超过 10%")
            elif review_growth_rate >= 0.03:
                score += 5
                signals.append("评论增长率超过 3%")

        score = min(score, 100)
        if score >= 80:
            level = "very_high"
        elif score >= 60:
            level = "high"
        elif score >= 30:
            level = "medium"
        else:
            level = "low"

        return {
            "score": score,
            "level": level,
            "confidence": "low",
            "signals": signals,
            "note": "基于公开数据推断，不代表真实收入。",
        }
