<template>
  <section class="page" data-module="collector">
    <header class="page-head">
      <div>
        <h2>采集引擎管理</h2>
        <p class="page-desc">维护采集任务的输入、执行约束与结果记录，为采集引擎提供可验证的数据工程流程。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记采集任务</button>
        <button class="btn" type="button" @click="exportRows">导出采集引擎清单</button>
      </div>
    </header>

    <div v-if="highlightTaskId" class="locator-banner ok">
      <span>已从链路分发候选定位到采集任务 id={{ highlightTaskId }}，对应行已高亮；可在此直接查看或操作真实采集目标。</span>
      <button class="btn ghost" type="button" @click="clearHighlight">取消高亮</button>
    </div>

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
        <tr v-for="row in rows" :key="String(row.id)" :class="{ 'highlight-row': String(row.id) === String(highlightTaskId) }">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无采集引擎数据，可先登记采集任务</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条采集引擎记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/collector'
const columns = ["任务编号", "目标网址", "HTTP方法", "请求头部", "并发线程", "超时秒数", "代理地址", "字符编码"]
const actions = ["提交启动", "暂停采集", "恢复采集", "归档任务"]
const statuses = ["草稿", "待启动", "运行中", "已完成", "已停用"]
const stats = [{"label": "采集任务总数", "value": 0}, {"label": "运行中任务", "value": 0}, {"label": "已完成任务", "value": 0}]

const route = useRoute()
const router = useRouter()
// 链路分发候选跳转时携带 taskId，用于高亮真实采集目标。
const highlightTaskId = ref<string | null>(typeof route.query.taskId === 'string' ? route.query.taskId : null)

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

function clearHighlight() {
  highlightTaskId.value = null
  void router.replace({ path: route.path, query: {} })
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '采集任务登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('采集引擎动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '采集引擎操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('采集任务列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '采集引擎列表读取失败'
  }
}

onMounted(reload)
</script>
