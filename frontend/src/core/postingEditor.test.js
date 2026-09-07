import { describe, expect, it } from 'vitest'
import { applyTag, findTagAtSelection, imageTag, parseImageOption, wrapSelection } from './postingEditor.js'

describe('posting editor commands', () => {
  it('wraps selected text and keeps it selected', () => {
    expect(wrapSelection('make this bold', { start:5, end:9 }, '[b]', '[/b]')).toEqual({
      value:'make [b]this[/b] bold', start:8, end:12,
    })
  })

  it('inserts paired tags with the caret between them', () => {
    expect(wrapSelection('text', { start:4, end:4 }, '[quote]', '[/quote]')).toEqual({
      value:'text[quote][/quote]', start:11, end:11,
    })
  })

  it('finds and edits the tag containing the caret', () => {
    const text = '[url=https://old.example]label[/url]'
    expect(findTagAtSelection(text, { start:28, end:28 }, new Set(['url']))?.option).toBe('https://old.example')
    expect(applyTag(text, { start:28, end:28 }, 'url', 'https://new.example', 'label').value)
      .toBe('[url=https://new.example]label[/url]')
  })

  it('accepts independent arbitrary image dimensions', () => {
    expect(imageTag('https://example.com/a.jpg', '1200', '500'))
      .toBe('[img=1200x500]https://example.com/a.jpg[/img]')
    expect(imageTag('https://example.com/a.jpg', '', '')).toBe('[img]https://example.com/a.jpg[/img]')
    expect(parseImageOption('320x640')).toEqual({ width:'320', height:'640' })
  })
})
