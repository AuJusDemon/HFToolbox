import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { api } from './api.js'
import useStore from '../store.js'

// ── Forum data (hardcoded from FID map, zero API calls) ──────────────────────
const CATEGORY_FIDS = new Set([1,7,45,88,105,120,141,151,156,241,259,444,445,446,447,448,449,450,451,452,453,460])

// Ordered to match HF website: Hack, Tech, Money, Market, Social
// Official is folded under Hack as it appears on the real site
const CATEGORIES = [
  {
    fid: 45, name: 'Hack', icon: '⚡',
    subs: [
      {
        name: 'Official',
        forums: [
          { fid: 2,   name: 'Site News' },
          { fid: 134, name: 'Suggestions & Ideas' },
        ]
      },
      {
        name: 'Blackhat',
        forums: [
          { fid: 10,  name: 'Hacking Tools & Programs' },
          { fid: 114, name: 'Remote Administration Tools' },
          { fid: 92,  name: 'Botnets & Botting' },
          { fid: 113, name: 'Keyloggers' },
          { fid: 126, name: 'Cryptography & Encryption' },
          { fid: 287, name: 'Malware & Viruses' },
          { fid: 229, name: 'Reverse Engineering' },
          { fid: 466, name: 'Jailbreaking, Modding & Rooting' },
        ]
      },
      {
        name: 'Grayhat',
        forums: [
          { fid: 4,   name: 'Beginner Hacking' },
          { fid: 43,  name: 'Website Hacking' },
          { fid: 91,  name: 'VPN, Proxies & Socks' },
          { fid: 46,  name: 'Social Media Hacks' },
          { fid: 104, name: 'Wifi / Wireless Hacking' },
          { fid: 433, name: 'Hacktivism' },
        ]
      },
      {
        name: 'Whitehat',
        forums: [
          { fid: 110, name: 'Malware & Virus Removal' },
          { fid: 400, name: 'White Hat Hacking' },
          { fid: 322, name: 'OpSec & OSINT' },
          { fid: 231, name: 'Pentesting & Forensics' },
          { fid: 193, name: 'IoT & Embedded Systems' },
          { fid: 434, name: 'Bug Bounties' },
        ]
      },
    ]
  },
  {
    fid: 444, name: 'Tech', icon: '💻',
    subs: [
      {
        name: 'Artificial Intelligence',
        forums: [
          { fid: 431, name: 'AI Discussion' },
          { fid: 461, name: 'Prompt Engineering' },
          { fid: 462, name: 'AI Programming & Vibe Coding' },
          { fid: 463, name: 'AI for Marketing & Automation' },
          { fid: 464, name: 'AI Tools, APIs & Platforms' },
          { fid: 465, name: 'AI-Generated Art, Music & Video' },
        ]
      },
      {
        name: 'Coding',
        forums: [
          { fid: 5,   name: 'Coders Lounge' },
          { fid: 118, name: 'Software Development' },
          { fid: 117, name: 'Mobile Development' },
          { fid: 183, name: 'Web Development' },
          { fid: 375, name: 'HF API' },
        ]
      },
      {
        name: 'Computing',
        forums: [
          { fid: 8,   name: 'Computing Lounge' },
          { fid: 87,  name: 'Computer Hardware' },
          { fid: 240, name: 'Networking & Firewalls' },
          { fid: 79,  name: 'Mobile Smartphones' },
          { fid: 192, name: 'Android OS' },
          { fid: 137, name: 'Apple iOS' },
          { fid: 347, name: 'Microsoft Windows' },
          { fid: 85,  name: 'Linux' },
          { fid: 159, name: 'MacOS' },
        ]
      },
      {
        name: 'Webmasters',
        forums: [
          { fid: 50,  name: 'Website Construction' },
          { fid: 172, name: 'Website Showcase & Reviews' },
          { fid: 142, name: 'SEO & Internet Marketing' },
          { fid: 139, name: 'Social Networking' },
          { fid: 143, name: 'Hosting & Web Servers' },
        ]
      },
      {
        name: 'Graphics',
        forums: [
          { fid: 6,   name: 'Graphics' },
          { fid: 133, name: 'Rate My Graphic' },
          { fid: 158, name: 'Free Graphic Help' },
          { fid: 160, name: 'Video Editing' },
          { fid: 293, name: 'Photography' },
        ]
      },
    ]
  },
  {
    fid: 241, name: 'Money', icon: '💵',
    subs: [
      {
        name: 'Crypto Currency',
        forums: [
          { fid: 380, name: 'Crypto Currency' },
        ]
      },
      {
        name: 'Monetizing Techniques',
        forums: [
          { fid: 221, name: 'Free Money Making Ebooks' },
          { fid: 245, name: 'Surveys' },
          { fid: 127, name: 'Referrals' },
          { fid: 268, name: 'CPA / PPD Make Money' },
        ]
      },
      {
        name: 'Other',
        forums: [
          { fid: 170, name: 'Adult Content Management' },
          { fid: 155, name: 'Member Contests' },
          { fid: 121, name: 'Shopping Deals' },
          { fid: 281, name: 'Markets, Finance & Investing' },
        ]
      },
    ]
  },
  {
    fid: 105, name: 'Market', icon: '🏪',
    subs: [
      {
        name: 'Bazaar',
        forums: [
          { fid: 163, name: 'Marketplace Discussions' },
          { fid: 402, name: 'Promotional Advertising' },
          { fid: 186, name: 'Free Services & Giveaways' },
          { fid: 205, name: 'Appraisals & Pricing' },
          { fid: 217, name: 'Jobs & Partnerships' },
          { fid: 111, name: 'Deal Disputes' },
        ]
      },
      {
        name: 'Premium',
        forums: [
          { fid: 107, name: 'Premium Sellers Section' },
          { fid: 374, name: 'Premium Tools & Programs' },
          { fid: 299, name: 'Cryptography & Encryption Market' },
          { fid: 136, name: 'Ebook Bazaar' },
          { fid: 182, name: 'Currency Exchange' },
          { fid: 218, name: 'Virtual Game Items' },
        ]
      },
      {
        name: 'Services',
        forums: [
          { fid: 145, name: 'Hosting Services' },
          { fid: 263, name: 'Social Media Services' },
          { fid: 106, name: 'Service Offerings' },
          { fid: 219, name: 'Graphics Market' },
          { fid: 171, name: 'VPN & Proxy Services' },
          { fid: 308, name: 'Service Requests' },
        ]
      },
      {
        name: 'Auxiliary',
        forums: [
          { fid: 44,  name: 'Buyers Bay' },
          { fid: 176, name: 'Member Sales Market' },
          { fid: 291, name: 'Online Accounts' },
          { fid: 339, name: 'Hash Bounties' },
          { fid: 255, name: 'Rewards & Small Favors' },
          { fid: 225, name: 'Webmaster Marketplace' },
        ]
      },
    ]
  },
  {
    fid: 7, name: 'Social', icon: '💬',
    subs: [
      {
        name: 'World',
        forums: [
          { fid: 25,  name: 'The Lounge' },
          { fid: 89,  name: 'News & Happenings' },
          { fid: 12,  name: 'Bragging Rights' },
          { fid: 260, name: 'Education & Careers' },
        ]
      },
      {
        name: 'Entertainment',
        forums: [
          { fid: 65,  name: 'Gaming' },
          { fid: 112, name: 'Anime & Manga' },
          { fid: 32,  name: 'Movies, TV & Videos' },
          { fid: 37,  name: 'Music' },
          { fid: 167, name: 'Sports' },
          { fid: 385, name: 'Cars, Bikes & Motors' },
        ]
      },
      {
        name: 'Personal Life',
        forums: [
          { fid: 318, name: 'Vices' },
          { fid: 370, name: 'Gambling' },
          { fid: 262, name: 'Health Wise' },
          { fid: 180, name: 'Innuendo' },
          { fid: 261, name: 'Pets & Animals' },
          { fid: 354, name: 'Food, Recipes & Cooking' },
        ]
      },
    ]
  },
  {
    fid: 99, name: 'VIP', icon: '👑',
    subs: [
      {
        name: 'Crews & Clans',
        forums: [
          { fid: 52,  name: 'Group and Crew General Discussions' },
          { fid: 235, name: 'H4CK3R$ Forum',     requiredGroups: ['46'] },
          { fid: 239, name: 'Quantum Forum',       requiredGroups: ['48'] },
          { fid: 236, name: 'Sociopaths Forum',    requiredGroups: ['49'] },
          { fid: 242, name: 'Legends Forum',       requiredGroups: ['50'] },
          { fid: 250, name: 'PinkLSZ Forum',       requiredGroups: ['52'] },
          { fid: 344, name: 'Blacklisted Forum',   requiredGroups: ['56'] },
          { fid: 413, name: 'Gamblers Forum',      requiredGroups: ['70'] },
          { fid: 421, name: 'Warriors Forum',      requiredGroups: ['71'] },
          { fid: 456, name: 'Academy Forum',       requiredGroups: ['77'] },
        ]
      },
      {
        name: 'Brotherhood',
        requiredGroups: ['68'],
        forums: [
          { fid: 403, name: 'Brotherhood Forum' },
        ]
      },
      {
        name: 'Vendors',
        requiredGroups: ['67'],
        forums: [
          { fid: 401, name: 'Vendor Forum' },
        ]
      },
      {
        name: 'VIBE',
        requiredGroups: ['78'],
        forums: [
          { fid: 459, name: 'VIBE Forum' },
        ]
      },
    ]
  },
]

// Flat list for search
// ALL_FORUMS is built at module level — group filtering happens at render time via ForumSelector
const ALL_FORUMS = CATEGORIES.flatMap(cat =>
  cat.subs.flatMap(sub =>
    sub.forums.map(f => ({
      ...f,
      catName: cat.name, catIcon: cat.icon, subName: sub.name,
      // per-forum requiredGroups takes priority, else inherit from sub
      requiredGroups: f.requiredGroups || sub.requiredGroups || null,
    }))
  )
)

// Returns CATEGORIES with empty subs/forums filtered out based on user's groups
function filterCategoriesByGroups(userGroups) {
  const gset = new Set(userGroups || [])
  return CATEGORIES.map(cat => ({
    ...cat,
    subs: cat.subs
      .filter(sub => !sub.requiredGroups || sub.requiredGroups.some(g => gset.has(g)))
      .map(sub => ({
        ...sub,
        forums: sub.forums.filter(f => !f.requiredGroups || f.requiredGroups.some(g => gset.has(g)))
      }))
      .filter(sub => sub.forums.length > 0),
  })).filter(cat => cat.subs.length > 0)
}

// Rules per FID
const FORUM_RULES = {
  107: '⚠ Premium Sellers only. Must have the Vendor tag. Price must be clearly listed.',
  111: '⚠ Deal Disputes only. Both parties should be contacted first.',
  402: '⚠ Promotional posts only. No direct sales — use Premium Sellers for that.',
  186: '⚠ Free services and giveaways only. No paid offers.',
  163: '⚠ Discussion only — no sales posts in this forum.',
  400: '⚠ Legitimate security research and whitehat topics only.',
  433: '⚠ Hacktivism discussion only. No personal targeting.',
}

// ── BBCode → HTML renderer ───────────────────────────────────────────────────
// ── Group CSS styles for preview rendering ────────────────────────────────────
const GROUP_CSS_STYLES = {
  68: 'font-family:Cinzel,serif;font-weight:900;letter-spacing:1.15px;background:linear-gradient(90deg,#9a9a9a 0%,#cfcfcf 20%,#ffffff 35%,#ffffff 45%,#e6e6e6 55%,#cfcfcf 70%,#9a9a9a 100%);background-size:300% auto;animation:brotherhood-shine 4s ease-in-out infinite;-webkit-background-clip:text;-webkit-text-fill-color:transparent;',
  78: 'display:inline-block;font-family:Orbitron,Cinzel,serif;font-weight:900;letter-spacing:1.15px;background:linear-gradient(90deg,#00ffb2 0%,#00e6ff 35%,#b7fff1 50%,#00e6ff 65%,#00ffb2 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;animation:vibe-glitch 3.5s infinite;',
  67: 'color:#2D7E52;font-weight:bold;text-shadow:0px 2px 3px #000;',
  9:  'color:#FFCC00;',
  28: 'color:#0066FF;',
  52: 'color:#FF99CC;font-weight:bold;font-family:Comic Sans MS;text-shadow:2px 2px 2px #4020dd;',
  50: 'font-weight:700;font-family:Cinzel,serif;letter-spacing:2px;background:linear-gradient(135deg,#FFD700,#FFC200,#B8860B);-webkit-background-clip:text;-webkit-text-fill-color:transparent;',
  77: 'color:#ffffff;font-family:graduate;letter-spacing:2px;text-shadow:-1px -1px 0 #467fff,1px -1px 0 #098ed9,-1px 1px 0 #1199df,1px 1px 0 #139add;',
  70: 'color:#ff54a1;font-weight:bold;text-shadow:2px 2px 2px #000000;',
  71: 'color:#00feb0;text-shadow:0px 2px 3px #000;',
  48: 'color:#dfcbff;font-weight:bold;font-family:New Rocker,system-ui;letter-spacing:1.75px;text-shadow:0 0 1px #b380ff,0 0 3px #9933ff,0 0 6px #7722cc;',
  46: 'color:#222;font-weight:bold;font-family:Amarante,serif;text-shadow:-1px -1px 0 #00ff00,1px -1px 0 #00ff00,-1px 1px 0 #00ff00,1px 1px 0 #00ff00,0 0 5px #00ff00,0 0 10px #00ff00,0 0 15px #008000;',
}

