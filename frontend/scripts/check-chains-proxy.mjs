// Plain-node live check: /api/tax/chains returns exactly what tax-encode serves.
// Usage: SESSION_COOKIE=<jwt> node frontend/scripts/check-chains-proxy.mjs
//   APP_URL (default http://127.0.0.1:8765), TAX_API_URL (default http://127.0.0.1:8793)
import assert from 'node:assert/strict'

const APP = process.env.APP_URL || 'http://127.0.0.1:8765'
const TAX = process.env.TAX_API_URL || 'http://127.0.0.1:8793'
const headers = process.env.SESSION_COOKIE ? { Cookie: `session=${process.env.SESSION_COOKIE}` } : {}

const get = async (url, opts) => {
  const r = await fetch(url, opts)
  assert.equal(r.status, 200, `${url} -> ${r.status}`)
  return r.json()
}

const direct = await get(`${TAX}/chains/itaa-1997/152-10`)
const proxied = await get(`${APP}/api/tax/chains/itaa-1997/152-10`, { headers })
assert.ok(direct.nodes.length > 0, 'tax-encode returned an empty graph')
assert.equal(proxied.nodes.length, direct.nodes.length, 'node count differs')
assert.equal(proxied.edges.length, direct.edges.length, 'edge count differs')
assert.deepEqual(proxied.counts, direct.counts, 'counts differ')
console.log(`ok chains itaa-1997/152-10: ${proxied.nodes.length} nodes, ${proxied.edges.length} edges`)
