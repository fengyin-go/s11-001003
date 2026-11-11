"""候选定位端到端冒烟（仅标准库，不依赖 FastAPI）。

覆盖：检索 -> 跨页续读 -> 配置变更触发 stale -> 新检索换版本 -> 会话失效 -> 动作推进版本。
运行：python3 -I scripts/locator_smoke.py
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/workspace/backend")

from app.services.locator import locator_service  # noqa: E402
from app.services.router import RouterService  # noqa: E402
from app.store import store  # noqa: E402

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"[{'PASS' if condition else 'FAIL'}] {name} {detail}")
    if not condition:
        failures.append(name)


# 1. 同权重冲突稳定裁决：ROUT-101/102 同权重同比例，id 小者排前。
first = locator_service.open_search("https://news.example.com/list/9", 1, 20)
order = [item["规则编号"] for item in first["items"]]
check("同权重按规则id稳定裁决", order[:2] == ["ROUT-101", "ROUT-102"], str(order))
check("快照初始不过期", first["snapshot"]["stale"] is False)
sid = first["searchId"]

# 2. 跨页连续定位：每页 2 条，全局序号连续且任务不重复。
seen_tasks: list[int] = []
seen_nos: list[int] = []
for page in range(1, 4):
    payload = locator_service.read_page(sid, page, 2)
    for item in payload["items"]:
        seen_nos.append(item["候选序号"])
        seen_tasks.append(item["采集任务id"])
check("跨页序号连续", seen_nos == list(range(1, first["total"] + 1)), str(seen_nos))
check("跨页无重复任务", len(seen_tasks) == len(set(seen_tasks)))

# 3. 检索期间停用规则：旧检索翻页仍绑定原版本，仅标记 stale。
before_versions = (first["snapshot"]["routerVersion"], first["snapshot"]["collectorVersion"])
svc = RouterService()
svc.run_action(102, "停用规则")
same = locator_service.read_page(sid, 2, 2)
check("配置变更后旧检索仍绑定原版本",
      (same["snapshot"]["routerVersion"], same["snapshot"]["collectorVersion"]) == before_versions)
check("旧检索被标记 stale", same["snapshot"]["stale"] is True)
check("stale 原因可读", "版本 1 → 2" in (same["snapshot"]["staleReason"] or ""))
check("旧检索候选集合不变", [i["规则编号"] for i in same["items"]] == ["ROUT-103", "ROUT-114"])

# 4. 新检索使用新版本，停用规则不再参与。
fresh = locator_service.open_search("https://news.example.com/list/9", 1, 20)
check("新检索使用新版本", fresh["snapshot"]["routerVersion"] == before_versions[0] + 1)
check("新检索未过期", fresh["snapshot"]["stale"] is False)
check("停用规则退出候选", "ROUT-102" not in [i["规则编号"] for i in fresh["items"]])

# 5. 会话状态查询与失效语义。
meta = locator_service.get_search(sid)
check("会话元数据含版本对照", meta["stale"] is True and meta["currentVersions"]["router"] == 2)
try:
    locator_service.read_page("lc_missing_session", 1, 2)
    check("失效会话抛出 KeyError（路由层映射 410）", False)
except KeyError:
    check("失效会话抛出 KeyError（路由层映射 410）", True)

# 6. 排除口径：停用/完成目标、无法解析目标均有原因记录。
legacy = locator_service.open_search("https://legacy.example.com/a", 1, 20)
check("停用目标被排除", any(e["规则编号"] == "ROUT-108" for e in legacy["exclusions"]))
finance = locator_service.open_search("https://finance.example.com/a", 1, 20)
check("完成目标被排除", any(e["规则编号"] == "ROUT-109" for e in finance["exclusions"]))
unknown = locator_service.open_search("https://unknown.example.com/a", 1, 20)
check("无法解析目标被排除", any(e["规则编号"] == "ROUT-110" for e in unknown["exclusions"]))

# 7. 空 URL 拒绝。
try:
    locator_service.open_search("  ", 1, 20)
    check("空 URL 被拒绝", False)
except ValueError:
    check("空 URL 被拒绝", True)

# 8. 动作确实推进了 store 版本号。
check("store 版本已推进", store.version("router") == 2)

print()
if failures:
    print(f"冒烟失败 {len(failures)} 项：{failures}")
    sys.exit(1)
print("全部冒烟通过")
