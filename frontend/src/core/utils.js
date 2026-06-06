/**
 * Extract a numeric HF ID from either a raw number string or a hackforums.net URL.
 *
 * parseHfId('12345',        'tid') => '12345'
 * parseHfId('  12345  ',   'uid') => '12345'
 * parseHfId('https://hackforums.net/showthread.php?tid=12345', 'tid') => '12345'
 * parseHfId('https://hackforums.net/member.php?action=profile&uid=67890', 'uid') => '67890'
 */
export function parseHfId(raw, param) {
  if (!raw) return ''
  const s = raw.trim()
  if (s.includes('hackforums.net')) {
    try {
      const url = new URL(s.startsWith('http') ? s : 'https://' + s)
      const val = url.searchParams.get(param)
      if (val && /^\d+$/.test(val)) return val
    } catch {}
    // Regex fallback for partial/malformed URLs
    const m = s.match(new RegExp('[?&]' + param + '=(\\d+)'))
    if (m) return m[1]
  }
  return s
}
