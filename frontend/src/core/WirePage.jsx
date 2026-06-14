import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { api } from './api.js'
import { parseHfId } from './utils.js'
import useStore from '../store.js'

// Module-level cache for resolved mentions — persists across renders, never fetches same UID twice
const _mentionCache = {}  // uid → username
const _mentionPending = new Set()  // UIDs currently in-flight

// ── Wire beta gate ─────────────────────────────────────────────────────────
// Set to null to make The Wire public for all users.

const ago = ts => {
  if (!ts) return '--'
  const d = Math.floor(Date.now() / 1000) - ts
  if (d < 60)    return `${d}s`
  if (d < 3600)  return `${Math.floor(d/60)}m`
  if (d < 86400) return `${Math.floor(d/3600)}h`
  if (d < 86400*30)  return `${Math.floor(d/86400)}d`
  if (d < 86400*365) return `${Math.floor(d/(86400*30))}mo`
  return `${Math.floor(d/(86400*365))}y`
}
const fmtDate = ts => {
  if (!ts) return '--'
  return new Date(ts*1000).toLocaleDateString('en-US',{month:'short',year:'numeric'})
}
const fmtDateFull = ts => {
  if (!ts) return '--'
  return new Date(ts*1000).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'})
}

const TAGS = ['all','guide','tool','discussion','resource','analysis','classic','news']
const SUBMIT_TAGS = ['guide','tool','discussion','resource','analysis','classic','news']

const TAG_COLORS = {
  guide:      { bg:'rgba(57,255,20,.09)',   color:'#39ff14', border:'rgba(57,255,20,.3)',   glow:'rgba(57,255,20,.2)'    },
  tool:       { bg:'rgba(0,221,255,.08)',   color:'#00ddff', border:'rgba(0,221,255,.3)',   glow:'rgba(0,221,255,.18)'   },
  discussion: { bg:'rgba(255,187,0,.08)',   color:'#ffbb00', border:'rgba(255,187,0,.3)',   glow:'rgba(255,187,0,.18)'   },
  resource:   { bg:'rgba(57,255,20,.05)',   color:'#39ff14', border:'rgba(57,255,20,.2)',   glow:'rgba(57,255,20,.1)'    },
  analysis:   { bg:'rgba(170,100,255,.09)', color:'#aa64ff', border:'rgba(170,100,255,.3)', glow:'rgba(170,100,255,.18)' },
  classic:    { bg:'rgba(255,140,0,.08)',   color:'#ff8c00', border:'rgba(255,140,0,.3)',   glow:'rgba(255,140,0,.18)'   },
  news:       { bg:'rgba(255,68,68,.08)',   color:'#ff4444', border:'rgba(255,68,68,.3)',   glow:'rgba(255,68,68,.18)'   },
}
const TAG_DESC = {
  guide:'Step-by-step technical walkthrough', tool:'Software release, script, or utility',
  discussion:'Notable conversation or debate', resource:'Reference material or compilation',
  analysis:'Deep dive or research writeup', classic:'Timeless thread worth preserving',
  news:'Current events or announcements',
}
const ROLE_BADGE = {
  admin:   { label:'ADMIN',   style:{ background:'rgba(255,68,68,.1)',   color:'var(--red)',    border:'1px solid rgba(255,68,68,.3)'   } },
  lead:    { label:'LEAD',    style:{ background:'rgba(255,187,0,.1)',   color:'var(--yellow)', border:'1px solid rgba(255,187,0,.3)'   } },
  curator: { label:'CURATOR', style:{ background:'rgba(57,255,20,.07)',  color:'var(--acc)',    border:'1px solid rgba(57,255,20,.2)'   } },
}
const GROUPS = {
  "2":"Registered","9":"L33t","28":"Ub3r","67":"Vendor",
  "46":"H4CK3R$","48":"Quantum","50":"Legends","52":"PinkLSZ",
  "68":"Brotherhood","70":"Gamblers","71":"Warriors","77":"Academy","78":"VIBE",
  "7":"Exiled","38":"Banned",
}
const WIRE_GROUP_PRIORITY = ["9","28","67","46","48","50","52","68","70","71","77","78","7","38","2"]
const WIRE_GROUP_STYLES = {
  "2":  {color:"#efefef"},
  "9":  {color:"#FFCC00"},
  "28": {color:"#0066FF"},
  "67": {color:"#2D7E52",fontWeight:"bold"},
  "46": {color:"#222",fontFamily:"\"Amarante\",serif",fontWeight:"bold",textShadow:"-1px -1px 0 #0f0,1px -1px 0 #0f0,-1px 1px 0 #0f0,1px 1px 0 #0f0,0 0 5px #0f0"},
  "48": {color:"#dfcbff",fontFamily:"\"New Rocker\",system-ui",fontWeight:"bold",textShadow:"0 0 1px #b380ff,0 0 3px #9933ff,0 0 6px #7722cc"},
  "50": {fontWeight:"700",fontFamily:"\"Cinzel\",serif",letterSpacing:"2px",background:"linear-gradient(135deg,#FFD700,#FFC200,#B8860B)",WebkitBackgroundClip:"text",WebkitTextFillColor:"transparent"},
  "52": {color:"#FF99CC",fontFamily:"\"Comic Sans MS\",cursive",fontWeight:"bold",textShadow:"2px 2px 2px #4020dd"},
  "68": {fontFamily:"\"Cinzel\",serif",fontWeight:"900",letterSpacing:"1.15px",background:"linear-gradient(90deg,#9a9a9a 0%,#cfcfcf 20%,#fff 35%,#fff 45%,#e6e6e6 55%,#cfcfcf 70%,#9a9a9a 100%)",backgroundSize:"300% auto",animation:"brotherhood-shine 4s ease-in-out infinite",WebkitBackgroundClip:"text",WebkitTextFillColor:"transparent"},
  "70": {color:"#ff54a1",fontWeight:"bold",textShadow:"2px 2px 2px #000"},
  "71": {color:"#00feb0",textShadow:"0 2px 3px #000"},
  "77": {color:"#fff",fontFamily:"Graduate,sans-serif",letterSpacing:"2px",textShadow:"-1px -1px 0 #467fff,1px -1px 0 #098ed9,-1px 1px 0 #1199df,1px 1px 0 #139add,0 0 5px #529ec0"},
  "78": {display:"inline-block",fontFamily:"\"Orbitron\",serif",fontWeight:"900",background:"linear-gradient(90deg,#00ffb2 0%,#00e6ff 35%,#b7fff1 50%,#00e6ff 65%,#00ffb2 100%)",WebkitBackgroundClip:"text",WebkitTextFillColor:"transparent",animation:"vibe-glitch 3.5s infinite"},
  "7":  {color:"#aaa",textDecoration:"line-through"},
  "38": {color:"#aaa",textDecoration:"line-through"},
}
function sortGroupIds(ids) {
  return [...ids].sort((a,b) => {
    const ai=WIRE_GROUP_PRIORITY.indexOf(a), bi=WIRE_GROUP_PRIORITY.indexOf(b)
    if(ai===-1&&bi===-1)return 0; if(ai===-1)return 1; if(bi===-1)return -1; return ai-bi
  })
}
function GroupTags({ groups }) {
  if (!groups) return null
  const all = sortGroupIds(groups.split(',').map(g=>g.trim()).filter(g=>GROUPS[g]))
  if (!all.length) return null
  return (
    <span style={{display:'flex',gap:4,flexWrap:'wrap',alignItems:'center'}}>
      {all.map(g => (
        <span key={g} style={{fontSize:10,...(WIRE_GROUP_STYLES[g]||{color:"var(--sub)"})}}>{GROUPS[g]}</span>
      ))}
    </span>
  )
}

function TagPill({ tag, active, onClick }) {
  const c = TAG_COLORS[tag] || { bg:'var(--s3)', color:'var(--sub)', border:'var(--b2)', glow:'transparent' }
  return (
    <button onClick={onClick} style={{
      display:'inline-flex', alignItems:'center', gap:4,
      padding:'3px 10px',
      background: active ? c.bg : 'transparent',
      border:`1px solid ${active ? c.border : c.border.replace(/[\d.]+\)$/, '0.15)')}`,
      color: active ? c.color : c.color,
      opacity: active ? 1 : 0.45,
      fontFamily:'var(--mono)', fontSize:10, letterSpacing:'.08em',
      cursor:'pointer', whiteSpace:'nowrap',
      transition:'all var(--ease)',
      textShadow: active ? `0 0 8px ${c.glow}` : 'none',
    }}>
      {tag === 'all' ? 'ALL' : tag.toUpperCase()}
    </button>
  )
}

function TagBadge({ tag, style={} }) {
  const c = TAG_COLORS[tag] || { bg:'var(--s3)', color:'var(--sub)', border:'var(--b2)', glow:'transparent' }
  return (
    <span style={{
      fontSize:9, padding:'2px 7px', fontFamily:'var(--mono)',
      letterSpacing:'.12em', textTransform:'uppercase', fontWeight:600,
      background:c.bg, color:c.color, border:`1px solid ${c.border}`,
      boxShadow:`0 0 6px ${c.glow}`,
      flexShrink:0, ...style,
    }}>{tag}</span>
  )
}

// ── Crypto helpers for [uimg] decryption (same as PostingPage) ───────────────

function _b64urlDecode(s) {
  s = s.replace(/-/g,'+').replace(/_/g,'/')
  while (s.length%4) s+='='
  const bin=atob(s), arr=new Uint8Array(bin.length)
  for (let i=0;i<bin.length;i++) arr[i]=bin.charCodeAt(i)
  return arr
}
async function _e2eDeriveKey(seed) {
  const ikm=await crypto.subtle.importKey('raw',seed,'HKDF',false,['deriveKey'])
  return crypto.subtle.deriveKey(
    {name:'HKDF',hash:'SHA-256',salt:new TextEncoder().encode('UIMG-E2E1-KEY'),info:new TextEncoder().encode('aes-256-gcm')},
    ikm,{name:'AES-GCM',length:256},false,['decrypt']
  )
}

