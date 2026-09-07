const TAGS_WITH_VALUE = new Set(['url', 'color', 'size', 'font', 'align', 'img', 'spoiler', 'quote'])

export function selectionRange(text, selection) {
  const length = String(text || '').length
  const start = Math.max(0, Math.min(Number(selection?.start) || 0, length))
  const end = Math.max(start, Math.min(Number(selection?.end) || start, length))
  return { start, end }
}

export function replaceRange(text, selection, replacement, selectStart, selectEnd) {
  const source = String(text || '')
  const { start, end } = selectionRange(source, selection)
  return {
    value: source.slice(0, start) + replacement + source.slice(end),
    start: start + selectStart,
    end: start + (selectEnd ?? selectStart),
  }
}

export function wrapSelection(text, selection, open, close) {
  const source = String(text || '')
  const { start, end } = selectionRange(source, selection)
  const selected = source.slice(start, end)
  return replaceRange(source, { start, end }, `${open}${selected}${close}`, open.length, open.length + selected.length)
}

export function findTagAtSelection(text, selection, allowedTags = TAGS_WITH_VALUE) {
  const source = String(text || '')
  const { start, end } = selectionRange(source, selection)
  const tagPattern = /\[([a-z]+)(?:=([^\]]*))?\]([\s\S]*?)\[\/\1\]/gi
  let match
  while ((match = tagPattern.exec(source))) {
    const tag = match[1].toLowerCase()
    if (!allowedTags.has(tag)) continue
    const rangeEnd = match.index + match[0].length
    if (start >= match.index && end <= rangeEnd) {
      return {
        tag,
        option: match[2] || '',
        content: match[3],
        start: match.index,
        end: rangeEnd,
      }
    }
  }
  return null
}

export function applyTag(text, selection, tag, option = '', contentOverride) {
  const source = String(text || '')
  const current = findTagAtSelection(source, selection, new Set([tag]))
  const target = current || selectionRange(source, selection)
  const content = contentOverride ?? (current ? current.content : source.slice(target.start, target.end))
  const open = `[${tag}${option ? `=${option}` : ''}]`
  return replaceRange(source, target, `${open}${content}[/${tag}]`, open.length, open.length + content.length)
}

export function removeTag(text, selection, tag) {
  const source = String(text || '')
  const current = findTagAtSelection(source, selection, new Set([tag]))
  if (!current) return { value: source, ...selectionRange(source, selection) }
  return replaceRange(source, current, current.content, 0, current.content.length)
}

export function imageTag(url, width, height) {
  const cleanUrl = String(url || '').trim()
  const w = Number.parseInt(width, 10)
  const h = Number.parseInt(height, 10)
  if (!cleanUrl) return ''
  return Number.isInteger(w) && w > 0 && Number.isInteger(h) && h > 0
    ? `[img=${w}x${h}]${cleanUrl}[/img]`
    : `[img]${cleanUrl}[/img]`
}

export function parseImageOption(option) {
  const match = String(option || '').match(/^(\d+)x(\d+)$/i)
  return match ? { width: match[1], height: match[2] } : { width: '', height: '' }
}
