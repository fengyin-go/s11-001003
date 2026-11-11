"""候选定位服务：来源 URL -> 确定性候选集合，可解释、可分页、可对照基准。

设计要点
--------
1. 确定性检索：分发规则的「来源URL模式、目标引擎、优先级权重、分发比例」全部参与
   服务端计算。匹配采用精确/通配（fnmatch）口径，同权重冲突按
   （优先级权重降序、分发比例降序、规则 id 升序）稳定裁决，任何时候结果都可复现。
2. 排除口径：仅「已启用」规则参与；目标引擎无法解析、对应采集任务为「已停用/已完成」
   的候选一律排除，排除原因逐条记录，供页面展开解释。
3. 去重：同一采集目标被多条规则命中时，只保留排名最靠前的命中规则，其余计入
   候选的「同目标其他命中」说明，保证跨页无重复、无漏项。
4. 快照与版本：每次检索生成不可变快照（数据深拷贝 + 当时配置版本号），翻页/断点续读
   始终绑定该版本；检索期间配置变更只标记 stale，本次翻页不换集合，重新检索才用新版本。
5. 索引：按版本缓存「模式前缀索引 + 采集任务索引」，避免每个候选都全表扫描；
   同时保留全量扫描实现作为基准，基准接口可证明两者结果完全一致。
"""
from __future__ import annotations

import fnmatch
import threading
import time
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from app.store import store

ROUTER_MODULE = "router"
COLLECTOR_MODULE = "collector"

ENABLED_STATUS = "已启用"
# 采集任务处于这两种状态时不允许作为分发候选。
EXCLUDED_COLLECTOR_STATUS = {"已停用", "已完成"}

SEARCH_TTL_SECONDS = 30 * 60
SEARCH_LIMIT = 100
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 200


def parse_number(value: Any) -> float:
    """把权重/比例字段解析成可比较的数字。

    兼容整数、小数、百分数字符串以及基础种子里的占位文本（无法解析按 0 处理，
    占位数据因此排在所有真实权重之后，且彼此按规则 id 稳定区分）。
    """
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return 0.0
    if text.endswith("%"):
        text = text[:-1].strip()
    try:
        return float(text)
    except ValueError:
        return 0.0


def split_patterns(pattern: Any) -> list[str]:
    """一条规则可在「来源URL模式」里用逗号/分号配置多个备选模式。"""
    if pattern is None:
        return []
    parts = str(pattern).replace(";", ",").split(",")
    return [part.strip() for part in parts if part.strip()]


def match_pattern(source_url: str, pattern: str) -> bool:
    """单个模式匹配：无通配符走精确匹配，否则走 fnmatch（*、?、[] 语义）。"""
    if any(char in pattern for char in "*?["):
        return fnmatch.fnmatchcase(source_url, pattern)
    return source_url == pattern


def _pattern_index_key(pattern: str) -> str:
    """取第一个通配符之前的字面量前缀作为索引桶键。

    命中某个 URL 的通配模式，其字面量前缀一定是该 URL 的前缀；精确模式则整体入桶。
    全通配（* 开头）模式放进空串桶，每次检索兜底参与。
    """
    for index, char in enumerate(pattern):
        if char in "*?[":
            return pattern[:index]
    return pattern