function UimgEmbed({ url, size }) {
  const [phase,   setPhase]   = useState('loading')
  const [blobUrl, setBlobUrl] = useState(null)
  const [errMsg,  setErrMsg]  = useState('')

  useEffect(() => {
    let cancelled=false, objectUrl=null
    async function load() {
      try {
        const hashPart = url.split('#')[1]||''
        if (!hashPart.startsWith('E2E1.')) { setErrMsg('no E2E1 fragment'); setPhase('error'); return }
        const pieces = hashPart.slice(5).split('.')
        if (pieces.length<4) { setErrMsg('bad fragment'); setPhase('error'); return }
        let seed,iv
        try { seed=_b64urlDecode(pieces[0]) } catch(e) { setErrMsg('seed: '+e.message); setPhase('error'); return }
        try { iv=_b64urlDecode(pieces[1])   } catch(e) { setErrMsg('iv: '+e.message);   setPhase('error'); return }
        const gwKey  = pieces[3]
        const imageId = url.match(/uploadimages\.org\/([a-f0-9]+)/)?.[1]
        if (!imageId) { setErrMsg('no image id'); setPhase('error'); return }
        let resp
        try { resp = await fetch(`/api/uimg/${imageId}?key=${encodeURIComponent(gwKey)}`) }
        catch(e) { setErrMsg('fetch: '+e.message); setPhase('error'); return }
        if (!resp.ok) { const b=await resp.text().catch(()=>''); setErrMsg(`image ${resp.status}: ${b.slice(0,60)}`); setPhase('error'); return }
        const encrypted = await resp.arrayBuffer()
        let key
        try { key=await _e2eDeriveKey(seed) } catch(e) { setErrMsg('key: '+e.message); setPhase('error'); return }
        let decrypted
        try { decrypted=await crypto.subtle.decrypt({name:'AES-GCM',iv,tagLength:128},key,encrypted) }
        catch(e) { setErrMsg('decrypt: '+(e.message||e.name)); setPhase('error'); return }
        if (cancelled) return
        objectUrl = URL.createObjectURL(new Blob([decrypted]))
        setBlobUrl(objectUrl); setPhase('ok')
      } catch(e) { if (!cancelled) { setErrMsg('err: '+e.message); setPhase('error') } }
    }
    load()
    return () => { cancelled=true; if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [url])

  const sizeStyle={}
  if (size) {
    if (/^\d+[x×]\d+$/i.test(size)) { const [w,h]=size.split(/[x×]/i); sizeStyle.width=w+'px'; sizeStyle.height=h+'px' }
    else if (/^\d+%$/.test(size)) sizeStyle.width=size
  }
  const pill={display:'inline-flex',alignItems:'center',gap:6,padding:'4px 10px',borderRadius:4,fontSize:11,fontFamily:'var(--mono)',margin:'4px 0',verticalAlign:'middle'}
  if (phase==='loading') return <span style={{...pill,background:'rgba(57,255,20,.06)',border:'1px solid rgba(57,255,20,.2)',color:'var(--acc)'}}>⏳ loading…</span>
  if (phase==='error')   return <span style={{...pill,background:'rgba(255,68,68,.06)',border:'1px solid rgba(255,68,68,.2)',color:'var(--red)'}} title={errMsg}>⚠ {errMsg}</span>
  return <img src={blobUrl} alt="" style={{maxWidth:'100%',verticalAlign:'middle',margin:'4px 0',...sizeStyle}}/>
}

// ── Award name lookup (for tooltip on [award=N] tags) ─────────────────────────
const WIRE_AWARD_NAMES = {1:'Diamond',2:'White Hat Helper',3:'Speaker of the House',4:'Member of the Month',5:'Drunk',6:'Genius',7:'The Protector',8:'Dunce',9:'Turkey',10:'Asswipe',11:'Hustler',12:'Flamer',13:'Ninja',14:'Dark Inferno Wings',15:'Asskisser',16:'Militant',18:'Rich Bitch',19:'Star',20:'Black Hatter',21:'Gold Medal',23:'Gamer',24:'Frog',25:'Cool',26:'DaBomb',27:'Dancing Queen',28:'Pizza',29:'Silver Medal',30:'Bronze Tutorial Award',31:'GFX Guru',32:'Golden Content',34:'Jokester',35:'Emerald Donator',36:'Cat Lover',37:'Cuddly and Cute',38:'Mad Scientist',39:'Great Thinker',40:'Sapphire of Ub3r',41:'Dog Lover',42:'Support Feather',47:'Graphic Master',49:'Grammar Nazi',50:'Master Donator',51:'YouTube',52:'Fish Err Man',54:'Rat Expert',55:'The Alien',56:'Hot Dog',57:'Sushi Lover',58:'Businessman',59:'FPS Gawd',60:'Award Whore',61:'Liberty Reserve Head',62:'Qwazz Star',63:'Sticky Man',64:'Gavel of Dredd',65:'MRT Graduate',66:'Brony',67:'24k',68:'HackerCraft',69:'Spy',70:'Bitcoinage',71:'Gift',72:'Litecoinage',73:'Phreak',74:'HackerCraft Purple',75:'OMC',76:'Legend',77:'Top Banana',78:'Green Apple',79:'Legalize It',80:'Grand Amethyst',81:'Dogecoinage',82:'Royalty',83:'Benefactor',84:'DarkDash',85:'Green Clover',86:'Purple Clover',87:'Gold Clover',88:'Dstat Power God',89:'Instagrammy',90:'HackerCraft Blue',91:'Music Lover',92:'Ethereist',93:'Poke Ball',94:'Testified',95:'HF News Contributor',96:'Monero',97:'Dicey',98:'Eclipse',99:'ZECret',100:'XEMplary',101:'Rippled',102:'Stratisphere',103:'Fox',104:'BTCash',105:'Lounge Head',106:'Diamond of Hell',107:'Ace of Spades',108:'Lisking',109:'Qtum Umm',110:'PivX',111:'Wave Rider',112:'Xerotic Bot DNA',113:'Purple Gift',114:'Blue Gift',115:'Green Gift',116:'Cup of Joe',117:'Medal of Honor',118:'Youtube 2018',119:'Taco Taco Taco',120:'Grey Star',121:'Green Star',122:'Red Star',123:'Blue Star',124:'Gold Star',125:'Heart of HF',126:'Omners',127:'iHydra',128:'Cyber Diamond',130:'Money Money',131:'Everyday Ninja',132:'Cheap Skate',133:'SportsBook',134:'CyberMonday',135:'DIVIne Comedy',136:'Diamond of Gamblers',140:'Corona Virus',141:'Mr Monopoly',142:'Hackuman Killer',144:'K1NG',145:'Independence Egg',146:'Quickly Loved',147:'Astropink',148:'Ghoul',149:'Hack Friday',150:'Heart of Generosity',151:'LGBQT',152:'Euthanasia',154:'The Plug',155:'Dainamic',156:'Binance Dance',157:'Olympians Trident',158:'Purple Haze',159:'Infamous Delta',161:'Ruby Heart Master Donator',162:'Emerald Heart',163:'Octoberfest 2021',164:'Bytes Bag',165:'Skull of Emptiness',166:'Skull of Agony',167:'Skull of Death',168:'Blackened Heart Gem',169:'Hot Wheels',170:'420 Award 2022',171:'420 Award 2022 Blue',172:'King Skull',173:'Green Bong',174:'True Gambler',175:'Warrior',176:'A Purple Hat',177:'Pint',178:'Octoberfest 2022',179:'Xmas 2022 Ornament 1',180:'Xmas 2022 Ornament 2',181:'Xmas 2022 Ornament 3',182:'Riddle King',183:'Youtube 2023',184:'Molten Sword',185:'Dynamite',186:'Lucky',187:'Shining Knight',188:'Black Hat Hacker',189:'White Hat Hacker',190:'Grey Hat Hacker',191:'Red Hat Hacker',192:'Blue Hat Hacker',193:'Green Hat Hacker',194:'King Decade',196:'Octoberfest 2023',197:'Gift 2023',198:'Gift in Yellow Box',200:'Gold Coins',202:'Black Dank',203:'Solana',204:'Octoberfest 2024',205:'100',208:'G.O.A.T',209:'Troll',210:'Golden Fleur-De-Lis',211:'Pulse Controller',213:'Xmas Ornament 2024',214:'Javascript Junkie',215:'Python Punk',216:'PHP Prodigy',217:'Money-',218:'Bounty Hunter',219:'Gaming Shooter 2025',220:'Chef Hat',221:'TikTok Trooper',222:'Flip Reaper',223:'H4CK3R$ Black Hat',224:'H4CK3R$ Red Hat',225:'H4CK3R$ Blue Hat',226:'Holy Leaf',227:'HF 18 Cake',228:'America',229:'Blazing Ember',230:'Stanley Fan',231:'Octoberfest 2025',232:'API Dev',233:'Earthling'}

// ── BBCode parser ─────────────────────────────────────────────────────────────────
// [uimg] emits a <span class="wire-uimg" data-url data-size> placeholder.
// BBCode component finds these in useEffect and decrypts them directly in DOM —
// so [uimg] inside [spoiler], [quote], [table] etc. all work correctly.

function parseBBCode(raw) {
  if (!raw) return ''

  // ── STEP 1: Extract [code] blocks FIRST — protect from all other handlers ──
  // They are restored LAST (step 6), after all other processing is done.
  const _codeStore = []
  let s = raw
  const _save = (lang, code) => { _codeStore.push({lang, code}); return `\x02C${_codeStore.length-1}\x02` }
  s = s.replace(/\[code=([^\]]+)\]([\s\S]*?)\[\/code\]/gi,  (_,l,c) => _save(l,c))
  s = s.replace(/\[code\]([\s\S]*?)\[\/code\]/gi,            (_,c)   => _save('',c))
  s = s.replace(/\[php\]([\s\S]*?)\[\/php\]/gi,              (_,c)   => _save('php',c))
  for (const l of ['python','javascript','js','typescript','ts','html','css','bash','sh','sql','xml','json','cpp','c','java','ruby','go','rust']) {
    s = s.replace(new RegExp(`\\[${l}\\]([\\s\\S]*?)\\[\\/${l}\\]`,'gi'), (_,c) => _save(l,c))
  }

  // ── STEP 2: HTML-escape everything else ───────────────────────────────────
  s = s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')

  // ── STEP 3: All other BBCode handlers ────────────────────────────────────
  s = s.replace(/\[css=(\d+)\]([\s\S]*?)\[\/css\]/gi, (_,g,inner) => `<span class="group${g}">${inner}</span>`)
  s = s.replace(/\[award=(\d+)\]/gi, (_,id) => {
    const name = WIRE_AWARD_NAMES[parseInt(id)] || `Award #${id}`
    return `<i class="award_sprite award_${id}" title="${name}" style="display:inline-block;vertical-align:middle;margin:2px 3px"></i>`
  })
  // [mention=UID] — clickable profile link, username resolved after render
  s = s.replace(/\[mention=(\d+)\]/gi, (_,uid) =>
    `<a class="wire-mention" data-uid="${uid}" href="https://hackforums.net/member.php?action=profile&uid=${uid}" target="_blank" rel="noopener" style="color:var(--acc);font-weight:500;text-decoration:none">@${uid}</a>`)
  s = s.replace(/\[b\]([\s\S]*?)\[\/b\]/gi,'<strong>$1</strong>')
  s = s.replace(/\[i\]([\s\S]*?)\[\/i\]/gi,'<em>$1</em>')
  s = s.replace(/\[u\]([\s\S]*?)\[\/u\]/gi,'<u>$1</u>')
  s = s.replace(/\[s\]([\s\S]*?)\[\/s\]/gi,'<s>$1</s>')
  s = s.replace(/\[sup\]([\s\S]*?)\[\/sup\]/gi,'<sup>$1</sup>')
  s = s.replace(/\[sub\]([\s\S]*?)\[\/sub\]/gi,'<sub>$1</sub>')
  s = s.replace(/\[center\]([\s\S]*?)\[\/center\]/gi,'<div style="text-align:center">$1</div>')
  s = s.replace(/\[left\]([\s\S]*?)\[\/left\]/gi,'<div style="text-align:left">$1</div>')
  s = s.replace(/\[right\]([\s\S]*?)\[\/right\]/gi,'<div style="text-align:right">$1</div>')
  s = s.replace(/\[align=([^\]]+)\]([\s\S]*?)\[\/align\]/gi,'<div style="text-align:$1">$2</div>')
  s = s.replace(/\[url=([^\]]+)\]([\s\S]*?)\[\/url\]/gi,'<a href="$1" target="_blank" rel="noopener" style="color:var(--acc)">$2</a>')
  s = s.replace(/\[url\]([\s\S]*?)\[\/url\]/gi,'<a href="$1" target="_blank" rel="noopener" style="color:var(--acc)">$1</a>')
  s = s.replace(/\[img=(\d+)[x×](\d+)\]([\s\S]*?)\[\/img\]/gi,'<img src="$3" style="width:$1px;height:$2px;max-width:100%;vertical-align:middle;margin:4px 0" />')
  s = s.replace(/\[img\]([\s\S]*?)\[\/img\]/gi,'<img src="$1" style="max-width:100%;vertical-align:middle;margin:4px 0" />')
  const _uimgP = (url,size) => `<span class="wire-uimg" data-url="${encodeURIComponent((url||'').trim())}" data-size="${encodeURIComponent(size||'')}"></span>`
  s = s.replace(/\[uimg=([^\]]+)\]([\s\S]*?)\[\/uimg\]/gi, (_,sz,url) => _uimgP(url,sz))
  s = s.replace(/\[uimg\]([\s\S]*?)\[\/uimg\]/gi,           (_,url)    => _uimgP(url,''))
  s = s.replace(/\[table\]([\s\S]*?)\[\/table\]/gi,'<table style="border-collapse:collapse;width:100%;margin:8px 0;font-size:13px;font-family:Verdana,Arial,sans-serif">$1</table>')
  s = s.replace(/\[thead\]([\s\S]*?)\[\/thead\]/gi,'<thead>$1</thead>')
  s = s.replace(/\[tbody\]([\s\S]*?)\[\/tbody\]/gi,'<tbody>$1</tbody>')
  s = s.replace(/\[tr\]([\s\S]*?)\[\/tr\]/gi,'<tr>$1</tr>')
  s = s.replace(/\[th\]([\s\S]*?)\[\/th\]/gi,'<th style="padding:6px 10px;border:1px solid #444;background:#3a3a3a;text-align:left;font-weight:bold;color:#ddd">$1</th>')
  s = s.replace(/\[td\]([\s\S]*?)\[\/td\]/gi,'<td style="padding:6px 10px;border:1px solid #3a3a3a;color:#ccc">$1</td>')
  s = s.replace(/\[quote=([^\]]+)\]([\s\S]*?)\[\/quote\]/gi,'<blockquote style="border-left:3px solid #444;margin:4px 0;background:#2a2a2a;padding:8px 12px;color:#bbb"><cite style="font-style:normal;font-weight:bold;color:#ccc;display:block;margin-bottom:4px;font-size:12px">$1 wrote:</cite>$2</blockquote>')
  s = s.replace(/\[quote\]([\s\S]*?)\[\/quote\]/gi,'<blockquote style="border-left:3px solid #444;margin:4px 0;background:#2a2a2a;padding:8px 12px;color:#bbb">$1</blockquote>')
  s = s.replace(/\[color=([^\]]+)\]([\s\S]*?)\[\/color\]/gi,'<span style="color:$1">$2</span>')
  s = s.replace(/\[size=(\d+)\]([\s\S]*?)\[\/size\]/gi,(_,sz,c)=>`<span style="font-size:${Math.min(Math.max(parseInt(sz)*1.1,10),24)}px">${c}</span>`)
  s = s.replace(/\[font=([^\]]+)\]([\s\S]*?)\[\/font\]/gi,'<span style="font-family:$1">$2</span>')
  const _li = inner => inner.split(/\[\*\]/).filter(Boolean).map(i=>`<li>${i.trim()}</li>`).join('')
  s = s.replace(/\[list=1\]([\s\S]*?)\[\/list\]/gi, (_,i) => `<ol style="margin:6px 0 6px 20px">${_li(i)}</ol>`)
  s = s.replace(/\[list=a\]([\s\S]*?)\[\/list\]/gi, (_,i) => `<ol type="a" style="margin:6px 0 6px 20px">${_li(i)}</ol>`)
  s = s.replace(/\[list\]([\s\S]*?)\[\/list\]/gi,   (_,i) => `<ul style="margin:6px 0 6px 20px">${_li(i)}</ul>`)
  s = s.replace(/\[li\]([\s\S]*?)\[\/li\]/gi,'<li>$1</li>')
  s = s.replace(/\[spoiler=([^\]]+)\]([\s\S]*?)\[\/spoiler\]/gi,'<details style="border:1px solid #444;background:#2a2a2a;padding:6px 10px;margin:6px 0"><summary style="cursor:pointer;color:#aaa;font-size:12px">$1</summary><div style="margin-top:6px">$2</div></details>')
  s = s.replace(/\[spoiler\]([\s\S]*?)\[\/spoiler\]/gi,'<details style="border:1px solid #444;background:#2a2a2a;padding:6px 10px;margin:6px 0"><summary style="cursor:pointer;color:#aaa;font-size:12px">Spoiler</summary><div style="margin-top:6px">$1</div></details>')
  s = s.replace(/\[hr\]/gi,'<hr style="display:block;border:none;border-top:1px solid #555;margin:10px auto;width:100%"/>')
  s = s.replace(/\[video=youtube\]([\s\S]*?)\[\/video\]/gi, (_,url) => {
    const id = url.match(/(?:v=|youtu\.be\/)([A-Za-z0-9_-]{11})/)?.[1]||''
    return id ? `<div style="position:relative;padding-bottom:56.25%;height:0;margin:8px 0"><iframe src="https://www.youtube.com/embed/${id}" style="position:absolute;top:0;left:0;width:100%;height:100%;border:none" allowfullscreen></iframe></div>` : ''
  })

  // ── STEP 4: Strip remaining unknown BBCode tags (keep content) ─────────────
  s = s.replace(/\[[^\]]+\]/g,'')

  // ── STEP 5: Newlines → <br />, then strip br adjacent to block elements ───
  s = s.replace(/\n/g,'<br />')
  const _bl = '(?:pre|table|thead|tbody|tr|td|th|details|blockquote|[uo]l|li|hr|div)'
  s = s.replace(new RegExp(`(?:<br\\s*/?>)+\\s*(<${_bl}[\\s>])`,'gi'),'$1')
  s = s.replace(new RegExp(`(</${_bl}>)\\s*(?:<br\\s*/?>)+`,'gi'),'$1')

  // ── STEP 6: Restore code blocks LAST — content shown as raw escaped text ──
  s = s.replace(/\x02C(\d+)\x02/g, (_, i) => {
    const {lang, code} = _codeStore[parseInt(i)]
    const cls = lang ? ` class="language-${lang.toLowerCase()}"` : ''
    const escaped = code.replace(/^[\r\n]+|[\r\n]+$/g,'')
      .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    return `<pre class="wire-code-pre"><code${cls}>${escaped}</code></pre>`
  })

  return s
}