function bbToHtml(raw, userGroups) {
  if (!raw) return ''
  let s = raw
    // escape HTML entities first
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // Inline tags
  s = s.replace(/\[b\]([\s\S]*?)\[\/b\]/gi,        '<strong>$1</strong>')
  s = s.replace(/\[i\]([\s\S]*?)\[\/i\]/gi,        '<em>$1</em>')
  s = s.replace(/\[u\]([\s\S]*?)\[\/u\]/gi,        '<u>$1</u>')
  s = s.replace(/\[s\]([\s\S]*?)\[\/s\]/gi,        '<s>$1</s>')
  s = s.replace(/\[color=([^\]]+)\]([\s\S]*?)\[\/color\]/gi, '<span style="color:$1">$2</span>')
  s = s.replace(/\[size=([^\]]+)\]([\s\S]*?)\[\/size\]/gi,   '<span style="font-size:$1">$2</span>')
  s = s.replace(/\[font=([^\]]+)\]([\s\S]*?)\[\/font\]/gi,   '<span style="font-family:$1">$2</span>')
  s = s.replace(/\[align=([^\]]+)\]([\s\S]*?)\[\/align\]/gi, '<div style="text-align:$1">$2</div>')

  // [css=N] group tag — renders with group style if user is in that group
  s = s.replace(/\[css=(\d+)\]([\s\S]*?)\[\/css\]/gi, (_, gid, inner) => {
    const id = parseInt(gid)
    const inGroup = !userGroups || userGroups.includes(String(id))
    const style = GROUP_CSS_STYLES[id]
    if (style && inGroup) {
      return `<span style="${style}">${inner}</span>`
    }
    // Not in group or unknown group — show as plain text with a note
    return `<span style="color:var(--dim)" title="Group ${gid} CSS">${inner}</span>`
  })

  // Images with dimensions: [img=WxH]url[/img]
  s = s.replace(/\[img=(\d+)[x×](\d+)\]([\s\S]*?)\[\/img\]/gi,
    '<img src="$3" alt="" style="width:$1px;height:$2px;max-width:100%;vertical-align:middle;margin:4px 0" />')
  // Images without dimensions
  s = s.replace(/\[img\]([\s\S]*?)\[\/img\]/gi,
    '<img src="$1" alt="" style="max-width:100%;vertical-align:middle;margin:4px 0" />')
  // [uimg] / [uimg=WxH] / [uimg=X%] — HF encrypted image hosting (uploadimages.org)
  // Can't render in preview — key only exists in URL fragment
  const _uimgPill = (url, size) => {
    const id = (url || '').match(/uploadimages\.org\/([a-f0-9]+)/)?.[1] || ''
    const label = `🔒 uimg${id ? ':'+id.slice(0,8) : ''}${size ? ' ('+size+')' : ''}`
    return `<span style="display:inline-flex;align-items:center;gap:6px;padding:4px 10px;background:rgba(75,140,245,.08);border:1px solid rgba(75,140,245,.2);border-radius:4px;font-size:11px;color:var(--acc);font-family:var(--mono);margin:4px 0;vertical-align:middle">${label}</span>`
  }
  s = s.replace(/\[uimg=([^\]]+)\]([\s\S]*?)\[\/uimg\]/gi, (_, size, url) => _uimgPill(url, size))
  s = s.replace(/\[uimg\]([\s\S]*?)\[\/uimg\]/gi,           (_, url)       => _uimgPill(url, ''))

  // URLs — HF link color
  s = s.replace(/\[url=([^\]]+)\]([\s\S]*?)\[\/url\]/gi,
    '<a href="$1" target="_blank" rel="noreferrer" style="color:#6da9d2">$2</a>')
  s = s.replace(/\[url\]([\s\S]*?)\[\/url\]/gi,
    '<a href="$1" target="_blank" rel="noreferrer" style="color:#6da9d2">$1</a>')

  // Code — matches HF .codeblock
  s = s.replace(/\[code\]([\s\S]*?)\[\/code\]/gi,
    '<div style="background:#2F2F2F;border:1px dashed #888;margin:6px 0;overflow:hidden"><div style="background:#555;padding:3px 8px;font-size:11px;color:#ccc;font-family:Verdana,Arial,sans-serif">Code:</div><div style="padding:10px;font-family:Courier New,monospace;font-size:12px;color:#ccc;white-space:pre-wrap;overflow-x:auto">$1</div></div>')
  s = s.replace(/\[php\]([\s\S]*?)\[\/php\]/gi,
    '<div style="background:#2F2F2F;border:1px dashed #888;margin:6px 0;overflow:hidden"><div style="background:#555;padding:3px 8px;font-size:11px;color:#a8d8aa;font-family:Verdana,Arial,sans-serif">PHP Code:</div><div style="padding:10px;font-family:Courier New,monospace;font-size:12px;color:#ccc;white-space:pre-wrap;overflow-x:auto">$1</div></div>')

  // Quote — matches HF blockquote style
  s = s.replace(/\[quote="([^"]*)"[^\]]*\]([\s\S]*?)\[\/quote\]/gi,
    '<blockquote style="border-left:3px solid var(--b3);margin:4px 0;background:var(--s2);padding:8px 12px;color:var(--sub)"><cite style="font-style:normal;font-weight:bold;color:var(--text);display:block;margin-bottom:4px;font-size:12px">$1 wrote:</cite>$2</blockquote>')
  s = s.replace(/\[quote\]([\s\S]*?)\[\/quote\]/gi,
    '<blockquote style="border-left:3px solid var(--b3);margin:4px 0;background:var(--s2);padding:8px 12px;color:var(--sub)">$1</blockquote>')

  // Spoiler
  s = s.replace(/\[spoiler=([^\]]+)\]([\s\S]*?)\[\/spoiler\]/gi,
    '<details style="border:1px dashed #555;background:#3a3a3a;padding:6px 10px;margin:6px 0"><summary style="cursor:pointer;color:#6da9d2;font-size:12px;font-weight:600">$1</summary><div style="margin-top:6px;color:#ccc">$2</div></details>')
  s = s.replace(/\[spoiler\]([\s\S]*?)\[\/spoiler\]/gi,
    '<details style="border:1px dashed #555;background:#3a3a3a;padding:6px 10px;margin:6px 0"><summary style="cursor:pointer;color:#6da9d2;font-size:12px;font-weight:600">Spoiler</summary><div style="margin-top:6px;color:#ccc">$1</div></details>')

  // Lists
  s = s.replace(/\[list=1\]([\s\S]*?)\[\/list\]/gi, (_, inner) => {
    const items = inner.split(/\[\*\]/).filter(Boolean).map(i => `<li>${i.trim()}</li>`).join('')
    return `<ol style="padding-left:20px;margin:6px 0">${items}</ol>`
  })
  s = s.replace(/\[list=a\]([\s\S]*?)\[\/list\]/gi, (_, inner) => {
    const items = inner.split(/\[\*\]/).filter(Boolean).map(i => `<li>${i.trim()}</li>`).join('')
    return `<ol type="a" style="padding-left:20px;margin:6px 0">${items}</ol>`
  })
  s = s.replace(/\[list\]([\s\S]*?)\[\/list\]/gi, (_, inner) => {
    const items = inner.split(/\[\*\]/).filter(Boolean).map(i => `<li>${i.trim()}</li>`).join('')
    return `<ul style="padding-left:20px;margin:6px 0">${items}</ul>`
  })

  // Horizontal rule
  s = s.replace(/\[hr\]/gi, '<hr style="border:none;border-top:1px solid var(--b2);margin:10px 0"/>')

  // YouTube video
  s = s.replace(/\[video=youtube\]([\s\S]*?)\[\/video\]/gi, (_, url) => {
    const id = url.match(/(?:v=|youtu\.be\/)([A-Za-z0-9_-]{11})/)?.[1] || ''
    return id
      ? `<div style="position:relative;padding-bottom:56.25%;height:0;margin:8px 0"><iframe src="https://www.youtube.com/embed/${id}" style="position:absolute;top:0;left:0;width:100%;height:100%;border-radius:4px;border:none" allowfullscreen></iframe></div>`
      : `<span style="color:var(--dim)">[YouTube: ${url}]</span>`
  })

  // Contract tags — just show as a preview button
  s = s.replace(/\[contract[^\]]*\]([\s\S]*?)\[\/contract\]/gi,
    '<span style="display:inline-block;background:rgba(0,212,180,.1);border:1px solid rgba(0,212,180,.3);border-radius:4px;padding:2px 10px;font-size:11px;color:var(--acc);font-family:var(--mono)">📋 $1</span>')
  s = s.replace(/\[contract_template[^\]]*\]([\s\S]*?)\[\/contract_template\]/gi,
    '<span style="display:inline-block;background:rgba(0,212,180,.1);border:1px solid rgba(0,212,180,.3);border-radius:4px;padding:2px 10px;font-size:11px;color:var(--acc);font-family:var(--mono)">📋 $1</span>')

  // Mention
  s = s.replace(/\[mention=(\d+)\]([\s\S]*?)\[\/mention\]/gi,
    '<a href="https://hackforums.net/member.php?action=profile&uid=$1" target="_blank" rel="noreferrer" style="color:var(--acc);font-weight:600">@$2</a>')
  s = s.replace(/\[mention=(\d+)\]\[\/mention\]/gi,
    '<a href="https://hackforums.net/member.php?action=profile&uid=$1" target="_blank" rel="noreferrer" style="color:var(--acc);font-weight:600">@$1</a>')

  // PM link
  s = s.replace(/\[pmme=[^\]]*\]([\s\S]*?)\[\/pmme\]/gi,
    '<span style="color:var(--blue);text-decoration:underline;cursor:pointer">$1</span>')

  // Newlines → <br>
  s = s.replace(/\n/g, '<br/>')

  return s
}

