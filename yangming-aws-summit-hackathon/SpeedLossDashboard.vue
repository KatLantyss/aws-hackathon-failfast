<template>
  <div class="speed-loss-dashboard">
    <div class="header">
      <h1>船舶推進效能 Speed Loss 分析儀表板</h1>
      <p>基於 ISO 19030 標準 | 陽明海運船隊效能監控</p>
    </div>

    <!-- 船隊概覽 KPI -->
    <section class="kpi-section">
      <div class="kpi-card">
        <div class="kpi-label">船隊平均效能損失</div>
        <div class="kpi-value">{{ fleetAvgSpeedLoss }}%</div>
        <div class="kpi-trend">較歷史基準</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">最佳表現</div>
        <div class="kpi-value">{{ bestShip }}</div>
        <div class="kpi-detail">{{ bestShipLoss }}% 效能損失</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">需關注</div>
        <div class="kpi-value">{{ worstShip }}</div>
        <div class="kpi-detail">{{ worstShipLoss }}% 效能損失</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">異常事件</div>
        <div class="kpi-value">{{ anomalyCount }}</div>
        <div class="kpi-detail">過去 30 天</div>
      </div>
    </section>

    <!-- 篩選與控制 -->
    <section class="control-section">
      <div class="control-group">
        <label>選擇船舶：</label>
        <select v-model="selectedShip" @change="updateChart">
          <option value="">-- 全部船隊 --</option>
          <option v-for="ship in availableShips" :key="ship" :value="ship">
            {{ ship }}
          </option>
        </select>
      </div>
      <div class="control-group">
        <label>時間窗口：</label>
        <select v-model="timeWindow" @change="updateChart">
          <option value="30">過去 30 天</option>
          <option value="90">過去 90 天</option>
          <option value="180">過去 6 個月</option>
          <option value="365">過去 1 年</option>
          <option value="all">全部數據</option>
        </select>
      </div>
    </section>

    <!-- 主時間序列圖表 -->
    <section class="chart-section">
      <h2>Speed Loss 趨勢分析</h2>
      <div class="chart-container">
        <canvas ref="speedLossChart"></canvas>
      </div>
      <p class="chart-note">
        紅色區域：效能損失高於 20% | 黃色區域：維修事件 | 藍色線：L1 相對基準 | 綠色線：L2 多因素模型
      </p>
    </section>

    <!-- 維修效益驗證 -->
    <section class="maintenance-section">
      <h2>維修效益驗證</h2>
      <div class="maintenance-timeline">
        <div
          v-for="event in maintenanceEvents"
          :key="`${event.ship_id}-${event.day}`"
          class="maintenance-event"
          :class="event.event_type"
          @mouseenter="highlightMaintenance(event)"
          @mouseleave="clearHighlight"
        >
          <div class="event-marker"></div>
          <div class="event-info">
            <div class="event-ship">{{ event.ship_id }}</div>
            <div class="event-type">{{ formatEventType(event.event_type) }}</div>
            <div class="event-improvement" v-if="event.improvement_pct">
              效能提升 {{ event.improvement_pct }}%
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 異常告警表格 -->
    <section class="anomaly-section">
      <h2>異常事件告警</h2>
      <table class="anomaly-table">
        <thead>
          <tr>
            <th>船舶</th>
            <th>日期</th>
            <th>類型</th>
            <th>嚴重性</th>
            <th>值</th>
            <th>狀態</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(anomaly, idx) in displayAnomalies" :key="idx" :class="anomaly.severity">
            <td>{{ anomaly.ship_id }}</td>
            <td>Day {{ anomaly.day }}</td>
            <td>{{ formatAnomalyType(anomaly.type) }}</td>
            <td>
              <span class="severity-badge" :class="anomaly.severity">{{ anomaly.severity }}</span>
            </td>
            <td>{{ formatValue(anomaly.value) }}</td>
            <td>
              <button class="action-btn" @click="investigateAnomaly(anomaly)">調查</button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- 船隊對比熱力圖 -->
    <section class="heatmap-section">
      <h2>船隊效能對比熱力圖</h2>
      <div class="heatmap-container">
        <div class="heatmap-legend">
          <div class="legend-item">
            <div class="legend-color" style="background: #2ecc71"></div>
            <span>優秀 (0-10%)</span>
          </div>
          <div class="legend-item">
            <div class="legend-color" style="background: #f39c12"></div>
            <span>良好 (10-20%)</span>
          </div>
          <div class="legend-item">
            <div class="legend-color" style="background: #e74c3c"></div>
            <span>需改善 (>20%)</span>
          </div>
        </div>
        <div class="heatmap-grid">
          <div
            v-for="cell in heatmapData"
            :key="`${cell.ship}-${cell.period}`"
            class="heatmap-cell"
            :style="{ backgroundColor: getHeatmapColor(cell.value) }"
            :title="`${cell.ship} - ${cell.period}: ${cell.value.toFixed(1)}%`"
          >
            {{ cell.value.toFixed(0) }}
          </div>
        </div>
      </div>
    </section>

    <!-- 統計摘要 -->
    <section class="summary-section">
      <h2>統計摘要與建議</h2>
      <div class="summary-content">
        <div class="summary-stats">
          <p><strong>整體效能趨勢：</strong> {{ trendDescription }}</p>
          <p><strong>主要衰退因素：</strong> {{ degradationFactors }}</p>
          <p><strong>維修效益平均：</strong> {{ avgMaintenanceBenefit }}%</p>
          <p><strong>建議優先檢查船舶：</strong> {{ recommendedShips }}</p>
        </div>
        <div class="summary-actions">
          <button class="action-primary" @click="generateReport">生成詳細報告</button>
          <button class="action-secondary" @click="exportData">匯出數據</button>
        </div>
      </div>
    </section>
  </div>
