<template>
  <section class="page" data-module="router">
    <header class="page-head">
      <div>
        <h2>链路分发管理</h2>
        <p class="page-desc">维护分发规则的输入、执行约束与结果记录，为链路分发提供可验证的数据工程流程。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记分发规则</button>
        <button class="btn" type="button" @click="exportRows">导出链路分发清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <!-- 候选定位：输入来源 URL，服务端做确定性检索并返回可解释候选集合 -->
    <section class="locator-panel">
      <header class="locator-head">
        <div>
          <h3>候选定位</h3>
          <p class="page-desc">输入来源 URL，按来源URL模式、目标引擎、优先级权重与分发比例在服务端确定性检索候选采集任务。</p>
        </div>
        <div class="locator-head-actions">
          <button class="btn" type="button" :disabled="benchLoading" @click="runBenchmark">
            {{ benchLoading ? '对照计算中…' : '运行全量扫描基准对照' }}
          </button>
          <button class="btn ghost" type="button" @click="showSemantics = !showSemantics">
            {{ showSemantics ? '收起检索口径' : '展开检索口径' }}
          </button>
        </div>
      </header>

      <form class="locator-search" @submit.prevent="startSearch(1)">
        <label class="locator-url">
          <span>来源 URL</span>
          <input
            v-model="sourceUrl"
            type="text"
            placeholder="例如 https://news.example.com/detail/1024"
            aria-label="来源 URL"
          />
        </label>
        <label class="locator-size">
          <span>每页候选数</span>
          <input v-model.number="pageSize" type="number" min="1" max="200" />
        </label>
        <button class="btn primary" type="submit" :disabled="locatorLoading">
          {{ locatorLoading ? '检索中…' : '发起候选检索' }}
        </button>
        <button v-if="searchId" class="btn ghost" type="button" @click="resetLocator">清空检索</button>
      </form>

      <div v-if="showSemantics" class="semantics-box">
        <template v-if="semantics">
          <p><strong>匹配：</strong>{{ semantics.matching.rule }}；{{ semantics.matching.scope }}</p>
          <p><strong>同权重裁决：</strong>{{ semantics.tieBreak.rule }}。{{ semantics.tieBreak.note }}</p>
          <p><strong>排除：</strong>采集任务状态为{{ semantics.exclusion.collectorStatus.join('、') }}时排除；{{ semantics.exclusion.unresolvableTarget }}；{{ semantics.exclusion.dedup }}</p>
          <p><strong>快照与版本：</strong>{{ semantics.snapshot.rule }}；{{ semantics.snapshot.stale }}；{{ semantics.snapshot.expired }}</p>
          <p><strong>分页：</strong>{{ semantics.pagination.rule }}</p>
        </template>
        <p v-else class="page-desc">检索口径加载中…</p>
      </div>

      <div v-if="locatorError" class="locator-banner error" role="alert">
        <span>{{ locatorError }}</span>
        <button v-if="sessionExpired" class="btn primary" type="button" @click="startSearch(1)">重新发起检索</button>
      </div>

      <div v-if="result" class="locator-result">
        <div class="locator-meta">
          <div class="meta-tags">
            <span class="tag">检索 {{ result.searchId }}</span>
            <span class="tag">命中规则 {{ result.matchedRuleCount }} 条</span>
            <span class="tag">候选 {{ result.total }} 个</span>
            <span class="tag">排除 {{ result.exclusionTotal }} 项</span>
            <span class="tag">规则版本 v{{ result.snapshot.routerVersion }}</span>
            <span class="tag">采集版本 v{{ result.snapshot.collectorVersion }}</span>
          </div>
          <div v-if="result.snapshot.stale" class="locator-banner warn">
            <span>⚠ {{ result.snapshot.staleReason }}</span>
            <button class="btn" type="button" @click="startSearch(1)">用新版本重开检索</button>
          </div>
          <div v-else class="locator-banner ok">本次翻页绑定检索时的配置快照，跨页候选连续、无重复无漏项。</div>
        </div>

        <table class="data-table locator-table">
          <thead>
            <tr>
              <th style="width: 42px">#</th>
              <th>裁决排名</th>
              <th>分发规则</th>
              <th>目标采集任务</th>
              <th>优先级权重</th>
              <th>分发比例</th>
              <th>任务状态</th>
              <th>解释与跳转</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="item in result.items" :key="String(item['采集任务id'])">
              <tr>
                <td>{{ item['候选序号'] }}</td>
                <td>{{ item['裁决排名'] }}</td>
                <td>
                  <strong>{{ item['规则编号'] }}</strong>
                  <div class="cell-sub">命中模式：{{ item['命中模式'] }}</div>
                </td>
                <td>
                  <strong>{{ item['采集任务编号'] }}</strong>
                  <div class="cell-sub">{{ item['采集任务目标网址'] }}</div>
                </td>
                <td>{{ item['优先级权重'] }}</td>
                <td>{{ item['分发比例'] }}</td>
                <td><span class="status-pill">{{ item['采集任务状态'] }}</span></td>
                <td class="row-actions">
                  <button class="link" type="button" @click="toggleExplain(item['采集任务id'])">
                    {{ expandedIds.has(item['采集任务id']) ? '收起解释' : '展开解释' }}
                  </button>
                  <button class="link" type="button" @click="openCollector(item)">进入采集任务</button>
                </td>
              </tr>
              <tr v-if="expandedIds.has(item['采集任务id'])" class="explain-row">
                <td colspan="8">
                  <div class="explain-box">
                    <p><strong>选中原因：</strong>{{ item['选中原因'] }}</p>
                    <p>
                      <strong>来源URL模式：</strong>{{ item['来源URL模式'] }}
                      ｜ <strong>目标引擎：</strong>{{ item['目标引擎'] }}
                      ｜ <strong>采集任务详情接口：</strong>{{ item['采集任务详情'] }}
                    </p>
                    <p v-if="item['同目标其他命中'].length">
                      <strong>同目标其他命中（已去重）：</strong>
                      <span v-for="hit in item['同目标其他命中']" :key="hit['规则id']" class="tag">
                        {{ hit['规则编号'] }}（排名 {{ hit['裁决排名'] }}，权重 {{ hit['优先级权重'] }}，比例 {{ hit['分发比例'] }}）
                      </span>
                    </p>
                  </div>
                </td>
              </tr>
            </template>
            <tr v-if="!result.items.length">
              <td colspan="8" class="empty-state">该来源 URL 没有可用候选，可查看下方排除说明定位原因</td>
            </tr>
          </tbody>
        </table>

        <section v-if="result.exclusions.length" class="exclusion-box">
          <h4>排除说明（{{ result.exclusionTotal }} 项，仅首页展示完整列表）</h4>
          <ul>
            <li v-for="ex in result.exclusions" :key="`${ex['规则id']}-${ex['原因']}`">
              <strong>{{ ex['规则编号'] }}</strong>
              <span v-if="ex['裁决排名']">（裁决排名 {{ ex['裁决排名'] }}）</span>
              ：{{ ex['原因'] }}
              <span class="cell-sub">命中模式：{{ ex['命中模式'] }}</span>
            </li>
          </ul>
        </section>

        <footer class="locator-pager">
          <span>候选 {{ result.pagination.firstCandidateNo }}–{{ result.pagination.lastCandidateNo }} / 共 {{ result.total }} 个</span>
          <div class="pager-buttons">
            <button class="btn" type="button" :disabled="result.page <= 1 || locatorLoading" @click="turnPage(result.page - 1)">上一页</button>
            <span class="tag">第 {{ result.page }} 页</span>
            <button class="btn" type="button" :disabled="!result.pagination.hasNext || locatorLoading" @click="turnPage(result.page + 1)">下一页</button>
          </div>
        </footer>
      </div>

      <div v-if="benchmark" class="bench-box">
        <header class="bench-head">
          <h3>大量候选对照基准</h3>
          <span class="tag" :class="benchmark.passed ? 'pass' : 'fail'">
            {{ benchmark.passed ? '全部校验通过' : '存在校验失败' }}
          </span>
        </header>
        <div class="stat-row">
          <article class="stat-card">
            <span class="stat-label">合成规则 / 采集任务</span>
            <strong class="stat-value">{{ benchmark.dataset.routerRuleCount }} / {{ benchmark.dataset.collectorTaskCount }}</strong>
          </article>
          <article class="stat-card">
            <span class="stat-label">候选总数（全量扫描同值）</span>
            <strong class="stat-value">{{ benchmark.result.candidateTotal }} / {{ benchmark.equivalence.fullScanCandidateTotal }}</strong>
          </article>
          <article class="stat-card">
            <span class="stat-label">排除项</span>
            <strong class="stat-value">{{ benchmark.result.exclusionTotal }}</strong>
          </article>
          <article class="stat-card">
            <span class="stat-label">同权重分组</span>
            <strong class="stat-value">{{ benchmark.tieBreak.sameWeightGroupCount }}</strong>
          </article>
        </div>
        <ul class="bench-checks">
          <li :class="benchmark.equivalence.indexVsFullScanSameOrder ? 'ok' : 'bad'">
            索引检索与全量扫描排序一致：{{ benchmark.equivalence.indexVsFullScanSameOrder }}
          </li>
          <li :class="benchmark.equivalence.indexVsFullScanSamePayload ? 'ok' : 'bad'">
            索引检索与全量扫描候选明细完全一致：{{ benchmark.equivalence.indexVsFullScanSamePayload }}
          </li>
          <li :class="benchmark.pagination.noDuplicateAcrossPages ? 'ok' : 'bad'">
            跨页无重复：{{ benchmark.pagination.noDuplicateAcrossPages }}
          </li>
          <li :class="benchmark.pagination.noMissingAcrossPages ? 'ok' : 'bad'">
            跨页无漏项：{{ benchmark.pagination.noMissingAcrossPages }}
          </li>
          <li :class="benchmark.pagination.continuousCandidateNo ? 'ok' : 'bad'">
            候选序号全局连续：{{ benchmark.pagination.continuousCandidateNo }}
          </li>
          <li :class="benchmark.tieBreak.stable ? 'ok' : 'bad'">
            同权重裁决稳定（{{ benchmark.tieBreak.rule }}）：{{ benchmark.tieBreak.stable }}
          </li>
        </ul>
        <p class="cell-sub">
          模拟每页 {{ benchmark.pagination.pageSize }} 条、共 {{ benchmark.pagination.pageCount }} 页连续读取；
          数据集合含停用/完成目标 {{ benchmark.dataset.excludedCollectorCount }} 个、无法解析规则 {{ benchmark.dataset.unresolvableRuleCount }} 条。
        </p>
      </div>
    </section>

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
          <td :colspan="columns.length + 1" class="empty-state">暂无链路分发数据，可先登记分发规则</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条链路分发记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type SameTargetHit = {
  '规则编号': string
  '规则id': number
  '裁决排名': number
  '优先级权重': string
  '分发比例': string
}
type Candidate = {
  '候选序号': number
  '裁决排名': number
  '规则id': number
  '规则编号': string
  '来源URL模式': string
  '命中模式': string
  '目标引擎': string
  '优先级权重': string
  '优先级权重数值': number
  '分发比例': string
  '分发比例数值': number
  '采集任务id': number
  '采集任务编号': string
  '采集任务状态': string
  '采集任务目标网址': string
  '采集任务详情': string
  '采集引擎页面': string
  '选中原因': string
  '同目标其他命中': SameTargetHit[]
}
type Exclusion = {
  '规则编号': string
  '规则id': number
  '原因': string
  '命中模式': string
  '裁决排名'?: number
}
type SearchResult = {
  searchId: string
  sourceUrl: string
  page: number
  size: number
  total: number
  matchedRuleCount: number
  exclusionTotal: number
  items: Candidate[]
  exclusions: Exclusion[]
  pagination: { hasPrevious: boolean; hasNext: boolean; firstCandidateNo: number; lastCandidateNo: number; pagesServed: number[] }
  snapshot: {
    routerVersion: number
    collectorVersion: number
    currentRouterVersion: number
    currentCollectorVersion: number
    stale: boolean
    staleReason: string | null
    ttlSeconds: number
  }
}
type Benchmark = Record<string, any>