// BBCode component — renders full HTML as one unit, then finds wire-uimg
// placeholders and decrypts them directly in the DOM via useEffect.
// This means [uimg] inside [spoiler]/[quote]/[table] always works.
function BBCode({ raw }) {
  const ref = useRef(null)
  const html = useMemo(() => parseBBCode(raw), [raw])

  // Apply hljs to code blocks after render
  useEffect(() => {
    if (!ref.current || !window.hljs) return
    ref.current.querySelectorAll('pre.wire-code-pre code').forEach(el => {
      if (!el.dataset.highlighted) {
        try { window.hljs.highlightElement(el) } catch(e) {}
      }
    })
  })

  // Resolve [mention=UID] → @username. Uses module-level cache so same UID is never fetched twice
  useEffect(() => {
    if (!ref.current) return
    const els = [...ref.current.querySelectorAll('.wire-mention[data-uid]')]
    if (!els.length) return

    // Apply anything already in cache immediately
    els.forEach(e => {
      const uid = e.dataset.uid
      if (_mentionCache[uid]) e.textContent = '@' + _mentionCache[uid]
    })

    // Only fetch UIDs not yet cached or in-flight
    const needed = [...new Set(
      els.map(e => e.dataset.uid).filter(uid => !_mentionCache[uid] && !_mentionPending.has(uid))
    )]
    if (!needed.length) return

    needed.forEach(uid => _mentionPending.add(uid))
    api.get(`/api/wire/users/resolve?uids=${needed.join(',')}`)
      .then(map => {
        if (!map) return
        needed.forEach(uid => _mentionPending.delete(uid))
        Object.entries(map).forEach(([uid, name]) => { if (name) _mentionCache[uid] = name })
        if (!ref.current) return
        ref.current.querySelectorAll('.wire-mention[data-uid]').forEach(e => {
          const name = _mentionCache[e.dataset.uid]
          if (name) e.textContent = '@' + name
        })
      })
      .catch(() => { needed.forEach(uid => _mentionPending.delete(uid)) })
  })

  // Decrypt and embed uimg placeholders directly in DOM
  useEffect(() => {    if (!ref.current) return
    ref.current.querySelectorAll('span.wire-uimg[data-url]:not([data-loaded])').forEach(el => {
      el.dataset.loaded = '1'
      const url  = decodeURIComponent(el.dataset.url  || '')
      const size = decodeURIComponent(el.dataset.size || '')

      el.innerHTML = '<span style="display:inline-flex;align-items:center;gap:5px;padding:3px 9px;background:rgba(57,255,20,.06);border:1px solid rgba(57,255,20,.2);border-radius:3px;font-size:11px;color:var(--acc);font-family:monospace">⏳</span>';

      (async () => {
        try {
          const hashPart = url.split('#')[1] || ''
          if (!hashPart.startsWith('E2E1.')) throw new Error('no E2E1 fragment')
          const pieces = hashPart.slice(5).split('.')
          if (pieces.length < 4) throw new Error('bad fragment')
          const seed  = _b64urlDecode(pieces[0])
          const iv    = _b64urlDecode(pieces[1])
          const gwKey = pieces[3]
          const imageId = url.match(/uploadimages\.org\/([a-f0-9]+)/)?.[1]
          if (!imageId) throw new Error('no image id')

          const resp = await fetch(`/api/uimg/${imageId}?key=${encodeURIComponent(gwKey)}`)
          if (!resp.ok) throw new Error(`image ${resp.status}`)

          const key       = await _e2eDeriveKey(seed)
          const decrypted = await crypto.subtle.decrypt({name:'AES-GCM',iv,tagLength:128}, key, await resp.arrayBuffer())
          const blobUrl   = URL.createObjectURL(new Blob([decrypted]))

          const img = document.createElement('img')
          img.src = blobUrl
          img.alt = ''
          img.style.cssText = 'max-width:100%;vertical-align:middle;margin:4px 0'
          if (size) {
            if (/^\d+[x×]\d+$/i.test(size)) {
              const [w,h] = size.split(/[x×]/i)
              img.style.width = w+'px'; img.style.height = h+'px'
            } else if (/^\d+%$/.test(size)) {
              img.style.width = size
            }
          }
          el._uimgBlob = blobUrl
          el.innerHTML = ''
          el.appendChild(img)
        } catch(e) {
          el.innerHTML = `<span style="display:inline-flex;align-items:center;gap:5px;padding:3px 9px;background:rgba(255,68,68,.06);border:1px solid rgba(255,68,68,.2);border-radius:3px;font-size:11px;color:var(--red);font-family:monospace" title="${e.message}">⚠ uimg: ${e.message}</span>`
        }
      })()
    })
  })

  return <div ref={ref} className="wire-body" dangerouslySetInnerHTML={{__html:html}}/>
}