class RuleIndex:
    """按配置版本构建一次、可重复使用的检索索引。"""

    def __init__(self, router_rows: list[dict[str, Any]], collector_rows: list[dict[str, Any]]) -> None:
        self.prefix_buckets: dict[str, list[dict[str, Any]]] = {}
        self.any_bucket: list[dict[str, Any]] = []
        for row in router_rows:
            patterns = split_patterns(row.get("来源URL模式"))
            if not patterns:
                continue
            keys = {_pattern_index_key(pattern) for pattern in patterns}
            if "" in keys:
                self.any_bucket.append(row)
            for key in keys:
                if key:
                    self.prefix_buckets.setdefault(key, []).append(row)
        # 采集任务按任务编号与内部 id 双路解析。
        self.collector_by_code: dict[str, dict[str, Any]] = {}
        self.collector_by_id: dict[int, dict[str, Any]] = {}
        for row in collector_rows:
            code = str(row.get("任务编号") or "").strip()
            if code:
                self.collector_by_code[code] = row
            self.collector_by_id[int(row.get("id", 0))] = row

    def candidate_rules(self, source_url: str) -> list[dict[str, Any]]:
        """用前缀索引缩小规则范围，再逐模式做确定性匹配。"""
        seen: dict[int, dict[str, Any]] = {}
        for key, rows in self.prefix_buckets.items():
            if source_url.startswith(key):
                for row in rows:
                    seen.setdefault(int(row["id"]), row)
        for row in self.any_bucket:
            seen.setdefault(int(row["id"]), row)
        return list(seen.values())

    def resolve_collector(self, engine: Any) -> dict[str, Any] | None:
        code = str(engine or "").strip()
        if code in self.collector_by_code:
            return self.collector_by_code[code]
        if code.isdigit() and int(code) in self.collector_by_id:
            return self.collector_by_id[int(code)]
        return None


@dataclass
class SearchSnapshot:
    """一次检索的不可变上下文：翻页和断点续读都绑定它。

    评估在创建会话时一次性完成，快照只留存候选/排除结果与配置版本，
    不再持有整表深拷贝；结果列表在构造时已与在线数据隔离，后续配置变更
    无法影响本次检索的候选集合。
    """

    search_id: str
    source_url: str
    created_at: float
    router_version: int
    collector_version: int
    candidates: list[dict[str, Any]]
    exclusions: list[dict[str, Any]]
    matched_rule_count: int
    last_read_page: int = 0
    accessed_at: float = 0.0
    pages_served: list[int] = field(default_factory=list)


