export default function HeroRouteTransition({ state, target }) {
  const visible = state === 'resolving' || state === 'transfer'
  return (
    <div className={`hero-route-transition state-${state}`} aria-hidden={!visible}>
      <div className="hero-transfer-bars" aria-hidden="true">
        {Array.from({ length: 9 }, (_, index) => <i key={index} style={{ '--transfer-index': index }} />)}
      </div>
      <p><span>{state === 'transfer' ? 'TRANSFERRING' : 'RESOLVING ROUTE'}</span><b>{target}</b></p>
    </div>
  )
}
