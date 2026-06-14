import { createSupabaseBrowser } from './supabase-browser'

export async function fetchWithAuth(url: string, options?: RequestInit): Promise<Response> {
  const supabase = createSupabaseBrowser()
  const { data: { session } } = await supabase.auth.getSession()

  return fetch(url, {
    ...options,
    headers: {
      ...options?.headers,
      ...(session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {}),
    },
  })
}
