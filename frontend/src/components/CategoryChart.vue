<script setup>
import { ref, onMounted, watch, onBeforeUnmount } from 'vue'
import echarts from '../echarts'

const props = defineProps({ categories: { type: Array, default: () => [] } })
const el = ref(null)
let chart = null

function render() {
  if (!chart) chart = echarts.init(el.value)
  const cats = [...props.categories].reverse()
  chart.setOption({
    grid: { left: 130, right: 50, top: 16, bottom: 28 },
    xAxis: { type: 'value', max: 100, splitLine: { lineStyle: { color: '#232833' } },
             axisLabel: { color: '#8b949e' } },
    yAxis: { type: 'category', data: cats.map(c => c.name),
             axisLabel: { color: '#c9d1d9', fontSize: 12 }, axisLine: { show: false }, axisTick: { show: false } },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' },
               formatter: p => `${p[0].name}<br/>得分 ${p[0].value} / ${cats[p[0].dataIndex].max_score}` },
    series: [{
      type: 'bar', barWidth: 18,
      data: cats.map(c => ({ value: c.score, itemStyle: { color: c.score / c.max_score > 0.8 ? '#30a46c' : '#f5a524', borderRadius: [0, 4, 4, 0] } })),
      label: { show: true, position: 'right', color: '#c9d1d9', formatter: '{c}' }
    }]
  }, true)
}
onMounted(render)
watch(() => props.categories, render, { deep: true })
onBeforeUnmount(() => chart?.dispose())
</script>
<template><div ref="el" style="width:100%;height:220px"></div></template>
