import { existsSync, readdirSync } from 'node:fs'
import path from 'node:path'

export function validateWorkbenchTestRegistration(root, base, python) {
  const registered = [...base, ...python]
  if (new Set(registered).size !== registered.length) throw new Error('Duplicate Workbench test registration')
  for (const spec of registered) {
    if (!/^tests\/frontend\/[\w-]+\.spec\.ts$/.test(spec) || !existsSync(path.join(root, spec))) {
      throw new Error(`Invalid or missing Workbench test: ${spec}`)
    }
  }
  const missing = readdirSync(path.join(root, 'tests/frontend'))
    .filter(name => /^workbench-v2-.*\.spec\.ts$/.test(name))
    .map(name => `tests/frontend/${name}`)
    .filter(spec => !registered.includes(spec))
  if (missing.length) throw new Error(`Unregistered Workbench tests: ${missing.sort().join(', ')}`)
}
