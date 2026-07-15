<template>
  <div class="speed-loss-page">
    <div class="page-header">
      <h1>船舶推進效能 Speed Loss 分析</h1>
      <p class="subtitle">基於 ISO 19030 標準，實時監控船隊效能</p>
    </div>

    <div class="loading" v-if="loading">
      <p>⏳ 載入數據中...</p>
    </div>

    <div class="error" v-if="error">
      <p>❌ {{ error }}</p>
      <button @click="loadData">重試</button>
    </div>

    <SpeedLossDashboard v-if="!loading && !error" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import SpeedLossDashboard from '@/components/SpeedLossDashboard.vue'

const loading = ref(true)
const error = ref('')

const loadData = async () => {
  loading.value = true
  error.value = ''

  try {
    let data = null

    // 優先嘗試 API
    try {
      const apiResponse = await fetch('/api/speed-loss/visualization-data')
      if (apiResponse.ok) {
        const result = await apiResponse.json()
        data = result.data || result
        console.log('✅ 從 API 載入 Speed Loss 數據')
      }
    } catch (apiErr) {
      console.log('API 不可用，改用本地文件...')
    }

    // 方式 2：從 public/data 讀取本地文件（最可靠）
    if (!data) {
      try {
        const fileResponse = await fetch('/data/visualization_data.json')
        if (fileResponse.ok) {
          data = await fileResponse.json()
          console.log('✅ 從本地文件載入 Speed Loss 數據')
        } else {
          throw new Error(`HTTP ${fileResponse.status}`)
        }
      } catch (fileErr) {
        console.error('本地文件讀取失敗:', fileErr)
        error.value = `無法載入數據: ${fileErr.message}。請確認 speed_loss_pipeline.py 已運行。`
      }
    }

    if (data) {
      console.log('已載入 Speed Loss 數據', {
        fleet_summary: !!data.fleet_summary,
        timeseries_ships: Object.keys(data.timeseries || {}).length,
        maintenance_events: (data.maintenance_events || []).length
      })
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '未知錯誤'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.speed-loss-page {
  min-height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 20px;
}

.page-header {
  text-align: center;
  color: white;
  margin-bottom: 40px;
}

.page-header h1 {
  font-size: 2.5em;
  margin: 0 0 10px 0;
}

.subtitle {
  font-size: 1.1em;
  opacity: 0.9;
}

.loading,
.error {
  background: white;
  border-radius: 12px;
  padding: 40px;
  text-align: center;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
}

.error {
  background: #ffe5e5;
  color: #e74c3c;
}

.error button {
  margin-top: 20px;
  padding: 10px 20px;
  background: #e74c3c;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
}

.error button:hover {
  background: #c0392b;
}
</style>