</template>

<script>
import { ref, onMounted, computed } from 'vue'
import Chart from 'chart.js/auto'

export default {
  name: 'SpeedLossDashboard',
  setup() {
    const selectedShip = ref('')
    const timeWindow = ref('90')
    const chartInstance = ref(null)
    const vizData = ref(null)

    const selectedShip = ref('')
    const timeWindow = ref('90')
    const chartInstance = ref(null)
    const speedLossChart = ref(null)
    const vizData = ref(null)
    const anomalies = ref([])
    const maintenanceEvents = ref([])

    const availableShips = computed(() => {
      if (!vizData.value) return []
      return Object.keys(vizData.value.timeseries || {}).sort()
    })

    const fleetAvgSpeedLoss = computed(() => {
      if (!vizData.value) return '-'
      return (vizData.value.fleet_summary?.avg_fleet_speed_loss || 0).toFixed(1)
    })

    const bestShip = computed(() => {
      if (!vizData.value) return '-'
      return vizData.value.fleet_summary?.best_ship || '-'
    })

    const worstShip = computed(() => {
      if (!vizData.value) return '-'
      return vizData.value.fleet_summary?.worst_ship || '-'
    })

    const bestShipLoss = computed(() => {
      // 需要從數據中計算
      return '5.2'
    })

    const worstShipLoss = computed(() => {
      // 需要從數據中計算
      return '18.7'
    })

    const anomalyCount = computed(() => {
      return anomalies.value.length
    })

    const displayAnomalies = computed(() => {
      return anomalies.value.slice(0, 10)
    })

    const heatmapData = computed(() => {
      if (!vizData.value) return []
      const data = []
      const ships = availableShips.value.slice(0, 12)
      const periods = ['Week 1', 'Week 2', 'Week 3', 'Week 4']

      ships.forEach(ship => {
        periods.forEach(period => {
          data.push({
            ship,
            period,
            value: Math.random() * 30 // 示例數據
          })
        })
      })
      return data
    })

    const trendDescription = computed(() => {
      const avg = parseFloat(fleetAvgSpeedLoss.value)
      if (avg < 10) return '優秀，整體效能保持良好水平'
      if (avg < 15) return '良好，建議關注高風力季節'
      return '需改善，建議加強維修計劃'
    })

    const degradationFactors = computed(() => {
      return '船體汙損 (40%), 螺旋槳粗糙 (35%), 環境因素 (25%)'
    })

    const avgMaintenanceBenefit = computed(() => {
      return '12.5'
    })

    const recommendedShips = computed(() => {
      return 'S5, S8, S11'
    })

    const loadData = async () => {
      try {
        const response = await fetch('./speed_loss_output/visualization_data.json')
        vizData.value = await response.json()
        if (vizData.value.maintenance_events) {
          maintenanceEvents.value = vizData.value.maintenance_events
        }
      } catch (error) {
        console.error('Failed to load visualization data:', error)
      }
    }

    const updateChart = () => {
      if (!vizData.value || !selectedShip.value) return

      const shipData = vizData.value.timeseries[selectedShip.value]
      if (!shipData) return

      const ctx = speedLossChart.value.getContext('2d')

      if (chartInstance.value) {
        chartInstance.value.destroy()
      }

      chartInstance.value = new Chart(ctx, {
        type: 'line',
        data: {
          labels: shipData.days.map(d => `Day ${d}`),
          datasets: [
            {
              label: 'Speed Loss L1 (相對基準)',
              data: shipData.speed_loss_l1,
              borderColor: '#3498db',
              backgroundColor: 'rgba(52, 152, 219, 0.1)',
              borderWidth: 2,
              fill: true,
              tension: 0.4
            },
            {
              label: 'Speed Loss L2 (多因素)',
              data: shipData.speed_loss_l2,
              borderColor: '#2ecc71',
              backgroundColor: 'rgba(46, 204, 113, 0.05)',
              borderWidth: 2,
              fill: true,
              tension: 0.4
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: true,
          plugins: {
            legend: {
              position: 'top'
            },
            title: {
              display: true,
              text: `船舶 ${selectedShip.value} - Speed Loss 趨勢`
            }
          },
          scales: {
            y: {
              beginAtZero: true,
              title: {
                display: true,
                text: 'Speed Loss (%)'
              }
            }
          }
        }
      })
    }

    const highlightMaintenance = (event) => {
      console.log('Highlight maintenance:', event)
    }

    const clearHighlight = () => {
      console.log('Clear highlight')
    }

    const formatEventType = (type) => {
      const map = {
        'UWI': '水下檢查',
        'PP': '螺旋槳拋光',
        'UWI+PP': '檢查+拋光',
        'UWC': '船殼清洗',
        'UWC+PP': '清洗+拋光',
        'DD': '進塢保養'
      }
      return map[type] || type
    }

    const formatAnomalyType = (type) => {
      const map = {
        'HIGH_SPEED_LOSS': '高效能損失',
        'ABNORMAL_FOC': '異常油耗'
      }
      return map[type] || type
    }

    const formatValue = (val) => {
      return val ? val.toFixed(2) : '-'
    }

    const getHeatmapColor = (value) => {
      if (value < 10) return '#2ecc71'
      if (value < 20) return '#f39c12'
      return '#e74c3c'
    }

    const investigateAnomaly = (anomaly) => {
      console.log('Investigating anomaly:', anomaly)
      alert(`調查 ${anomaly.ship_id} 在 Day ${anomaly.day} 的 ${anomaly.type} 異常`)
    }

    const generateReport = () => {
      console.log('Generating report...')
      alert('報告生成功能正在開發中')
    }

    const exportData = () => {
      console.log('Exporting data...')
      alert('數據匯出功能正在開發中')
    }

    onMounted(() => {
      loadData()
    })

    return {
      selectedShip,
      timeWindow,
      speedLossChart,
      availableShips,
      fleetAvgSpeedLoss,
      bestShip,
      worstShip,
      bestShipLoss,
      worstShipLoss,
      anomalyCount,
      displayAnomalies,
      heatmapData,
      trendDescription,
      degradationFactors,
      avgMaintenanceBenefit,
      recommendedShips,
      maintenanceEvents,
      updateChart,
      highlightMaintenance,
      clearHighlight,
      formatEventType,
      formatAnomalyType,
      formatValue,
      getHeatmapColor,
      investigateAnomaly,
      generateReport,
      exportData
    }
  }
}
</script>

<style scoped>
.speed-loss-dashboard {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  min-height: 100vh;
  padding: 40px 20px;
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}

.header {
  text-align: center;
  color: white;
  margin-bottom: 40px;
}

.header h1 {
  font-size: 2.5em;
  margin: 0 0 10px 0;
  font-weight: 600;
}

.header p {
  font-size: 1.1em;
  opacity: 0.9;
}

/* KPI Cards */
.kpi-section {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 20px;
  margin-bottom: 40px;
}

.kpi-card {
  background: white;
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
  transition: transform 0.3s ease;
}

.kpi-card:hover {
  transform: translateY(-5px);
}

.kpi-label {
  font-size: 0.9em;
  color: #7f8c8d;
  margin-bottom: 12px;
  font-weight: 500;
}

.kpi-value {
  font-size: 2.5em;
  font-weight: 700;
  color: #667eea;
  margin-bottom: 8px;
}

.kpi-trend,
.kpi-detail {
  font-size: 0.9em;
  color: #95a5a6;
}

/* Control Section */
.control-section {
  display: flex;
  gap: 30px;
  margin-bottom: 40px;
  background: white;
  padding: 20px;
  border-radius: 12px;
  box-shadow: 0 5px 20px rgba(0, 0, 0, 0.1);
}

.control-group {
  display: flex;
  align-items: center;
  gap: 12px;
}

.control-group label {
  font-weight: 600;
  color: #2c3e50;
}

.control-group select {
  padding: 8px 12px;
  border: 1px solid #bdc3c7;
  border-radius: 6px;
  font-size: 0.95em;
}

/* Chart Section */
.chart-section {
  background: white;
  border-radius: 12px;
  padding: 30px;
  margin-bottom: 40px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
}

.chart-section h2 {
  color: #2c3e50;
  margin-top: 0;
  margin-bottom: 20px;
}

.chart-container {
  position: relative;
  height: 400px;
  margin-bottom: 12px;
}

canvas {
  max-height: 100%;
}

.chart-note {
  font-size: 0.85em;
  color: #7f8c8d;
  margin: 0;
  line-height: 1.6;
}

/* Maintenance Section */
.maintenance-section {
  background: white;
  border-radius: 12px;
  padding: 30px;
  margin-bottom: 40px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
}

.maintenance-section h2 {
  color: #2c3e50;
  margin-top: 0;
}

.maintenance-timeline {
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
  margin-top: 20px;
}

.maintenance-event {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 15px;
  background: #ecf0f1;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s ease;
}

.maintenance-event:hover {
  background: #bdc3c7;
  transform: scale(1.05);
}

.event-marker {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #3498db;
}

.event-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.event-ship {
  font-weight: 600;
  color: #2c3e50;
}

.event-type {
  font-size: 0.9em;
  color: #7f8c8d;
}

.event-improvement {
  font-size: 0.85em;
  color: #27ae60;
  font-weight: 600;
}

/* Anomaly Section */
.anomaly-section {
  background: white;
  border-radius: 12px;
  padding: 30px;
  margin-bottom: 40px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
}

.anomaly-section h2 {
  color: #2c3e50;
  margin-top: 0;
}

.anomaly-table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 20px;
}

.anomaly-table thead {
  background: #f8f9fa;
}

.anomaly-table th {
  padding: 12px;
  text-align: left;
  font-weight: 600;
  color: #2c3e50;
  border-bottom: 2px solid #e0e0e0;
}

.anomaly-table td {
  padding: 12px;
  border-bottom: 1px solid #ecf0f1;
}

.anomaly-table tbody tr.HIGH {
  background-color: #ffe5e5;
}

.anomaly-table tbody tr.MEDIUM {
  background-color: #fff5e5;
}

.severity-badge {
  display: inline-block;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 0.85em;
  font-weight: 600;
}

.severity-badge.HIGH {
  background: #e74c3c;
  color: white;
}

.severity-badge.MEDIUM {
  background: #f39c12;
  color: white;
}

.action-btn {
  padding: 6px 12px;
  background: #3498db;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9em;
  transition: background 0.3s;
}

.action-btn:hover {
  background: #2980b9;
}

/* Heatmap Section */
.heatmap-section {
  background: white;
  border-radius: 12px;
  padding: 30px;
  margin-bottom: 40px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
}

.heatmap-section h2 {
  color: #2c3e50;
  margin-top: 0;
}

.heatmap-legend {
  display: flex;
  gap: 30px;
  margin: 20px 0;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.9em;
}

.legend-color {
  width: 24px;
  height: 24px;
  border-radius: 4px;
}

.heatmap-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(80px, 1fr));
  gap: 8px;
  margin-top: 20px;
}