const ENDPOINT = '/api/router'
const LOCATOR = '/api/router/locator'
const columns = ["规则编号", "来源URL模式", "目标引擎", "优先级权重", "分发比例", "熔断阈值", "降级策略", "健康检查间隔"]
const actions = ["提交校验", "启用规则", "停用规则"]
const statuses = ["草稿", "待校验", "已启用", "已停用"]
const stats = [{"label": "分发规则总数", "value": 0}, {"label": "已启用规则", "value": 0}, {"label": "待校验规则", "value": 0}]

const router = useRouter()
const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

// ---- 候选定位状态 ----
const sourceUrl = ref('')
const pageSize = ref(10)
const locatorLoading = ref(false)
const locatorError = ref('')
const sessionExpired = ref(false)
const searchId = ref('')
const result = ref<SearchResult | null>(null)
const expandedIds = ref<Set<number>>(new Set())
const semantics = ref<Record<string, any> | null>(null)
const showSemantics = ref(false)
const benchmark = ref<Benchmark | null>(null)
const benchLoading = ref(false)

function resetLocator() {
  searchId.value = ''
  result.value = null
  locatorError.value = ''
  sessionExpired.value = false
  expandedIds.value = new Set()
}

async function startSearch(page: number) {
  const url = sourceUrl.value.trim()
  if (!url) {
    locatorError.value = '请先输入来源 URL 再发起检索'
    return
  }
  locatorLoading.value = true
  locatorError.value = ''
  sessionExpired.value = false
  try {
    const response = await request(`${LOCATOR}/searches`, {
      method: 'POST',
      body: JSON.stringify({ sourceUrl: url, page, size: pageSize.value }),
    })
    if (!response.ok) {
      const detail = await readDetail(response)
      throw new Error(detail)
    }
    const payload = (await response.json()) as SearchResult
    result.value = payload
    searchId.value = payload.searchId
    expandedIds.value = new Set()
  } catch (error) {
    locatorError.value = error instanceof Error ? error.message : '候选检索失败'
  } finally {
    locatorLoading.value = false
  }
}

