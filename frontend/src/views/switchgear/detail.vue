<template>
  <section class="page" data-module="switchgear-detail">
    <header class="page-head">
      <div>
        <h2>开关设备详情</h2>
        <p class="page-desc">分合状态、操作许可、上次操作日与设备状态由每次分合操作一起更新，进入本页一律重新读取。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="reload">重新读取</button>
        <RouterLink class="btn" to="/switchgear">返回列表</RouterLink>
      </div>
    </header>

    <p v-if="notFound" class="error-text">开关设备不存在或已归档。</p>

    <template v-else-if="entry">
      <article class="detail-card">
        <dl class="detail-grid">
          <div v-for="field in detailFields" :key="field" class="detail-item">
            <dt>{{ field }}</dt>
            <dd>{{ (entry[field] ?? '—') as string }}</dd>
          </div>
        </dl>
      </article>

      <section class="action-card">
        <h3>可执行动作</h3>
        <div class="row-actions">
          <button
            v-for="action in allowedActions"
            :key="action"
            class="btn primary"
            type="button"
            :disabled="busy"
            @click="runAction(action)"
          >
            {{ action }}
          </button>
          <span v-if="!allowedActions.length" class="text-muted">当前状态下暂无可执行动作</span>
        </div>
        <p v-if="okMessage" class="ok-text">{{ okMessage }}</p>
        <p v-if="errorMessage" class="error-text">
          {{ errorMessage }}
          <button class="link" type="button" @click="reload">重新读取</button>
        </p>
      </section>
    </template>

    <p v-else-if="errorMessage" class="error-text">
      {{ errorMessage }}
      <button class="link" type="button" @click="reload">重新读取</button>
    </p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { request } from '@/api/client'

type Entry = {
  id: number
  可执行动作?: string[]
  [key: string]: unknown
}

const route = useRoute()
const ENDPOINT = '/api/switchgear'
const detailFields = ["设备编号", "设备名称", "电压等级", "所属电站", "分合状态", "操作许可", "上次操作日", "设备状态"]

const entry = ref<Entry | null>(null)
const errorMessage = ref('')
const okMessage = ref('')
const notFound = ref(false)
const busy = ref(false)

const allowedActions = computed<string[]>(() =>
  Array.isArray(entry.value?.['可执行动作']) ? (entry.value?.['可执行动作'] as string[]) : [],
)

function entryId(): number {
  return Number(route.params.id)
}

async function runAction(action: string) {
  if (!entry.value) {
    return
  }
  errorMessage.value = ''
  okMessage.value = ''
  busy.value = true
  // 操作许可取自本次进入详情时读到的记录：若列表页或他人已先操作，许可即过期。
  const permit = typeof entry.value['操作许可'] === 'string' ? (entry.value['操作许可'] as string) : ''
  try {
    const response = await request(`${ENDPOINT}/${entry.value.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action, permit } }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload || payload.ok === false) {
      // 失败时保留页面现有的分合状态与可执行动作，不做本地覆盖，引导重新读取。
      if (payload?.code === 'not_found') {
        notFound.value = true
        return
      }
      const reason = payload?.message ? String(payload.message) : '开关站管理动作未生效'
      errorMessage.value = `${reason}，请重新读取最新状态后再操作`
      return
    }
    // 成功后重新读取，详情与列表看到的是同一份服务端状态。
    const message = String(payload.message ?? '操作已生效')
    await reload()
    okMessage.value = message
  } catch (error) {
    errorMessage.value = error instanceof Error ? `${error.message}，请重新读取最新状态后再操作` : '开关站管理操作失败，请重新读取'
  } finally {
    busy.value = false
  }
}

async function reload() {
  errorMessage.value = ''
  okMessage.value = ''
  notFound.value = false
  try {
    const response = await request(`${ENDPOINT}/${entryId()}`)
    if (response.status === 404) {
      notFound.value = true
      entry.value = null
      return
    }
    if (!response.ok) {
      throw new Error('开关设备详情读取失败')
    }
    entry.value = await response.json()
  } catch (error) {
    entry.value = null
    errorMessage.value = error instanceof Error ? error.message : '开关设备详情读取失败'
  }
}

onMounted(reload)
</script>
