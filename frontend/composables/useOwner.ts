export interface Owner {
  id: string
  full_name: string
  email: string
  phone: string | null
  user_id: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

/**
 * The Owner record linked to the current user — the companion to useAuth's
 * fetchMe()/User. Cached in a useState so pages that both need it
 * (panel.vue's link, panel/apartments.vue) don't each pay for a separate
 * /owners/me round trip within the same session.
 */
export function useOwner() {
  const api = useApi()
  const owner = useState<Owner | null>('current-owner', () => null)

  async function fetchOwner(): Promise<Owner | null> {
    if (owner.value) return owner.value
    try {
      owner.value = await api<Owner>('/owners/me')
    } catch {
      // No linked Owner (admin, or a not-yet-linked owner-role user) — not
      // an error the caller needs to distinguish from a network failure.
      owner.value = null
    }
    return owner.value
  }

  function clearOwner(): void {
    owner.value = null
  }

  return { owner, fetchOwner, clearOwner }
}
