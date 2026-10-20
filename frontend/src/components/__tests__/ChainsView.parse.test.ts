import { describe, it, expect } from 'vitest'
import { parseQuery } from '../ChainsView'

describe('chains search parsing', () => {
  it('uses the selected act for a bare section', () => {
    expect(parseQuery('152-10', 'itaa-1997')).toEqual(['itaa-1997', '152-10'])
    expect(parseQuery(' s 152-10 ', 'itaa-1997')).toEqual(['itaa-1997', '152-10'])
  })
  it('takes the act from the query when given', () => {
    expect(parseQuery('itaa-1936 340', 'itaa-1997')).toEqual(['itaa-1936', '340'])
  })
  it('rejects junk', () => {
    expect(parseQuery('', 'itaa-1997')).toBeNull()
    expect(parseQuery('a b c', 'itaa-1997')).toBeNull()
  })
})
