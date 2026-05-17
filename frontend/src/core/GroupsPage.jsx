import useStore from '../store.js'

const GROUPS_WITH_FEATURES = {
  '68': 'Brotherhood',
}

const MEMBER_GROUPS = {
  '78': 'VIBE',
  '46': 'H4CK3R$',
  '48': 'Quantum',
  '52': 'PinkLSZ',
  '70': 'Gamblers',
  '50': 'Legends',
  '77': 'Academy',
  '71': 'Warriors',
}

export default function GroupsPage() {
  const user    = useStore(s => s.user)
  const profile = useStore(s => s.profile)
  const myGroups = profile?.groups || user?.groups || []

  const myMemberGroups = Object.entries(MEMBER_GROUPS)
    .filter(([gid]) => myGroups.includes(gid))
    .map(([, name]) => name)

  return (
    <div style={{ maxWidth: 700, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 20 }}>

      <div className="card" style={{ padding: '20px 24px' }}>
        <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text)', marginBottom: 6 }}>
          Group Features
        </div>
        <div style={{ fontSize: 13, color: 'var(--sub)', lineHeight: 1.7 }}>
          HFToolbox supports per-group modules — tools built specifically for member-owned groups.
          These show up in the sidebar under your group's section.
        </div>
      </div>

      {/* Groups the user is in */}
      {myMemberGroups.length > 0 && (
        <div className="card" style={{ padding: '20px 24px' }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--acc)', textTransform: 'uppercase', letterSpacing: '.08em', fontFamily: 'var(--mono)', marginBottom: 14 }}>
            Your Groups
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {myMemberGroups.map(name => (
              <div key={name} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '10px 14px', background: 'var(--bg)', borderRadius: 4,
                border: '1px solid var(--b1)',
              }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>{name}</span>
                <span style={{
                  fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)',
                  background: 'var(--s3)', padding: '2px 8px', borderRadius: 3,
                  border: '1px solid var(--b2)',
                }}>
                  No features yet
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* How to add features */}
      <div className="card" style={{ padding: '20px 24px' }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--acc)', textTransform: 'uppercase', letterSpacing: '.08em', fontFamily: 'var(--mono)', marginBottom: 14 }}>
          Adding Group Features
        </div>
        <div style={{ fontSize: 13, color: 'var(--sub)', lineHeight: 1.8 }}>
          Group-specific modules can be added to any self-hosted instance of HFToolbox.
          The source code is open — groups can build and run their own private version with their own features.
        </div>
        <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
          {[
            ['1', 'Fork the repo', 'github.com/AuJusDemon/hftoolbox'],
            ['2', 'Add your module under backend/modules/ and frontend/src/core/'],
            ['3', 'Wire it into Shell.jsx GROUP_NAV for your group\'s gid'],
            ['4', 'Self-host it — your group\'s features stay private'],
          ].map(([num, text, link]) => (
            <div key={num} style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
              <span style={{
                width: 22, height: 22, borderRadius: '50%', background: 'var(--s3)',
                border: '1px solid var(--b2)', display: 'flex', alignItems: 'center',
                justifyContent: 'center', fontSize: 10, color: 'var(--acc)',
                fontFamily: 'var(--mono)', fontWeight: 700, flexShrink: 0, marginTop: 1,
              }}>{num}</span>
              <span style={{ fontSize: 13, color: 'var(--sub)', lineHeight: 1.6 }}>
                {text}{' '}
                {link && (
                  <a href={`https://${link}`} target="_blank" rel="noreferrer"
                    style={{ color: 'var(--acc)', textDecoration: 'none' }}>
                    {link}
                  </a>
                )}
              </span>
            </div>
          ))}
        </div>
      </div>

    </div>
  )
}
