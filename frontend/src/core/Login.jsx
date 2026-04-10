import { useEffect, useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import useStore from '../store.js'

const ASCII_LOGO = `
██╗  ██╗███████╗
██║  ██║██╔════╝
███████║█████╗  
██╔══██║██╔══╝  
██║  ██║██║     
╚═╝  ╚═╝╚═╝     
████████╗ ██████╗  ██████╗ ██╗     ██████╗  ██████╗ ██╗  ██╗
╚══██╔══╝██╔═══██╗██╔═══██╗██║     ██╔══██╗██╔═══██╗╚██╗██╔╝
   ██║   ██║   ██║██║   ██║██║     ██████╔╝██║   ██║ ╚███╔╝ 
   ██║   ██║   ██║██║   ██║██║     ██╔══██╗██║   ██║ ██╔██╗ 
   ██║   ╚██████╔╝╚██████╔╝███████╗██████╔╝╚██████╔╝██╔╝ ██╗
   ╚═╝    ╚═════╝  ╚═════╝ ╚══════╝╚═════╝  ╚═════╝ ╚═╝  ╚═╝`.trim()




const BOOT_MSGS = [
  { text: 'BIOS v2.4.1  (C) HF Systems', delay: 0,    status: null,  color: 'var(--sub)' },
  { text: 'CPU: HF-API-Core @ 240 calls/hr', delay: 180, status: null, color: 'var(--dim)' },
  { text: 'RAM: 256MB OAuth token cache', delay: 280,  status: null,  color: 'var(--dim)' },
  { text: '', delay: 380, status: null, color: null },
  { text: 'Loading HFTOOLBOX kernel...', delay: 520,   status: 'OK',  color: 'var(--text)' },
  { text: 'Initializing HF API v2 client...', delay: 780, status: 'OK', color: 'var(--text)' },
  { text: 'Mounting encrypted session store...', delay: 1000, status: 'OK', color: 'var(--text)' },
  { text: 'Starting OAuth2 daemon...', delay: 1220,   status: 'OK',  color: 'var(--text)' },
  { text: 'Checking hackforums.net connectivity...', delay: 1480, status: 'OK', color: 'var(--text)' },
  { text: 'Loading user modules [bytes, contracts, bumper, posting]...', delay: 1700, status: 'OK', color: 'var(--text)' },
  { text: '', delay: 1900, status: null, color: null },
  { text: 'System ready.', delay: 2050, status: null, color: 'var(--acc)' },
]

const PROMPT_DELAY = 2400
const AUTH_DELAY   = 2700

export default function Login() {
  const { user, authLoading } = useStore()
  const nav = useNavigate()

  const [shown,      setShown]      = useState(0)   // how many boot msgs revealed
  const [showPrompt, setShowPrompt] = useState(false)
  const [showAuth,   setShowAuth]   = useState(false)
  const [cursorOn,   setCursorOn]   = useState(true)
  const [typed,      setTyped]      = useState('')
  const [typeDone,   setTypeDone]   = useState(false)
  const bottomRef = useRef(null)

  const CMD = 'authenticate --provider=hackforums'

  useEffect(() => {
    if (!authLoading && user) nav('/dashboard', { replace: true })
  }, [user, authLoading])

  /* Reveal boot messages one by one */
  useEffect(() => {
    BOOT_MSGS.forEach((_, i) => {
      setTimeout(() => setShown(n => Math.max(n, i + 1)), BOOT_MSGS[i].delay)
    })
    setTimeout(() => setShowPrompt(true), PROMPT_DELAY)
    setTimeout(() => setShowAuth(true),   AUTH_DELAY)
  }, [])

  /* Typewriter effect for the command */
  useEffect(() => {
    if (!showPrompt) return
    let i = 0
    const id = setInterval(() => {
      i++
      setTyped(CMD.slice(0, i))
      if (i >= CMD.length) { clearInterval(id); setTypeDone(true) }
    }, 28)
    return () => clearInterval(id)
  }, [showPrompt])

  /* Blinking cursor */
  useEffect(() => {
    const id = setInterval(() => setCursorOn(c => !c), 530)
    return () => clearInterval(id)
  }, [])

  /* Auto-scroll to bottom as messages appear */
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [shown, showPrompt, showAuth])

  const visibleMsgs = BOOT_MSGS.slice(0, shown)

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=VT323&family=Share+Tech+Mono&display=swap');

        .login-root {
          min-height: 100vh;
          background: #030803;
          font-family: 'Share Tech Mono', monospace;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 20px 16px;
          box-sizing: border-box;
          position: relative;
          overflow: hidden;
        }

        /* scanlines */
        .login-root::after {
          content: '';
          position: fixed; inset: 0;
          background: repeating-linear-gradient(
            to bottom,
            transparent 0px, transparent 1px,
            rgba(0,0,0,.08) 1px, rgba(0,0,0,.08) 2px
          );
          pointer-events: none; z-index: 10;
        }
        /* vignette */
        .login-root::before {
          content: '';
          position: fixed; inset: 0;
          background: radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,.65) 100%);
          pointer-events: none; z-index: 9;
        }

        .login-screen {
          width: 100%;
          max-width: 760px;
          min-height: min(96vh, 560px);
          display: flex;
          flex-direction: column;
          border: 1px solid #183818;
          border-left: 2px solid #225022;
          background: rgba(5,12,5,.95);
          position: relative;
        }

        /* corner decorations */
        .login-screen::before {
          content: '╔';
          position: absolute; top: -1px; left: -2px;
          font-family: 'Share Tech Mono', monospace;
          font-size: 14px; color: #225022; line-height: 1;
        }
        .login-screen::after {
          content: '╚';
          position: absolute; bottom: -1px; left: -2px;
          font-family: 'Share Tech Mono', monospace;
          font-size: 14px; color: #183818; line-height: 1;
        }

        .login-titlebar {
          padding: 7px 14px;
          border-bottom: 1px solid #183818;
          background: #050c05;
          display: flex;
          align-items: center;
          justify-content: space-between;
          flex-shrink: 0;
        }
        .login-titlebar-name {
          font-size: 11px;
          color: #2a5c2a;
          letter-spacing: .1em;
          text-transform: uppercase;
        }
        .login-titlebar-controls {
          display: flex;
          gap: 5px;
        }
        .login-titlebar-dot {
          width: 8px; height: 8px;
          border: 1px solid;
        }

        .login-body {
          flex: 1;
          padding: 22px 28px;
          overflow-y: auto;
          display: flex;
          flex-direction: column;
          gap: 0;
        }

        /* ASCII logo */
        .login-logo-big {
          font-family: 'Share Tech Mono', monospace;
          font-size: 7.5px;
          line-height: 1.2;
          color: #39ff14;
          text-shadow: 0 0 10px #39ff14, 0 0 24px rgba(57,255,20,.3);
          white-space: pre;
          margin-bottom: 16px;
          letter-spacing: 0;
          display: block;
        }
        .login-logo-small {
          font-family: 'Share Tech Mono', monospace;
          font-size: 11px;
          line-height: 1.3;
          color: #39ff14;
          text-shadow: 0 0 8px rgba(57,255,20,.6);
          white-space: pre;
          margin-bottom: 14px;
          letter-spacing: 0;
          display: none;
        }

        .login-divider {
          height: 1px;
          background: linear-gradient(90deg, rgba(57,255,20,.3), transparent);
          margin-bottom: 16px;
        }

        /* Boot messages */
        .boot-line {
          display: flex;
          gap: 8px;
          font-size: 11.5px;
          font-family: 'Share Tech Mono', monospace;
          line-height: 1.65;
          align-items: baseline;
        }
        .boot-line-text {
          flex: 1;
        }
        .boot-status-ok {
          font-size: 10px;
          color: #39ff14;
          text-shadow: 0 0 6px rgba(57,255,20,.5);
          letter-spacing: .06em;
          white-space: nowrap;
          flex-shrink: 0;
        }
        .boot-status-ok::before { content: '[ ' }
        .boot-status-ok::after  { content: ' ]' }

        /* command prompt */
        .login-prompt {
          display: flex;
          align-items: baseline;
          gap: 0;
          margin-top: 12px;
          font-size: 12.5px;
          font-family: 'Share Tech Mono', monospace;
          color: #9ecf9e;
        }
        .login-prompt-prefix {
          color: #39ff14;
          text-shadow: 0 0 8px rgba(57,255,20,.5);
          white-space: nowrap;
          flex-shrink: 0;
        }
        .login-prompt-cmd {
          color: #c4e8c4;
        }
        .login-cursor {
          display: inline-block;
          width: 8px; height: 14px;
          background: #39ff14;
          box-shadow: 0 0 6px rgba(57,255,20,.6);
          margin-left: 2px;
          vertical-align: middle;
          flex-shrink: 0;
        }

        /* auth button panel */
        .login-auth-panel {
          margin-top: 20px;
          border: 1px solid #183818;
          border-left: 2px solid #225022;
          padding: 16px 18px;
          background: rgba(5,8,5,.6);
        }
        .login-auth-header {
          font-size: 9px;
          color: #2a5c2a;
          letter-spacing: .12em;
          text-transform: uppercase;
          margin-bottom: 10px;
        }
        .login-auth-btn {
          display: block;
          width: 100%;
          padding: 12px 16px;
          background: rgba(57,255,20,.06);
          border: 1px solid rgba(57,255,20,.3);
          color: #39ff14;
          font-size: 14px;
          font-family: 'Share Tech Mono', monospace;
          cursor: pointer;
          letter-spacing: .06em;
          text-transform: uppercase;
          text-shadow: 0 0 8px rgba(57,255,20,.5);
          transition: all .12s ease;
          text-align: left;
        }
        .login-auth-btn::before { content: '> '; opacity: .6 }
        .login-auth-btn:hover {
          background: rgba(57,255,20,.1);
          border-color: rgba(57,255,20,.6);
          box-shadow: 0 0 12px rgba(57,255,20,.15);
          padding-left: 22px;
        }
        .login-auth-sub {
          font-size: 10px;
          color: #2a5c2a;
          margin-top: 10px;
          font-family: 'Share Tech Mono', monospace;
          line-height: 1.6;
        }

        .login-footer {
          position: fixed;
          bottom: 12px; right: 14px;
          font-size: 10px;
          color: #183818;
          font-family: 'Share Tech Mono', monospace;
          letter-spacing: .06em;
          z-index: 20;
        }

        /* Fade in animation */
        @keyframes fadeIn { from { opacity: 0; transform: translateY(4px) } to { opacity: 1; transform: none } }
        .boot-line { animation: fadeIn 180ms ease forwards }

        @keyframes loginAppear { from { opacity: 0 } to { opacity: 1 } }
        .login-auth-panel { animation: loginAppear 400ms ease forwards }

        @media (min-width: 600px) {
          .login-logo-big { display: block }
          .login-logo-small { display: none }
        }
        @media (max-width: 599px) {
          .login-logo-big { display: none }
          .login-logo-small { display: block }
          .login-body { padding: 16px 16px }
          .login-logo-small { font-size: 10px }
        }
      `}</style>

      <div className="login-root">
        <div className="login-screen">

          {/* Title bar */}
          <div className="login-titlebar">
            <span className="login-titlebar-name">hftoolbox — terminal v2</span>
            <div className="login-titlebar-controls">
              <div className="login-titlebar-dot" style={{borderColor:'#183818',background:'var(--b1)'}}/>
              <div className="login-titlebar-dot" style={{borderColor:'#ffaa0040',background:'rgba(255,170,0,.1)'}}/>
              <div className="login-titlebar-dot" style={{borderColor:'rgba(57,255,20,.3)',background:'rgba(57,255,20,.08)'}}/>
            </div>
          </div>

          {/* Body */}
          <div className="login-body">

            {/* Logo */}
            <div style={{marginBottom:14}}>
              <div style={{fontFamily:"'VT323', monospace",fontSize:52,lineHeight:1,color:'#39ff14',textShadow:'0 0 10px #39ff14, 0 0 28px rgba(57,255,20,.35)',letterSpacing:'.06em'}}>
                HF.TOOLBOX
              </div>
              <div style={{fontFamily:"'Share Tech Mono', monospace",fontSize:10,color:'#3d6b3d',letterSpacing:'.18em',marginTop:4,textTransform:'uppercase'}}>
                hackforums utility terminal // v2
              </div>
            </div>

            <div className="login-divider"/>

            {/* Boot messages */}
            <div>
              {visibleMsgs.map((msg, i) => (
                <div key={i} className="boot-line">
                  {msg.text === '' ? (
                    <span>&nbsp;</span>
                  ) : (
                    <>
                      <span className="boot-line-text" style={{color: msg.color || 'var(--sub)'}}>
                        {msg.text}
                      </span>
                      {msg.status === 'OK' && (
                        <span className="boot-status-ok">OK</span>
                      )}
                    </>
                  )}
                </div>
              ))}
            </div>

            {/* Command prompt + typewriter */}
            {showPrompt && (
              <div className="login-prompt">
                <span className="login-prompt-prefix">root@hftoolbox:~$&nbsp;</span>
                <span className="login-prompt-cmd">{typed}</span>
                {!typeDone
                  ? <span className="login-cursor" style={{opacity: cursorOn ? 1 : 0}}/>
                  : null
                }
              </div>
            )}

            {/* Auth panel — appears after typewriter done */}
            {showAuth && (
              <div className="login-auth-panel">
                <div className="login-auth-header">// oauth2 authentication required</div>
                <button
                  className="login-auth-btn"
                  onClick={() => { window.location.href = '/auth/login' }}
                >
                  Continue with HackForums
                </button>
                <div className="login-auth-sub">
                  {'// No passwords stored. Authorization via official HF API v2 OAuth2.'}<br/>
                  {'// Access scopes: Basic Info · Advanced Info · Posts · Bytes · Contracts'}
                </div>
              </div>
            )}

            {/* Blinking cursor at bottom when nothing is happening */}
            {showAuth && (
              <div style={{marginTop:10,fontFamily:'Share Tech Mono, monospace',fontSize:12,color:'var(--dim)',display:'flex',alignItems:'center',gap:0}}>
                <span>root@hftoolbox:~$&nbsp;</span>
                <span style={{
                  display:'inline-block',width:8,height:13,
                  background:'#2a5c2a',
                  boxShadow:'0 0 4px rgba(57,255,20,.3)',
                  opacity: cursorOn ? 1 : 0,
                  verticalAlign:'middle',
                }}/>
              </div>
            )}

            <div ref={bottomRef} />
          </div>

        </div>

        <div className="login-footer">hftoolbox.com // v2</div>
      </div>
    </>
  )
}