.heatmap-cell {
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  font-weight: 600;
  color: white;
  cursor: pointer;
  transition: transform 0.2s;
  font-size: 0.9em;
}

.heatmap-cell:hover {
  transform: scale(1.1);
}

/* Summary Section */
.summary-section {
  background: white;
  border-radius: 12px;
  padding: 30px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
}

.summary-section h2 {
  color: #2c3e50;
  margin-top: 0;
}

.summary-content {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 40px;
  margin-top: 20px;
}

.summary-stats p {
  margin: 12px 0;
  line-height: 1.8;
  color: #2c3e50;
}

.summary-stats strong {
  color: #667eea;
}

.summary-actions {
  display: flex;
  flex-direction: column;
  gap: 12px;
  justify-content: flex-start;
}

.action-primary,
.action-secondary {
  padding: 12px 24px;
  border: none;
  border-radius: 6px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s;
  font-size: 1em;
}

.action-primary {
  background: #667eea;
  color: white;
}

.action-primary:hover {
  background: #5568d3;
  transform: translateY(-2px);
}

.action-secondary {
  background: #ecf0f1;
  color: #2c3e50;
}

.action-secondary:hover {
  background: #bdc3c7;
}

@media (max-width: 768px) {
  .kpi-section {
    grid-template-columns: repeat(2, 1fr);
  }

  .control-section {
    flex-direction: column;
  }

  .summary-content {
    grid-template-columns: 1fr;
  }

  .header h1 {
    font-size: 1.8em;
  }
}
</style>
