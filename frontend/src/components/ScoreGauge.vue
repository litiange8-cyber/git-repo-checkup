<script setup>
import { ref, onMounted, watch, onBeforeUnmount } from 'vue'
import echarts from '../echarts'

const props = defineProps({ score: { type: Number, default: 0 }, threshold: { type: Number, default: 80 } })
const el = ref(null)
let chart = null

function render() {
  if (!chart) chart = echarts.init(el.value)
  const color = props.score > props.threshold ? '#30a46c' : '#e5484d'
  chart.setOption({
    series: [{
      type: 'gauge', startAngle: 210, endAngle: -30, min: 0, max: 100,
      center: ['50%', '62%'], radius: '92%',
      progress: { show: true, width: 16, itemStyle: { color } },
      axisLine: { lineStyle: { width: 16, color: [[1, '#262b36']] } },
      axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false },
      pointer: { show: false }, anchor: { show: false },
      title: { show: true, offsetCenter: [0, '32%'], color: '#8b949e', fontSize: 13 },
      detail: { valueAnimation: true, fontSize: 52, fontWeight: 700, color, offsetCenter: [0, '-2%'],
                formatter: '{value}' },
      data: [{ value: props.score, name: props.score > props.threshold ? '接入就绪' : '未达就绪' }]
    }]
  }, true)
}
onMounted(render)
watch(() => props.score, render)
onBeforeUnmount(() => chart?.dispose())
</script>
<template><div ref="el" style="width:100%;height:230px"></div></template>
