<template>
  <section class="page" data-module="switchgear">
    <header class="page-head">
      <div>
        <h2>开关站管理管理</h2>
        <p class="page-desc">维护开关设备，围绕设备编号、设备名称、电压等级、所属电站做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记开关设备</button>
        <button class="btn" type="button" @click="exportRows">导出开关站管理清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <RouterLink v-if="column === '设备编号'" class="link" :to="`/switchgear/${row.id}`">
              {{ row[column] ?? '—' }}
            </RouterLink>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <template v-if="allowedActions(row).length">
              <button
                v-for="action in allowedActions(row)"
                :key="action"
                class="link"
                type="button"
                :disabled="busyId === row.id"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </template>
            <span v-else class="text-muted">暂无可执行动作</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无开关站管理数据，可先登记开关设备</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条开关站管理记录</span>
      <span v-if="okMessage" class="ok-text">{{ okMessage }}</span>
      <span v-if="errorMessage" class="error-text">
        {{ errorMessage }}
        <button class="link" type="button" @click="reload">重新读取</button>
      </span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = {
  id: number
  可执行动作?: string[]
  [key: string]: unknown
}

const ENDPOINT = '/api/switchgear'
const columns = ["设备编号", "设备名称", "电压等级", "所属电站", "分合状态", "操作许可", "上次操作日", "设备状态"]
const statLabels = [["合闸设备", "合闸运行"], ["分闸设备", "分闸备用"], ["检修设备", "检修挂牌"]] as const

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const okMessage = ref('')
const busyId = ref<number | null>(null)
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const stats = computed(() =>
  statLabels.map(([label, status]) => ({
    label,
    value: rows.value.filter((row) => row['分合状态'] === status).length,
  })),
)

function allowedActions(row: Row): string[] {
  return Array.isArray(row['可执行动作']) ? (row['可执行动作'] as string[]) : []
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '开关设备登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  okMessage.value = ''
  busyId.value = row.id
  // 提交携带读取时拿到的操作许可，后端据此判断本页面的状态是不是已经过期。
  const permit = typeof row['操作许可'] === 'string' ? (row['操作许可'] as string) : ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action, permit } }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload || payload.ok === false) {
      // 失败时不重新拉取：保留这一页原来的可执行动作，提示人工重新读取后再操作。
      const reason = payload?.message ? String(payload.message) : '开关站管理动作未生效'
      errorMessage.value = `${reason}，请重新读取最新状态后再操作`
      return
    }
    const message = String(payload.message ?? '操作已生效')
    await reload()
    okMessage.value = message
  } catch (error) {
    errorMessage.value = error instanceof Error ? `${error.message}，请重新读取最新状态后再操作` : '开关站管理操作失败，请重新读取'
  } finally {
    busyId.value = null
  }
}

async function reload() {
  errorMessage.value = ''
  okMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('开关设备列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '开关站管理列表读取失败'
  }
}

onMounted(reload)
</script>
