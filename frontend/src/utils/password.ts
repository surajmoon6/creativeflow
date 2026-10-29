/** Letters and digits without look-alikes (0/O, 1/l/I), so a password read out over a call is hard to get wrong. */
export function makePassword() {
  const chars = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
  const bytes = crypto.getRandomValues(new Uint32Array(14))
  return Array.from(bytes, (b) => chars[b % chars.length]).join('')
}
