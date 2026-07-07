import { defineStore } from 'pinia'

export type RequestStatus = 'pending' | 'confirmed' | 'completed'

export interface MaintenanceRequest {
  id: string
  vesselId: string
  vesselName: string
  requestedDate: string
  port: string
  note: string
  notifyTeam: boolean
  status: RequestStatus
  createdAt: string
}

let counter = 0

export const useMaintenanceRequestStore = defineStore('maintenanceRequests', {
  state: () => ({
    requests: [] as MaintenanceRequest[]
  }),
  actions: {
    createRequest(input: Omit<MaintenanceRequest, 'id' | 'status' | 'createdAt'>): MaintenanceRequest {
      counter += 1
      const request: MaintenanceRequest = {
        ...input,
        id: `REQ-${new Date().getFullYear()}-${String(counter).padStart(3, '0')}`,
        status: 'pending',
        createdAt: new Date().toISOString()
      }
      this.requests.unshift(request)
      return request
    },
    advanceStatus(id: string) {
      const req = this.requests.find((r) => r.id === id)
      if (!req) return
      if (req.status === 'pending') req.status = 'confirmed'
      else if (req.status === 'confirmed') req.status = 'completed'
    }
  }
})
