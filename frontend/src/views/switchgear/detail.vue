<template>
  <section class="page" data-module="switchgear-detail">
    <header class="page-head">
      <div>
        <h2>开关设备详情</h2>
        <p class="page-desc">每次进入都从服务端重新读取，与列表页共用同一份状态、操作许可与可执行动作。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/switchgear">返回列表</RouterLink>
        <button class="btn ghost" type="button" @click="reload">重新读取</button>
      </div>
    </header>

    <div v-if="entry" class="detail-card">
      <dl class="detail-grid">
        <template v-for="column in columns" :key="column">
          <dt>{{ column }}</dt>
          <dd>{{ entry[column] ?? '—' }}</dd>
        </template>
        <dt>当前状态</dt>
        <dd>{{ entry.status }}</dd>
      </dl>

      <div class="detail-actions">
        <button
          v-for="action in availableActions(entry)"
          :key="action"
          class="btn primary"
          type="button"
          :disabled="busy || !!actionError"
          @click="runAction(action)"
        >
          {{ action }}
        </button>
        <span v-if="!availableActions(entry).length" class="muted-text">当前状态暂无可执行动作</span>
      </div>
    </div>

    <div v-else-if="!readError" class="empty-state">正在读取开关设备…</div>

    <footer class="page-foot">
      <span v-if="actionError" class="error-text">
        {{ actionError }}
        <button class="link" type="button" @click="reload">重新读取</button>
      </span>
      <span v-else-if="readError" class="error-text">
        {{ readError }}
        <button class="link" type="button" @click="reload">重新读取</button>
      </span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { request } from '@/api/client'
import { availableActions, ENDPOINT, submitAction, type Row } from './actions'

const columns = ['设备编号', '设备名称', '电压等级', '所属电站', '分合状态', '操作许可', '上次操作日', '设备状态']

const route = useRoute()
const entryId = String(route.params.id)

const entry = ref<Row | null>(null)
const readError = ref('')
const actionError = ref('')
const busy = ref(false)

async function runAction(action: string) {
  if (!entry.value) {
    return
  }
  actionError.value = ''
  busy.value = true
  // 提交本页读取到的许可；失败时保留原状态与原可执行动作，只提示重新读取
  const result = await submitAction(entry.value.id, action, entry.value['操作许可'])
  busy.value = false
  if (!result.ok) {
    actionError.value = result.message
    return
  }
  await reload()
}

async function reload() {
  readError.value = ''
  actionError.value = ''
  try {
    const response = await request(`${ENDPOINT}/${entryId}`)
    if (!response.ok) {
      throw new Error(`开关设备详情读取失败（HTTP ${response.status}）`)
    }
    entry.value = (await response.json()) as Row
  } catch (error) {
    entry.value = null
    readError.value = error instanceof Error ? error.message : '开关设备详情读取失败'
  }
}

onMounted(reload)
</script>
