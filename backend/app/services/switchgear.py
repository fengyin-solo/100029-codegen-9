"""开关站管理业务规则：状态流转、字段校验、操作许可令牌与并发提交口径都收在这里。"""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

from app.store import store

MODULE = "switchgear"
REQUIRED_FIELDS = ["设备编号", "设备名称", "电压等级"]
OPTIONAL_FIELDS = ["所属电站"]
STATUS_ORDER = ["合闸运行", "分闸备用", "检修挂牌"]
ACTION_RULES = {"分闸操作": "分闸备用", "合闸送电": "合闸运行", "挂牌检修": "检修挂牌"}
# 当前分合状态下允许执行的动作；页面上的「可执行动作」以此为准，详情页与列表页共用同一份口径。
ALLOWED_ACTIONS: dict[str, list[str]] = {
    "合闸运行": ["分闸操作", "挂牌检修"],
    "分闸备用": ["合闸送电", "挂牌检修"],
    "检修挂牌": ["合闸送电"],
}
# 分合状态对应的设备状态：分合操作完成时与操作许可、最近操作日一起落库。
DEVICE_STATE = {
    "合闸运行": "运行正常",
    "分闸备用": "备用正常",
    "检修挂牌": "检修中",
}

# 服务内部字段（许可序号），不出接口
_SEQ_KEY = "_permit_seq"

# 同一设备的分合提交串行化，配合操作许可校验，拦住「过期许可覆盖已生效结果」。
_action_lock = threading.Lock()


def make_permit(entry_id: int, seq: int) -> str:
    """操作许可即乐观锁令牌：每次成功操作换发新许可，旧许可随即失效。"""
    return f"XK-{entry_id:04d}-{seq:03d}"


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _permit_seq(entry: dict[str, Any]) -> int:
    seq = entry.get(_SEQ_KEY)
    if seq is None:
        # 兼容种子数据：优先从许可文本尾部取序号，取不到就按 1 起步。
        tail = str(entry.get("操作许可") or "").rsplit("-", 1)[-1]
        seq = int(tail) if tail.isdigit() else 1
        entry[_SEQ_KEY] = int(seq)
    return int(seq)


def _present(entry: dict[str, Any]) -> dict[str, Any]:
    """剥离内部字段并补上当前可执行动作；列表与详情走同一出口，保证两页状态口径一致。"""
    data = {key: value for key, value in entry.items() if not str(key).startswith("_")}
    data["可执行动作"] = list(ALLOWED_ACTIONS.get(str(entry.get("status")), []))
    return data


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
        return [_present(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return _present(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        for field in OPTIONAL_FIELDS:
            if str(values.get(field) or "").strip():
                entry[field] = values[field]
        # 登记即给出完整状态四元组，列表与详情读到的永远是同一份。
        entry["status"] = STATUS_ORDER[0]
        entry["分合状态"] = STATUS_ORDER[0]
        entry["设备状态"] = DEVICE_STATE[STATUS_ORDER[0]]
        entry[_SEQ_KEY] = 1
        entry["操作许可"] = make_permit(entry["id"], 1)
        entry["上次操作日"] = now_text()
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return _present(entry), []

    def run_action(
        self, entry_id: int, action: str, permit: str
    ) -> tuple[dict[str, Any] | None, str, str]:
        """执行分合操作。

        返回 (最新记录, 结果码, 说明)：结果码为 ok / not_found / invalid / stale_permit。
        stale_permit 表示提交携带的操作许可已过期，服务端状态保持不变。
        """
        action = (action or "").strip()
        permit = (permit or "").strip()
        # 加锁保证「读状态 → 校许可 → 写四元组」整体原子，两个页面同时提交也不会交叉覆盖。
        with _action_lock:
            entry = store.find(MODULE, entry_id)
            if entry is None:
                return None, "not_found", f"开关设备 {entry_id} 不存在或已归档"
            if action not in ACTION_RULES:
                return None, "invalid", f"动作「{action}」不属于开关站管理可执行范围"
            if not permit:
                return None, "stale_permit", "缺少操作许可，无法确认设备当前状态"
            current_permit = make_permit(entry_id, _permit_seq(entry))
            if permit != current_permit:
                return (
                    None,
                    "stale_permit",
                    "操作许可已过期，设备状态可能已被其他操作更新，本次提交未生效",
                )
            target = ACTION_RULES[action]
            if action not in ALLOWED_ACTIONS.get(str(entry.get("status")), []):
                return None, "invalid", f"设备当前为「{entry.get('status')}」，不允许执行「{action}」"
            seq = _permit_seq(entry) + 1
            # 分合状态、设备状态、操作许可、最近操作日一次性写入，不存在半成功。
            entry["status"] = target
            entry["分合状态"] = target
            entry["设备状态"] = DEVICE_STATE[target]
            entry[_SEQ_KEY] = seq
            entry["操作许可"] = make_permit(entry_id, seq)
            entry["上次操作日"] = now_text()
            entry["pending"] = target != STATUS_ORDER[-1]
            entry["abnormal"] = False
            return _present(entry), "ok", f"开关设备已{action}"
