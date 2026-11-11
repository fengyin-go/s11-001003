"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。

除了示例数据外，仓库还维护每个模块的单调递增「配置版本号」：
候选定位检索在创建快照时记录版本，翻页期间若有人改了配置，可据此判断快照已过期，
而本次翻页仍然绑定旧版本，只有重新发起检索才会拿到新版本。
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.seed import SEED_ROWS
from app.seed_locator import LOCATOR_ROWS


class Store:
    def __init__(self) -> None:
        merged: dict[str, list[dict[str, Any]]] = {
            name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()
        }
        # 定位演示数据与基础种子同模块合并，id 从 101 起，避免覆盖既有示例。
        for module, rows in LOCATOR_ROWS.items():
            merged.setdefault(module, []).extend(dict(row) for row in rows)
        self._tables: dict[str, list[dict[str, Any]]] = merged
        self._versions: dict[str, int] = {name: 1 for name in self._tables}

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def snapshot(self, module: str) -> list[dict[str, Any]]:
        """返回模块数据的深拷贝，检索快照与在线配置隔离，后续修改不会污染快照。"""
        return deepcopy(self.rows(module))

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def version(self, module: str) -> int:
        """读取模块当前配置版本；模块首次出现时登记为版本 1。"""
        return self._versions.setdefault(module, 1)

    def bump_version(self, module: str) -> int:
        """配置发生登记/状态流转后推进版本号，返回推进后的版本。"""
        version = self._versions.get(module, 1) + 1
        self._versions[module] = version
        return version

    def versions(self) -> dict[str, int]:
        return dict(self._versions)

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(1 for row in rows if row.get("abnormal")),
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        return {"cards": cards, "modules": modules}


store = Store()
