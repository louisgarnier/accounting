'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'

interface Props {
  accountUid: string
}

export default function BankSyncButton({ accountUid }: Props) {
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const router = useRouter()

  async function handleSync(fullSync: boolean) {
    setLoading(true)
    setMessage('')
    const supabase = createClient()
    const { data: { session } } = await supabase.auth.getSession()
    try {
      const resp = await fetch(
        `${process.env.NEXT_PUBLIC_BACKEND_URL}/api/banking/sync`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${session?.access_token}`,
          },
          body: JSON.stringify({ account_uid: accountUid, full_sync: fullSync }),
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
    <div className="flex flex-col items-end gap-1">
      <div className="flex items-center gap-2">
        <button
          onClick={() => handleSync(false)}
          disabled={loading}
          className="text-xs bg-slate-900 text-white rounded px-2.5 py-1 disabled:opacity-50"
        >
          {loading ? 'Syncing…' : 'Sync'}
        </button>
        <button
          onClick={() => handleSync(true)}
          disabled={loading}
          className="text-xs text-slate-500 hover:text-slate-700 disabled:opacity-50"
        >
          Full sync
        </button>
      </div>
      {message && <span className="text-xs text-slate-400">{message}</span>}
    </div>
  )
}
