import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { BumpActivityTimeline, BumpPerformanceSummary, JobScheduleEditor } from './BumpPerformance.jsx'

const metric = (value, source = 'observed', available = true) => ({ value, source, available })

describe('shared bump performance components', () => {
  it('renders missing current reply data as unknown rather than zero', () => {
    render(<BumpPerformanceSummary data={{ freshness:{thread_observed_at:null}, current_period:{replies_since_latest_bump:metric(null,'observed',false),contracts_opened:metric(0)}, metrics:{} }} />)
    expect(screen.getByText('Replies since latest bump').parentElement).toHaveTextContent('Unknown')
  })

  it('renders quiet groups and explicit pagination', () => {
    const onPage = vi.fn()
    render(<BumpActivityTimeline data={{ activity:[{kind:'quiet_group',count:17,start_ts:1,end_ts:2,summary:'No replies or contract activity'}], pagination:{page:1,total_pages:2,has_previous:false,has_next:true} }} onPage={onPage} />)
    expect(screen.getByText('17 successful bumps')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'Next'}))
    expect(onPage).toHaveBeenCalledWith(2)
  })

  it('keeps thread identity immutable while saving schedule fields', () => {
    const onSave = vi.fn()
    render(<JobScheduleEditor job={{tid:'6319077',fid:'107',thread_title:'Sales thread',mode:'timer',interval_h:12,enabled:true,bump_until:null}} onSave={onSave} onCancel={()=>{}} />)
    expect(screen.queryByRole('textbox',{name:/Thread/})).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Mode'),{target:{value:'page1'}})
    fireEvent.click(screen.getByRole('button',{name:'Save schedule'}))
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({mode:'page1',interval_h:12,enabled:true}))
    expect(onSave.mock.calls[0][0]).not.toHaveProperty('tid')
  })

  it('uses a compact accessible switch instead of a native checkbox', () => {
    render(<JobScheduleEditor job={{tid:'6319077',fid:'107',thread_title:'Sales thread',mode:'timer',interval_h:12,enabled:true,bump_until:null}} onSave={()=>{}} onCancel={()=>{}} />)
    const toggle = screen.getByRole('switch', { name:'Scheduler enabled' })
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(toggle).toHaveAttribute('aria-checked', 'true')
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-checked', 'false')
    expect(toggle).toHaveTextContent('Paused')
  })
})
