<script setup>
import { ref, computed } from 'vue'
import axios from 'axios'
import ScoreGauge from './components/ScoreGauge.vue'
import CategoryChart from './components/CategoryChart.vue'

const url = ref('')
const useAi = ref(true)
const loading = ref(false)
const error = ref('')
const result = ref(null)

const sevLabel = { high: '高风险', medium: '中风险', low: '低风险', info: '提示' }
const sevColor = { high: '#e5484d', medium: '#f5a524', low: '#30a46c', info: '#8b8b8b' }
const topRisks = computed(() => result.value?.findings?.slice(0, 20) || [])

async function analyze() {
  error.value = ''
  result.value = null
  if (!url.value.trim()) { error.value = '请输入 GitHub 仓库链接'; return }
  loading.value = true
  try {
    const { data } = await axios.post('/api/analyze', { repo_url: url.value.trim(), use_ai: useAi.value }, { timeout: 200000 })
    result.value = data
  } catch (e) {
    error.value = e.response?.data?.detail || e.message || '请求失败'
  } finally {
    loading.value = false
  }
}
function openReport() {
  if (result.value?.report_id) window.open(`/api/report/${result.value.report_id}`, '_blank')
}
</script>

<template>
  <div class="page">
    <header>
      <h1>Git 仓库接入体检</h1>
      <p>输入公开 GitHub 仓库链接，自动识别接入风险并生成就绪度评分</p>
    </header>

    <section class="card input-card">
      <div class="input-row">
        <input v-model="url" placeholder="https://github.com/owner/repo" @keyup.enter="analyze"
               :disabled="loading" spellcheck="false" />
        <label class="ai-toggle"><input type="checkbox" v-model="useAi" :disabled="loading" /> AI 建议</label>
        <button @click="analyze" :disabled="loading">{{ loading ? '分析中…' : '开始体检' }}</button>
      </div>
      <div v-if="error" class="error">{{ error }}</div>
      <div class="hint">检测项：完整度 15 · Windows 脚本 25 · 硬编码路径 20 · 密钥敏感 40 ｜ 得分 &gt; 80 视为接入就绪</div>
    </section>

    <div v-if="loading" class="loading">
      <div class="spinner"></div>
      <p>正在克隆仓库并执行静态扫描，请稍候（通常 10–40 秒）…</p>
    </div>

    <template v-if="result">
      <div class="result-head">
        <div>
          <h2>{{ result.repo_name }}</h2>
          <a :href="result.repo_url" target="_blank" rel="noopener">{{ result.repo_url }}</a>
          <span class="meta">扫描 {{ result.scanned_files }} 个文件 ｜ {{ result.generated_at }}</span>
        </div>
        <button class="ghost" @click="openReport">📄 打开完整报告页</button>
      </div>

      <div class="grid">
        <section class="card gauge-card">
          <h3>接入就绪度</h3>
          <ScoreGauge :score="result.total_score" :threshold="result.threshold" />
          <div class="threshold">就绪阈值：&gt; {{ result.threshold }} 分</div>
        </section>
        <section class="card chart-card">
          <h3>分类得分</h3>
          <CategoryChart :categories="result.categories" />
        </section>
      </div>

      <section class="card" v-if="result.ai.enabled">
        <h3>AI 接入建议 <span class="tag">DeepSeek · {{ result.ai.score }}/100</span></h3>
        <p class="summary">{{ result.ai.summary }}</p>
        <ol class="suggestions"><li v-for="(s, i) in result.ai.suggestions" :key="i">{{ s }}</li></ol>
      </section>
      <section class="card muted" v-else-if="result.ai.error">
        <h3>AI 建议</h3><p class="sub">{{ result.ai.error }}</p>
      </section>

      <section class="card">
        <h3>主要风险清单 <span class="tag">{{ result.findings.length }} 项</span></h3>
        <div class="table-wrap">
          <table>
            <thead><tr><th>等级</th><th>类别</th><th>文件</th><th>问题</th><th>证据</th></tr></thead>
            <tbody>
              <tr v-for="(f, i) in topRisks" :key="i">
                <td><span class="badge" :style="{background: sevColor[f.severity]}">{{ sevLabel[f.severity] }}</span></td>
                <td>{{ f.category }}</td>
                <td class="path">{{ f.file }}<template v-if="f.line">:{{ f.line }}</template></td>
                <td>{{ f.message }}</td>
                <td class="snippet">{{ f.snippet }}</td>
              </tr>
              <tr v-if="!topRisks.length"><td colspan="5" class="empty">未检出明显风险项</td></tr>
            </tbody>
          </table>
        </div>
        <div v-if="result.findings.length > 20" class="sub">仅展示前 20 项，完整清单见报告页。</div>
      </section>
    </template>

    <footer>自动化静态扫描结果仅供辅助判断，密钥风险请人工复核。</footer>
  </div>
</template>

<style scoped>
.page { max-width: 1120px; margin: 0 auto; padding: 40px 24px 80px; }
header h1 { font-size: 28px; margin: 0 0 6px; }
header p, .sub, .hint, .meta { color: #8b949e; font-size: 13px; }
.card { background: #171a21; border: 1px solid #262b36; border-radius: 12px; padding: 22px; margin-top: 18px; }
h2 { font-size: 20px; margin: 0 0 6px; } h3 { font-size: 16px; margin: 0 0 14px; }
.input-row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
input[type=text], input:not([type]) { flex: 1; min-width: 280px; background: #0f1115; border: 1px solid #30363d;
  color: #e6e6e6; padding: 12px 14px; border-radius: 8px; font-size: 14px; outline: none; }
input:focus { border-color: #5b8def; }
.ai-toggle { color: #c9d1d9; font-size: 13px; white-space: nowrap; }
button { background: #5b8def; color: #fff; border: none; padding: 12px 22px; border-radius: 8px;
  font-size: 14px; font-weight: 600; cursor: pointer; }
button:disabled { opacity: .6; cursor: not-allowed; }
button.ghost { background: transparent; border: 1px solid #30363d; color: #c9d1d9; font-weight: 500; }
.error { color: #ff7b72; margin-top: 12px; font-size: 13px; }
.hint { margin-top: 12px; }
.loading { text-align: center; padding: 60px; color: #8b949e; }
.spinner { width: 36px; height: 36px; margin: 0 auto 16px; border: 3px solid #262b36;
  border-top-color: #5b8def; border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.result-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-top: 28px; }
.result-head a { font-size: 13px; }
.result-head .meta { display: block; margin-top: 6px; }
.grid { display: grid; grid-template-columns: 1fr 1.4fr; gap: 18px; }
.gauge-card { text-align: center; } .threshold { color: #8b949e; font-size: 13px; }
.tag { font-size: 12px; color: #8b949e; font-weight: 400; }
.summary { color: #c9d1d9; } .suggestions { color: #c9d1d9; padding-left: 22px; }
.suggestions li { margin: 6px 0; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { padding: 9px 10px; text-align: left; border-bottom: 1px solid #232833; vertical-align: top; }
th { color: #8b949e; }
.badge { color: #0f1115; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; white-space: nowrap; }
.path, .snippet { font-family: Consolas, monospace; word-break: break-all; }
.path { color: #79c0ff; } .snippet { color: #a0a8b5; max-width: 320px; }
.empty { text-align: center; color: #8b949e; padding: 24px; }
.muted { color: #8b949e; }
footer { text-align: center; color: #6e7681; font-size: 12px; margin-top: 40px; }
@media (max-width: 800px) { .grid { grid-template-columns: 1fr; } }
</style>
