import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import useStore from '../store.js'

export default function Login() {
  const { user, authLoading } = useStore()
  const nav = useNavigate()
  const [vis, setVis] = useState(false)

  useEffect(() => {
    requestAnimationFrame(() => setVis(true))
    if (!authLoading && user) nav('/dashboard', { replace: true })
  }, [user, authLoading])

  return (
    <>
      <style>{`
        .login-wrap {
          min-height: 100vh;
          background: #07090d;
          font-family: 'DM Sans', sans-serif;
          display: flex;
          align-items: center;
          justify-content: center;
          position: relative;
          overflow: hidden;
          padding: 24px 16px;
          box-sizing: border-box;
        }
        .login-inner {
          display: flex;
          align-items: stretch;
          width: 100%;
          max-width: 960px;
          min-height: min(100vh, 520px);
          position: relative;
        }
        .login-left {
          flex: 1;
          display: flex;
          flex-direction: column;
          justify-content: center;
          padding: 64px 72px;
          max-width: 620px;
        }
        .login-divider {
          width: 1px;
          background: linear-gradient(180deg,transparent,rgba(255,255,255,.05) 25%,rgba(255,255,255,.05) 75%,transparent);
          margin: 80px 0;
          flex-shrink: 0;
        }
        .login-right {
          width: 340px;
          flex-shrink: 0;
          display: flex;
          flex-direction: column;
          justify-content: center;
          padding: 64px 52px;
          position: relative;
        }
        .login-h1 {
          font-family: 'Syne', sans-serif;
          font-size: 46px;
          font-weight: 800;
          letter-spacing: -.04em;
          line-height: 1.0;
          color: #e8edf8;
          margin-bottom: 18px;
          max-width: 380px;
        }
        .login-btn {
          width: 100%;
          padding: 13px;
          background: #4d8ef0;
          border: none;
          border-radius: 10px;
          color: #fff;
          font-size: 15px;
          font-weight: 600;
          cursor: pointer;
          font-family: inherit;
          letter-spacing: -.01em;
          transition: background .13s ease, transform .13s ease;
          margin-bottom: 18px;
        }
        .login-btn:hover { background: #3a7ae0; transform: translateY(-1px); }
        @media (max-width: 640px) {
          .login-inner {
            flex-direction: column;
            align-items: center;
            min-height: auto;
            gap: 32px;
          }
          .login-left {
            padding: 16px 0 0;
            max-width: 100%;
            text-align: center;
            align-items: center;
          }
          .login-h1 { font-size: 32px; max-width: 100%; }
          .login-divider { display: none; }
          .login-right {
            width: 100%;
            max-width: 360px;
            padding: 0 0 32px;
          }
          .login-btn { font-size: 16px; padding: 15px; }
        }
      `}</style>
      <div className="login-wrap">
        <div className="login-inner" style={{
          opacity: vis ? 1 : 0, transform: vis ? 'none' : 'translateY(12px)',
          transition: 'opacity .5s ease, transform .5s ease',
        }}>
          {/* top line */}
          <div style={{ position:'absolute',top:0,left:0,right:0,height:1,background:'linear-gradient(90deg,transparent,rgba(77,142,240,0.35),transparent)' }}/>

          {/* Left */}
          <div className="login-left">
            <div style={{ fontSize:11,fontFamily:"'DM Mono',monospace",letterSpacing:'.18em',textTransform:'uppercase',color:'rgba(77,142,240,.6)',marginBottom:20 }}>
              HF.Toolbox
            </div>
            <h1 className="login-h1">Your HackForums toolkit.</h1>
            <p style={{ fontSize:14,color:'rgba(232,237,248,.7)',lineHeight:1.7,maxWidth:300,marginBottom:0 }}>
              Tools for HackForums members, built on the official API v2.
            </p>
          </div>

          {/* divider */}
          <div className="login-divider"/>

          {/* Right */}
          <div className="login-right">
            <div style={{ fontFamily:"'Syne',sans-serif",fontSize:19,fontWeight:700,letterSpacing:'-.02em',color:'#e8edf8',marginBottom:6 }}>
              Sign in
            </div>
            <div style={{ fontSize:12.5,color:'rgba(232,237,248,.72)',marginBottom:30,lineHeight:1.6 }}>
              Connect your HackForums account via OAuth2. No passwords stored.
            </div>
            <button className="login-btn" onClick={() => { window.location.href = '/auth/login' }}>
              Continue with HackForums
            </button>
            <div style={{ fontSize:11,color:'rgba(232,237,248,.45)',lineHeight:1.6,textAlign:'center' }}>
              By signing in you authorize HF.Toolbox to access your HackForums account via the official API.
            </div>
          </div>

          {/* bottom line */}
          <div style={{ position:'absolute',bottom:0,left:0,right:0,height:1,background:'linear-gradient(90deg,transparent,rgba(77,142,240,.12),transparent)' }}/>
        </div>
        <div style={{ position:'fixed',bottom:16,right:16,fontSize:11,color:'rgba(232,237,248,.2)',fontFamily:"'DM Mono',monospace" }}>
          hftoolbox.com
        </div>
      </div>
    </>
  )
}
