// Shared clickable stat tile: label (small caps) → large value → optional sub-line,
// colored left border. Originated in Seller HQ's Overview tab; reuse this instead of
// re-hand-rolling the same tile inline elsewhere.
export default function StatTile({ label, value, sub, color, onClick }) {
  return (
    <button
      className="btn"
      style={{
        flex: '1 1 0', minWidth: 90, textAlign: 'left',
        padding: '10px 12px', display: 'block',
        borderLeft: `2px solid ${color || 'var(--b3)'}`,
      }}
      onClick={onClick}
    >
      <div style={{ fontSize: 8, color: 'var(--dim)', fontFamily: 'var(--mono)', letterSpacing: '.1em', textTransform: 'uppercase', marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: 26, fontWeight: 700, color: color || 'var(--text)', fontFamily: 'var(--mono)', lineHeight: 1 }}>
        {value ?? 0}
      </div>
      {sub && (
        <div style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)', marginTop: 3 }}>{sub}</div>
      )}
    </button>
  )
}
