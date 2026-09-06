const BOOT_MESSAGES = ['interface mounted', 'program registry loaded', 'input ready']

export default function HeroBootSequence({ phaseIndex }) {
  return (
    <div className="hero-boot-log" aria-hidden="true">
      {BOOT_MESSAGES.map((message, index) => (
        <span key={message} className={phaseIndex >= 5 ? 'is-visible' : ''} style={{ '--boot-line-index': index }}>
          <b>[OK]</b> {message}
        </span>
      ))}
    </div>
  )
}
