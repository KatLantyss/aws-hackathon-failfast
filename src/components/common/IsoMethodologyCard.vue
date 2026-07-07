<script setup lang="ts">
const windCorrectionTable = [
  { scale: '0–2', desc: '無風／輕風', factor: 1.0 },
  { scale: '3–4', desc: '微風／和風（本系統採用門檻內）', factor: 1.02 },
  { scale: '5–6', desc: '清風／強風（已於前處理過濾）', factor: 1.08 },
  { scale: '7+', desc: '大風以上（已於前處理過濾）', factor: 1.15 }
]
</script>

<template>
  <div class="text-body-2 mb-4">
    <div class="text-subtitle-2 font-weight-medium mb-2">1. 資料前處理</div>
    <div class="d-flex align-center ga-2 mb-1">
      <v-icon icon="mdi-check-circle-outline" size="16" color="secondary" />
      <span>僅採用 <code>WIND_SCALE ≤ 4</code> 且 <code>HOURS_FULL_SPEED ≥ 22h</code> 的午報紀錄，排除極端海況造成的建模誤差</span>
    </div>
    <div class="d-flex align-center ga-2">
      <v-icon icon="mdi-check-circle-outline" size="16" color="secondary" />
      <span>燃油統一以 VLSFO 當量換算（LCV 加權），避免混燒不同燃料造成的耗油量偏差</span>
    </div>
  </div>

  <div class="text-body-2 mb-4">
    <div class="text-subtitle-2 font-weight-medium mb-2">2. Daily FOC 計算</div>
    <div class="d-flex align-center ga-2">
      <v-icon icon="mdi-check-circle-outline" size="16" color="secondary" />
      <span>Daily FOC = ME_FULLSPEED_CONSUMP_VLSFO ÷ HOURS_FULL_SPEED × 24</span>
    </div>
  </div>

  <div class="text-body-2 mb-4">
    <div class="text-subtitle-2 font-weight-medium mb-2">
      3. Speed Loss 量測方法
      <v-chip size="x-small" color="warning" variant="tonal" class="ml-2">Demo 簡化版</v-chip>
    </div>
    <p class="text-medium-emphasis mb-2">
      概念上參考 <strong>ISO 19030</strong>（船體與螺旋槳效能量測標準）的量測邏輯：以上次水下清潔後 60 天內的午報資料擬合「乾淨船體基準功率-航速曲線」，之後每日以同航速下的實際主機功率需求，對比基準曲線計算偏差百分比，即為 Speed Loss。
    </p>
    <p class="text-medium-emphasis">
      航行修正部分概念上參考 <strong>ISO 15016</strong>（船舶試航修正標準）的風阻／浪阻修正思路，下表為 Demo 使用的簡化風力修正係數（非正式 ISO 數值）：
    </p>
    <v-table density="compact" class="mt-2 wind-table">
      <thead>
        <tr>
          <th>Beaufort 風力等級</th>
          <th>說明</th>
          <th>修正係數（Demo）</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in windCorrectionTable" :key="row.scale">
          <td>{{ row.scale }}</td>
          <td class="text-medium-emphasis">{{ row.desc }}</td>
          <td>{{ row.factor.toFixed(2) }}</td>
        </tr>
      </tbody>
    </v-table>
  </div>

  <v-alert type="warning" variant="tonal" density="compact" icon="mdi-alert-outline">
    本頁計算方法為 Demo 簡化實作與示範係數，用於呈現分析邏輯與 Web Dashboard 呈現方式；正式 ISO 15016 / ISO 19030 條文內容、修正係數與適用版本，待節能小組提供後覆核更新。
  </v-alert>
</template>

<style scoped>
.wind-table {
  background: transparent;
}
</style>