class LocatorService:
    def __init__(self) -> None:
        self._searches: dict[str, SearchSnapshot] = {}
        self._lock = threading.RLock()
        self._index_cache: tuple[tuple[int, int], RuleIndex] | None = None

    # ------------------------------------------------------------------ 索引
    def _index(self, router_rows: list[dict[str, Any]], collector_rows: list[dict[str, Any]],
               router_version: int, collector_version: int) -> RuleIndex:
        """索引按 (router 版本, collector 版本) 缓存；配置一变就重建。"""
        key = (router_version, collector_version)
        with self._lock:
            if self._index_cache is None or self._index_cache[0] != key:
                self._index_cache = (key, RuleIndex(router_rows, collector_rows))
            return self._index_cache[1]

    # ------------------------------------------------------------- 核心检索
    def _evaluate(self, source_url: str, router_rows: list[dict[str, Any]],
                  index: "RuleIndex") -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
        """纯函数式评估：给定规则数据与配套索引，返回候选、排除项、命中规则数。

        该方法同时服务于索引路径与全量扫描基准，两条路径共用同一套裁决口径，
        因此基准一致时可以证明索引检索与全量扫描等价。调用方负责传入与数据集
        配套的索引，避免在线版本缓存与基准合成数据串用。
        """
        matched: list[dict[str, Any]] = []
        exclusions: list[dict[str, Any]] = []

        for rule in index.candidate_rules(source_url):
            patterns = split_patterns(rule.get("来源URL模式"))
            hit_pattern = next((p for p in patterns if match_pattern(source_url, p)), None)
            if hit_pattern is None:
                continue
            if str(rule.get("status") or "") != ENABLED_STATUS:
                exclusions.append({
                    "规则编号": rule.get("规则编号"),
                    "规则id": int(rule.get("id", 0)),
                    "原因": f"规则状态为「{rule.get('status')}」，仅已启用规则参与候选检索",
                    "命中模式": hit_pattern,
                })
                continue
            matched.append(rule)

        # 稳定裁决：权重降序 -> 分发比例降序 -> 规则 id 升序。
        matched.sort(key=lambda row: (-parse_number(row.get("优先级权重")),
                                      -parse_number(row.get("分发比例")),
                                      int(row.get("id", 0))))

        candidates: list[dict[str, Any]] = []
        chosen_targets: set[int] = set()
        for rank, rule in enumerate(matched, start=1):
            engine = rule.get("目标引擎")
            collector = index.resolve_collector(engine)
            rule_id = int(rule.get("id", 0))
            if collector is None:
                exclusions.append({
                    "规则编号": rule.get("规则编号"),
                    "规则id": rule_id,
                    "原因": f"目标引擎「{engine}」无法解析到采集引擎中的任务",
                    "命中模式": _first_hit_pattern(source_url, rule),
                    "裁决排名": rank,
                })
                continue
            collector_id = int(collector.get("id", 0))
            collector_status = str(collector.get("status") or "")
            if collector_status in EXCLUDED_COLLECTOR_STATUS:
                exclusions.append({
                    "规则编号": rule.get("规则编号"),
                    "规则id": rule_id,
                    "原因": f"目标采集任务「{collector.get('任务编号')}」状态为「{collector_status}」，按排除口径不下发",
                    "命中模式": _first_hit_pattern(source_url, rule),
                    "裁决排名": rank,
                })
                continue
            if collector_id in chosen_targets:
                # 同目标去重：记录到已保留候选的附加命中里，不重复出现在候选集合。
                previous = next(item for item in candidates if item["采集任务id"] == collector_id)
                previous["同目标其他命中"].append({
                    "规则编号": rule.get("规则编号"),
                    "规则id": rule_id,
                    "裁决排名": rank,
                    "优先级权重": rule.get("优先级权重"),
                    "分发比例": rule.get("分发比例"),
                })
                continue
            chosen_targets.add(collector_id)
            candidates.append(self._build_candidate(rule, collector, source_url, rank, len(candidates) + 1))

        # 排除项也给出稳定顺序，便于页面解释与基准比对。
        exclusions.sort(key=lambda item: (item.get("裁决排名", 10**9), item["规则id"]))
        return candidates, exclusions, len(matched)

    def _build_candidate(self, rule: dict[str, Any], collector: dict[str, Any],
                         source_url: str, rank: int, candidate_no: int) -> dict[str, Any]:
        weight = parse_number(rule.get("优先级权重"))
        ratio = parse_number(rule.get("分发比例"))
        return {
            "候选序号": candidate_no,
            "裁决排名": rank,
            "规则id": int(rule.get("id", 0)),
            "规则编号": rule.get("规则编号"),
            "来源URL模式": rule.get("来源URL模式"),
            "命中模式": _first_hit_pattern(source_url, rule),
            "目标引擎": rule.get("目标引擎"),
            "优先级权重": rule.get("优先级权重"),
            "优先级权重数值": weight,
            "分发比例": rule.get("分发比例"),
            "分发比例数值": ratio,
            "采集任务id": int(collector.get("id", 0)),
            "采集任务编号": collector.get("任务编号"),
            "采集任务状态": collector.get("status"),
            "采集任务目标网址": collector.get("目标网址"),
            "采集任务详情": f"/api/collector/{collector.get('id')}",
            "采集引擎页面": f"/collector?taskId={collector.get('id')}",
            "选中原因": (
                f"规则「{rule.get('规则编号')}」命中模式「{_first_hit_pattern(source_url, rule)}」；"
                f"优先级权重 {rule.get('优先级权重')}、分发比例 {rule.get('分发比例')}，"
                f"按权重降序、比例降序、规则id升序裁决为第 {rank} 位；"
                f"目标任务「{collector.get('任务编号')}」状态「{collector.get('status')}」，不在停用/完成排除范围。"
            ),
            "同目标其他命中": [],
        }

    # ------------------------------------------------------------- 检索会话
    def open_search(self, source_url: str, page: int, size: int) -> dict[str, Any]:
        source_url = (source_url or "").strip()
        if not source_url:
            raise ValueError("来源 URL 不能为空")
        page = max(page, 1)
        size = min(max(size, 1), MAX_PAGE_SIZE)

        router_version = store.version(ROUTER_MODULE)
        collector_version = store.version(COLLECTOR_MODULE)
        # 深拷贝快照数据：之后任何人改配置都不影响本次检索。
        router_rows = store.snapshot(ROUTER_MODULE)
        collector_rows = store.snapshot(COLLECTOR_MODULE)
        # 在线路径索引按配置版本缓存；快照数据不变，同版本检索可安全复用。
        index = self._index(router_rows, collector_rows, router_version, collector_version)
        candidates, exclusions, matched_count = self._evaluate(
            source_url, router_rows, index
        )

        search_id = f"lc_{uuid.uuid4().hex[:16]}"
        now = time.time()
        snapshot = SearchSnapshot(
            search_id=search_id,
            source_url=source_url,
            created_at=now,
            router_version=router_version,
            collector_version=collector_version,
            candidates=candidates,
            exclusions=exclusions,
            matched_rule_count=matched_count,
            last_read_page=0,
            accessed_at=now,
        )
        with self._lock:
            self._evict(now)
            self._searches[search_id] = snapshot
        return self._page_payload(snapshot, page, size, opened=True)

    def read_page(self, search_id: str, page: int, size: int) -> dict[str, Any]:
        page = max(page, 1)
        size = min(max(size, 1), MAX_PAGE_SIZE)
        with self._lock:
            self._evict(time.time())
            snapshot = self._searches.get(search_id)
            if snapshot is None:
                raise KeyError(search_id)
            # 断点续读仍绑定原检索版本；若中途翻过的页再次请求，直接返回同一批数据。
            snapshot.accessed_at = time.time()
            snapshot.last_read_page = max(snapshot.last_read_page, page)
            if page not in snapshot.pages_served:
                snapshot.pages_served.append(page)
            return self._page_payload(snapshot, page, size, opened=False)

    def get_search(self, search_id: str) -> dict[str, Any]:
        with self._lock:
            self._evict(time.time())
            snapshot = self._searches.get(search_id)
            if snapshot is None:
                raise KeyError(search_id)
            return {
                "searchId": snapshot.search_id,
                "sourceUrl": snapshot.source_url,
                "createdAt": snapshot.created_at,
                "routerVersion": snapshot.router_version,
                "collectorVersion": snapshot.collector_version,
                "matchedRuleCount": snapshot.matched_rule_count,
                "candidateTotal": len(snapshot.candidates),
                "exclusionTotal": len(snapshot.exclusions),
                "lastReadPage": snapshot.last_read_page,
                "pagesServed": sorted(snapshot.pages_served),
                "stale": self._stale(snapshot),
                "currentVersions": {
                    "router": store.version(ROUTER_MODULE),
                    "collector": store.version(COLLECTOR_MODULE),
                },
            }

    def _page_payload(self, snapshot: SearchSnapshot, page: int, size: int, *, opened: bool) -> dict[str, Any]:
        total = len(snapshot.candidates)
        start = (page - 1) * size
        page_items = snapshot.candidates[start:start + size]
        # 页内序号与候选全局序号保持一致，跨页连续、无重复无漏项。
        for offset, item in enumerate(page_items, start=start + 1):
            item["候选序号"] = offset
        current_router_version = store.version(ROUTER_MODULE)
        current_collector_version = store.version(COLLECTOR_MODULE)
        stale = self._stale(snapshot)
        return {
            "searchId": snapshot.search_id,
            "sourceUrl": snapshot.source_url,
            "opened": opened,
            "snapshot": {
                "createdAt": snapshot.created_at,
                "routerVersion": snapshot.router_version,
                "collectorVersion": snapshot.collector_version,
                "currentRouterVersion": current_router_version,
                "currentCollectorVersion": current_collector_version,
                "stale": stale,
                "staleReason": _stale_reason(snapshot, current_router_version, current_collector_version),
                "ttlSeconds": SEARCH_TTL_SECONDS,
            },
            "page": page,
            "size": size,
            "total": total,
            "matchedRuleCount": snapshot.matched_rule_count,
            "exclusionTotal": len(snapshot.exclusions),
            "items": page_items,
            "exclusions": snapshot.exclusions if page == 1 else [],
            "pagination": {
                "hasPrevious": page > 1,
                "hasNext": start + size < total,
                "firstCandidateNo": start + 1 if total else 0,
                "lastCandidateNo": min(start + size, total),
                "pagesServed": sorted(set(snapshot.pages_served + [page])),
            },
        }

    def _stale(self, snapshot: SearchSnapshot) -> bool:
        return (store.version(ROUTER_MODULE) != snapshot.router_version
                or store.version(COLLECTOR_MODULE) != snapshot.collector_version)

    def _evict(self, now: float) -> None:
        expired = [sid for sid, snap in self._searches.items()
                   if now - snap.accessed_at > SEARCH_TTL_SECONDS]
        for sid in expired:
            self._searches.pop(sid, None)
        while len(self._searches) > SEARCH_LIMIT:
            oldest = min(self._searches, key=lambda sid: self._searches[sid].accessed_at)
            self._searches.pop(oldest, None)

    # ------------------------------------------------------------- 基准对照
    def full_scan(self, source_url: str, router_rows: list[dict[str, Any]],
                  index: "RuleIndex") -> list[dict[str, Any]]:
        """全量扫描基准：不用前缀索引，逐条规则匹配，再走同一套裁决/排除/去重口径。"""
        matched: list[dict[str, Any]] = []
        for rule in router_rows:
            if str(rule.get("status") or "") != ENABLED_STATUS:
                continue
            if _first_hit_pattern(source_url, rule) is None:
                continue
            matched.append(rule)
        matched.sort(key=lambda row: (-parse_number(row.get("优先级权重")),
                                      -parse_number(row.get("分发比例")),
                                      int(row.get("id", 0))))
        candidates: list[dict[str, Any]] = []
        chosen: set[int] = set()
        candidate_no = 0
        for rank, rule in enumerate(matched, start=1):
            collector = index.resolve_collector(rule.get("目标引擎"))
            if collector is None:
                continue
            collector_id = int(collector.get("id", 0))
            if str(collector.get("status") or "") in EXCLUDED_COLLECTOR_STATUS:
                continue
            if collector_id in chosen:
                # 与索引路径保持同一去重口径：重复命中计入已保留候选的附加命中，
                # 否则两条路径的候选明细会出现差异，基准就无法证明等价。
                previous = next(item for item in candidates if item["采集任务id"] == collector_id)
                previous["同目标其他命中"].append({
                    "规则编号": rule.get("规则编号"),
                    "规则id": int(rule.get("id", 0)),
                    "裁决排名": rank,
                    "优先级权重": rule.get("优先级权重"),
                    "分发比例": rule.get("分发比例"),
                })
                continue
            chosen.add(collector_id)
            candidate_no += 1
            candidates.append(self._build_candidate(rule, collector, source_url, rank, candidate_no))
        return candidates

    def run_benchmark(self, candidate_target: int = 120) -> dict[str, Any]:
        """合成大量候选并对照：索引检索 vs 全量扫描，且模拟跨页读取校验无重复漏项。

        数据在独立的合成数据集里构造，不触碰仓库里的在线配置与既有检索快照。
        """
        candidate_target = min(max(candidate_target, 10), 2000)
        router_rows, collector_rows, source_url = _build_benchmark_dataset(candidate_target)
        # 基准使用独立索引，不触碰在线版本缓存，保证与合成数据集严格配套。
        bench_index = RuleIndex(router_rows, collector_rows)

        indexed, exclusions, matched_count = self._evaluate(
            source_url, router_rows, bench_index
        )
        scanned = self.full_scan(source_url, router_rows, bench_index)

        identity_keys = lambda items: [  # noqa: E731 - 对照只看稳定身份键与排序
            (item["规则id"], item["采集任务id"], item["裁决排名"]) for item in items
        ]
        same_order = identity_keys(indexed) == identity_keys(scanned)
        # 等值比对必须在分页处理之前：分页会就地改写候选序号，不能让展示层处理污染基准结论。
        same_payload = indexed == scanned
        page_source = deepcopy(indexed)

        # 模拟跨页连续读取：每页 7 条，汇总后应与完整候选集合逐序号一致且无重复。
        page_size = 7
        page_count = (len(page_source) + page_size - 1) // page_size
        collected: list[dict[str, Any]] = []
        seen_ids: list[int] = []
        page_windows = []
        for page in range(1, page_count + 1):
            start = (page - 1) * page_size
            window = page_source[start:start + page_size]
            # 与线上分页同一口径：页内候选序号按全局位置重排，验证跨页连续。
            for offset, item in enumerate(window, start=start + 1):
                item["候选序号"] = offset
            page_windows.append({
                "page": page,
                "firstCandidateNo": start + 1,
                "lastCandidateNo": start + len(window),
                "taskIds": [item["采集任务id"] for item in window],
            })
            for item in window:
                seen_ids.append(item["采集任务id"])
                collected.append(item)
        no_duplicate = len(seen_ids) == len(set(seen_ids))
        no_missing = sorted(seen_ids) == sorted(item["采集任务id"] for item in page_source)
        continuous = [item["候选序号"] for item in collected] == list(range(1, len(page_source) + 1))

        tie_groups: dict[tuple[float, float], list[int]] = {}
        for rule in router_rows:
            key = (parse_number(rule.get("优先级权重")), parse_number(rule.get("分发比例")))
            tie_groups.setdefault(key, []).append(int(rule["id"]))
        tie_pair_count = sum(1 for ids in tie_groups.values() if len(ids) > 1)
        # 直接验证候选顺序严格满足完整裁决键：权重降序、比例降序、规则id升序。
        sort_keys = [
            (-item["优先级权重数值"], -item["分发比例数值"], item["规则id"])
            for item in indexed
        ]
        tie_stable = sort_keys == sorted(sort_keys)

        return {
            "sourceUrl": source_url,
            "dataset": {
                "routerRuleCount": len(router_rows),
                "collectorTaskCount": len(collector_rows),
                "excludedCollectorCount": sum(
                    1 for row in collector_rows if str(row.get("status")) in EXCLUDED_COLLECTOR_STATUS
                ),
                "unresolvableRuleCount": sum(
                    1 for row in router_rows if str(row.get("目标引擎")) == "COLL-BENCH-MISSING"
                ),
            },
            "result": {
                "matchedRuleCount": matched_count,
                "candidateTotal": len(indexed),
                "exclusionTotal": len(exclusions),
            },
            "equivalence": {
                "indexVsFullScanSameOrder": same_order,
                "indexVsFullScanSamePayload": same_payload,
                "fullScanCandidateTotal": len(scanned),
            },
            "pagination": {
                "pageSize": page_size,
                "pageCount": page_count,
                "noDuplicateAcrossPages": no_duplicate,
                "noMissingAcrossPages": no_missing,
                "continuousCandidateNo": continuous,
                "pageWindows": page_windows[:10],
                "pageWindowNote": "仅回传前 10 个分页窗口明细，全量窗口数见 pageCount",
            },
            "tieBreak": {
                "sameWeightGroupCount": tie_pair_count,
                "stableOrder": tie_stable,
                "rule": "优先级权重降序 -> 分发比例降序 -> 规则id升序",
            },
            "passed": bool(same_order and same_payload and no_duplicate and no_missing and continuous and tie_stable),
        }


