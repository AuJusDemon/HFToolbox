import { prefetchProgram } from '../../system/programRegistry.js'

export default function HeroProgramBus({ runtime }) {
  return (
    <section className={`hero-program-bus${runtime.pulseProgramId ? ' is-routing' : ''}${runtime.activeProgramId ? ' has-selection' : ''}`} aria-label="Toolbox programs">
      <header><span>PROGRAM BUS</span><b>{runtime.heroPrograms.length} MOUNTED</b></header>
      <div className="hero-bus-route" aria-hidden="true"><i /></div>
      <div className="hero-program-grid">
        {runtime.heroPrograms.map((program, index) => {
          const unavailable = program.availability !== 'available'
          const active = runtime.activeProgramId === program.id
          const pulsing = runtime.pulseProgramId === program.id
          return <button key={program.id} type="button" style={{ '--program-index': index }} className={`${active ? 'is-active ' : ''}${pulsing ? 'is-pulsing' : ''}`.trim()} aria-pressed={active} disabled={!runtime.ready || runtime.interactionState !== 'idle'} onClick={() => runtime.selectProgram(program)} onMouseEnter={() => { runtime.setActiveProgramId(program.id); prefetchProgram(program) }} onMouseLeave={() => runtime.setActiveProgramId('')} onFocus={() => { runtime.setActiveProgramId(program.id); prefetchProgram(program) }} onBlur={() => runtime.setActiveProgramId('')}>
            <span>{String(index + 1).padStart(2, '0')}</span>
            <strong>{program.label}</strong>
            <small>{unavailable ? 'COMING SOON' : `OPEN ${program.command.toUpperCase()}`}</small>
          </button>
        })}
      </div>
    </section>
  )
}
