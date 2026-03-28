'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'

export default function SyncButton() {
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const router = useRouter()

  async function handleSync() {
    setLoading(true)
    setMessage('')

    const supabase = createClient()
    const {
      data: { session },
    } = await supabase.auth.getSession()

    try {
      const resp = await fetch(
        `${process.env.NEXT_PUBLIC_BACKEND_URL}/api/banking/sync`,
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${session?.access_token}`,
          },
        }
      )
      if (!resp.ok) throw new Error('Sync failed')
      const data = await resp.json()
      setMessage(
        data.synced === 0
          ? 'Already up to date'
          : `${data.synced} new transaction${data.synced !== 1 ? 's' : ''} synced`
      )
      router.refresh()
    } catch {
      setMessage('Sync failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={handleSync}
        disabled={loading}
        className="text-sm bg-slate-900 text-white rounded-md px-3 py-1.5 disabled:opacity-50"
      >
        {loading ? 'Syncing…' : 'Sync'}
      </button>
      {message && <span className="text-xs text-slate-500">{message}</span>}
    </div>
  )
}
