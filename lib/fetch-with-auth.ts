import { createSupabaseBrowser } from './supabase-browser'
import type { SupabaseClient } from '@supabase/supabase-js'

let _client: SupabaseClient | null = null

function getClient() {
  if (!_client) _client = createSupabaseBrowser()
  return _client
}

export async function fetchWithAuth(url: string, options?: RequestInit): Promise<Response> {
  const supabase = getClient()
  const { data: { session } } = await supabase.auth.getSession()

  return fetch(url, {
    ...options,
    headers: {
      ...options?.headers,
      ...(session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {}),
    },
  })
}
