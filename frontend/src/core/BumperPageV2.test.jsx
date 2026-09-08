import { describe, expect, it } from 'vitest'
import { budgetState, classifyJob, orderJobs } from './BumperPageV2.jsx'

const job = (id, fields = {}) => ({ id, tid: String(id), enabled: true, expired: false, next_bump: id * 100, seconds_until_bump: 60, ...fields })

describe('Bump Service operational state', () => {
  it('orders failures, due, active, paused, and expired', () => {
    const jobs = [job(5, { expired: true }), job(4, { enabled: false }), job(3), job(2, { seconds_until_bump: 0 }), job(1)]
    const log = [{ id: 9, tid: '1', action: 'error', ts: 200 }]
    expect(orderJobs(jobs, log).map(item => item.id)).toEqual([1, 2, 3, 4, 5])
  })

  it('uses soonest attempt to order active jobs', () => {
    const jobs = [job(1, { next_bump: 400 }), job(2, { next_bump: 200 })]
    expect(orderJobs(jobs).map(item => item.id)).toEqual([2, 1])
  })

  it('marks enabled jobs blocked when the next bump exceeds budget', () => {
    expect(classifyJob(job(1), [], true)).toMatchObject({ key: 'blocked', rank: 1 })
  })

  it('prioritizes retired Page 1 jobs as action required', () => {
    expect(classifyJob(job(1, { mode:'page1', enabled:false, requires_schedule_update:true }))).toMatchObject({ key:'action', label:'Action required', rank:0 })
  })

  it('calculates unlimited and constrained budget states', () => {
    expect(budgetState({ weekly_budget: 0, bytes_this_week: 50, total_cost: 60 })).toMatchObject({ unlimited: true, remaining: null })
    expect(budgetState({ weekly_budget: 200, bytes_this_week: 150, total_cost: 60 })).toMatchObject({ exceeded: true, remaining: 50, remainingBumps: 0, percent: 75 })
  })
})
