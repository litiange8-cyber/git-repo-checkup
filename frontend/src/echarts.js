// ECharts 按需引入：仅注册用到的图表与组件，避免全量打包
import * as echarts from 'echarts/core'
import { GaugeChart, BarChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([GaugeChart, BarChart, GridComponent, TooltipComponent, CanvasRenderer])

export default echarts
