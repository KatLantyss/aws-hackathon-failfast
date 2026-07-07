<script setup lang="ts">
import { computed } from 'vue'
import { useMaintenanceRequestStore, type RequestStatus } from '@/stores/maintenanceRequestStore'
import StatCard from '@/components/common/StatCard.vue'

const store = useMaintenanceRequestStore()

const counts = computed(() => ({
  pending: store.requests.filter((r) => r.status === 'pending').length,
  confirmed: store.requests.filter((r) => r.status === 'confirmed').length,
  completed: store.requests.filter((r) => r.status === 'completed').length
}))

const statusLabel: Record<RequestStatus, string> = { pending: '待確認', confirmed: '已確認排程', completed: '已完成' }
const statusColor: Record<RequestStatus, string> = { pending: 'warning', confirmed: 'primary', completed: 'secondary' }
const nextActionLabel: Record<RequestStatus, string> = { pending: '確認排程', confirmed: '標記完成', completed: '' }
</script>

<template>
  <div class="pa-6">
    <div class="d-flex flex-wrap ga-4 mb-4">
      <div style="flex: 1; min-width: 180px">
        <StatCard icon="mdi-clock-outline" label="待確認" :value="counts.pending" suffix="件" color="warning" />
      </div>
      <div style="flex: 1; min-width: 180px">
        <StatCard icon="mdi-calendar-check-outline" label="已確認排程" :value="counts.confirmed" suffix="件" color="primary" />
      </div>
      <div style="flex: 1; min-width: 180px">
        <StatCard icon="mdi-check-circle-outline" label="已完成" :value="counts.completed" suffix="件" color="secondary" />
      </div>
    </div>

    <v-sheet rounded color="card" class="pa-4" elevation="0">
      <div class="text-subtitle-2 mb-3">水下清潔申請追蹤</div>
      <v-table density="comfortable">
        <thead>
          <tr>
            <th>申請編號</th>
            <th>船名</th>
            <th>建議日期</th>
            <th>靠港地點</th>
            <th>狀態</th>
            <th>備註</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in store.requests" :key="r.id">
            <td>{{ r.id }}</td>
            <td>{{ r.vesselName }}</td>
            <td>{{ r.requestedDate }}</td>
            <td>{{ r.port }}</td>
            <td><v-chip size="small" :color="statusColor[r.status]" variant="tonal">{{ statusLabel[r.status] }}</v-chip></td>
            <td class="text-medium-emphasis">{{ r.note || '—' }}</td>
            <td>
              <v-btn v-if="r.status !== 'completed'" size="small" variant="text" @click="store.advanceStatus(r.id)">
                {{ nextActionLabel[r.status] }}
              </v-btn>
            </td>
          </tr>
          <tr v-if="!store.requests.length">
            <td colspan="7" class="text-center text-medium-emphasis py-8">
              尚無維修申請，可從「船隊總覽」點選船舶後，於維修排程建議卡片建立申請
            </td>
          </tr>
        </tbody>
      </v-table>
    </v-sheet>
  </div>
</template>
