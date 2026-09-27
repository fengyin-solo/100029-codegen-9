/**
 * 开关设备动作口径：列表页与详情页共用同一份状态机与提交逻辑，
 * 保证两个页面看到的可执行动作、许可校验与失败处理完全一致。
 */

import { request } from '@/api/client'

export const ENDPOINT = '/api/switchgear'

export type Row = Record<string, string | number | boolean | null>

/** 设备状态 -> 当前可执行动作；失败时不重算，页面保留这份口径下的原动作 */
export function availableActions(row: Row): string[] {
  switch (row.status) {
    case '合闸运行':
      return ['分闸操作']
    case '分闸备用':
      return ['合闸送电', '挂牌检修']
    case '检修挂牌':
      return ['合闸送电']
    default:
      return []
  }
}

export interface ActionOutcome {
  ok: boolean
  message: string
  /** stale_permit=许可过期，missing_permit=未带许可，invalid_transition=状态不允许 */
  code?: string | null
  entry?: Row | null
}

/**
 * 提交分合动作：回传读取页面时拿到的操作许可（乐观锁）。
 * 任何失败都不抛异常、不改本地数据，由调用方保留原可执行动作并提示重新读取。
 */
export async function submitAction(
  entryId: Row['id'],
  action: string,
  permit: unknown,
): Promise<ActionOutcome> {
  let response: Response
  try {
    response = await request(`${ENDPOINT}/${entryId}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action, 操作许可: permit ?? '' } }),
    })
  } catch (error) {
    const detail = error instanceof Error ? error.message : '请求未送达'
    return { ok: false, message: `${detail}，本地动作未变更，请重新读取` }
  }

  let payload: { ok?: unknown; message?: unknown; code?: unknown; entry?: unknown } = {}
  try {
    payload = await response.json()
  } catch {
    payload = {}
  }

  if (!response.ok || payload.ok !== true) {
    const message =
      typeof payload.message === 'string' && payload.message
        ? payload.message
        : `动作未生效（HTTP ${response.status}），请重新读取设备状态后再操作`
    return { ok: false, message, code: typeof payload.code === 'string' ? payload.code : null }
  }

  return {
    ok: true,
    message: typeof payload.message === 'string' ? payload.message : '操作已生效',
    entry: (payload.entry as Row | undefined) ?? null,
  }
}