def _first_hit_pattern(source_url: str, rule: dict[str, Any]) -> str | None:
    for pattern in split_patterns(rule.get("来源URL模式")):
        if match_pattern(source_url, pattern):
            return pattern
    return None


def _stale_reason(snapshot: SearchSnapshot, router_version: int, collector_version: int) -> str | None:
    """版本过期时给出可读原因，说明是哪一侧配置发生了变化。"""
    changed: list[str] = []
    if router_version != snapshot.router_version:
        changed.append(f"链路分发规则版本 {snapshot.router_version} → {router_version}")
    if collector_version != snapshot.collector_version:
        changed.append(f"采集任务版本 {snapshot.collector_version} → {collector_version}")
    if not changed:
        return None
    return "检索期间配置已变更（{}）；本次翻页仍绑定原检索版本，重新发起检索才会使用新版本".format("，".join(changed))


def _build_benchmark_dataset(candidate_target: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    """构造确定性的合成数据集：候选数围绕目标值，包含同权重对、停用/完成/缺失目标。"""
    collector_rows: list[dict[str, Any]] = []
    # 约 80% 任务可用，其余均分到已停用/已完成，配合无法解析目标的规则制造排除项。
    usable_target = max(1, int(candidate_target * 0.8))
    excluded_target = max(2, candidate_target - usable_target)
    status_cycle = ["已停用", "已完成"]
    total_collectors = usable_target + excluded_target
    for index in range(1, total_collectors + 1):
        status = "运行中" if index <= usable_target else status_cycle[index % 2]
        collector_rows.append({
            "id": 1000 + index,
            "status": status,
            "任务编号": f"COLL-BENCH-{index:04d}",
            "目标网址": f"https://bench-engine.internal/jobs/COLL-BENCH-{index:04d}",
        })

    source_url = "https://bench.example.com/path/item?page=1"
    router_rows: list[dict[str, Any]] = []
    rule_id = 5000
    for index in range(1, total_collectors + 1):
        # 每 5 条造一组同权重同比例规则，验证 id 升序兜底裁决。
        weight = 100 - (index % 5) * 10
        ratio = f"{50 + (index % 3) * 10}%"
        router_rows.append({
            "id": rule_id,
            "status": ENABLED_STATUS,
            "规则编号": f"ROUT-BENCH-{index:04d}",
            "来源URL模式": "https://bench.example.com/*",
            "目标引擎": f"COLL-BENCH-{index:04d}",
            "优先级权重": str(weight),
            "分发比例": ratio,
        })
        rule_id += 1
    # 同目标重复命中规则：给前 10 个可用任务各加一条较弱规则，验证去重。
    for index in range(1, min(11, usable_target + 1)):
        router_rows.append({
            "id": rule_id,
            "status": ENABLED_STATUS,
            "规则编号": f"ROUT-BENCH-DUP-{index:04d}",
            "来源URL模式": "https://bench.example.com/path/*",
            "目标引擎": f"COLL-BENCH-{index:04d}",
            "优先级权重": "10",
            "分发比例": "5%",
        })
        rule_id += 1
    # 无法解析目标引擎的规则。
    router_rows.append({
        "id": rule_id,
        "status": ENABLED_STATUS,
        "规则编号": "ROUT-BENCH-MISSING",
        "来源URL模式": "https://bench.example.com/*",
        "目标引擎": "COLL-BENCH-MISSING",
        "优先级权重": "999",
        "分发比例": "100%",
    })
    rule_id += 1
    # 未启用规则，不应进入命中集合。
    router_rows.append({
        "id": rule_id,
        "status": "草稿",
        "规则编号": "ROUT-BENCH-DRAFT",
        "来源URL模式": "https://bench.example.com/*",
        "目标引擎": f"COLL-BENCH-{1:04d}",
        "优先级权重": "999",
        "分发比例": "100%",
    })
    return router_rows, collector_rows, source_url


locator_service = LocatorService()
