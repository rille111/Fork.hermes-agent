const LEGACY_PRODUCT_ENV_ALIASES = [
  ['KUMO_HOME', 'HERMES_HOME'],
  ['KUMO_DESKTOP_REMOTE_URL', 'HERMES_DESKTOP_REMOTE_URL'],
  ['KUMO_DESKTOP_REMOTE_TOKEN', 'HERMES_DESKTOP_REMOTE_TOKEN'],
  ['KUMO_DESKTOP_APP_NAME', 'HERMES_DESKTOP_APP_NAME'],
  ['KUMO_DESKTOP_USER_DATA_DIR', 'HERMES_DESKTOP_USER_DATA_DIR']
] as const

/**
 * Keep branded launchers compatible with the upstream Hermes environment.
 * Explicit canonical values, including an empty value, always win.
 */
export function applyLegacyProductEnvAliases(env: NodeJS.ProcessEnv = process.env): void {
  for (const [legacyName, canonicalName] of LEGACY_PRODUCT_ENV_ALIASES) {
    if (!(canonicalName in env) && legacyName in env) {
      env[canonicalName] = env[legacyName]
    }
  }
}
