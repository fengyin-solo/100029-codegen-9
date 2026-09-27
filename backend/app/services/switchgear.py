"""开关站管理业务规则：状态流转、字段校验与筛选口径都收在这里。

并发口径：操作许可（许可令牌里带版本号）是乐观锁。提交动作时必须回传页面读取到的
许可；两个页面同时提交时，先到的请求使许可轮换，后到的请求带着过期许可会被拒绝，
已经生效的状态不会被覆盖。操作许可、上次操作日、设备状态与分合状态在同一把模块锁
内一次性写入，保证列表与明细读到的是同一份结果。
"""
from __future__ import annotations

import threading
from datetime import date
from typing import Any

from app.store import store

MODULE = "switchgear"
REQUIRED_FIELDS = ["设备编号", "设备名称", "电压等级"]
STATUS_ORDER = ["合闸运行", "分闸备用", "检修挂牌"]

# 动作 -> 目标状态
ACTION_RULES = {"分闸操作": "分闸备用", "合闸送电": "合闸运行", "挂牌检修": "检修挂牌"}
# 当前状态允许执行的动作（可执行动作以这份状态机为准，明细和列表口径一致）
ALLOWED_ACTIONS: dict[str, list[str]] = {
    "合闸运行": ["分闸操作"],
    "分闸备用": ["合闸送电", "挂牌检修"],
    "检修挂牌": ["合闸送电"],
}

# 分合状态：只描述断路器本身合/分
BREAKER_STATE = {"合闸运行": "合闸", "分闸备用": "分闸", "检修挂牌": "分闸"}
# 设备状态：检修挂牌视为异常工况
DEVICE_STATE = {"合闸运行": "运行正常", "分闸备用": "热备用", "检修挂牌": "检修中"}
NEGATIVE_STATUSES = ["检修挂牌"]

# 对外不可见的内部字段（版本号只藏在许可令牌里，不直接下发）
INTERNAL_KEYS = ("_version",)

# 模块级写入锁：动作是读-校验-写一组字段，必须整段互斥
_write_lock = threading.Lock()


def _version(entry: dict[str, Any]) -> int:
    return int(entry.get("_version", 1))


def _permit(entry: dict[str, Any]) -> str:
    """许可令牌：设备编号 + 版本号。版本每生效一次动作就递增，旧许可随即过期。"""
    return f"PERM-{entry['设备编号']}-{_version(entry):04d}"


def public_view(entry: dict[str, Any]) -> dict[str, Any]:
    """对外视图：列表与明细都走这里，保证两个页面读到同一份字段口径。"""
    return {key: value for key, value in entry.items() if key not in INTERNAL_KEYS}


class SwitchgearService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("设备编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [public_view(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return public_view(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        with _write_lock:
            rows = store.rows(MODULE)
            entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
            entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
            entry.update(
                {
                    "所属电站": values.get("所属电站", ""),
                    "status": STATUS_ORDER[0],
                    "pending": True,
                    "abnormal": False,
                    "_version": 1,
                    "分合状态": BREAKER_STATE[STATUS_ORDER[0]],
                    "操作许可": "",
                    "上次操作日": "",
                    "设备状态": DEVICE_STATE[STATUS_ORDER[0]],
                }
            )
            entry["操作许可"] = _permit(entry)
            rows.append(entry)
            return public_view(entry), []

    def run_action(
        self, entry_id: int, action: str, permit: str | None
    ) -> tuple[dict[str, Any] | None, str, str]:
        """执行分闸/合闸/挂牌。

        返回 (明细, 提示语, 失败代码)；成功时代码为空。任何失败都不改写记录，
        页面因此保留原来的可执行动作，按提示重新读取后再提交。
        """
        permit = str(permit or "").strip()
        if not permit:
            return None, "缺少操作许可，请重新读取设备状态后再操作", "missing_permit"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于开关站管理可执行范围", "invalid_action"

        with _write_lock:
            entry = store.find(MODULE, entry_id)
            if entry is None:
                return None, f"开关设备 {entry_id} 不存在或已归档", "not_found"

            # 乐观锁：许可与当前版本不符，说明本页状态已过期，过期许可不得覆盖生效结果
            if permit != _permit(entry):
                return (
                    None,
                    "操作许可已过期，设备状态可能已在其他页面变更，请重新读取后再操作",
                    "stale_permit",
                )

            current = str(entry.get("status"))
            if action not in ALLOWED_ACTIONS.get(current, []):
                return (
                    None,
                    f"设备当前为「{current}」，不允许执行「{action}」，请重新读取状态",
                    "invalid_transition",
                )

            target = ACTION_RULES[action]
            # 操作许可、上次操作日、设备状态与分合状态在同一临界区一起落库
            entry["status"] = target
            entry["pending"] = target != STATUS_ORDER[-1]
            entry["abnormal"] = target in NEGATIVE_STATUSES
            entry["分合状态"] = BREAKER_STATE[target]
            entry["设备状态"] = DEVICE_STATE[target]
            entry["上次操作日"] = date.today().isoformat()
            entry["_version"] = _version(entry) + 1
            entry["操作许可"] = _permit(entry)
            return public_view(entry), f"开关设备已{action}", ""
