"""候选定位演示数据。

基础种子（app/seed.py）里的字段值是占位文本（如「链路分发样例1」），无法参与
确定性的 URL 匹配与权重裁决。这里补充一批字段取值真实、可解释的分发规则和采集任务，
id 从 101 开始，与基础种子同模块合并，不改动既有示例字段，也不影响其他模块页面。

覆盖场景：
- 多条规则命中同一来源 URL（同权重/不同权重），演示稳定裁决；
- 同一采集目标被多条规则命中，演示候选去重保留胜出规则；
- 已停用、已完成的采集目标以及无法解析目标引擎的规则，演示排除口径；
- 草稿/待校验/已停用规则不参与候选检索；
- 多备选模式（逗号分隔）与通配符模式。
"""
from __future__ import annotations

from typing import Any

# 采集任务（collector）：候选定位最终要落到这些真实目标上。
COLLECTOR_ROWS: list[dict[str, Any]] = [
    {
        "id": 101,
        "status": "运行中",
        "pending": False,
        "abnormal": False,
        "任务编号": "COLL-NEWS-MAIN",
        "目标网址": "https://news-engine.internal/jobs/COLL-NEWS-MAIN",
        "HTTP方法": "GET",
        "请求头部": "Accept: text/html",
        "并发线程": "8",
        "超时秒数": "15",
        "代理地址": "proxy-dc-01:8080",
        "字符编码": "utf-8",
    },
    {
        "id": 102,
        "status": "待启动",
        "pending": True,
        "abnormal": False,
        "任务编号": "COLL-NEWS-BACKUP",
        "目标网址": "https://news-engine.internal/jobs/COLL-NEWS-BACKUP",
        "HTTP方法": "GET",
        "请求头部": "Accept: text/html",
        "并发线程": "4",
        "超时秒数": "20",
        "代理地址": "proxy-dc-02:8080",
        "字符编码": "utf-8",
    },
    {
        "id": 103,
        "status": "运行中",
        "pending": False,
        "abnormal": False,
        "任务编号": "COLL-MARKET-MAIN",
        "目标网址": "https://market-engine.internal/jobs/COLL-MARKET-MAIN",
        "HTTP方法": "GET",
        "请求头部": "Accept: application/json",
        "并发线程": "12",
        "超时秒数": "10",
        "代理地址": "proxy-dc-03:8080",
        "字符编码": "utf-8",
    },
    {
        "id": 104,
        "status": "草稿",
        "pending": True,
        "abnormal": False,
        "任务编号": "COLL-MARKET-PREP",
        "目标网址": "https://market-engine.internal/jobs/COLL-MARKET-PREP",
        "HTTP方法": "GET",
        "请求头部": "Accept: application/json",
        "并发线程": "2",
        "超时秒数": "30",
        "代理地址": "proxy-dc-03:8080",
        "字符编码": "utf-8",
    },
    {
        "id": 105,
        "status": "已停用",
        "pending": True,
        "abnormal": True,
        "任务编号": "COLL-LEGACY-SHUT",
        "目标网址": "https://legacy-engine.internal/jobs/COLL-LEGACY-SHUT",
        "HTTP方法": "GET",
        "请求头部": "Accept: text/html",
        "并发线程": "1",
        "超时秒数": "60",
        "代理地址": "proxy-legacy:8080",
        "字符编码": "gbk",
    },
    {
        "id": 106,
        "status": "已完成",
        "pending": True,
        "abnormal": False,
        "任务编号": "COLL-FIN-DONE",
        "目标网址": "https://finance-engine.internal/jobs/COLL-FIN-DONE",
        "HTTP方法": "GET",
        "请求头部": "Accept: application/json",
        "并发线程": "4",
        "超时秒数": "15",
        "代理地址": "proxy-dc-04:8080",
        "字符编码": "utf-8",
    },
    {
        "id": 107,
        "status": "运行中",
        "pending": False,
        "abnormal": False,
        "任务编号": "COLL-TOP-RANK",
        "目标网址": "https://rank-engine.internal/jobs/COLL-TOP-RANK",
        "HTTP方法": "GET",
        "请求头部": "Accept: application/json",
        "并发线程": "6",
        "超时秒数": "12",
        "代理地址": "proxy-dc-05:8080",
        "字符编码": "utf-8",
    },
    {
        "id": 108,
        "status": "待启动",
        "pending": True,
        "abnormal": False,
        "任务编号": "COLL-PORTAL-PAGE",
        "目标网址": "https://portal-engine.internal/jobs/COLL-PORTAL-PAGE",
        "HTTP方法": "GET",
        "请求头部": "Accept: text/html",
        "并发线程": "3",
        "超时秒数": "20",
        "代理地址": "proxy-dc-06:8080",
        "字符编码": "utf-8",
    },
    {
        "id": 109,
        "status": "运行中",
        "pending": False,
        "abnormal": False,
        "任务编号": "COLL-VIDEO-FEED",
        "目标网址": "https://video-engine.internal/jobs/COLL-VIDEO-FEED",
        "HTTP方法": "GET",
        "请求头部": "Accept: application/json",
        "并发线程": "10",
        "超时秒数": "8",
        "代理地址": "proxy-dc-07:8080",
        "字符编码": "utf-8",
    },
    {
        "id": 110,
        "status": "待启动",
        "pending": True,
        "abnormal": False,
        "任务编号": "COLL-NEWS-SPLIT",
        "目标网址": "https://news-engine.internal/jobs/COLL-NEWS-SPLIT",
        "HTTP方法": "GET",
        "请求头部": "Accept: text/html",
        "并发线程": "5",
        "超时秒数": "18",
        "代理地址": "proxy-dc-02:8080",
        "字符编码": "utf-8",
    },
]