// ── Forum selector ────────────────────────────────────────────────────────────
function ForumSelector({ value, onChange, recents, userGroups }) {
  const [openCat,   setOpenCat]   = useState(null)
  const [openSub,   setOpenSub]   = useState(null)
  const [search,    setSearch]    = useState('')
  const [collapsed, setCollapsed] = useState(false)

  const selected = value ? ALL_FORUMS.find(f => String(f.fid) === String(value.fid)) : null

  const searchResults = useMemo(() => {
    if (!search.trim()) return []
    const q = search.toLowerCase()
    const accessibleForums = ALL_FORUMS.filter(f =>
      !f.requiredGroups || f.requiredGroups.some(g => (userGroups||[]).includes(g))
    )
    return accessibleForums.filter(f =>
      f.name.toLowerCase().includes(q) ||
      f.catName.toLowerCase().includes(q) ||
      f.subName.toLowerCase().includes(q)
    ).slice(0, 10)
  }, [search])

  const pickCat = (fid) => {
    if (openCat === fid) { setOpenCat(null); setOpenSub(null); return }
    const cat = CATEGORIES.find(c => c.fid === fid)
    setOpenCat(fid)
    // If only one sub, select it automatically — no extra click needed
    setOpenSub(cat?.subs.length === 1 ? cat.subs[0].name : null)
    setSearch('')
  }

  const pick = (f, catName) => {
    onChange({ fid: String(f.fid), name: f.name, cat: catName })
    setSearch(''); setOpenCat(null); setOpenSub(null); setCollapsed(true)
  }

  if (collapsed && selected) {
    return (
      <div style={{ display:'flex', alignItems:'center', gap:8, padding:'6px 0' }}>
        <span style={{ fontSize:11, color:'var(--sub)' }}>Posting to:</span>
        <span style={{ fontSize:12, fontWeight:600, color:'var(--acc)' }}>{selected.name}</span>
        <span style={{ fontSize:10, color:'var(--dim)' }}>({selected.catName} › {selected.subName})</span>
        <button className="btn btn-ghost" style={{ fontSize:10, padding:'2px 8px', marginLeft:'auto' }}
          onClick={() => setCollapsed(false)}>change</button>
      </div>
    )
  }

  const activeCat = CATEGORIES.find(c => c.fid === openCat)
  const activeSub = activeCat?.subs.find(s => s.name === openSub)

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
      {/* Recents */}
      {recents.length > 0 && !search && (
        <div>
          <div style={{ fontSize:9, color:'var(--dim)', textTransform:'uppercase', letterSpacing:'.08em', fontFamily:'var(--mono)', marginBottom:5 }}>Recent</div>
          <div style={{ display:'flex', gap:5, flexWrap:'wrap' }}>
            {recents.map(r => (
              <button key={r.fid}
                onClick={() => { onChange({ fid:String(r.fid), name:r.forum_name, cat:r.category_name }); setCollapsed(true) }}
                style={{ padding:'3px 10px', fontSize:11, borderRadius:3, border:'1px solid var(--b2)', background:'var(--s3)', color:'var(--sub)', cursor:'pointer', transition:'all 130ms' }}
                onMouseOver={e => { e.currentTarget.style.borderColor='var(--acc)'; e.currentTarget.style.color='var(--acc)' }}
                onMouseOut={e => { e.currentTarget.style.borderColor='var(--b2)'; e.currentTarget.style.color='var(--sub)' }}
              >{r.forum_name}</button>
            ))}
          </div>
        </div>
      )}

      {/* Search */}
      <input className="inp" style={{ width:'100%' }}
        placeholder="Search forums…" value={search}
        onChange={e => { setSearch(e.target.value); setOpenCat(null); setOpenSub(null) }}
      />

      {/* Search results */}
      {search && (
        <div style={{ display:'flex', flexDirection:'column', gap:2 }}>
          {searchResults.length === 0
            ? <div style={{ fontSize:11, color:'var(--dim)', fontStyle:'italic' }}>No forums found</div>
            : searchResults.map(f => (
                <button key={f.fid} onClick={() => pick(f, f.catName)}
                  style={{ padding:'6px 10px', fontSize:11.5, borderRadius:3, textAlign:'left', border:'1px solid var(--b1)', background:'var(--s3)', color:'var(--sub)', cursor:'pointer', display:'flex', alignItems:'center', gap:8, transition:'all 130ms' }}
                  onMouseOver={e => { e.currentTarget.style.borderColor='var(--acc)'; e.currentTarget.style.color='var(--acc)' }}
                  onMouseOut={e => { e.currentTarget.style.borderColor='var(--b1)'; e.currentTarget.style.color='var(--sub)' }}
                >
                  <span style={{ fontWeight:600, flex:1 }}>{f.name}</span>
                  <span style={{ fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)' }}>{f.catName} › {f.subName}</span>
                </button>
              ))
          }
        </div>
      )}

      {!search && (
        <div>
          {/* Level 1: top-level category tabs */}
          <div style={{ fontSize:9, color:'var(--dim)', textTransform:'uppercase', letterSpacing:'.08em', fontFamily:'var(--mono)', marginBottom:6 }}>Browse</div>
          <div style={{ display:'flex', gap:4, flexWrap:'wrap' }}>
            {filterCategoriesByGroups(userGroups).map(cat => {
              const on = openCat === cat.fid
              return (
                <button key={cat.fid} onClick={() => pickCat(cat.fid)}
                  style={{
                    padding:'5px 13px', fontSize:11.5, borderRadius:3, fontWeight:600,
                    border:'1px solid ' + (on ? 'var(--acc)' : 'var(--b2)'),
                    background: on ? 'rgba(0,212,180,.09)' : 'var(--s3)',
                    color: on ? 'var(--acc)' : 'var(--sub)',
                    cursor:'pointer', transition:'all 130ms',
                  }}
                >{cat.icon} {cat.name}</button>
              )
            })}
          </div>

          {/* Level 2: sub-section pills (only shown if cat has multiple subs) */}
          {activeCat && activeCat.subs.length > 1 && (
            <div style={{ display:'flex', gap:4, flexWrap:'wrap', marginTop:8 }}>
              {activeCat.subs.map(sub => {
                const on = openSub === sub.name
                return (
                  <button key={sub.name}
                    onClick={() => setOpenSub(on ? null : sub.name)}
                    style={{
                      padding:'4px 11px', fontSize:11, borderRadius:3, fontWeight:500,
                      border:'1px solid ' + (on ? 'rgba(77,142,240,.5)' : 'var(--b2)'),
                      background: on ? 'rgba(77,142,240,.09)' : 'var(--bg)',
                      color: on ? 'var(--blue)' : 'var(--sub)',
                      cursor:'pointer', transition:'all 130ms',
                    }}
                  >{sub.name} <span style={{ fontSize:9, opacity:.5 }}>({sub.forums.filter(f => !f.requiredGroups || f.requiredGroups.some(g => (userGroups||[]).includes(g))).length})</span></button>
                )
              })}
            </div>
          )}

          {/* Level 3: forum grid */}
          {activeSub && (
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:'2px 8px', marginTop:8 }}>
              {activeSub.forums.filter(f => !f.requiredGroups || f.requiredGroups.some(g => (userGroups||[]).includes(g))).map(f => (
                <button key={f.fid} onClick={() => pick(f, activeCat.name)}
                  style={{
                    padding:'5px 8px', fontSize:12, borderRadius:3, textAlign:'left',
                    border:'1px solid transparent', background:'transparent',
                    color:'var(--sub)', cursor:'pointer', transition:'all 100ms',
                    display:'flex', alignItems:'center', gap:6,
                  }}
                  onMouseOver={e => { e.currentTarget.style.color='var(--acc)'; e.currentTarget.style.background='rgba(0,212,180,.05)'; e.currentTarget.style.borderColor='rgba(0,212,180,.15)' }}
                  onMouseOut={e => { e.currentTarget.style.color='var(--sub)'; e.currentTarget.style.background='transparent'; e.currentTarget.style.borderColor='transparent' }}
                >
                  <span style={{ width:5, height:5, borderRadius:'50%', background:'var(--acc)', flexShrink:0, opacity:.5 }}/>
                  {f.name}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
// ── Inline modal (replaces browser prompt) ────────────────────────────────────
function Modal({ fields, onOk, onCancel }) {
  const [vals, setVals] = useState(() => Object.fromEntries(fields.map(f => [f.key, f.default||''])))
  return (
    <div style={{
      position:'fixed', inset:0, background:'rgba(0,0,0,.6)', zIndex:9999,
      display:'flex', alignItems:'center', justifyContent:'center',
    }} onClick={onCancel}>
      <div style={{
        background:'var(--s2)', border:'1px solid var(--b2)', borderRadius:6,
        padding:'16px 20px', minWidth:280, maxWidth:400,
      }} onClick={e => e.stopPropagation()}>
        {fields.map(f => (
          <div key={f.key} style={{ marginBottom:10 }}>
            <div style={{ fontSize:10, color:'var(--dim)', textTransform:'uppercase', letterSpacing:'.07em', fontFamily:'var(--mono)', marginBottom:4 }}>{f.label}</div>
            <input className="inp" style={{ width:'100%' }} placeholder={f.placeholder||''}
              value={vals[f.key]}
              onChange={e => setVals(v => ({...v, [f.key]: e.target.value}))}
              onKeyDown={e => { if(e.key==='Enter') onOk(vals); if(e.key==='Escape') onCancel() }}
              autoFocus={f.key === fields[0].key}
            />
          </div>
        ))}
        <div style={{ display:'flex', gap:8, justifyContent:'flex-end', marginTop:6 }}>
          <button className="btn btn-ghost" style={{ fontSize:11 }} onClick={onCancel}>Cancel</button>
          <button className="btn btn-acc" style={{ fontSize:11 }} onClick={() => onOk(vals)}>Insert</button>
        </div>
      </div>
    </div>
  )
}

// ── Group asset dropdown ─────────────────────────────────────────────────────
function GroupDropdown({ groups }) {
  const [open, setOpen] = useState(false)
  const [activeGroup, setActiveGroup] = useState(null)
  const ref = useRef(null)

  // Close on outside click
  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const active = groups.find(g => g.gid === activeGroup) || groups[0]

  return (
    <div ref={ref} style={{ position: 'relative', display: 'inline-flex', alignSelf: 'center', marginLeft: 2 }}>
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        style={{
          padding: '3px 8px', fontSize: 10, fontFamily: 'var(--mono)', fontWeight: 600,
          border: '1px solid var(--acc)', borderRadius: 3,
          background: open ? 'rgba(0,212,180,.12)' : 'rgba(0,212,180,.06)',
          color: 'var(--acc)', cursor: 'pointer', lineHeight: 1.4,
          display: 'flex', alignItems: 'center', gap: 4,
        }}
      >
        Groups {open ? '▲' : '▼'}
      </button>

      {open && (
        <div style={{
          position: 'absolute', top: '100%', left: 0, zIndex: 200, marginTop: 3,
          background: 'var(--s2)', border: '1px solid var(--b2)', borderRadius: 4,
          minWidth: 180, boxShadow: '0 4px 16px rgba(0,0,0,.4)',
        }}>
          {/* Group tabs — if multiple groups */}
          {groups.length > 1 && (
            <div style={{ display: 'flex', borderBottom: '1px solid var(--b1)' }}>
              {groups.map(g => (
                <button key={g.gid} type="button"
                  onClick={() => setActiveGroup(g.gid)}
                  style={{
                    flex: 1, padding: '5px 8px', fontSize: 10, fontWeight: 600,
                    fontFamily: 'var(--mono)', border: 'none', cursor: 'pointer',
                    background: (activeGroup || groups[0].gid) === g.gid ? 'var(--s3)' : 'transparent',
                    color: (activeGroup || groups[0].gid) === g.gid ? 'var(--acc)' : 'var(--dim)',
                    borderBottom: (activeGroup || groups[0].gid) === g.gid ? '2px solid var(--acc)' : '2px solid transparent',
                  }}
                >{g.name}</button>
              ))}
            </div>
          )}

          {/* Items for active group */}
          <div style={{ padding: '4px 0' }}>
            {groups.length === 1 && (
              <div style={{ padding: '4px 12px 2px', fontSize: 9, color: 'var(--dim)', textTransform: 'uppercase', letterSpacing: '.08em', fontFamily: 'var(--mono)' }}>
                {groups[0].name}
              </div>
            )}
            {active.items.map(item => (
              <button key={item.label} type="button"
                onClick={() => { item.action(); setOpen(false) }}
                style={{
                  display: 'block', width: '100%', textAlign: 'left',
                  padding: '6px 12px', fontSize: 11.5, background: 'none',
                  border: 'none', color: 'var(--sub)', cursor: 'pointer',
                  fontFamily: 'var(--sans)', transition: 'all 120ms',
                }}
                onMouseOver={e => { e.currentTarget.style.background='var(--s3)'; e.currentTarget.style.color='var(--text)' }}
                onMouseOut={e => { e.currentTarget.style.background='none'; e.currentTarget.style.color='var(--sub)' }}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── uploadimages.org E2E encryption (replicated from their open source JS) ────
// Encryption happens 100% in browser — key is only ever in the URL fragment.
function _b64url(bytes) {
  let s = ''
  for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i])
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}
async function _e2eDeriveKey(seed) {
  const ikm = await crypto.subtle.importKey('raw', seed, 'HKDF', false, ['deriveKey'])
  return crypto.subtle.deriveKey(
    { name: 'HKDF', hash: 'SHA-256', salt: new TextEncoder().encode('UIMG-E2E1-KEY'), info: new TextEncoder().encode('aes-256-gcm') },
    ikm, { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']
  )
}
async function _e2eHmac(seed, ct) {
  const hk = await crypto.subtle.importKey('raw', seed, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign'])
  return new Uint8Array(await crypto.subtle.sign('HMAC', hk, ct)).slice(0, 16)
}
async function _e2eEncrypt(buf) {
  const seed = crypto.getRandomValues(new Uint8Array(32))
  const iv   = crypto.getRandomValues(new Uint8Array(12))
  const key  = await _e2eDeriveKey(seed)
  const ct   = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv, tagLength: 128 }, key, buf))
  const hmac = await _e2eHmac(seed, ct)
  return { ciphertext: ct, seed, iv, hmac }
}
function _e2eLink(shareLink, seed, iv, hmac) {
  // uploadimages.org returns share_link like https://uploadimages.org/ID#base_fragment
  // We append #E2E1.seed.iv.hmac.originalFragment
  const parts = shareLink.split('#')
  const base  = parts[0]
  const orig  = parts[1] || ''
  return `${base}#E2E1.${_b64url(seed)}.${_b64url(iv)}.${_b64url(hmac)}.${orig}`
}

// ── BBCode Editor with toolbar ────────────────────────────────────────────────
// ── AutoTextarea — grows to fit content reliably for all change sources ─────
// useEffect watches value so paste, toolbar inserts, and initial load all work.
// overflow stays 'auto' so if somehow height calc is off, scroll still works.
function AutoTextarea({ taRef, value, onChange, onFocus, onBlur }) {
  // Set height once on mount imperatively — React never touches it again
  // since height is not in the style prop. resize:vertical lets user drag bigger.
  useEffect(() => {
    const ta = taRef.current
    if (!ta) return
    ta.style.height = '320px'
    ta.style.resize = 'vertical'
  }, [])

  return (
    <textarea
      ref={taRef}
      value={value}
      onChange={e => onChange(e.target.value)}
      className="bb-ta"
      style={{
        width: '100%', padding: '10px 12px',
        background: 'var(--bg)', border: '1px solid var(--b2)',
        borderRadius: '0 0 4px 4px', color: 'var(--text)',
        fontFamily: 'var(--mono)', fontSize: 12, lineHeight: 1.6,
        outline: 'none', overflowY: 'auto',
        boxSizing: 'border-box', display: 'block',
      }}
      onFocus={onFocus}
      onBlur={onBlur}
      placeholder="Write your post in BBCode…"
      spellCheck={false}
    />
  )
}

const FONTS = ['Arial','Comic Sans MS','Courier New','Georgia','Impact','Tahoma','Times New Roman','Trebuchet MS','Verdana']
const SIZES = ['xx-small','x-small','small','medium','large','x-large','xx-large']

function BBEditor({ value, onChange, userGroups }) {
  const taRef        = useRef(null)
  const colorRef     = useRef(null)
  const pendingColor = useRef(null)
  const selRef       = useRef({ start:0, end:0 })
  const [modal,      setModal]     = useState(null)
  const [uploading,  setUploading] = useState(false)
  const [uploadErr,  setUploadErr] = useState(null)

  const saveSelection = () => {
    const ta = taRef.current
    if (ta) { selRef.current = { start: ta.selectionStart, end: ta.selectionEnd } }
  }

  const wrap = (open, close, startOverride, endOverride) => {
    const ta = taRef.current
    if (!ta) return
    const start = startOverride ?? ta.selectionStart
    const end   = endOverride   ?? ta.selectionEnd
    const sel   = value.slice(start, end)
    const next  = value.slice(0, start) + open + sel + close + value.slice(end)
    onChange(next)
    setTimeout(() => {
      ta.focus()
      ta.selectionStart = start + open.length
      ta.selectionEnd   = start + open.length + sel.length
    }, 0)
  }

  const insert = (text) => {
    const ta = taRef.current
    if (!ta) return
    const pos  = ta.selectionStart
    const next = value.slice(0, pos) + text + value.slice(pos)
    onChange(next)
    setTimeout(() => { ta.focus(); ta.selectionStart = ta.selectionEnd = pos + text.length }, 0)
  }

  const openModal = (fields, onOk) => {
    saveSelection()
    setModal({ fields, onOk })
  }
  const closeModal = () => setModal(null)

  const uploadFile = async (file) => {
    setUploading(true)
    setUploadErr(null)
    try {
      const buf = await file.arrayBuffer()
      const { ciphertext, seed, iv, hmac } = await _e2eEncrypt(buf)
      const blob = new Blob([ciphertext], { type: 'application/octet-stream' })
      const fd   = new FormData()
      fd.append('file', blob, file.name)
      fd.append('e2e', 'true')
      fd.append('original_mime', file.type || 'application/octet-stream')
      fd.append('visibility', 'public')
      const resp = await fetch('/api/posting/imagehost/upload', { method: 'POST', body: fd })
      if (!resp.ok) { const d = await resp.json().catch(() => ({})); throw new Error(d.error || 'Upload failed') }
      const data = await resp.json()
      if (!data.share_link) throw new Error('No share_link in response')
      const fullUrl = _e2eLink(data.share_link, seed, iv, hmac)
      insert(`[uimg]${fullUrl}[/uimg]`)
    } catch (err) {
      setUploadErr(err.message)
      setTimeout(() => setUploadErr(null), 5000)
    } finally {
      setUploading(false)
    }
  }

  const btnStyle = {
    padding: '3px 7px', fontSize: 10, fontFamily: 'var(--mono)', fontWeight: 600,
    border: '1px solid var(--b2)', borderRadius: 3, background: 'var(--s3)',
    color: 'var(--sub)', cursor: 'pointer', lineHeight: 1.4, transition: 'all 130ms',
  }
  const hov = e => { e.currentTarget.style.borderColor='var(--b3)'; e.currentTarget.style.color='var(--muted)' }
  const unv = e => { e.currentTarget.style.borderColor='var(--b2)'; e.currentTarget.style.color='var(--sub)' }
  const Btn = ({ label, title, onClick }) => (
    <button type="button" title={title} style={btnStyle} onMouseOver={hov} onMouseOut={unv} onClick={onClick}>{label}</button>
  )
  const Sep = () => <div style={{ width:1, height:18, background:'var(--b2)', margin:'0 2px', alignSelf:'center' }}/>
  const selectStyle = { ...btnStyle, padding:'3px 5px', fontFamily:'var(--sans)', cursor:'pointer', appearance:'none', WebkitAppearance:'none' }

  return (
    <div>
      {/* Inline modal */}
      {modal && (
        <Modal
          fields={modal.fields}
          onOk={vals => { closeModal(); modal.onOk(vals) }}
          onCancel={closeModal}
        />
      )}

      {/* Toolbar */}
      <div style={{
        display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 3,
        padding: '6px 8px', background: 'var(--s3)',
        border: '1px solid var(--b2)', borderBottom: 'none', borderRadius: '4px 4px 0 0',
      }}>
        <Btn label="B"  title="Bold"          onClick={() => wrap('[b]','[/b]')} />
        <Btn label="I"  title="Italic"        onClick={() => wrap('[i]','[/i]')} />
        <Btn label="U"  title="Underline"     onClick={() => wrap('[u]','[/u]')} />
        <Btn label="S"  title="Strikethrough" onClick={() => wrap('[s]','[/s]')} />
        <Sep/>

        <Btn label="≡L" title="Align left"   onClick={() => wrap('[align=left]','[/align]')} />
        <Btn label="≡C" title="Center"       onClick={() => wrap('[align=center]','[/align]')} />
        <Btn label="≡R" title="Align right"  onClick={() => wrap('[align=right]','[/align]')} />
        <Btn label="≡J" title="Justify"      onClick={() => wrap('[align=justify]','[/align]')} />
        <Sep/>

        <select style={selectStyle} title="Font name" defaultValue=""
          onMouseOver={hov} onMouseOut={unv}
          onChange={e => { if (e.target.value) { wrap(`[font=${e.target.value}]`,'[/font]'); e.target.value='' } }}>
          <option value="" disabled>Font</option>
          {FONTS.map(f => <option key={f} value={f}>{f}</option>)}
        </select>

        <select style={selectStyle} title="Font size" defaultValue=""
          onMouseOver={hov} onMouseOut={unv}
          onChange={e => { if (e.target.value) { wrap(`[size=${e.target.value}]`,'[/size]'); e.target.value='' } }}>
          <option value="" disabled>Size</option>
          {SIZES.map(s => <option key={s} value={s}>{s}</option>)}
        </select>

        {/* Color — hidden input, only applies on blur (when picker closes) */}
        <div style={{ position:'relative', display:'inline-flex' }}>
          <input ref={colorRef} type="color" defaultValue="#ff3333"
            style={{ position:'absolute', opacity:0, width:'100%', height:'100%', cursor:'pointer', border:'none', padding:0 }}
            onChange={e => { pendingColor.current = e.target.value }}
            onBlur={() => {
              if (pendingColor.current) {
                const { start, end } = selRef.current
                wrap(`[color=${pendingColor.current}]`, '[/color]', start, end)
                pendingColor.current = null
              }
            }}
          />
          <button type="button" title="Font color" style={btnStyle} onMouseOver={hov} onMouseOut={unv}
            onClick={() => { saveSelection(); colorRef.current?.click() }}>
            Color
          </button>
        </div>
        <Sep/>

        <Btn label="HR"  title="Horizontal rule" onClick={() => insert('\n[hr]\n')} />
        <Btn label="IMG" title="Insert image" onClick={() => openModal(
          [{ key:'url', label:'Image URL', placeholder:'https://...' }],
          ({url}) => { if(url) insert(`[img]${url}[/img]`) }
        )} />

        {/* uimg Upload button */}
        {(() => {
          const [uOpen,  setUOpen]  = useState(false)
          const [uDrag,  setUDrag]  = useState(false)
          const uRef     = useRef(null)
          const uFileRef = useRef(null)

          useEffect(() => {
            const h = e => { if (uRef.current && !uRef.current.contains(e.target)) setUOpen(false) }
            document.addEventListener('mousedown', h)
            return () => document.removeEventListener('mousedown', h)
          }, [])

          useEffect(() => {
            if (!uOpen) return
            const h = e => {
              const items = e.clipboardData?.items
              if (!items) return
              for (let i = 0; i < items.length; i++) {
                if (items[i].type.startsWith('image/')) {
                  const f = items[i].getAsFile()
                  if (f) { setUOpen(false); uploadFile(f); break }
                }
              }
            }
            document.addEventListener('paste', h)
            return () => document.removeEventListener('paste', h)
          }, [uOpen])

          return (
            <div ref={uRef} style={{ position:'relative', display:'inline-flex', alignSelf:'center' }}>
              <input ref={uFileRef} type="file" accept="image/*" style={{ display:'none' }}
                onChange={e => { const f=e.target.files?.[0]; e.target.value=''; if(f){setUOpen(false);uploadFile(f)} }} />
              <button type="button"
                style={{ ...btnStyle, display:'flex', alignItems:'center', gap:4, color: uOpen?'var(--text)':'var(--sub)' }}
                onMouseOver={hov} onMouseOut={unv}
                onClick={() => { if (!uploading) setUOpen(o => !o) }}>
                {uploading ? <><div className="spin" style={{width:10,height:10}}/> uploading…</> : '🔒 Upload Image'}
              </button>
              {uOpen && (
                <div style={{
                  position:'absolute', top:'100%', left:0, zIndex:300, marginTop:4,
                  background:'var(--s2)', border:'1px solid var(--b2)', borderRadius:6,
                  width:250, boxShadow:'0 8px 28px rgba(0,0,0,.55)', padding:10,
                }}>
                  <div
                    onClick={() => uFileRef.current?.click()}
                    onDragOver={e => { e.preventDefault(); setUDrag(true) }}
                    onDragLeave={() => setUDrag(false)}
                    onDrop={e => {
                      e.preventDefault(); setUDrag(false)
                      const f = e.dataTransfer.files?.[0]
                      if (f && f.type.startsWith('image/')) { setUOpen(false); uploadFile(f) }
                    }}
                    style={{
                      border: `2px dashed ${uDrag ? 'var(--acc)' : 'rgba(75,140,245,.35)'}`,
                      borderRadius:6, padding:'20px 12px', textAlign:'center',
                      cursor:'pointer', background: uDrag ? 'rgba(0,212,180,.05)' : 'var(--bg)',
                      transition:'all 150ms',
                    }}
                  >
                    <svg viewBox="0 0 24 24" width="26" height="26" fill="none"
                      stroke="var(--acc)" strokeWidth="1.8" strokeLinecap="round"
                      style={{ marginBottom:6, opacity: uDrag?1:.7 }}>
                      <polyline points="16 16 12 12 8 16"/>
                      <line x1="12" y1="12" x2="12" y2="21"/>
                      <path d="M20.39 18.39A5 5 0 0018 9h-1.26A8 8 0 103 16.3"/>
                    </svg>
                    <div style={{ fontSize:11.5, color:'var(--sub)', marginBottom:2 }}>
                      Drop image or <span style={{ color:'var(--acc)', fontWeight:600 }}>click to browse</span>
                    </div>
                    <div style={{ fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)' }}>Ctrl+V to paste</div>
                  </div>
                  {uploadErr && (
                    <div style={{ marginTop:7, fontSize:10, color:'var(--red)', fontFamily:'var(--mono)' }}>✕ {uploadErr}</div>
                  )}
                </div>
              )}
            </div>
          )
        })()}

        {/* uimg Embed button */}
        {(() => {
          const [eOpen,     setEOpen]     = useState(false)
          const [eLinkUrl,  setELinkUrl]  = useState('')
          const [eSizeMode, setESizeMode] = useState('')
          const [eW,        setEW]        = useState('')
          const [eH,        setEH]        = useState('')
          const [ePct,      setEPct]      = useState('')
          const eRef = useRef(null)

          useEffect(() => {
            const h = e => { if (eRef.current && !eRef.current.contains(e.target)) setEOpen(false) }
            document.addEventListener('mousedown', h)
            return () => document.removeEventListener('mousedown', h)
          }, [])

          const doEmbed = () => {
            const url = eLinkUrl.trim()
            if (!url) return
            let tag
            if (eSizeMode === 'px' && eW && eH) tag = `[uimg=${eW}x${eH}]${url}[/uimg]`
            else if (eSizeMode === 'pct' && ePct) tag = `[uimg=${ePct}%]${url}[/uimg]`
            else tag = `[uimg]${url}[/uimg]`
            insert(tag)
            setELinkUrl(''); setEOpen(false)
          }

          return (
            <div ref={eRef} style={{ position:'relative', display:'inline-flex', alignSelf:'center' }}>
              <button type="button"
                style={{ ...btnStyle, display:'flex', alignItems:'center', gap:4, color: eOpen?'var(--text)':'var(--sub)' }}
                onMouseOver={hov} onMouseOut={unv}
                onClick={() => setEOpen(o => !o)}>
                🔒 Embed Image
              </button>
              {eOpen && (
                <div style={{
                  position:'absolute', top:'100%', left:0, zIndex:300, marginTop:4,
                  background:'var(--s2)', border:'1px solid var(--b2)', borderRadius:6,
                  width:270, boxShadow:'0 8px 28px rgba(0,0,0,.55)',
                  padding:10, display:'flex', flexDirection:'column', gap:8,
                }}>
                  <input className="inp" style={{ fontSize:11, width:'100%', boxSizing:'border-box' }}
                    placeholder="https://uploadimages.org/ID#E2E1…"
                    value={eLinkUrl} onChange={e => setELinkUrl(e.target.value)}
                    onKeyDown={e => { if(e.key==='Enter') doEmbed() }}
                    autoFocus
                  />
                  <div>
                    <div style={{ fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)', textTransform:'uppercase', letterSpacing:'.08em', marginBottom:5 }}>Size (optional)</div>
                    <div style={{ display:'flex', gap:4 }}>
                      {[['','Default'],['px','W×H px'],['pct','% width']].map(([v,l]) => (
                        <button key={v} type="button" onClick={() => setESizeMode(v)} style={{
                          flex:1, padding:'3px 0', fontSize:10, fontFamily:'var(--mono)',
                          border:'1px solid '+(eSizeMode===v?'var(--acc)':'var(--b2)'),
                          borderRadius:3, background: eSizeMode===v?'rgba(0,212,180,.08)':'var(--s3)',
                          color: eSizeMode===v?'var(--acc)':'var(--sub)', cursor:'pointer',
                        }}>{l}</button>
                      ))}
                    </div>
                  </div>
                  {eSizeMode === 'px' && (
                    <div style={{ display:'flex', gap:6, alignItems:'center' }}>
                      <input className="inp" placeholder="W" value={eW} onChange={e=>setEW(e.target.value)} style={{ fontSize:11, width:56 }} />
                      <span style={{ color:'var(--dim)', fontSize:12 }}>×</span>
                      <input className="inp" placeholder="H" value={eH} onChange={e=>setEH(e.target.value)} style={{ fontSize:11, width:56 }} />
                      <span style={{ fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)' }}>px</span>
                    </div>
                  )}
                  {eSizeMode === 'pct' && (
                    <div style={{ display:'flex', gap:6, alignItems:'center' }}>
                      <input className="inp" placeholder="50" value={ePct} onChange={e=>setEPct(e.target.value)} style={{ fontSize:11, width:60 }} />
                      <span style={{ fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)' }}>% width</span>
                    </div>
                  )}
                  <button type="button" className="btn btn-acc" style={{ fontSize:11, padding:'5px 0' }}
                    onClick={doEmbed} disabled={!eLinkUrl.trim()}>
                    Insert [uimg]
                  </button>
                </div>
              )}
            </div>
          )
        })()}
        <Btn label="URL" title="Insert link" onClick={() => openModal(
          [
            { key:'url',  label:'URL',              placeholder:'https://...' },
            { key:'text', label:'Link text (optional)', placeholder:'' },
          ],
          ({url,text}) => { if(url) insert(text ? `[url=${url}]${text}[/url]` : `[url]${url}[/url]`) }
        )} />
        <Btn label="YT" title="YouTube video" onClick={() => openModal(
          [{ key:'url', label:'YouTube URL', placeholder:'https://youtube.com/watch?v=...' }],
          ({url}) => { if(url) insert(`[video=youtube]${url}[/video]`) }
        )} />
        <Sep/>

        <Btn label="• List"  title="Bullet list"   onClick={() => insert('\n[list]\n[*]Item 1\n[*]Item 2\n[/list]\n')} />
        <Btn label="1. List" title="Numbered list"  onClick={() => insert('\n[list=1]\n[*]Item 1\n[*]Item 2\n[/list]\n')} />
        <Sep/>

        <Btn label="Code"    title="Code block" onClick={() => wrap('[code]','[/code]')} />
        <Btn label="PHP"     title="PHP block"  onClick={() => wrap('[php]','[/php]')} />
        <Btn label="Quote"   title="Quote"      onClick={() => wrap('[quote]','[/quote]')} />
        <Btn label="Spoiler" title="Spoiler"    onClick={() => openModal(
          [{ key:'label', label:'Spoiler label', placeholder:'Spoiler', default:'Spoiler' }],
          ({label}) => wrap(`[spoiler=${label||'Spoiler'}]`,'[/spoiler]', selRef.current.start, selRef.current.end)
        )} />
        <Sep/>

        {/* Contract — dropdown for all variants */}
        {(() => {
          const CONTRACT_OPTS = [
            { label: 'Blank',       hint: 'No auto-fill',                   action: () => openModal([{key:'text',label:'Button text',default:'Start Contract'}], ({text}) => insert(`[contract]${text||'Start Contract'}[/contract]`)) },
            { label: 'Thread Auto', hint: 'Auto-fills TID from the thread', action: () => openModal([{key:'text',label:'Button text',default:'Start Contract'}], ({text}) => insert(`[contract=tid]${text||'Start Contract'}[/contract]`)) },
            { label: 'User Auto',   hint: 'Auto-fills UID of post author',  action: () => openModal([{key:'text',label:'Button text',default:'Start Contract'}], ({text}) => insert(`[contract=uid]${text||'Start Contract'}[/contract]`)) },
            { label: 'With TID',    hint: 'Pre-fill a specific TID',        action: () => openModal([{key:'tid',label:'Thread ID',placeholder:'5847344'},{key:'text',label:'Button text',default:'Start Contract'}], ({tid,text}) => { if(tid) insert(`[contract=tid=${tid}]${text||'Start Contract'}[/contract]`) }) },
            { label: 'With UID',    hint: 'Pre-fill a specific UID',        action: () => openModal([{key:'uid',label:'User ID',placeholder:'42221'},{key:'text',label:'Button text',default:'Start Contract'}], ({uid,text}) => { if(uid) insert(`[contract=uid=${uid}]${text||'Start Contract'}[/contract]`) }) },
          ]
          const [cOpen, setCOpen] = useState(false)
          const cRef = useRef(null)
          useEffect(() => {
            const h = e => { if(cRef.current && !cRef.current.contains(e.target)) setCOpen(false) }
            document.addEventListener('mousedown', h)
            return () => document.removeEventListener('mousedown', h)
          }, [])
          return (
            <div ref={cRef} style={{ position:'relative', display:'inline-flex', alignSelf:'center' }}>
              <button type="button" style={{...btnStyle, display:'flex', alignItems:'center', gap:3}}
                onMouseOver={hov} onMouseOut={unv} onClick={() => setCOpen(o => !o)}>
                Contract {cOpen ? '▲' : '▼'}
              </button>
              {cOpen && (
                <div style={{
                  position:'absolute', top:'100%', left:0, zIndex:200, marginTop:3,
                  background:'var(--s2)', border:'1px solid var(--b2)', borderRadius:4,
                  minWidth:160, boxShadow:'0 4px 16px rgba(0,0,0,.4)',
                }}>
                  {CONTRACT_OPTS.map(o => (
                    <button key={o.label} type="button"
                      onClick={() => { setCOpen(false); o.action() }}
                      style={{ display:'block', width:'100%', textAlign:'left', padding:'7px 12px',
                        fontSize:11.5, background:'none', border:'none', color:'var(--sub)',
                        cursor:'pointer', fontFamily:'var(--sans)', transition:'all 120ms' }}
                      onMouseOver={e => { e.currentTarget.style.background='var(--s3)'; e.currentTarget.style.color='var(--text)' }}
                      onMouseOut={e => { e.currentTarget.style.background='none'; e.currentTarget.style.color='var(--sub)' }}
                    >
                      <span style={{ fontWeight:600 }}>{o.label}</span>
                      <span style={{ fontSize:9, color:'var(--dim)', display:'block', marginTop:1 }}>{o.hint}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )
        })()}
        <Btn label="Mention" title="Mention a user by UID" onClick={() => openModal(
          [{ key:'uid', label:'User ID', placeholder:'' }],
          ({uid}) => { if(uid) insert(`[mention=${uid}]`) }
        )} />
        <Btn label="PM Me"    title="PM link"         onClick={() => openModal(
          [
            { key:'subject', label:'PM Subject',  placeholder:'Hello' },
            { key:'text',    label:'Link Text',   placeholder:'PM Me' },
          ],
          ({subject,text}) => insert(`[pmme=${subject||'Hello'}]${text||'PM Me'}[/pmme]`)
        )} />

        {/* Group assets — collapsed dropdown */}
        {(() => {
          const GROUP_ASSETS = [
            {
              gid: '68', name: 'Brotherhood',
              items: [
                { label: 'Header',  action: () => insert('[align=center][img]https://i.ibb.co/C33BJJJg/header4.gif[/img][/align]') },
                { label: 'Div 1',   action: () => insert('[align=center][img]https://i.ibb.co/bpzTMYh/divider3.gif[/img][/align]') },
                { label: 'Div 2',   action: () => insert('[align=center][img]https://i.ibb.co/N2NSzmv9/divider.gif[/img][/align]') },
                { label: '[css]',   action: () => wrap('[css=68]','[/css]') },
              ]
            },
            {
              gid: '78', name: 'VIBE',
              items: [
                { label: 'Header',  action: () => insert('[align=center][img]https://i.ibb.co/4RGC0JNd/Vibe-Header.gif[/img][/align]') },
                { label: 'Divider', action: () => insert('[align=center][img]https://i.ibb.co/8LvxwtYQ/vibesignature.gif[/img][/align]') },
                { label: '[css]',   action: () => wrap('[css=78]','[/css]') },
              ]
            },
          ]
          const myGroups = GROUP_ASSETS.filter(g => userGroups?.includes(g.gid))
          if (!myGroups.length) return null
          return <GroupDropdown groups={myGroups} />
        })()}
      </div>

      {/* Textarea */}
      <AutoTextarea
        taRef={taRef}
        value={value}
        onChange={onChange}
        onFocus={e => e.currentTarget.style.borderColor='var(--acc)'}
        onBlur={e => e.currentTarget.style.borderColor='var(--b2)'}
      />
    </div>
  )
}

// ── BBCode Preview ────────────────────────────────────────────────────────────
// Inject @keyframes for group CSS animations once into the document
const PREVIEW_STYLE = `
  @keyframes brotherhood-shine {
    0%   { background-position: 300% center; }
    100% { background-position: -300% center; }
  }
  @keyframes vibe-glitch {
    0%,10%,50%,72%,100% { transform: translate(0); }
    4%  { transform: translate(-1px,0); }
    5%  { transform: translate(1px,0); }
    8%  { transform: translate(-2px,1px); }
    9%  { transform: translate(2px,-1px); }
    70% { transform: translate(-1px,0); }
    71% { transform: translate(1px,0); }
  }
  @keyframes lasers {
    0%   { background-position: 0% 50%; }
    100% { background-position: 100% 50%; }
  }
  @keyframes blinkingText {
    0%,49%  { color: #ccc; }
    60%,99% { color: transparent; }
    100%    { color: #ccc; }
  }
`

function BBPreview({ message, title, userGroups, compact }) {
  const html = useMemo(() => bbToHtml(message, userGroups), [message, userGroups])
  return (
    <div style={{
      background: compact ? 'var(--s3)' : '#343434', border: compact ? 'none' : '1px solid #444', borderRadius: compact ? 0 : 4,
      overflow: 'hidden',
    }}>
      <style>{PREVIEW_STYLE}</style>
      {title && (
        <div style={{
          background: '#555', borderBottom: '1px solid #444',
          padding: '6px 14px', fontSize: 14, fontWeight: 700, color: '#eee',
          fontFamily: 'Verdana, Arial, sans-serif',
        }}>
          {title}
        </div>
      )}
      {message
        ? <div
            style={{
              padding: compact ? '10px 12px' : '14px 16px',
              minHeight: compact ? 0 : 200, overflowY: 'auto',
              fontSize: 13, lineHeight: 1.7, color: compact ? 'var(--text)' : '#ccc',
              fontFamily: 'Verdana, Arial, sans-serif', wordBreak: 'break-word',
            }}
            dangerouslySetInnerHTML={{ __html: html }}
          />
        : <div style={{ padding: '14px 16px', fontSize: 12, color: '#777', fontStyle: 'italic', fontFamily: 'Verdana, Arial, sans-serif' }}>
            Nothing to preview yet…
          </div>
      }
    </div>
  )
}

// ── Composer ──────────────────────────────────────────────────────────────────
const FOOTER_TEXT = '[align=center][color=#7b94b5][size=small]Posted via [url=https://hftoolbox.com]HFToolbox[/url][/size][/color][/align]'
const BUMP_INTERVALS = [6, 8, 12, 18, 24]

function Composer({ onPosted }) {
  const user = useStore(s => s.user)
  const userGroups = user?.groups || []
  const [forum,       setForum]       = useState(null)
  const [title,       setTitle]       = useState('')
  const [message,     setMessage]     = useState('')
  const [scheduled,   setScheduled]   = useState(false)
  const [fireAt,      setFireAt]      = useState(() => { const d=new Date(Date.now()+3600000); return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')+'T'+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0') })
  const [preview,     setPreview]     = useState(false)
  const [sideBySide,  setSideBySide]  = useState(false)
  const [submitting,  setSubmitting]  = useState(false)
  const [result,      setResult]      = useState(null)
  const [recents,     setRecents]     = useState([])
  const [confirm,     setConfirm]     = useState(false)
  // New options
  const [addFooter,   setAddFooter]   = useState(false)
  const [autoBump,    setAutoBump]    = useState(false)
  const [bumpInterval,setBumpInterval]= useState(12)

  useEffect(() => {
    api.get('/api/posting/recents').then(d => setRecents(d.recents || [])).catch(() => {})
    // Load saved prefs
    api.get('/api/settings').then(d => {
      const s = d.settings || {}
      if (s.postingFooter !== undefined) setAddFooter(Boolean(s.postingFooter))
      if (s.postingBumpInterval) setBumpInterval(s.postingBumpInterval)
    }).catch(() => {})
  }, [])

  // Persist footer toggle when changed
  const toggleFooter = (val) => {
    setAddFooter(val)
    api.post('/api/settings', { postingFooter: val }).catch(() => {})
  }

  const rule = forum ? FORUM_RULES[parseInt(forum.fid)] : null
  const canSubmit = forum && title.trim() && message.trim() && !submitting

  const submit = async () => {
    if (!canSubmit) return
    setConfirm(false)
    setSubmitting(true)
    setResult(null)
    try {
      let fire_at = 0
      if (scheduled && fireAt) {
        fire_at = Math.floor(new Date(fireAt).getTime() / 1000)
        if (isNaN(fire_at) || fire_at <= 0) {
          setResult({ ok: false, error: 'Invalid scheduled time' })
          setSubmitting(false)
          return
        }
      }

      const finalMessage = addFooter
        ? message.trim() + '\n\n' + FOOTER_TEXT
        : message.trim()

      const d = await api.post('/api/posting/thread', {
        fid:             forum.fid,
        forum_name:      forum.name,
        category_name:   forum.cat,
        subject:         title.trim(),
        message:         finalMessage,
        fire_at,
        auto_bump:       autoBump,
        bump_interval_h: bumpInterval,
      })

      setResult({
        ok: true,
        message: d.message,
        id: d.id,
        tid: d.tid,
        scheduled: d.scheduled,
        fire_at: d.fire_at,
        bumperAdded: autoBump && !d.scheduled,
      })
      if (!d.scheduled) {
        setTitle('')
        setMessage('')
        setForum(null)
      }
      onPosted?.()
    } catch (e) {
      setResult({ ok: false, error: e.message || 'Failed' })
    }
    setSubmitting(false)
  }

  const editorContent = (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, flex: 1, minWidth: 0 }}>
      {/* Forum selector */}
      <div>
        <div style={{ fontSize: 9, color: 'var(--dim)', textTransform: 'uppercase', letterSpacing: '.08em', fontFamily: 'var(--mono)', marginBottom: 5 }}>Forum</div>
        <ForumSelector value={forum} onChange={setForum} recents={recents} userGroups={userGroups} />
      </div>

      {/* Forum rules */}
      {rule && (
        <div style={{ background: 'rgba(255,165,2,.06)', border: '1px solid rgba(255,165,2,.2)', borderRadius: 4, padding: '7px 10px', fontSize: 11, color: 'var(--yellow)', lineHeight: 1.5 }}>
          {rule}
        </div>
      )}

      {/* Title */}
      <div>
        <div style={{ fontSize: 9, color: 'var(--dim)', textTransform: 'uppercase', letterSpacing: '.08em', fontFamily: 'var(--mono)', marginBottom: 5 }}>Thread Title</div>
        <input className="inp" style={{ width: '100%' }} placeholder="Thread title…"
          value={title} onChange={e => setTitle(e.target.value)} />
        <div style={{ fontSize: 9, color: 'var(--dim)', marginTop: 3 }}>
          ⚠ Prefixes must be set directly on HackForums after posting.
        </div>
      </div>

      {/* Editor */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5 }}>
          <div style={{ fontSize: 9, color: 'var(--dim)', textTransform: 'uppercase', letterSpacing: '.08em', fontFamily: 'var(--mono)' }}>Content</div>
          <div style={{ display: 'flex', gap: 5 }}>
            <button className="btn btn-ghost" style={{ fontSize: 10, padding: '2px 8px' }}
              onClick={() => { setPreview(!preview); if (!preview) setSideBySide(false) }}>
              {preview ? 'Hide Preview' : 'Preview'}
            </button>
            {preview && (
              <button className="btn btn-ghost" style={{ fontSize: 10, padding: '2px 8px' }}
                onClick={() => setSideBySide(!sideBySide)}>
                {sideBySide ? 'Stack' : 'Side by Side'}
              </button>
            )}
          </div>
        </div>
        {sideBySide ? (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <BBEditor value={message} onChange={setMessage} userGroups={userGroups} />
            <BBPreview message={addFooter ? message + '\n\n' + FOOTER_TEXT : message} title={title} userGroups={userGroups} />
          </div>
        ) : (
          <>
            <BBEditor value={message} onChange={setMessage} userGroups={userGroups} />
            {preview && <div style={{ marginTop: 8 }}><BBPreview message={addFooter ? message + '\n\n' + FOOTER_TEXT : message} title={title} userGroups={userGroups} /></div>}
          </>
        )}
      </div>

      {/* ── Bottom options panel ── */}
      <div style={{ border: '1px solid var(--b1)', borderRadius: 4, overflow: 'hidden' }}>

        {/* Schedule row */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 12px', borderBottom: scheduled ? '1px solid var(--b1)' : 'none', background: 'var(--s3)' }}>
          <button className={`tog${scheduled ? '' : ' off'}`} onClick={() => setScheduled(!scheduled)} />
          <span style={{ fontSize: 12, color: 'var(--sub)', fontWeight: 500 }}>Schedule post</span>
          {scheduled && fireAt && (() => {
            const d = new Date(fireAt)
            return <span style={{ fontSize: 11, color: 'var(--acc)', fontFamily: 'var(--mono)' }}>→ {d.toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric'})} at {d.toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit'})}</span>
          })()}
        </div>
        {scheduled && (
          <div style={{ display:'flex', gap:8, alignItems:'center', flexWrap:'wrap', padding:'10px 12px', background:'var(--bg)', borderBottom:'1px solid var(--b1)' }}>
            <input type="datetime-local" className="inp"
              value={fireAt}
              min={(() => { const n=new Date(); return n.getFullYear()+'-'+String(n.getMonth()+1).padStart(2,'0')+'-'+String(n.getDate()).padStart(2,'0')+'T'+String(n.getHours()).padStart(2,'0')+':'+String(n.getMinutes()).padStart(2,'0') })()}
              onChange={e => setFireAt(e.target.value)}
              style={{ fontSize:12 }}
            />
            <div style={{ display:'flex', gap:3 }}>
              {[['1h',1],['6h',6],['12h',12],['1d',24],['2d',48],['1wk',168]].map(([lbl,hrs]) => (
                <button key={lbl} className="btn btn-ghost" style={{ fontSize:10, padding:'4px 9px' }}
                  onClick={() => { const d=new Date(Date.now()+hrs*3600000); setFireAt(d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')+'T'+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0')) }}>
                  {lbl}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Footer row */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 12px', borderBottom: '1px solid var(--b1)', background: 'var(--s3)' }}>
          <button className={`tog${addFooter ? '' : ' off'}`} onClick={() => toggleFooter(!addFooter)} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <span style={{ fontSize: 12, color: 'var(--sub)', fontWeight: 500 }}>HFToolbox footer</span>
            <span style={{ fontSize: 10, color: 'var(--dim)', marginLeft: 8 }}>— promotes the tool at the bottom of your post</span>
          </div>
          {addFooter && (
            <span style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)', fontStyle: 'italic' }}>visible in preview ↑</span>
          )}
        </div>

        {/* Auto-bump row */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 12px', background: 'var(--s3)' }}>
          <button className={`tog${autoBump ? '' : ' off'}`} onClick={() => setAutoBump(!autoBump)} />
          <span style={{ fontSize: 12, color: 'var(--sub)', fontWeight: 500 }}>Add to Auto Bumper</span>
          {autoBump && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginLeft: 4 }}>
              <span style={{ fontSize: 10, color: 'var(--dim)' }}>every</span>
              {BUMP_INTERVALS.map(h => (
                <button key={h}
                  className={bumpInterval === h ? 'btn btn-acc' : 'btn btn-ghost'}
                  style={{ fontSize: 10, padding: '2px 8px' }}
                  onClick={() => setBumpInterval(h)}
                >{h}h</button>
              ))}
            </div>
          )}
        </div>

      </div>

      {/* Result */}
      {result && (
        <div style={{
          padding: '8px 12px', borderRadius: 4, fontSize: 12,
          background: result.ok ? 'rgba(0,212,180,.06)' : 'var(--red2)',
          border: `1px solid ${result.ok ? 'rgba(0,212,180,.2)' : 'rgba(255,71,87,.2)'}`,
          color: result.ok ? 'var(--acc)' : 'var(--red)',
        }}>
          {result.ok
            ? <div>
                {result.message}
                {result.bumperAdded && <span style={{ marginLeft: 10, color: 'var(--yellow)' }}>⬆ Added to bumper ({bumpInterval}h)</span>}
                {result.tid && <span style={{ marginLeft: 10 }}><a href={`https://hackforums.net/showthread.php?tid=${result.tid}`} target="_blank" rel="noreferrer" style={{ color: 'var(--acc)' }}>View thread →</a></span>}
              </div>
            : `Error: ${result.error}`
          }
        </div>
      )}

      {/* Submit */}
      {!confirm ? (
        <div style={{ display:'flex', gap:8, alignItems:'center' }}>
          <button
            className="btn btn-acc"
            style={{ padding: '7px 20px', fontSize: 12 }}
            disabled={!canSubmit}
            onClick={() => scheduled ? submit() : setConfirm(true)}
          >
            {submitting ? 'Queuing…' : scheduled ? 'Schedule Thread' : 'Post Thread'}
          </button>
          <button
            className="btn btn-ghost"
            style={{ fontSize: 11 }}
            disabled={!(forum && title.trim() && message.trim())}
            onClick={async () => {
              if (!forum || !title.trim() || !message.trim()) return
              await api.post('/api/posting/drafts', {
                fid: forum.fid, forum_name: forum.name,
                subject: title.trim(), message: message.trim()
              })
              setResult({ ok: true, draft: true })
            }}
          >
            Save as draft
          </button>
        </div>
      ) : (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 12, color: 'var(--yellow)' }}>
            Post to <strong>{forum?.name}</strong>?
          </span>
          <button className="btn btn-acc" style={{ fontSize: 11, padding: '4px 14px' }}
            disabled={submitting} onClick={submit}>
            {submitting ? '…' : 'Yes, Post Now'}
          </button>
          <button className="btn btn-ghost" style={{ fontSize: 11 }}
            onClick={() => setConfirm(false)}>Cancel</button>
        </div>
      )}
    </div>
  )

  return editorContent
}

// ── Reply Queue ───────────────────────────────────────────────────────────────


function PostToThread() {
  const user       = useStore(s => s.user)
  const userGroups = user?.groups || []
  const [threads,     setThreads]     = useState([])
  const [loading,     setLoading]     = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [pgNum,       setPgNum]       = useState(1)
  const [hasMore,     setHasMore]     = useState(true)
  const [selected,    setSelected]    = useState(null)
  const [search,      setSearch]      = useState('')
  const [message,     setMessage]     = useState('')
  const [preview,     setPreview]     = useState(false)
  const [addFooter,   setAddFooter]   = useState(false)
  const [submitting,  setSubmitting]  = useState(false)
  const [result,      setResult]      = useState(null)

  const loadPage = useCallback((pg, append) => {
    if (pg === 1) setLoading(true); else setLoadingMore(true)
    api.get(`/api/posting/hf-threads?page=${pg}`)
      .then(d => {
        const rows = d.threads || []
        setThreads(t => append ? [...t, ...rows] : rows)
        setHasMore(rows.length === 30)
        setPgNum(pg)
        setLoading(false)
        setLoadingMore(false)
      })
      .catch(() => { setLoading(false); setLoadingMore(false) })
  }, [])

  useEffect(() => {
    loadPage(1, false)
    api.get('/api/settings').then(d => {
      const s = d.settings || {}
      if (s.postingFooter !== undefined) setAddFooter(Boolean(s.postingFooter))
    }).catch(() => {})
  }, [loadPage])

  const filtered = search.trim()
    ? threads.filter(t => (t.subject||'').toLowerCase().includes(search.toLowerCase()) || String(t.tid).includes(search))
    : threads

  const submit = async () => {
    if (!selected || !message.trim() || submitting) return
    setSubmitting(true)
    setResult(null)
    try {
      const finalMsg = addFooter ? message.trim() + '\n\n' + FOOTER_TEXT : message.trim()
      const d = await api.post('/api/posting/reply', { tid: String(selected.tid), message: finalMsg })
      if (d?.ok || d?.pid) {
        setResult({ ok: true, pid: d.pid })
        setMessage('')
      } else {
        setResult({ ok: false, error: d?.error || 'Post failed' })
      }
    } catch(e) {
      setResult({ ok: false, error: e.message })
    }
    setSubmitting(false)
  }

  if (loading) return <div style={{ padding: 30, display: 'flex', justifyContent: 'center' }}><div className="spin"/></div>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: '10px 0' }}>
      {!selected ? (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 11, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>YOUR THREADS</span>
            <input className="inp" placeholder="Search…" value={search}
              onChange={e => setSearch(e.target.value)} style={{ flex: 1, maxWidth: 260 }} />
            <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>
              {filtered.length}{hasMore && !search.trim() ? '+' : ''} threads
            </span>
          </div>

          {filtered.length === 0 && !loading && (
            <div style={{ fontSize: 12, color: 'var(--dim)', fontStyle: 'italic' }}>No threads found.</div>
          )}

          <div style={{ display: 'flex', flexDirection: 'column', gap: 2, maxHeight: 320, overflowY: 'auto' }}>
            {filtered.map(t => (
              <div key={t.tid} onClick={() => { setSelected(t); setResult(null) }}
                style={{ padding: '8px 10px', borderRadius: 4, cursor: 'pointer',
                  border: '1px solid var(--b1)', background: 'var(--card)', transition: 'border-color 120ms' }}
                onMouseOver={e => e.currentTarget.style.borderColor='var(--blue)'}
                onMouseOut={e => e.currentTarget.style.borderColor='var(--b1)'}
              >
                <div style={{ fontSize: 12, color: 'var(--text)', fontWeight: 500, marginBottom: 2,
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.subject}</div>
                <div style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>
                  TID {t.tid}
                  <a href={`https://hackforums.net/showthread.php?tid=${t.tid}`}
                    target="_blank" rel="noreferrer"
                    style={{ color: 'var(--blue)', marginLeft: 8 }}
                    onClick={e => e.stopPropagation()}>view →</a>
                </div>
              </div>
            ))}
          </div>

          {hasMore && !search.trim() && (
            <button className="btn btn-ghost" style={{ fontSize: 11, alignSelf: 'flex-start' }}
              disabled={loadingMore} onClick={() => loadPage(pgNum + 1, true)}>
              {loadingMore ? 'Loading…' : 'Load more'}
            </button>
          )}
        </>
      ) : (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <button className="btn btn-ghost" style={{ fontSize: 11, padding: '3px 8px' }}
              onClick={() => { setSelected(null); setResult(null) }}>← Back</button>
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', flex: 1,
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{selected.subject}</span>
            <a href={`https://hackforums.net/showthread.php?tid=${selected.tid}`}
              target="_blank" rel="noreferrer" style={{ fontSize: 11, color: 'var(--blue)', flexShrink: 0 }}>
              TID {selected.tid} →</a>
            <label style={{ fontSize: 11, color: 'var(--dim)', display: 'flex', alignItems: 'center', gap: 4, cursor: 'pointer' }}>
              <input type="checkbox" checked={preview} onChange={e => setPreview(e.target.checked)} /> Preview
            </label>
            <label style={{ fontSize: 11, color: 'var(--dim)', display: 'flex', alignItems: 'center', gap: 4, cursor: 'pointer' }}>
              <input type="checkbox" checked={addFooter} onChange={e => setAddFooter(e.target.checked)} /> Footer
            </label>
          </div>

          {preview ? (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <BBEditor value={message} onChange={setMessage} userGroups={userGroups} />
              <BBPreview message={addFooter ? message + '\n\n' + FOOTER_TEXT : message} title="" userGroups={userGroups} />
            </div>
          ) : (
            <BBEditor value={message} onChange={setMessage} userGroups={userGroups} />
          )}

          {result && (
            <div style={{
              padding: '8px 12px', borderRadius: 4, fontSize: 12,
              background: result.ok ? 'rgba(0,212,180,.06)' : 'rgba(255,71,87,.06)',
              border: `1px solid ${result.ok ? 'rgba(0,212,180,.2)' : 'rgba(255,71,87,.2)'}`,
              color: result.ok ? 'var(--acc)' : 'var(--red)',
            }}>
              {result.ok
                ? <>✓ Posted{result.pid && <> — <a href={`https://hackforums.net/showthread.php?pid=${result.pid}#pid${result.pid}`}
                    target="_blank" rel="noreferrer" style={{ color: 'var(--blue)' }}>View post →</a></>}</>
                : `Error: ${result.error}`}
            </div>
          )}

          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-p" disabled={!message.trim() || submitting}
              onClick={submit} style={{ fontSize: 12 }}>
              {submitting ? 'Posting…' : 'Post'}
            </button>
            {message && <button className="btn btn-ghost" style={{ fontSize: 12 }}
              onClick={() => { setMessage(''); setResult(null) }}>Clear</button>}
          </div>
        </>
      )}
    </div>
  )
}


function DraftsPanel({ onSchedule }) {
  const user       = useStore(s => s.user)
  const userGroups = user?.groups || []
  const [drafts,     setDrafts]     = useState([])
  const [loading,    setLoading]    = useState(true)
  const [editing,     setEditing]    = useState(null)
  const [editPreview, setEditPreview] = useState(false)
  const [scheduling,  setScheduling] = useState(null)
  const [fireAt,     setFireAt]     = useState(() => { const d=new Date(Date.now()+3600000); return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')+'T'+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0') })
  const [saving,     setSaving]     = useState(false)

  const load = useCallback(() => {
    api.get('/api/posting/drafts').then(d => {
      setDrafts(d.drafts || [])
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  const deleteDraft = async (id) => {
    await api.delete(`/api/posting/drafts/${id}`)
    setDrafts(d => d.filter(x => x.id !== id))
  }

  const scheduleNow = async (draft) => {
    // Schedule immediately (fire on next tick)
    const res = await api.post('/api/posting/thread', {
      fid: draft.fid, forum_name: draft.forum_name,
      subject: draft.subject, message: draft.message,
      fire_at: 0,
    })
    if (res?.ok || res?.id) {
      await api.delete(`/api/posting/drafts/${draft.id}`)
      setDrafts(d => d.filter(x => x.id !== draft.id))
      onSchedule?.()
    }
  }

  const scheduleLater = async (draft) => {
    if (!fireAt) return
    const fire_at = Math.floor(new Date(fireAt).getTime() / 1000)
    if (isNaN(fire_at) || fire_at <= 0) return
    setSaving(true)
    const res = await api.post('/api/posting/thread', {
      fid: draft.fid, forum_name: draft.forum_name,
      subject: draft.subject, message: draft.message,
      fire_at,
    })
    if (res?.ok || res?.id) {
      await api.delete(`/api/posting/drafts/${draft.id}`)
      setDrafts(d => d.filter(x => x.id !== draft.id))
      onSchedule?.()
    }
    setSaving(false)
    setScheduling(null)
  }

  const saveEdit = async (draft) => {
    await api.put(`/api/posting/drafts/${draft.id}`, {
      fid: draft.fid, forum_name: draft.forum_name,
      subject: editing.subject, message: editing.message,
    })
    setDrafts(d => d.map(x => x.id === draft.id ? { ...x, ...editing } : x))
    setEditing(null)
  }

  const fmtDate = ts => new Date(ts * 1000).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
  })

  if (loading) return <div style={{ display:'flex', justifyContent:'center', padding:20 }}><div className="spin"/></div>

  if (!drafts.length) return (
    <div style={{ fontSize:12, color:'var(--dim)', fontStyle:'italic', padding:'8px 0' }}>
      No drafts. Cancel a scheduled thread to save it here, or save from the composer.
    </div>
  )

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:8, padding:'8px 0' }}>
      {drafts.map(d => (
        <div key={d.id} style={{ border:'1px solid var(--b1)', borderRadius:4, background:'var(--card)', overflow:'hidden' }}>

          {/* Header row */}
          <div style={{ display:'grid', gridTemplateColumns:'1fr auto', gap:8, alignItems:'center', padding:'8px 10px' }}>
            <div>
              <div style={{ fontSize:12, fontWeight:600, marginBottom:2 }}>{d.subject}</div>
              <div style={{ fontSize:10, color:'var(--dim)' }}>{d.forum_name} · Saved {fmtDate(d.updated_at)}</div>
            </div>
            <div style={{ display:'flex', gap:4 }}>
              <button className="btn btn-ghost" style={{ fontSize:10, padding:'2px 7px' }}
                onClick={() => { const closing = editing?.id === d.id; setEditing(closing ? null : { id:d.id, subject:d.subject, message:d.message }); if(closing) setEditPreview(false) }}>
                {editing?.id === d.id ? 'Close' : 'Edit'}
              </button>
              <button className="btn btn-acc" style={{ fontSize:10, padding:'2px 7px' }}
                onClick={() => scheduleNow(d)}>
                Post now
              </button>
              <button className="btn btn-ghost" style={{ fontSize:10, padding:'2px 7px' }}
                onClick={() => { setScheduling(scheduling?.id === d.id ? null : d); const dt=new Date(Date.now()+3600000); setFireAt(dt.getFullYear()+'-'+String(dt.getMonth()+1).padStart(2,'0')+'-'+String(dt.getDate()).padStart(2,'0')+'T'+String(dt.getHours()).padStart(2,'0')+':'+String(dt.getMinutes()).padStart(2,'0')) }}>
                Schedule
              </button>
              <button className="btn btn-danger" style={{ fontSize:10, padding:'2px 7px' }}
                onClick={() => deleteDraft(d.id)}>Delete</button>
            </div>
          </div>

          {/* Schedule picker */}
          {scheduling?.id === d.id && (
            <div style={{ padding:'8px 10px', borderTop:'1px solid var(--b1)', display:'flex', gap:8, alignItems:'center', background:'var(--s2)' }}>
              <span style={{ fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)' }}>FIRE AT</span>
              <input type="datetime-local" className="inp"
                value={fireAt} onChange={e => setFireAt(e.target.value)}
                min={new Date().toISOString().slice(0,16)}
                style={{ fontSize:11 }} />
              <button className="btn btn-acc" style={{ fontSize:11 }} disabled={saving}
                onClick={() => scheduleLater(d)}>
                {saving ? 'Scheduling…' : 'Schedule'}
              </button>
              <button className="btn btn-ghost" style={{ fontSize:11 }} onClick={() => setScheduling(null)}>Cancel</button>
            </div>
          )}

          {/* Edit panel */}
          {editing?.id === d.id && (
            <div style={{ padding:'8px 10px', borderTop:'1px solid var(--b1)', display:'flex', flexDirection:'column', gap:8, background:'var(--s2)' }}>
              <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                <input className="inp" placeholder="Title" value={editing.subject}
                  onChange={e => setEditing(ed => ({ ...ed, subject: e.target.value }))}
                  style={{ flex:1 }} />
                <label style={{ fontSize:11, color:'var(--dim)', display:'flex', alignItems:'center', gap:4, cursor:'pointer', flexShrink:0 }}>
                  <input type="checkbox" checked={editPreview} onChange={e => setEditPreview(e.target.checked)} /> Preview
                </label>
              </div>
              {editPreview ? (
                <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8 }}>
                  <BBEditor value={editing.message} onChange={v => setEditing(ed => ({ ...ed, message: v }))} userGroups={userGroups} />
                  <BBPreview message={editing.message} title={editing.subject} userGroups={userGroups} />
                </div>
              ) : (
                <BBEditor value={editing.message} onChange={v => setEditing(ed => ({ ...ed, message: v }))} userGroups={userGroups} />
              )}
              <div style={{ display:'flex', gap:6 }}>
                <button className="btn btn-acc" style={{ fontSize:11 }} onClick={() => saveEdit(d)}>Save draft</button>
                <button className="btn btn-ghost" style={{ fontSize:11 }} onClick={() => setEditing(null)}>Discard</button>
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function ReplyQueue({ onCountChange }) {
  const user       = useStore(s => s.user)
  const userGroups = user?.groups || []
  const [replies,    setReplies]    = useState([])
  const [loading,    setLoading]    = useState(true)
  const [expandedTid, setExpandedTid] = useState(null)
  const [multiSel,   setMultiSel]   = useState({})
  const [threadMsg,  setThreadMsg]  = useState({})
  const [preview,    setPreview]    = useState({})
  const [sending,    setSending]    = useState({})
  const [sendResult, setSendResult] = useState({})

  const load = useCallback(() => {
    api.get('/api/posting/replies')
      .then(d => {
        const rs = d.replies || []
        setReplies(rs)
        onCountChange?.(rs.length)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  const stripQuotes = msg => (msg || '').replace(/\[quote[^\]]*\][\s\S]*?\[\/quote\]/gi, '').trim()

  const threads = useMemo(() => {
    const map = {}
    for (const r of replies) {
      if (!map[r.tid]) map[r.tid] = { tid: r.tid, title: r.thread_title, replies: [] }
      map[r.tid].replies.push(r)
    }
    for (const t of Object.values(map)) t.replies.sort((a, b) => a.dateline - b.dateline)
    return Object.values(map)
  }, [replies])

  const ago = ts => {
    if (!ts) return ''
    const d = Math.floor(Date.now() / 1000) - ts
    if (d < 60)    return `${d}s ago`
    if (d < 3600)  return `${Math.floor(d/60)}m ago`
    if (d < 86400) return `${Math.floor(d/3600)}h ago`
    return `${Math.floor(d/86400)}d ago`
  }

  const toggleMulti = (tid, id) => {
    setMultiSel(s => {
      const set = new Set(s[tid] || [])
      set.has(id) ? set.delete(id) : set.add(id)
      return { ...s, [tid]: set }
    })
  }

  const buildQuote = r => {
    const clean = stripQuotes(r.full_message).trim()
    return `[quote="${r.from_username}" pid='${r.pid}' dateline='${r.dateline}']${clean}[/quote]`
  }

  const buildMultiQuote = (tid, threadReplies) => {
    const ids = multiSel[tid] || new Set()
    const picked = threadReplies.filter(r => ids.has(r.id))
    const MAX = 4
    const capped = picked.slice(0, MAX)
    const overflow = picked.length - MAX
    const blocks = capped.map(r => buildQuote(r))
    if (overflow > 0) blocks.push(`[i](+${overflow} more omitted)[/i]`)
    return blocks.join('\n\n') + '\n\n'
  }

  const quoteOne = r => {
    setThreadMsg(m => ({ ...m, [r.tid]: buildQuote(r) + '\n\n' }))
    setExpandedTid(r.tid)
  }

  const replyWithMulti = (tid, threadReplies) => {
    setThreadMsg(m => ({ ...m, [tid]: buildMultiQuote(tid, threadReplies) }))
    setExpandedTid(tid)
  }

  const dismiss = async (id, tid) => {
    await api.post(`/api/posting/replies/${id}/dismiss`)
    const remaining = replies.filter(r => r.id !== id)
    setReplies(remaining)
    onCountChange?.(remaining.length)
    setMultiSel(s => { const set = new Set(s[tid]||[]); set.delete(id); return {...s,[tid]:set} })
  }

  const dismissAll = async (tid, threadReplies) => {
    await Promise.all(threadReplies.map(r => api.post(`/api/posting/replies/${r.id}/dismiss`)))
    const remaining = replies.filter(r => r.tid !== tid)
    setReplies(remaining)
    onCountChange?.(remaining.length)
    if (expandedTid === tid) setExpandedTid(null)
  }

  const sendReply = async (tid, threadReplies) => {
    const msg = threadMsg[tid] || ''
    if (!msg.trim()) return
    setSending(s => ({...s,[tid]:true}))
    try {
      await api.post('/api/posting/reply', { tid: String(tid), message: msg })
      setSendResult(s => ({...s,[tid]:{ok:true}}))
      const ids = multiSel[tid]
      const toDismiss = ids && ids.size > 0 ? threadReplies.filter(r => ids.has(r.id)) : threadReplies
      setTimeout(async () => {
        await Promise.all(toDismiss.map(r => api.post(`/api/posting/replies/${r.id}/dismiss`)))
        const remaining = replies.filter(r => !toDismiss.some(d => d.id === r.id))
        setReplies(remaining)
        onCountChange?.(remaining.length)
        setThreadMsg(m => ({...m,[tid]:''}))
        setExpandedTid(null)
        setSendResult(s => ({...s,[tid]:null}))
      }, 1200)
    } catch(e) {
      setSendResult(s => ({...s,[tid]:{ok:false,error:e.message}}))
    }
    setSending(s => ({...s,[tid]:false}))
  }

  if (loading) return <div style={{display:'flex',justifyContent:'center',padding:24}}><div className="spin"/></div>
  if (!replies.length) return (
    <div style={{fontFamily:'var(--mono)',fontSize:11,color:'var(--dim)',padding:'20px 0',textAlign:'center'}}>
      // no unread replies
    </div>
  )

  return (
    <div style={{display:'flex',flexDirection:'column',gap:4}}>
      {threads.map(({tid, title, replies: tReplies}) => {
        const isOpen  = expandedTid === tid
        const selSet  = multiSel[tid] || new Set()
        const selCount = selSet.size

        return (
          <div key={tid} style={{
            border:'1px solid var(--b1)',
            borderLeft:'3px solid ' + (isOpen ? 'var(--acc)' : 'var(--b1)'),
            background:'var(--bg)',
            transition:'border-color 150ms',
          }}>

            {/* ── Terminal-style thread header ── */}
            <div
              style={{
                display:'flex', alignItems:'center', gap:0,
                background:'var(--s2)',
                cursor:'pointer', minHeight:42,
                borderBottom: isOpen ? '1px solid var(--b1)' : 'none',
              }}
              onClick={() => setExpandedTid(isOpen ? null : tid)}
            >
              {/* Prompt + chevron */}
              <span style={{
                padding:'7px 10px', fontFamily:'var(--mono)', fontSize:10,
                color:'var(--acc)', flexShrink:0, userSelect:'none',
              }}>
                {isOpen ? '▾' : '▸'}
              </span>

              {/* Thread title — ONLY this opens thread, does NOT expand */}
              <span
                onClick={e => { e.stopPropagation(); window.open(`https://hackforums.net/showthread.php?tid=${tid}`, '_blank') }}
                style={{
                  fontFamily:'var(--mono)', fontSize:11, fontWeight:600,
                  color:'var(--blue)', flexShrink:0, padding:'7px 6px 7px 0',
                  overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap',
                  cursor:'pointer', maxWidth:'40%',
                }}
                onMouseOver={e => { e.currentTarget.style.color='var(--acc)'; e.currentTarget.style.textDecoration='underline' }}
                onMouseOut={e => { e.currentTarget.style.color='var(--blue)'; e.currentTarget.style.textDecoration='none' }}>
                {title}
              </span>

              {/* Spacer — clicking this expands the row (no stopPropagation) */}
              <div style={{flex:1, height:'100%', minHeight:30}} />

              {/* Right side controls */}
              <div style={{display:'flex',alignItems:'center',gap:6,padding:'4px 10px',flexShrink:0}}
                onClick={e => e.stopPropagation()}>
                <span style={{
                  fontFamily:'var(--mono)',fontSize:9,
                  color:'var(--yellow)',fontWeight:700,
                  padding:'1px 6px',border:'1px solid rgba(232,168,40,.3)',
                  background:'rgba(232,168,40,.08)',
                }}>
                  {tReplies.length} new
                </span>
                {selCount > 0 && (
                  <button className="btn btn-acc" style={{fontSize:9,padding:'2px 8px',fontFamily:'var(--mono)'}}
                    onClick={() => replyWithMulti(tid, tReplies)}>
                    reply [{selCount}]
                  </button>
                )}
                <button className="btn btn-ghost" style={{fontSize:9,padding:'2px 8px',fontFamily:'var(--mono)'}}
                  onClick={() => { setThreadMsg(m=>({...m,[tid]:''})); setExpandedTid(tid) }}>
                  reply
                </button>
                <button className="btn btn-danger" style={{fontSize:9,padding:'2px 8px',fontFamily:'var(--mono)'}}
                  onClick={() => dismissAll(tid, tReplies)}>
                  dismiss
                </button>
              </div>
            </div>

            {/* ── Reply list ── */}
            {isOpen && (
              <div>
                {tReplies.map((r, idx) => {
                  const inMulti = selSet.has(r.id)
                  return (
                    <div key={r.id} style={{
                      borderBottom:'1px solid var(--b1)',
                      borderLeft: inMulti ? '2px solid var(--acc)' : '2px solid transparent',
                      transition:'border-color 130ms',
                    }}>
                      {/* Reply meta row */}
                      <div style={{
                        display:'flex', alignItems:'center', gap:8,
                        padding:'5px 10px',
                        background:'var(--s1)',
                        borderBottom:'1px solid var(--b1)',
                      }}>
                        <span style={{fontFamily:'var(--mono)',fontSize:10,color:'var(--dim)'}}>›</span>
                        <span style={{fontFamily:'var(--mono)',fontSize:10,fontWeight:700,color:'var(--acc)'}}>{r.from_username}</span>
                        <span style={{fontFamily:'var(--mono)',fontSize:9,color:'var(--dim)'}}>{ago(r.dateline)}</span>
                        <div style={{flex:1}}/>
                        <button className="btn btn-ghost" style={{fontSize:9,padding:'1px 7px',fontFamily:'var(--mono)'}}
                          onClick={() => quoteOne(r)}>
                          quote
                        </button>
                        <button
                          style={{
                            padding:'1px 7px', fontSize:9, fontFamily:'var(--mono)', fontWeight:700,
                            border:'1px solid '+(inMulti?'var(--acc)':'var(--b2)'),
                            background:inMulti?'rgba(0,212,180,.1)':'transparent',
                            color:inMulti?'var(--acc)':'var(--sub)',
                            cursor:'pointer', borderRadius:3, transition:'all 130ms',
                          }}
                          onClick={() => toggleMulti(tid, r.id)}
                          title={inMulti?'Remove from multi-quote':'Add to multi-quote'}>
                          {inMulti ? '-mq' : '+mq'}
                        </button>
                        <button className="btn btn-danger" style={{fontSize:9,padding:'1px 7px',fontFamily:'var(--mono)'}}
                          onClick={() => dismiss(r.id, tid)}>
                          ✕
                        </button>
                      </div>

                      {/* Post body */}
                      <div style={{background:'var(--bg)'}}>
                        <BBPreview message={r.full_message} userGroups={userGroups} compact />
                      </div>
                    </div>
                  )
                })}

                {/* ── Composer ── */}
                <div style={{background:'var(--bg)',borderTop:'1px solid var(--b2)',padding:'10px 12px'}}>
                  <div style={{display:'flex',justifyContent:'flex-end',marginBottom:6}}>
                    <button className="btn btn-ghost" style={{fontSize:9,padding:'2px 8px',fontFamily:'var(--mono)'}}
                      onClick={() => setPreview(p => ({...p,[tid]:!p[tid]}))}>
                      {preview[tid] ? 'hide preview' : 'preview'}
                    </button>
                  </div>
                  {preview[tid] ? (
                    <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:8}}>
                      <BBEditor value={threadMsg[tid]||''} onChange={v=>setThreadMsg(m=>({...m,[tid]:v}))} userGroups={userGroups}/>
                      <BBPreview message={threadMsg[tid]||''} userGroups={userGroups}/>
                    </div>
                  ) : (
                    <BBEditor value={threadMsg[tid]||''} onChange={v=>setThreadMsg(m=>({...m,[tid]:v}))} userGroups={userGroups}/>
                  )}
                  {sendResult[tid] && (
                    <div style={{
                      fontFamily:'var(--mono)',fontSize:11,padding:'5px 8px',marginTop:6,
                      color:sendResult[tid].ok?'var(--acc)':'var(--red)',
                    }}>
                      {sendResult[tid].ok ? '// reply posted' : `// error: ${sendResult[tid].error}`}
                    </div>
                  )}
                  <div style={{display:'flex',gap:6,marginTop:8}}>
                    <button className="btn btn-acc" style={{fontSize:11,padding:'4px 14px'}}
                      disabled={!(threadMsg[tid]||'').trim()||sending[tid]}
                      onClick={() => sendReply(tid, tReplies)}>
                      {sending[tid] ? '…' : 'Post Reply'}
                    </button>
                    <button className="btn btn-ghost" style={{fontSize:11}}
                      onClick={() => { setExpandedTid(null); setThreadMsg(m=>({...m,[tid]:''})) }}>
                      Cancel
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}


// ── Scheduled Queue panel ─────────────────────────────────────────────────────
function ScheduledQueue({ refresh }) {
  const [queue, setQueue] = useState([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    Promise.all([
      api.get('/api/posting/queue'),
      api.get('/api/posting/sent'),
    ]).then(([q, s]) => {
      setQueue([...(q.queue || []), ...(s.sent || []).slice(0, 10)])
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [refresh])

  useEffect(() => { load() }, [load])

  const [editingTime, setEditingTime] = useState(null) // id of row being rescheduled
  const [editTimeVal, setEditTimeVal] = useState('')

  const cancelToDraft = async (id) => {
    try {
      await api.delete(`/api/posting/queue/${id}/to-draft`)
      setQueue(q => q.filter(x => x.id !== id))
    } catch {}
  }

  const startEditTime = (t) => {
    const d = new Date(t.fire_at * 1000)
    const local = d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+
      String(d.getDate()).padStart(2,'0')+'T'+String(d.getHours()).padStart(2,'0')+':'+
      String(d.getMinutes()).padStart(2,'0')
    setEditTimeVal(local)
    setEditingTime(t.id)
  }

  const saveEditTime = async (id) => {
    const fire_at = Math.floor(new Date(editTimeVal).getTime() / 1000)
    if (isNaN(fire_at) || fire_at <= 0) return
    try {
      await api.patch(`/api/posting/queue/${id}/reschedule`, { fire_at })
      setQueue(q => q.map(x => x.id === id ? { ...x, fire_at } : x))
      setEditingTime(null)
    } catch {}
  }

  const fmtTime = ts => new Date(ts * 1000).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
  })

  const STATUS_COLOR = {
    pending:   'var(--yellow)',
    sending:   'var(--acc)',
    sent:      'var(--green)',
    failed:    'var(--red)',
    cancelled: 'var(--dim)',
  }

  if (loading) return <div style={{ display: 'flex', justifyContent: 'center', padding: 20 }}><div className="spin" /></div>
  if (!queue.length) return <div style={{ fontSize: 12, color: 'var(--dim)', fontStyle: 'italic' }}>No threads queued</div>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {queue.map(t => (
        <div key={t.id} style={{
          display: 'grid', gridTemplateColumns: '1fr auto auto', gap: 8,
          alignItems: 'center', padding: '7px 10px',
          background: 'var(--s3)', border: '1px solid var(--b1)', borderRadius: 4,
        }}>
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 2 }}>{t.subject}</div>
            <div style={{ fontSize: 10, color: 'var(--dim)' }}>
              {t.forum_name} · {t.status === 'sent' ? `Sent ${fmtTime(t.sent_at)}` : `Fires ${fmtTime(t.fire_at)}`}
              {t.tid && <> · <a href={`https://hackforums.net/showthread.php?tid=${t.tid}`} target="_blank" rel="noreferrer" style={{ color: 'var(--acc)' }}>View ↗</a></>}
              {t.error && <span style={{ color: 'var(--red)' }}> · {t.error}</span>}
            </div>
          </div>
          <span style={{
            fontSize: 9, padding: '2px 7px', borderRadius: 2, fontFamily: 'var(--mono)',
            fontWeight: 600, border: '1px solid', textTransform: 'uppercase', letterSpacing: '.04em',
            color: STATUS_COLOR[t.status] || 'var(--dim)',
            background: 'rgba(0,0,0,.2)',
          }}>
            {t.status}
          </span>
          {t.status === 'pending' && editingTime === t.id ? (
            <div style={{ display:'flex', gap:4, alignItems:'center' }}>
              <input type="datetime-local" className="inp"
                value={editTimeVal} onChange={e => setEditTimeVal(e.target.value)}
                style={{ fontSize:10, padding:'2px 6px' }} />
              <button className="btn btn-acc" style={{ fontSize:10, padding:'2px 6px' }}
                onClick={() => saveEditTime(t.id)}>Save</button>
              <button className="btn btn-ghost" style={{ fontSize:10, padding:'2px 6px' }}
                onClick={() => setEditingTime(null)}>✕</button>
            </div>
          ) : t.status === 'pending' ? (
            <div style={{ display:'flex', gap:4 }}>
              <button className="btn btn-ghost" style={{ fontSize:10, padding:'2px 7px' }}
                onClick={() => startEditTime(t)}>Edit time</button>
              <button className="btn btn-danger" style={{ fontSize:10, padding:'2px 7px' }}
                onClick={() => cancelToDraft(t.id)}>Cancel → Draft</button>
            </div>
          ) : null}
        </div>
      ))}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function PostingPage() {
  const [tab,        setTab]        = useState('compose')
  const [replyCount, setReplyCount] = useState(0)
  const [queueKey,   setQueueKey]   = useState(0)
  const fetchMe = useStore(s => s.fetchMe)

  // Refresh user groups from DB on mount — crawl may have updated them since login
  useEffect(() => { fetchMe() }, [])

  useEffect(() => {
    api.get('/api/posting/replies/count').then(d => setReplyCount(d.count || 0)).catch(() => {})
    const id = setInterval(() => {
      api.get('/api/posting/replies/count').then(d => setReplyCount(d.count || 0)).catch(() => {})
    }, 60000)
    return () => clearInterval(id)
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div className="card">
        <div className="card-head">
          <span className="card-icon">💬</span>
          <span className="card-title">Thread & Post Management</span>
        </div>

        <div style={{ display: 'flex', padding: '0 13px', borderBottom: '1px solid var(--b1)' }}>
          {[
            ['compose',    'New Thread',      null],
            ['postthread', 'New Post',         null],
            ['drafts',     'Drafts',          null],
            ['scheduled',  'Scheduled',       null],
            ['replies',    'Replies',         replyCount],
          ].map(([key, label, badge]) => (
            <button key={key} className={`tab${tab === key ? ' on' : ''}`} onClick={() => setTab(key)}>
              {label}
              {badge > 0 && (
                <span style={{
                  marginLeft: 5, fontSize: 9, padding: '1px 5px', borderRadius: 2,
                  background: 'var(--red2)', color: 'var(--red)',
                  border: '1px solid rgba(255,71,87,.2)', fontFamily: 'var(--mono)', fontWeight: 700,
                }}>
                  {badge}
                </span>
              )}
            </button>
          ))}
        </div>

        <div className="card-body">
          {tab === 'compose' && (
            <Composer onPosted={() => setQueueKey(k => k + 1)} />
          )}
          {tab === 'scheduled' && (
            <ScheduledQueue refresh={queueKey} />
          )}
          {tab === 'postthread' && <PostToThread />}
          {tab === 'drafts' && <DraftsPanel onSchedule={() => { setTab('scheduled'); setQueueKey(k => k+1) }} />}
          {tab === 'replies' && (
            <ReplyQueue onCountChange={setReplyCount} />
          )}
        </div>
      </div>
    </div>
  )
}