// ── ThreadCard ─────────────────────────────────────────────────────────────────

function ThreadCard({ thread, onRead, me, onRemove, featured }) {
  const [confirmRemove, setConfirmRemove] = useState(false)
  const [hovered, setHovered] = useState(false)
  const canRemove = me.is_lead || thread.curator_uid === me.uid
  const tc = TAG_COLORS[thread.tag] || { color:'var(--sub)', border:'var(--b2)', bg:'var(--s3)', glow:'transparent' }

  const DeleteBtn = () => !canRemove ? null : confirmRemove ? (
    <div style={{display:'flex',gap:4,alignItems:'center'}} onClick={e=>e.stopPropagation()}>
      <span style={{fontSize:9,color:'var(--red)',fontFamily:'var(--mono)'}}>remove?</span>
      <button className="btn btn-danger btn-sm" style={{fontSize:9}}
        onClick={e=>{e.stopPropagation();onRemove(thread.tid);setConfirmRemove(false)}}>YES</button>
      <button className="btn btn-ghost btn-sm" style={{fontSize:9}}
        onClick={e=>{e.stopPropagation();setConfirmRemove(false)}}>NO</button>
    </div>
  ) : (
    <button className="btn btn-sm"
      style={{fontSize:9,padding:'1px 6px',color:'var(--red)',borderColor:'rgba(255,68,68,.2)',
        background:'transparent',opacity:hovered?.7:0,transition:'opacity var(--ease)'}}
      onClick={e=>{e.stopPropagation();setConfirmRemove(true)}}>✕</button>
  )


  if (featured) return (
    <div onClick={()=>onRead(thread)}
      onMouseEnter={()=>setHovered(true)} onMouseLeave={()=>setHovered(false)}
      style={{padding:'16px 22px',borderBottom:'1px solid var(--b1)',
        borderLeft:`3px solid ${hovered?tc.color:tc.border}`,
        background:hovered?tc.bg:'transparent',cursor:'pointer',
        transition:'all var(--ease)',position:'relative'}}>
      <div style={{position:'absolute',top:10,right:12}}><DeleteBtn/></div>
      <div style={{display:'flex',alignItems:'center',gap:8,marginBottom:10}}>
        <TagBadge tag={thread.tag}/>
        {!!thread.closed && <span style={{fontSize:8,padding:'1px 5px',fontFamily:'var(--mono)',
          background:'var(--red2)',color:'var(--red)',border:'1px solid rgba(255,68,68,.3)'}}>CLOSED</span>}
      </div>
      <div style={{fontFamily:'var(--disp)',fontSize:26,color:hovered?tc.color:'#c8d0de',
        lineHeight:1.2,marginBottom:8,paddingRight:32,
        textShadow:hovered?`0 0 20px ${tc.glow}`:'none',transition:'all var(--ease)'}}>
        {thread.subject}
      </div>
      {thread.curator_note && (
        <div style={{fontSize:11,color:'var(--sub)',lineHeight:1.6,fontStyle:'italic',
          marginBottom:10,borderLeft:`2px solid ${tc.border}`,paddingLeft:10,
          overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
          "{thread.curator_note}"
        </div>
      )}
      <div style={{display:'flex',alignItems:'center',gap:8,fontSize:9,color:'var(--dim)',fontFamily:'var(--mono)'}}>
        <span style={{color:'var(--sub)'}}>{thread.author_name||`uid:${thread.author_uid}`}</span>
        <span>·</span><span>{fmtDate(thread.dateline)}</span>
        <span>·</span><span>{thread.fid_name}</span>
        <span style={{marginLeft:'auto',color:tc.color,letterSpacing:'.08em',
          textShadow:`0 0 8px ${tc.glow}`,opacity:hovered?1:.6,transition:'opacity var(--ease)'}}>READ ▶</span>
      </div>
    </div>
  )

  return (
    <div onClick={()=>onRead(thread)}
      onMouseEnter={()=>setHovered(true)} onMouseLeave={()=>setHovered(false)}
      style={{padding:'11px 16px',borderBottom:'1px solid var(--b1)',
        borderLeft:`2px solid ${hovered?tc.color:'transparent'}`,
        background:hovered?tc.bg:'transparent',cursor:'pointer',
        transition:'all var(--ease)',position:'relative'}}>
      <div style={{position:'absolute',top:8,right:10}}><DeleteBtn/></div>
      <div style={{display:'flex',alignItems:'flex-start',gap:8,marginBottom:6,paddingRight:30}}>
        <TagBadge tag={thread.tag} style={{marginTop:3,flexShrink:0}}/>
        {!!thread.closed && <span style={{fontSize:8,padding:'1px 5px',fontFamily:'var(--mono)',
          background:'var(--red2)',color:'var(--red)',border:'1px solid rgba(255,68,68,.3)',flexShrink:0,marginTop:3}}>CLOSED</span>}
        <div style={{fontFamily:'var(--disp)',fontSize:19,color:hovered?tc.color:'#c8d0de',
          lineHeight:1.2,flex:1,textShadow:hovered?`0 0 12px ${tc.glow}`:'none',transition:'all var(--ease)'}}>
          {thread.subject}
        </div>
      </div>
      {thread.curator_note && (
        <div style={{fontSize:10,color:'var(--dim)',lineHeight:1.5,fontStyle:'italic',marginBottom:6,
          overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',paddingRight:30}}>
          "{thread.curator_note}"
        </div>
      )}
      <div style={{display:'flex',alignItems:'center',gap:8,fontSize:9,color:'var(--dim)',fontFamily:'var(--mono)'}}>
        <span style={{color:'var(--sub)'}}>{thread.author_name||`uid:${thread.author_uid}`}</span>
        <span>·</span><span>{fmtDate(thread.dateline)}</span>
        <span>·</span><span>{thread.fid_name}</span>
        <span style={{marginLeft:'auto',fontSize:9,color:'var(--sub)',letterSpacing:'.06em',
          opacity:hovered?1:0,transition:'opacity var(--ease)'}}>READ ▶</span>
      </div>
    </div>
  )
}

// ── Feed ───────────────────────────────────────────────────────────────────────


function Feed({ me, onRead }) {
  const [activeTag,  setActiveTag]  = useState('all')
  const [page,       setPage]       = useState(1)
  const [data,       setData]       = useState(null)
  const [loading,    setLoading]    = useState(true)
  const [search,     setSearch]     = useState('')
  const [searchQ,    setSearchQ]    = useState('')
  const [sort,       setSort]       = useState('recent')
  const [filterOpen, setFilterOpen] = useState(false)
  const filterRef = useRef(null)

  const [hfNews, setHfNews] = useState(null)

    const load = useCallback(async (tag, pg, q, s) => {
    setLoading(true)
    try {
      const qs = q ? `&search=${encodeURIComponent(q)}` : ''
      const r = await api.get(`/api/wire/threads?tag=${tag}&page=${pg}${qs}&sort=${s}`)
      if (r) setData(r)
    } finally { setLoading(false) }
  }, [])

  useEffect(() => { load(activeTag, page, searchQ, sort) }, [activeTag, page, searchQ, sort])

  // Fetch pinned HF News edition once on mount
  useEffect(() => {
    api.get('/api/wire/hf-news').then(r => { if (r?.thread) setHfNews(r.thread) }).catch(()=>{})
  }, [])

  useEffect(() => {
    const t = setTimeout(() => { setSearchQ(search); setPage(1) }, 400)
    return () => clearTimeout(t)
  }, [search])

  // Close filter dropdown on outside click
  useEffect(() => {
    if (!filterOpen) return
    const h = e => { if (filterRef.current && !filterRef.current.contains(e.target)) setFilterOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [filterOpen])

  const switchTag  = t => { setActiveTag(t); setPage(1); setFilterOpen(false) }
  const switchSort = s => { setSort(s); setPage(1) }
  const handleRemove = async tid => { await api.delete(`/api/wire/threads/${tid}`); load(activeTag, page, searchQ, sort) }
  const threads = data?.threads || []

  const SORT_LABELS = { recent: 'Recent', active: 'Active' }
  const TAG_LABELS  = { all:'All', guide:'Guides', tool:'Tools', discussion:'Discussion',
    resource:'Resource', analysis:'Analysis', classic:'Classic', news:'News' }

  // Split threads: first 2 as "featured" (only on unfiltered view), rest as normal
  const isDefault    = activeTag === 'all' && !searchQ && page === 1 && sort === 'recent'
  const featured     = isDefault ? threads.slice(0, 2) : []
  const feedThreads  = isDefault ? threads.slice(2)    : threads

  return (
    <>
      {/* Masthead */}
      <div style={{padding:'18px 22px 14px',borderBottom:'1px solid var(--b1)',background:'var(--bg)'}}>
        <div style={{fontFamily:'var(--disp)',fontSize:44,color:'var(--acc)',lineHeight:1,
          letterSpacing:'.04em',textShadow:'var(--glow-md)',marginBottom:4}}>THE WIRE</div>
        <div style={{fontSize:9,color:'var(--dim)',fontFamily:'var(--mono)',letterSpacing:'.1em'}}>
          // CURATED THREADS FROM HACKFORUMS
        </div>
      </div>

      {/* Controls bar: search + filter dropdown + sort dropdown */}
      <div style={{padding:'8px 22px',borderBottom:'1px solid var(--b1)',background:'var(--s1)',
        display:'flex',gap:8,alignItems:'center'}}>
        {/* Search */}
        <input className="inp" value={search} onChange={e=>setSearch(e.target.value)}
          placeholder="search threads…"
          style={{fontSize:11,padding:'3px 8px',flex:1,minWidth:0}}/>

        {/* Filter dropdown */}
        <div ref={filterRef} style={{position:'relative',flexShrink:0}}>
          <button onClick={()=>setFilterOpen(o=>!o)}
            style={{fontFamily:'var(--mono)',fontSize:10,padding:'3px 10px',cursor:'pointer',
              letterSpacing:'.08em',border:'1px solid',transition:'all var(--ease)',whiteSpace:'nowrap',
              background: activeTag!=='all' ? TAG_COLORS[activeTag]?.bg||'var(--s3)' : 'transparent',
              color:       activeTag!=='all' ? TAG_COLORS[activeTag]?.color||'var(--sub)' : 'var(--sub)',
              borderColor: activeTag!=='all' ? TAG_COLORS[activeTag]?.border||'var(--b2)' : 'var(--b2)',
            }}>
            {TAG_LABELS[activeTag]||activeTag.toUpperCase()} ▾
          </button>
          {filterOpen && (
            <div style={{position:'absolute',top:'calc(100% + 4px)',right:0,zIndex:100,
              background:'var(--card)',border:'1px solid var(--b2)',borderRadius:4,
              boxShadow:'0 8px 24px rgba(0,0,0,.4)',minWidth:140,overflow:'hidden'}}>
              {Object.entries(TAG_LABELS).map(([val,lbl]) => {
                const tc2 = TAG_COLORS[val]
                const active = activeTag===val
                return (
                  <div key={val} onClick={()=>switchTag(val)}
                    style={{padding:'7px 12px',cursor:'pointer',fontSize:10,fontFamily:'var(--mono)',
                      letterSpacing:'.08em',display:'flex',alignItems:'center',gap:8,
                      background: active ? (tc2?.bg||'var(--s3)') : 'transparent',
                      color: active ? (tc2?.color||'var(--acc)') : 'var(--sub)',
                      transition:'background var(--ease)',}}
                    onMouseOver={e=>{ if(!active) e.currentTarget.style.background='var(--hover)' }}
                    onMouseOut={e=>{ if(!active) e.currentTarget.style.background='transparent' }}>
                    {val!=='all' && <span style={{width:6,height:6,borderRadius:'50%',flexShrink:0,
                      background:tc2?.color||'var(--dim)',boxShadow:`0 0 4px ${tc2?.glow||'transparent'}`}}/>}
                    {lbl}
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Sort dropdown */}
        <select value={sort} onChange={e=>switchSort(e.target.value)}
          className="inp" style={{fontSize:10,padding:'3px 6px',flexShrink:0,fontFamily:'var(--mono)',
            letterSpacing:'.06em',cursor:'pointer'}}>
          <option value="recent">Sort: Recent</option>
          <option value="active">Sort: Active</option>
        </select>
      </div>

      {loading ? (
        <div className="empty" style={{padding:60}}><div className="spin"/></div>
      ) : threads.length === 0 ? (
        <div className="empty" style={{padding:60}}>
          <div style={{fontFamily:'var(--disp)',fontSize:32,color:'var(--b3)',marginBottom:8}}>NO SIGNAL</div>
          <div style={{fontFamily:'var(--mono)',fontSize:10,color:'var(--dim)'}}>
            {search ? `no results for "${search}"` : activeTag!=='all' ? `no threads tagged [${activeTag}]` : 'no threads curated yet'}
          </div>
        </div>
      ) : (
        <>
          {/* Pinned HF News — always shown when available */}
          {hfNews && (
            <div style={{borderBottom:'1px solid var(--b1)'}}>
              <div style={{padding:'8px 22px 6px',background:'var(--bg)',display:'flex',alignItems:'center',gap:8}}>
                <span style={{fontSize:8,fontFamily:'var(--mono)',letterSpacing:'.14em',color:'#ff4444'}}>📰 HF NEWS</span>
              </div>
              <ThreadCard thread={hfNews} me={me} onRead={onRead} onRemove={handleRemove} featured/>
            </div>
          )}

          {/* Featured section — top 2 on default view */}
          {featured.length > 0 && (
            <>
              <div style={{padding:'8px 22px 6px',background:'var(--bg)',
                borderBottom:'1px solid var(--b1)',display:'flex',alignItems:'center',gap:8}}>
                <span style={{fontSize:8,fontFamily:'var(--mono)',letterSpacing:'.14em',color:'var(--dim)'}}>🔥 FEATURED</span>
              </div>
              {featured.map(t => (
                <ThreadCard key={t.tid} thread={t} me={me} onRead={onRead} onRemove={handleRemove} featured/>
              ))}
              <div style={{padding:'8px 22px 6px',background:'var(--bg)',
                borderBottom:'1px solid var(--b1)',marginTop:4}}>
                <span style={{fontSize:8,fontFamily:'var(--mono)',letterSpacing:'.14em',color:'var(--dim)'}}>📋 ALL THREADS</span>
              </div>
            </>
          )}
          {feedThreads.map(t => (
            <ThreadCard key={t.tid} thread={t} me={me} onRead={onRead} onRemove={handleRemove}/>
          ))}
          {data.pages > 1 && (
            <div className="pg" style={{padding:'10px 22px'}}>
              <button className="pg-btn" disabled={page<=1} onClick={()=>setPage(p=>p-1)}>←</button>
              <span className="pg-info">{page} / {data.pages}</span>
              <button className="pg-btn" disabled={page>=data.pages} onClick={()=>setPage(p=>p+1)}>→</button>
            </div>
          )}
        </>
      )}
    </>
  )
}

// ── ThreadReader ───────────────────────────────────────────────────────────────

function ThreadReader({ thread: initialThread, onBack }) {
  const [thread,       setThread]       = useState(initialThread)
  const [repliesOpen,  setRepliesOpen]  = useState(false)
  const [replies,      setReplies]      = useState([])
  const [replyPage,    setReplyPage]    = useState(1)
  const [cachedAt,     setCachedAt]     = useState(null)
  const [replyLoading, setReplyLoading] = useState(false)
  const [replyMsg,     setReplyMsg]     = useState('')
  const [posting,      setPosting]      = useState(false)
  const [postErr,      setPostErr]      = useState('')
  const [postOk,       setPostOk]       = useState(false)
  const [refreshing,   setRefreshing]   = useState(false)
  const [refreshLeft,  setRefreshLeft]  = useState(3)
  const [refreshMsg,   setRefreshMsg]   = useState('')
  const [showTop,      setShowTop]      = useState(false)
  const scrollRef = useRef(null)

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const onScroll = () => setShowTop(el.scrollTop > 300)
    el.addEventListener('scroll', onScroll)
    return () => el.removeEventListener('scroll', onScroll)
  }, [])

  const OLD_THRESHOLD = 86400 * 180
  const isOld  = thread.lastpost && (Date.now()/1000 - thread.lastpost) > OLD_THRESHOLD
  const closed = !!thread.closed
  const tc = TAG_COLORS[thread.tag] || { color:'var(--sub)', border:'var(--b2)', bg:'var(--s3)', glow:'transparent' }

  const loadReplies = useCallback(async (page=1, refresh=false) => {
    setReplyLoading(true)
    try {
      const r = await api.get(`/api/wire/thread/${thread.tid}/replies?page=${page}${refresh?'&refresh=true':''}`)
      if (r?.replies) { setReplies(r.replies); setCachedAt(r.cached_at); setReplyPage(page) }
    } finally { setReplyLoading(false) }
  }, [thread.tid])

  const toggleReplies = () => {
    if (!repliesOpen) { setRepliesOpen(true); if (!replies.length) loadReplies(1) }
    else setRepliesOpen(false)
  }

  const postReply = async () => {
    if (!replyMsg.trim()||posting) return
    setPosting(true); setPostErr(''); setPostOk(false)
    try {
      const r = await api.post(`/api/wire/thread/${thread.tid}/reply`,{message:replyMsg})
      if (r?.ok) { setPostOk(true); setReplyMsg(''); if (repliesOpen) loadReplies(replyPage,true) }
      else setPostErr(r?.detail||'Reply failed')
    } catch(e) { setPostErr(e?.message||'Error') } finally { setPosting(false) }
  }

  const hfUrl = `https://hackforums.net/showthread.php?tid=${thread.tid}`

  const doRefresh = async () => {
    if (refreshing || refreshLeft <= 0) return
    setRefreshing(true); setRefreshMsg('')
    try {
      const r = await api.post(`/api/wire/thread/${thread.tid}/refresh`, {})
      if (r?.ok) {
        if (r.thread) setThread(r.thread)
        setRefreshLeft(r.refreshes_left ?? 0)
        setRefreshMsg('updated')
        setTimeout(() => setRefreshMsg(''), 3000)
      } else {
        setRefreshMsg(r?.detail || 'refresh failed')
      }
    } catch(e) { setRefreshMsg(e?.message || 'error') }
    finally { setRefreshing(false) }
  }

  return (
    <div ref={scrollRef} style={{display:'flex',flexDirection:'column',overflowY:'auto',maxHeight:'calc(100vh - var(--topbar-h) - 20px)'}}>

      {/* Back to top — fixed inside reader, appears after scrolling */}
      {showTop && (
        <button onClick={() => scrollRef.current?.scrollTo({top:0,behavior:'smooth'})}
          style={{
            position:'sticky',top:4,zIndex:10,marginLeft:'auto',marginRight:12,
            background:'var(--s3)',border:'1px solid var(--b3)',color:'var(--sub)',
            fontFamily:'var(--mono)',fontSize:9,padding:'3px 8px',cursor:'pointer',
            letterSpacing:'.08em',transition:'all var(--ease)',alignSelf:'flex-end',
          }}
          onMouseOver={e=>e.currentTarget.style.color='var(--acc)'}
          onMouseOut={e=>e.currentTarget.style.color='var(--sub)'}>
          ↑ TOP
        </button>
      )}

      {/* Nav breadcrumb */}
      <div style={{padding:'8px 16px',borderBottom:'1px solid var(--b1)',background:'var(--bg)',display:'flex',alignItems:'center',gap:10}}>
        <button onClick={onBack} style={{background:'none',border:'none',color:'var(--dim)',fontSize:10,cursor:'pointer',fontFamily:'var(--mono)',padding:0,letterSpacing:'.08em'}}
          onMouseOver={e=>e.currentTarget.style.color='var(--acc)'}
          onMouseOut={e=>e.currentTarget.style.color='var(--dim)'}>
          ← WIRE
        </button>
        <span style={{fontSize:9,color:'var(--b3)',fontFamily:'var(--mono)'}}>/</span>
        <TagBadge tag={thread.tag}/>
        <a href={hfUrl} target="_blank" rel="noopener noreferrer"
          style={{marginLeft:'auto',fontSize:9,color:'var(--blue)',fontFamily:'var(--mono)',letterSpacing:'.06em'}}>
          HF ↗
        </a>
        <button
          className="btn btn-ghost btn-sm"
          style={{fontSize:9, opacity: refreshLeft<=0 ? .3 : 1}}
          disabled={refreshing || refreshLeft<=0}
          onClick={doRefresh}
          title={`Refresh thread data from HF (${refreshLeft} left this hour)`}
        >
          {refreshing ? '…' : '↻ REFRESH'}
        </button>
        {refreshMsg && (
          <span style={{fontSize:9, color: refreshMsg==='updated' ? 'var(--acc)' : 'var(--red)', fontFamily:'var(--mono)'}}>
            {refreshMsg}
          </span>
        )}
      </div>

      {/* Hero */}
      <div style={{padding:'22px 22px 18px',borderBottom:'1px solid var(--b1)',background:'var(--bg)',borderLeft:`3px solid ${tc.color}`}}>
        <div style={{display:'flex',alignItems:'center',gap:6,marginBottom:12}}>
          <TagBadge tag={thread.tag}/>
          {closed && <span style={{fontSize:8,padding:'1px 5px',fontFamily:'var(--mono)',letterSpacing:'.08em',background:'var(--red2)',color:'var(--red)',border:'1px solid rgba(255,68,68,.3)'}}>CLOSED</span>}
          <span style={{fontSize:9,color:'var(--dim)',fontFamily:'var(--mono)',marginLeft:'auto'}}>{thread.fid_name} · {fmtDateFull(thread.dateline)}</span>
        </div>
        <div style={{
          fontFamily:'var(--disp)', fontSize:36, color:tc.color,
          lineHeight:1.15, letterSpacing:'.03em',
          textShadow:`0 0 28px ${tc.glow}`, marginBottom:16,
        }}>
          {thread.subject}
        </div>
        {/* Author */}
        <div style={{display:'flex',alignItems:'center',gap:10}}>
          <div style={{
            width:32,height:32,flexShrink:0,background:'var(--s3)',
            border:`1px solid ${tc.border}`,overflow:'hidden',
            display:'flex',alignItems:'center',justifyContent:'center',
            fontFamily:'var(--disp)',fontSize:18,color:tc.color,
          }}>
            {thread.author_avatar
              ? <img src={thread.author_avatar} alt="" style={{width:'100%',height:'100%',objectFit:'cover'}} onError={e=>e.currentTarget.style.display='none'}/>
              : (thread.author_name||'?').slice(0,2).toUpperCase()}
          </div>
          <div style={{flex:1,minWidth:0}}>
            <div style={{display:'flex',alignItems:'center',gap:8,marginBottom:2,flexWrap:'wrap'}}>
              <span style={{fontSize:12,color:'var(--text)',fontFamily:'var(--mono)'}}>{thread.author_name||`uid:${thread.author_uid}`}</span>
              {thread.author_reputation && thread.author_reputation!=='0' && (
                <span style={{fontSize:10,color:'var(--acc)',fontFamily:'var(--mono)'}}>+{thread.author_reputation}</span>
              )}
            </div>
            {thread.author_usertitle && <div style={{fontSize:9,color:'var(--dim)',fontFamily:'var(--mono)',marginBottom:3}}>{thread.author_usertitle}</div>}
            <GroupTags groups={thread.author_groups}/>
          </div>
          <div style={{display:'flex',gap:6}}>
            <a href={hfUrl} target="_blank" rel="noopener noreferrer" style={{textDecoration:'none'}}>
              <button className="btn btn-ghost btn-sm" style={{fontSize:9}}>↗ HACKFORUMS</button>
            </a>
          </div>
        </div>
      </div>

      {/* Post body */}
      <div style={{padding:'16px 20px',borderBottom:'1px solid var(--b1)',background:'#333'}}>
        <BBCode raw={thread.firstpost_content}/>
      </div>

      {/* Additional posts — multipost threads (HF News style) */}
      {!!thread.is_multipost && thread.secondpost_content && (
        <div style={{padding:'16px 20px',borderBottom:'1px solid var(--b1)',background:'#2e2e2e',
          borderLeft:`3px solid ${tc.border}`}}>
          <div style={{fontSize:8,color:'var(--dim)',fontFamily:'var(--mono)',letterSpacing:'.1em',marginBottom:8}}>// CONTINUED</div>
          <BBCode raw={thread.secondpost_content}/>
        </div>
      )}
      {(() => {
        if (!thread.extra_posts) return null
        try {
          const extras = JSON.parse(thread.extra_posts)
          if (!extras?.length) return null
          return extras.map((ep, i) => ep?.message ? (
            <div key={ep.pid||i} style={{padding:'16px 20px',borderBottom:'1px solid var(--b1)',
              background:i%2===0?'#2a2a2a':'#2e2e2e',borderLeft:`3px solid ${tc.border}`}}>
              <div style={{fontSize:8,color:'var(--dim)',fontFamily:'var(--mono)',letterSpacing:'.1em',marginBottom:8}}>// CONTINUED ({i+2})</div>
              <BBCode raw={ep.message}/>
            </div>
          ) : null)
        } catch { return null }
      })()}

      {/* Replies */}
      <div style={{display:'flex',alignItems:'center',gap:8,padding:'8px 16px',borderBottom:'1px solid var(--b1)',background:'var(--s1)',cursor:'pointer'}} onClick={toggleReplies}>
        <span style={{fontSize:10,color:'var(--sub)',fontFamily:'var(--mono)',letterSpacing:'.1em',fontWeight:600}}>REPLIES</span>
        {cachedAt && <span style={{fontSize:9,color:'var(--dim)',fontFamily:'var(--mono)'}}>cached {ago(cachedAt)} ago</span>}
        <div style={{marginLeft:'auto',display:'flex',gap:6}}>
          {repliesOpen && cachedAt && (
            <button className="btn btn-ghost btn-sm" style={{fontSize:9}} onClick={e=>{e.stopPropagation();loadReplies(replyPage,true)}}>↻</button>
          )}
          <button className="btn btn-ghost btn-sm" style={{fontSize:9}} onClick={e=>{e.stopPropagation();toggleReplies()}}>
            {repliesOpen?'COLLAPSE':'LOAD'}
          </button>
        </div>
      </div>

      {repliesOpen && (
        <div style={{borderBottom:'1px solid var(--b1)'}}>
          {replyLoading ? (
            <div className="empty" style={{padding:20}}><div className="spin"/></div>
          ) : replies.length===0 ? (
            <div className="empty" style={{padding:20,fontSize:10}}>no replies cached</div>
          ) : (
            <>
              {replies.filter(r => {
                if (String(r.pid) === String(thread.firstpost_pid)) return false
                if (!!thread.is_multipost && thread.secondpost_pid && String(r.pid) === String(thread.secondpost_pid)) return false
                if (thread.extra_posts) {
                  try {
                    const extras = JSON.parse(thread.extra_posts)
                    if (extras?.some(ep => ep?.pid && String(ep.pid) === String(r.pid))) return false
                  } catch {}
                }
                return true
              }).map(r=>(
                <div key={r.pid} style={{display:'flex',gap:10,padding:'10px 16px',borderBottom:'1px solid var(--b1)'}}>
                  <div style={{
                    width:26,height:26,minWidth:26,flexShrink:0,
                    background:'var(--s3)',border:'1px solid var(--b2)',
                    overflow:'hidden',display:'flex',alignItems:'center',justifyContent:'center',
                    fontSize:13,color:'var(--dim)',fontFamily:'var(--disp)',
                  }}>
                    {r.avatar
                      ? <img src={r.avatar} alt="" style={{width:'100%',height:'100%',objectFit:'cover'}} onError={e=>e.currentTarget.style.display='none'}/>
                      : (r.username||'?').slice(0,1).toUpperCase()}
                  </div>
                  <div style={{flex:1,minWidth:0}}>
                    <div style={{display:'flex',alignItems:'center',gap:8,marginBottom:6}}>
                      <span style={{fontSize:11,color:'var(--acc)',fontFamily:'var(--mono)'}}>{r.username}</span>
                      <span style={{fontSize:9,color:'var(--dim)',fontFamily:'var(--mono)',marginLeft:'auto'}}>{fmtDateFull(r.dateline)}</span>
                    </div>
                    <div style={{background:'#333',padding:'6px 0'}}><BBCode raw={r.message}/></div>
                  </div>
                </div>
              ))}
              <div className="pg" style={{padding:'8px 16px'}}>
                <button className="pg-btn" disabled={replyPage<=1} onClick={()=>loadReplies(replyPage-1)}>←</button>
                <span className="pg-info">page {replyPage}</span>
                <button className="pg-btn" disabled={replies.length<30} onClick={()=>loadReplies(replyPage+1)}>→</button>
              </div>
            </>
          )}
        </div>
      )}

      {/* Reply box */}
      <div style={{padding:'14px 16px',background:'var(--s1)'}}>
        {isOld && !closed && (
          <div style={{background:'var(--yellow2)',border:'1px solid rgba(255,187,0,.25)',padding:'5px 10px',fontSize:9,color:'var(--yellow)',fontFamily:'var(--mono)',marginBottom:8}}>
            ⚠ last activity {ago(thread.lastpost)} ago — replying will bump an old thread
          </div>
        )}
        {closed ? (
          <div style={{fontSize:10,color:'var(--dim)',fontFamily:'var(--mono)',padding:'6px 0'}}>
            {'> '}<span style={{color:'var(--red)'}}>THREAD CLOSED</span> — replies are disabled.
          </div>
        ) : (
          <>
            <textarea className="inp" style={{width:'100%',height:70,resize:'none',fontSize:11}}
              placeholder="Reply… (BBCode supported)" value={replyMsg} onChange={e=>setReplyMsg(e.target.value)}/>
            <div style={{display:'flex',alignItems:'center',gap:8,marginTop:7}}>
              <button className="btn btn-acc btn-sm" onClick={postReply} disabled={posting}>
                {posting?'POSTING…':'POST REPLY'}
              </button>
              <span style={{fontSize:9,color:'var(--dim)',fontFamily:'var(--mono)',marginLeft:'auto'}}>{replyMsg.length} / 8000</span>
            </div>
            {postErr && <div style={{fontSize:10,color:'var(--red)',marginTop:6,fontFamily:'var(--mono)'}}>{'> '}{postErr}</div>}
            {postOk  && <div style={{fontSize:10,color:'var(--acc)',marginTop:6,fontFamily:'var(--mono)'}}>{'> reply posted'}</div>}
          </>
        )}
      </div>
    </div>
  )
}

// ── Manage ─────────────────────────────────────────────────────────────────────

function Section({ title, children }) {
  return (
    <div style={{marginBottom:24}}>
      <div style={{fontSize:9,color:'var(--acc)',fontFamily:'var(--mono)',letterSpacing:'.12em',textTransform:'uppercase',marginBottom:12,paddingBottom:6,borderBottom:'1px solid var(--b1)',textShadow:'var(--glow-sm)'}}>
        {'// '}{title}
      </div>
      {children}
    </div>
  )
}

function SubmitForm({ onSubmitted }) {
  const [url,          setUrl]          = useState('')
  const [tag,          setTag]          = useState('guide')
  const [note,         setNote]         = useState('')
  const [postCount,    setPostCount]    = useState(1)
  const [isHfNews,     setIsHfNews]     = useState(false)
  const [busy,         setBusy]         = useState(false)
  const [err,  setErr]  = useState('')
  const [ok,   setOk]   = useState('')

  const submit = async () => {
    if (!url.trim()) { setErr('Enter a TID or HF thread URL'); return }
    setBusy(true); setErr(''); setOk('')
    try {
      const r = await api.post('/api/wire/threads', { url: url.trim(), tag, note, post_count: postCount, is_hf_news: isHfNews })
      if (r?.ok) { setOk(`Added: "${r.subject}"`); setUrl(''); setNote(''); onSubmitted() }
      else setErr(r?.detail||'Submission failed')
    } catch(e) { setErr(e?.message||'Error') } finally { setBusy(false) }
  }

  return (
    <Section title="Submit Thread">
      <div style={{display:'grid',gridTemplateColumns:'1fr auto',gap:8,marginBottom:10}}>
        <input className="inp" style={{width:'100%'}} placeholder="hackforums.net/showthread.php?tid=... or just the TID"
          value={url} onChange={e=>setUrl(e.target.value)}/>
        <select className="inp" value={tag} onChange={e=>setTag(e.target.value)}>
          {SUBMIT_TAGS.map(t=><option key={t} value={t}>{t.toUpperCase()}</option>)}
        </select>
      </div>
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fill,minmax(180px,1fr))',gap:4,marginBottom:12}}>
        {SUBMIT_TAGS.map(t => {
          const tc2 = TAG_COLORS[t]; const active = tag===t
          return (
            <div key={t} onClick={()=>setTag(t)} style={{
              padding:'6px 10px',cursor:'pointer',
              background:active?tc2.bg:'var(--bg)',
              border:`1px solid ${active?tc2.border:'var(--b1)'}`,
              borderLeft:`2px solid ${active?tc2.color:'transparent'}`,
              transition:'all var(--ease)',
            }}>
              <div style={{fontSize:9,fontFamily:'var(--mono)',letterSpacing:'.08em',color:active?tc2.color:'var(--sub)',marginBottom:2,textShadow:active?`0 0 6px ${tc2.glow}`:'none'}}>
                {t.toUpperCase()}
              </div>
              <div style={{fontSize:9,color:'var(--dim)'}}>{TAG_DESC[t]}</div>
            </div>
          )
        })}
      </div>
      <div style={{marginBottom:12}}>
        <div className="col-lbl" style={{marginBottom:5}}>CURATOR NOTE <span style={{color:'var(--dim)',textTransform:'none',letterSpacing:'normal',fontSize:8}}>(optional — why is this worth reading?)</span></div>
        <textarea className="inp" style={{width:'100%',height:60,resize:'none'}}
          placeholder="e.g. Best writeup on this topic I've seen. Still relevant."
          value={note} onChange={e=>setNote(e.target.value)}/>
      </div>
      <div style={{display:'flex',alignItems:'center',gap:10}}>
        <button className="btn btn-acc" onClick={submit} disabled={busy}>{busy?'FETCHING…':'SUBMIT THREAD'}</button>
        <div style={{display:'flex',alignItems:'center',gap:12,flexWrap:'wrap'}}>
          <label style={{display:'flex',alignItems:'center',gap:6,cursor:'pointer',fontSize:10,color:'var(--sub)',fontFamily:'var(--mono)'}}>
            <span style={{color:'var(--dim)'}}>Posts to fetch:</span>
            <select value={postCount} onChange={e=>setPostCount(Number(e.target.value))}
              className="inp" style={{fontSize:10,padding:'2px 6px',fontFamily:'var(--mono)',width:55,cursor:'pointer'}}>
              {[1,2,3,4,5,6,7,8].map(n=><option key={n} value={n}>{n}</option>)}
            </select>
            <span style={{color:'var(--dim)',fontSize:9}}>{postCount===1?'(OP only)':'(OP + '+( postCount-1)+' repl'+(postCount===2?'y':'ies')+')'}</span>
          </label>
          <label style={{display:'flex',alignItems:'center',gap:6,cursor:'pointer',fontSize:10,color:'var(--sub)',fontFamily:'var(--mono)'}}>
            <input type="checkbox" checked={isHfNews} onChange={e=>setIsHfNews(e.target.checked)} style={{cursor:'pointer'}}/>
            <span style={{color:isHfNews?'#ff4444':'var(--dim)'}}>HF News Edition</span>
            <span style={{color:'var(--dim)',fontSize:9}}>(pins to top of Wire)</span>
          </label>
        </div>
        {err && <span style={{fontSize:10,color:'var(--red)',fontFamily:'var(--mono)'}}>{'> '}{err}</span>}
        {ok  && <span style={{fontSize:10,color:'var(--acc)',fontFamily:'var(--mono)'}}>{'> '}{ok}</span>}
      </div>
    </Section>
  )
}

function MySubmissions({ refreshKey }) {
  const [subs, setSubs] = useState(null)
  useEffect(() => {
    api.get('/api/wire/my-submissions').then(r=>{ if(r) setSubs(r.submissions) }).catch(()=>{})
  }, [refreshKey])
  if (subs===null) return <div className="empty" style={{padding:20}}><div className="spin"/></div>
  return (
    <Section title={`Your Submissions (${subs.length})`}>
      {subs.length===0 ? (
        <div style={{fontSize:10,color:'var(--dim)',fontFamily:'var(--mono)'}}>{'> none yet'}</div>
      ) : (
        <div>
          {subs.map(t=>(
            <div key={t.tid} style={{display:'grid',gridTemplateColumns:'auto 1fr auto',gap:10,alignItems:'center',padding:'7px 0',borderBottom:'1px solid var(--b1)'}}>
              <TagBadge tag={t.tag}/>
              <div style={{minWidth:0}}>
                <div style={{fontSize:12,color:'var(--text)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{t.subject}</div>
                <div style={{fontSize:9,color:'var(--dim)',fontFamily:'var(--mono)',marginTop:2}}>{fmtDate(t.dateline)} · added {ago(t.added_at)} ago</div>
              </div>
              <span style={{fontSize:9,color:'var(--dim)',fontFamily:'var(--mono)',whiteSpace:'nowrap'}}>{t.tid}</span>
            </div>
          ))}
        </div>
      )}
    </Section>
  )
}

function CuratorRoster({ me, refreshKey }) {
  const [curators, setCurators] = useState(null)
  const [addUid,   setAddUid]   = useState('')
  const [addRole,  setAddRole]  = useState('curator')
  const [addBusy,  setAddBusy]  = useState(false)
  const [addErr,   setAddErr]   = useState('')

  const load = () => { api.get('/api/wire/curators').then(r=>{ if(r) setCurators(r.curators) }).catch(()=>{}) }
  useEffect(load, [refreshKey])

  const addCurator = async () => {
    if (!addUid.trim()) { setAddErr('Enter a UID'); return }
    setAddBusy(true); setAddErr('')
    try {
      const r = await api.post('/api/wire/curators',{uid:addUid.trim(),role:addRole})
      if (r?.ok) { setAddUid(''); load() } else setAddErr(r?.detail||'Failed')
    } catch(e) { setAddErr(e?.message||'Error') } finally { setAddBusy(false) }
  }

  const removeCurator = async uid => { await api.delete(`/api/wire/curators/${uid}`); load() }
  const setRole = async (uid,role) => { await api.patch(`/api/wire/curators/${uid}`,{role}); load() }

  if (curators===null) return <div className="empty" style={{padding:20}}><div className="spin"/></div>

  return (
    <Section title="Curator Roster">
      <div style={{marginBottom:8,padding:'7px 10px',background:'var(--bg)',border:'1px solid var(--b1)',borderLeft:'2px solid var(--red)',display:'flex',alignItems:'center',gap:10}}>
        <span style={{fontSize:10,color:'var(--text)',fontFamily:'var(--mono)',flex:1}}>{me.uid} <span style={{color:'var(--dim)'}}>· you</span></span>
        <span className="badge" style={ROLE_BADGE.lead.style}>LEAD</span>
      </div>
      {curators.map(c => {
        const rb = ROLE_BADGE[c.role]||ROLE_BADGE.curator
        return (
          <div key={c.uid} style={{display:'flex',alignItems:'center',gap:8,padding:'7px 10px',borderBottom:'1px solid var(--b1)',background:'var(--bg)'}}>
            <span style={{fontSize:10,color:'var(--text)',fontFamily:'var(--mono)',flex:1}}>{c.uid}{c.username&&<span style={{color:'var(--sub)'}}> · {c.username}</span>}</span>
            <span className="badge" style={rb.style}>{rb.label}</span>
            {me.is_admin && (
              <div style={{display:'flex',gap:4}}>
                {c.role==='curator'&&<button className="btn btn-ghost btn-sm" style={{fontSize:8,padding:'1px 6px'}} onClick={()=>setRole(c.uid,'lead')}>↑ LEAD</button>}
                {c.role==='lead'&&<button className="btn btn-ghost btn-sm" style={{fontSize:8,padding:'1px 6px'}} onClick={()=>setRole(c.uid,'curator')}>↓ CURATOR</button>}
                <button className="btn btn-danger btn-sm" style={{fontSize:8,padding:'1px 6px'}} onClick={()=>removeCurator(c.uid)}>✕</button>
              </div>
            )}
            {!me.is_admin&&me.is_lead&&c.role==='curator'&&(
              <button className="btn btn-danger btn-sm" style={{fontSize:8,padding:'1px 6px'}} onClick={()=>removeCurator(c.uid)}>✕</button>
            )}
          </div>
        )
      })}
      <div style={{marginTop:12,display:'flex',gap:8,alignItems:'flex-start',flexWrap:'wrap'}}>
        <input className="inp" style={{width:150}} placeholder="UID or profile URL" value={addUid} onChange={e=>setAddUid(parseHfId(e.target.value,'uid'))}/>
        {me.is_admin && (
          <select className="inp" value={addRole} onChange={e=>setAddRole(e.target.value)}>
            <option value="curator">CURATOR</option>
            <option value="lead">LEAD</option>
          </select>
        )}
        <button className="btn btn-acc" onClick={addCurator} disabled={addBusy}>{addBusy?'…':'+ ADD'}</button>
        {addErr&&<span style={{fontSize:9,color:'var(--red)',fontFamily:'var(--mono)',alignSelf:'center'}}>{addErr}</span>}
      </div>
      <div style={{marginTop:10,fontSize:9,color:'var(--dim)',fontFamily:'var(--mono)',lineHeight:1.9}}>
        <div>CURATOR — submit threads, remove own submissions</div>
        <div>LEAD — add/remove curators</div>
      </div>
    </Section>
  )
}

function ManageView({ me }) {
  const [refreshKey, setRefreshKey] = useState(0)
  const bump = () => setRefreshKey(k=>k+1)
  return (
    <div style={{padding:'20px 22px'}}>
      <SubmitForm onSubmitted={bump}/>
      <MySubmissions refreshKey={refreshKey}/>
      {me.is_lead && <CuratorRoster me={me} refreshKey={refreshKey}/>}
    </div>
  )
}

// ── Root ───────────────────────────────────────────────────────────────────────

// Wrapper handles the group gate — inner component owns all hooks (Rules of Hooks)
export default function WirePage() {
  const user = useStore(s => s.user)
  return <WirePageInner />
}

function WirePageInner() {
  const [me,         setMe]         = useState({role:'none',is_curator:false,is_lead:false,is_admin:false})
  const [view,       setView]       = useState('feed')
  const [openThread, setOpenThread] = useState(null)

  // Load highlight.js from CDN once — used by BBCode component for code blocks
  useEffect(() => {
    if (window.hljs) return
    if (!document.getElementById('hljs-theme')) {
      const link = document.createElement('link')
      link.id = 'hljs-theme'
      link.rel = 'stylesheet'
      link.href = 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.11.1/styles/atom-one-dark.min.css'
      document.head.appendChild(link)
    }
    if (!document.getElementById('hljs-script')) {
      const script = document.createElement('script')
      script.id = 'hljs-script'
      script.src = 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.11.1/highlight.min.js'
      document.head.appendChild(script)
    }
  }, [])

  useEffect(() => {
    api.get('/api/wire/me').then(r=>{ if(r) setMe({...r,uid:r.uid}) }).catch(()=>{})
    // /api/profile 401s if not logged in — only call it if we have a session
    api.get('/auth/me').then(r=>{ if(r?.uid) api.get('/api/profile').then(p=>{ if(p?.uid) setMe(prev=>({...prev,uid:String(p.uid)})) }).catch(()=>{}) }).catch(()=>{})
  }, [])

  const handleRead = async thread => {
    const full = await api.get(`/api/wire/thread/${thread.tid}`).catch(()=>null)
    setOpenThread(full||thread); setView('reader')
  }
  const handleBack = () => { setOpenThread(null); setView('feed') }

  return (
    <div className="card" style={{padding:0,overflow:'hidden'}}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Amarante&family=Cinzel:wght@400..900&family=Graduate&family=New+Rocker&family=Orbitron:wght@400..900&display=swap');
        @import url('https://hackforums.net/cache/themes/theme12/award.css');
        @keyframes brotherhood-shine{0%{background-position:300% center}100%{background-position:-300% center}}
        @keyframes vibe-glitch{0%,10%,50%,72%,100%{transform:translate(0)}4%{transform:translate(-1px,0)}5%{transform:translate(1px,0)}8%{transform:translate(-2px,1px)}9%{transform:translate(2px,-1px)}70%{transform:translate(-1px,0)}71%{transform:translate(1px,0)}}
        @keyframes lasers{0%{background-position:0% 50%}100%{background-position:100% 50%}}
        .group2{color:#efefef;text-decoration:none}
        .group6{color:#AAAAFF;font-weight:bold}
        .group7{color:#000;text-decoration:none}
        .group9{color:#FFCC00}
        .group12{color:#F3CB90!important;font-weight:bold}
        .group23{color:#00cc66!important;font-weight:bold}
        .group24{color:#AA00FF}
        .group28{color:#0066FF}
        .group38{color:#ccc;text-decoration:line-through}
        .group46{color:#222!important;font-family:"Amarante",serif;font-weight:bold;text-shadow:-1px -1px 0 #0f0,-1px 1px 0 #0f0,1px -1px 0 #0f0,1px 1px 0 #0f0,0 0 5px #0f0,0 0 10px #0f0,0 0 15px #080}
        .group48{color:#dfcbff!important;font-family:"New Rocker",system-ui;font-weight:bold;letter-spacing:1.75px;text-shadow:0 0 1px #b380ff,0 0 3px #9933ff,0 0 6px #7722cc,0 0 12px #550099}
        .group49{color:#ed1c24!important}
        .group50{font-weight:700;font-family:"Cinzel",serif;letter-spacing:2px;background:linear-gradient(135deg,#FFD700,#FFC200,#B8860B);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
        .group52{color:#FF99CC!important;font-family:"Comic Sans MS",cursive!important;font-weight:bold;text-shadow:2px 2px 2px #4020dd}
        .group53{color:#1a1a1a!important;text-shadow:0 2px 8px #eaeaea;font-weight:bold}
        .group54{color:#40074E!important;text-shadow:1px 1px #e30ee9}
        .group56{color:#171717!important;text-shadow:1.7px 1.6px 1.6px #b5252d;font-weight:bold}
        .group57{color:#fff!important;font-weight:bold;text-shadow:0 2px 2px #fa0606}
        .group59{color:#1ecafe!important;font-weight:bold;text-shadow:0 2px 2px #000}
        .group63{color:#EC7E03!important;text-shadow:1px 1px 1px #000}
        .group67{color:#2D7E52!important;font-weight:bold;text-shadow:0 2px 3px #000}
        .group68{font-family:'Cinzel',serif;font-weight:900;letter-spacing:1.15px;background:linear-gradient(90deg,#9a9a9a 0%,#cfcfcf 20%,#fff 35%,#fff 45%,#e6e6e6 55%,#cfcfcf 70%,#9a9a9a 100%);background-size:300% auto;animation:brotherhood-shine 4s ease-in-out infinite;-webkit-background-clip:text;-webkit-text-fill-color:transparent}
        .group70{color:#ff54a1!important;font-weight:bold;text-shadow:2px 2px 2px #000}
        .group71{color:#00feb0!important;text-shadow:0 2px 3px #000}
        .group75{color:#99CCFF!important;font-weight:bold}
        .group77{color:#fff!important;font-family:Graduate,sans-serif;letter-spacing:2px;text-shadow:-1px -1px 0 #467fff,1px -1px 0 #098ed9,-1px 1px 0 #1199df,1px 1px 0 #139add,0 0 5px #529ec0,0 0 10px #56cad8,0 0 15px #4abfd6}
        .group78{display:inline-block;font-family:'Orbitron','Cinzel',serif;font-weight:900;letter-spacing:1.15px;background:linear-gradient(90deg,#00ffb2 0%,#00e6ff 35%,#b7fff1 50%,#00e6ff 65%,#00ffb2 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;animation:vibe-glitch 3.5s infinite}
        .wire-code-pre{margin:8px 0;border-radius:4px;overflow:auto;font-size:12px;line-height:1.55;background:#0f1115!important;border:1px solid rgba(255,255,255,.08)!important;max-height:380px;overflow-y:auto}
        .wire-code-pre code{font-family:Consolas,Monaco,'Courier New',monospace!important;display:block;padding:14px!important;white-space:pre-wrap}
        .wire-body table tr:nth-child(even) td{background:rgba(255,255,255,.03)}
        .wire-body .wire-code{background:#0f1115;border:1px solid rgba(255,255,255,.08);padding:14px;margin:8px 0;font-family:Consolas,Monaco,monospace;font-size:12px;white-space:pre-wrap;overflow-x:auto}
        .wire-body blockquote cite{font-family:Verdana,sans-serif}
        .wire-body{font-family:Verdana,Arial,sans-serif;font-size:13px;line-height:1.6;color:#ccc}
        .wire-body img{max-width:100%;height:auto}
      `}</style>
      {view !== 'reader' && (
        <div className="card-head">
          <span className="card-title">// THE WIRE</span>
          <div style={{display:'flex',gap:0,marginLeft:'auto'}}>
            <button className={`tab${view==='feed'?' on':''}`} style={{padding:'4px 12px',fontSize:10}} onClick={()=>setView('feed')}>FEED</button>
            {me.is_curator && (
              <button className={`tab${view==='manage'?' on':''}`} style={{padding:'4px 12px',fontSize:10}} onClick={()=>setView('manage')}>MANAGE</button>
            )}
          </div>
        </div>
      )}
      {view==='reader'&&openThread ? <ThreadReader thread={openThread} onBack={handleBack}/>
       : view==='manage'&&me.is_curator ? <ManageView me={me}/>
       : <Feed me={me} onRead={handleRead}/>}
    </div>
  )
}