async function turnPage(page: number) {
  if (!searchId.value) {
    return
  }
  locatorLoading.value = true
  locatorError.value = ''
  try {
    const query = new URLSearchParams({ page: String(page), size: String(pageSize.value) })
    const response = await request(`${LOCATOR}/searches/${searchId.value}/pages?${query}`)
    if (response.status === 410) {
      sessionExpired.value = true
      throw new Error('检索会话已过期或不存在，请重新输入来源 URL 发起检索，系统不会悄悄切换候选集合')
    }
    if (!response.ok) {
      throw new Error(await readDetail(response))
    }
    result.value = (await response.json()) as SearchResult
  } catch (error) {
    locatorError.value = error instanceof Error ? error.message : '候选翻页失败'
  } finally {
    locatorLoading.value = false
  }
}

function toggleExplain(taskId: number) {
  const next = new Set(expandedIds.value)
  if (next.has(taskId)) {
    next.delete(taskId)
  } else {
    next.add(taskId)
  }
  expandedIds.value = next
}

function openCollector(item: Candidate) {
  const taskId = item['采集任务id']
  // 跳到采集引擎页并带上任务 id，采集页可据此高亮/定位真实目标。
  void router.push({ path: '/collector', query: { taskId: String(taskId) } })
}

async function runBenchmark() {
  benchLoading.value = true
  try {
    const response = await request(`${LOCATOR}/benchmark?candidateTarget=120`, { method: 'POST' })
    if (!response.ok) {
      throw new Error(await readDetail(response))
    }
    benchmark.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '基准对照运行失败'
  } finally {
    benchLoading.value = false
  }
}

async function loadSemantics() {
  try {
    const response = await request(`${LOCATOR}/semantics`)
    if (response.ok) {
      semantics.value = await response.json()
    }
  } catch {
    // 口径说明是辅助信息，加载失败不阻塞主流程。
  }
}

async function readDetail(response: Response): Promise<string> {
  try {
    const payload = await response.json()
    return String(payload.detail ?? '候选定位接口返回异常')
  } catch {
    return `候选定位接口返回 ${response.status}`
  }
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '分发规则登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('链路分发动作未生效，请稍后重试')
    }
    await reload()
    // 配置变更后若存在进行中的检索，刷新当前页以拿到 stale 标记，但仍绑定原快照版本。
    const current = result.value
    if (searchId.value && current) {
      await turnPage(current.page)
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '链路分发操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('分发规则列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '链路分发列表读取失败'
  }
}

onMounted(() => {
  void reload()
  void loadSemantics()
})
</script>
