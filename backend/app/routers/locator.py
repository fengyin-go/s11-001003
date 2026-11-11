"""候选定位接口：来源 URL 确定性检索、快照分页、断点续读与全量扫描基准对照。

会话语义
--------
- POST   /api/router/locator/searches        发起检索，创建版本化快照，返回首页候选
- GET    /api/router/locator/searches/{id}   读取检索会话状态（含版本是否过期）
- GET    /api/router/locator/searches/{id}/pages  绑定原快照翻页/断点续读
- POST   /api/router/locator/benchmark       大量候选下索引检索与全量扫描的对照基准
- GET    /api/router/locator/semantics       检索口径说明（匹配、裁决、排除、快照）

会话过期（TTL 失效或被淘汰）统一返回 410，提示值班人员重新发起检索，
而不是悄悄换成新配置下的候选集合。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.locator import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, locator_service

router = APIRouter(prefix="/api/router/locator", tags=["链路分发-候选定位"])


class SearchRequest(BaseModel):
    sourceUrl: str = Field(..., description="值班人员输入的来源 URL")
    page: int = Field(default=1, ge=1)
    size: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)


class PageRequest(BaseModel):
    page: int = Field(default=1, ge=1)
    size: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)


@router.post("/searches")
def open_search(payload: SearchRequest) -> dict:
    """发起一次候选定位检索：服务端按当前配置版本生成不可变快照。"""
    try:
        return locator_service.open_search(payload.sourceUrl, payload.page, payload.size)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/searches/{search_id}")
def get_search(search_id: str) -> dict:
    """读取检索会话状态；版本过期时显式标注 stale，要求重开检索。"""
    try:
        return locator_service.get_search(search_id)
    except KeyError:
        raise HTTPException(
            status_code=410,
            detail="检索会话已过期或不存在，请重新输入来源 URL 发起检索",
        )


@router.get("/searches/{search_id}/pages")
def read_page(
    search_id: str,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> dict:
    """在同一检索版本上翻页；配置中途变更只标记 stale，本次翻页不换候选集合。"""
    try:
        return locator_service.read_page(search_id, page, size)
    except KeyError:
        raise HTTPException(
            status_code=410,
            detail="检索会话已过期或不存在，请重新输入来源 URL 发起检索",
        )


@router.post("/benchmark")
def run_benchmark(candidateTarget: int = Query(default=120, ge=10, le=2000)) -> dict:
    """合成大量候选，证明索引检索与全量扫描结果相同且跨页无重复漏项。"""
    return locator_service.run_benchmark(candidateTarget)


@router.get("/semantics")
def semantics() -> dict:
    """检索口径说明，供页面「展开解释」与后续维护对照。"""
    return {
        "matching": {
            "rule": "来源URL模式支持精确匹配与 fnmatch 通配（*、?、[]），多备选模式用逗号或分号分隔",
            "scope": "仅状态为「已启用」的分发规则参与检索，其余状态计入排除说明",
        },
        "tieBreak": {
            "rule": "优先级权重降序 -> 分发比例降序 -> 规则id升序",
            "note": "同权重同比例冲突时由规则 id 兜底，裁决结果稳定可复现",
            "fields": ["来源URL模式", "目标引擎", "优先级权重", "分发比例"],
        },
        "exclusion": {
            "collectorStatus": ["已停用", "已完成"],
            "unresolvableTarget": "目标引擎无法解析到采集任务时排除并记录原因",
            "dedup": "同一采集任务被多条规则命中时只保留裁决排名最靠前的一条",
        },
        "snapshot": {
            "rule": "检索创建时深拷贝规则与采集任务并记录配置版本，翻页/断点续读始终绑定该版本",
            "stale": "配置在检索期间变更时标记 stale，本次翻页仍用旧集合，重新检索才使用新版本",
            "expired": "会话超过 TTL 或被淘汰后返回 410，需重新发起检索，不悄悄切换集合",
        },
        "pagination": {
            "rule": "候选按裁决顺序全局连续编号，跨页无重复、无漏项",
            "maxPageSize": MAX_PAGE_SIZE,
        },
    }