def _router_row(
    row_id: int,
    code: str,
    status: str,
    pattern: str,
    engine: str,
    weight: str,
    ratio: str,
    *,
    pending: bool = False,
    abnormal: bool = False,
    breaker: str = "连续失败 5 次",
    fallback: str = "转备用引擎",
    health_interval: str = "30s",
) -> dict[str, Any]:
    return {
        "id": row_id,
        "status": status,
        "pending": pending,
        "abnormal": abnormal,
        "规则编号": code,
        "来源URL模式": pattern,
        "目标引擎": engine,
        "优先级权重": weight,
        "分发比例": ratio,
        "熔断阈值": breaker,
        "降级策略": fallback,
        "健康检查间隔": health_interval,
    }


# 链路分发规则（router）。
ROUTER_ROWS: list[dict[str, Any]] = [
    # 新闻域：ROUT-101/102 同权重且同分发比例，演示同权重冲突按规则 id 稳定裁决（101 胜）。
    _router_row(101, "ROUT-101", "已启用", "https://news.example.com/*", "COLL-NEWS-MAIN", "80", "60%"),
    _router_row(102, "ROUT-102", "已启用", "https://news.example.com/*", "COLL-NEWS-BACKUP", "80", "60%"),
    _router_row(103, "ROUT-103", "已启用", "https://news.example.com/*", "COLL-NEWS-SPLIT", "60", "10%"),
    # 更具体的新闻详情页规则，权重最高。
    _router_row(104, "ROUT-104", "已启用", "https://news.example.com/detail/*", "COLL-NEWS-MAIN", "100", "70%"),
    # 行情域：同目标被两条规则命中，演示候选去重（保留排名更靠前的 ROUT-105）。
    _router_row(105, "ROUT-105", "已启用", "https://market.example.com/*", "COLL-MARKET-MAIN", "90", "80%"),
    _router_row(106, "ROUT-106", "已启用", "https://market.example.com/quotes/*", "COLL-MARKET-MAIN", "70", "20%"),
    # 目标采集任务是草稿（可参与，未停用/未完成）。
    _router_row(107, "ROUT-107", "已启用", "https://market.example.com/prepare/*", "COLL-MARKET-PREP", "50", "100%"),
    # 目标采集任务已停用 -> 候选排除。
    _router_row(108, "ROUT-108", "已启用", "https://legacy.example.com/*", "COLL-LEGACY-SHUT", "40", "100%"),
    # 目标采集任务已完成 -> 候选排除。
    _router_row(109, "ROUT-109", "已启用", "https://finance.example.com/*", "COLL-FIN-DONE", "55", "100%"),
    # 无法解析到采集任务的目标引擎 -> 候选排除并给出原因。
    _router_row(110, "ROUT-110", "已启用", "https://unknown.example.com/*", "COLL-ENGINE-MISSING", "90", "100%"),
    # 非已启用规则不参与检索。
    _router_row(111, "ROUT-111", "草稿", "https://news.example.com/draft/*", "COLL-NEWS-MAIN", "200", "100%", pending=True),
    _router_row(112, "ROUT-112", "已停用", "https://news.example.com/off/*", "COLL-NEWS-BACKUP", "200", "100%", pending=True, abnormal=True),
    # 多备选模式 + 通配符。
    _router_row(113, "ROUT-113", "已启用", "https://www.example.com/top/*,https://m.example.com/top/*", "COLL-TOP-RANK", "75", "50%"),
    # 兜底规则：模式最宽、权重最低，任何 www/m 路径都命中。
    _router_row(114, "ROUT-114", "已启用", "*", "COLL-PORTAL-PAGE", "10", "5%"),
    # 视频域规则，分发比例使用小数形式，兼容不同填写口径。
    _router_row(115, "ROUT-115", "已启用", "https://video.example.com/feed/*", "COLL-VIDEO-FEED", "85", "0.9"),
]


LOCATOR_ROWS: dict[str, list[dict[str, Any]]] = {
    "collector": COLLECTOR_ROWS,
    "router": ROUTER_ROWS,
}
