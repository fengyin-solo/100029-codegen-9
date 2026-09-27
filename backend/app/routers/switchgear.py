"""开关站管理接口：维护开关设备，覆盖分闸操作、合闸送电、挂牌检修等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.switchgear import SwitchgearService

router = APIRouter(prefix="/api/switchgear", tags=["开关站管理"])

service = SwitchgearService()

LIST_FIELDS = ["设备编号", "设备名称", "电压等级", "所属电站", "分合状态", "操作许可", "上次操作日", "设备状态"]
STATUSES = ["合闸运行", "分闸备用", "检修挂牌"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按设备编号检索"),
    status: str | None = Query(default=None, description="合闸运行、分闸备用、检修挂牌"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按设备编号与状态过滤开关站管理列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出开关站管理清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "switchgear", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条开关设备明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"开关设备 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条开关设备，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="开关设备已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条开关设备执行分闸操作、合闸送电、挂牌检修。

    必须携带读取时拿到的「操作许可」作为校验令牌：
    - 许可与服务端一致才执行，分合状态/设备状态/操作许可/最近操作日一起落库；
    - 许可过期（其他页面或其他人已先操作）时拒绝覆盖，状态保持不变；
    - 动作不在当前状态允许范围内时拦下并说明原因。
    """
    values = payload.values
    action = str(values.get("action") or "").strip()
    permit = str(values.get("permit") or values.get("操作许可") or "").strip()
    entry, code, message = service.run_action(entry_id, action, permit)
    if entry is None:
        return ActionResult(ok=False, code=code, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
