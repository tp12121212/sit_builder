import { PublicClientApplication, type AccountInfo, type AuthenticationResult, BrowserCacheLocation } from '@azure/msal-browser'

const tenantId = import.meta.env.VITE_AZURE_TENANT_ID ?? 'organizations'
const clientId = import.meta.env.VITE_AZURE_CLIENT_ID ?? ''
const redirectUri = import.meta.env.VITE_AZURE_REDIRECT_URI ?? window.location.origin
const configuredScopes = (import.meta.env.VITE_AZURE_SCOPES as string | undefined)
  ?.split(',')
  .map((scope) => scope.trim())
  .filter(Boolean)

const defaultScopes = ['openid', 'profile', 'offline_access', 'https://outlook.office365.com/.default']

function isLocalhostHost(host: string): boolean {
  return host === 'localhost' || host === '127.0.0.1' || host === '::1'
}

function canUseMsalInCurrentOrigin(): boolean {
  if (!clientId) {
    return false
  }
  // MSAL/browser crypto APIs require secure context; localhost is exempt.
  return window.isSecureContext || isLocalhostHost(window.location.hostname)
}

function shouldUseRedirectAuth(): boolean {
  const ua = navigator.userAgent || ''
  return /iPhone|iPad|iPod|Android|Mobile/i.test(ua)
}

let msal: PublicClientApplication | null = null
let initError: Error | null = null
let redirectHandled: Promise<AuthenticationResult | null> | null = null

function getMsal(): PublicClientApplication | null {
  if (msal || initError) {
    return msal
  }
  if (!canUseMsalInCurrentOrigin()) {
    initError = new Error('Microsoft auth requires HTTPS or localhost origin.')
    return null
  }
  try {
    msal = new PublicClientApplication({
      auth: {
        clientId,
        authority: `https://login.microsoftonline.com/${tenantId}`,
        redirectUri,
      },
      cache: {
        cacheLocation: BrowserCacheLocation.LocalStorage,
      },
    })
    return msal
  } catch (err) {
    initError = err instanceof Error ? err : new Error('Failed to initialize Microsoft auth')
    return null
  }
}

async function handleRedirectResult(instance: PublicClientApplication): Promise<AuthenticationResult | null> {
  if (!redirectHandled) {
    redirectHandled = instance.handleRedirectPromise()
  }
  const result = await redirectHandled
  if (result?.account) {
    instance.setActiveAccount(result.account)
  }
  return result ?? null
}

const loginRequest = {
  scopes: configuredScopes && configuredScopes.length > 0 ? configuredScopes : defaultScopes,
}

export async function loginAndGetToken(): Promise<AuthenticationResult | null> {
  const instance = getMsal()
  if (!instance) {
    throw initError ?? new Error('Microsoft auth is unavailable in this origin.')
  }

  await instance.initialize()
  await handleRedirectResult(instance)

  if (shouldUseRedirectAuth()) {
    await instance.loginRedirect(loginRequest)
    return null
  }

  const loginResult = await instance.loginPopup(loginRequest)
  instance.setActiveAccount(loginResult.account)

  const tokenResult = await instance.acquireTokenSilent({
    ...loginRequest,
    account: loginResult.account,
  })

  return tokenResult
}

export async function getTokenSilently(): Promise<AuthenticationResult | null> {
  const instance = getMsal()
  if (!instance) {
    return null
  }
  await instance.initialize()
  const redirectResult = await handleRedirectResult(instance)
  if (redirectResult?.account) {
    try {
      return await instance.acquireTokenSilent({ ...loginRequest, account: redirectResult.account })
    } catch {
      return redirectResult
    }
  }

  const account = instance.getActiveAccount() ?? instance.getAllAccounts()[0]
  if (!account) {
    return null
  }

  try {
    return await instance.acquireTokenSilent({ ...loginRequest, account })
  } catch {
    return null
  }
}

export function getActiveAccount(): AccountInfo | null {
  const instance = getMsal()
  if (!instance) {
    return null
  }
  const account = instance.getActiveAccount() ?? instance.getAllAccounts()[0] ?? null
  if (account) {
    instance.setActiveAccount(account)
  }
  return account
}
