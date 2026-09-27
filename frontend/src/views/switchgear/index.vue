<template>
  <section class="page" data-module="switchgear">
    <header class="page-head">
      <div>
        <h2>开关站管理</h2>
        <p class="page-desc">维护开关设备，围绕设备编号、设备名称、电压等级、所属电站做登记、筛选与分合状态流转。</p>
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
            <template v-if="availableActions(row).length">
              <button
                v-for="action in availableActions(row)"
                :key="action"
                class="link"
                type="button"
                :disabled="busyId === row.id || !!actionError"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </template>
            <span v-else class="muted-text">—</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无开关站管理数据，可先登记开关设备</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条开关站管理记录</span>
      <span v-if="actionError" class="error-text">
        {{ actionError }}
        <button class="link" type="button" @click="reload">重新读取</button>
      </span>
      <span v-else-if="readError" class="error-text">{{ readError }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'
import { availableActions, ENDPOINT, submitAction, type Row } from './actions'

const columns = ['设备编号', '设备名称', '电压等级', '所属电站', '分合状态', '操作许可', '上次操作日', '设备状态']
const filterFields = columns.slice(0, 3)

const rows = ref<Row[]>([])
const total = ref(0)
const readError = ref('')
const actionError = ref('')
const busyId = ref<Row['id'] | null>(null)
const filters = ref<Record<string, string>>({})

const stats = computed(() => [
  { label: '合闸设备', value: rows.value.filter((row) => row.status === '合闸运行').length },
  { label: '分闸设备', value: rows.value.filter((row) => row.status === '分闸备用').length },
  { label: '检修设备', value: rows.value.filter((row) => row.status === '检修挂牌').length },
])

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  readError.value = '开关设备登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  actionError.value = ''
  busyId.value = row.id
  // 只提交读取页面时拿到的许可；失败时不改 rows，保留原来的可执行动作
  const result = await submitAction(row.id, action, row['操作许可'])
  busyId.value = null
  if (!result.ok) {
    actionError.value = result.message
    return
  }
  await reload()
}

async function reload() {
  readError.value = ''
  actionError.value = ''
  const query = new URLSearchParams(filters.value).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error(`开关设备列表读取失败（HTTP ${response.status}）`)
    }
    const payload = (await response.json()) as { items?: Row[]; total?: number }
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    readError.value = error instanceof Error ? error.message : '开关设备列表读取失败'
  }
}

onMounted(reload)
</script>
