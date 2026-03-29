'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'

interface Props {
  accountUids: string[]
}

export default function SyncAllButton({ accountUids }: Props) {
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const router = useRouter()

  async function handleSyncAll() {
    if (accountUids.length === 0) return
    setLoading(true)
    setMessage('')

    const supabase = createClient()
    const { data: { session } } = await supabase.auth.getSession()

    let totalSynced = 0
    let failed = 0

    for (let i = 0; i < accountUids.length; i++) {
      setMessage(`Syncing ${i + 1}/${accountUids.length}…`)
      try {
        const resp = await fetch(
          `${process.env.NEXT_PUBLIC_BACKEND_URL}/api/banking/sync`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${session?.access_token}`,
            },
            body: JSON.stringify({ account_uid: accountUids[i], full_sync: false }),
          }
        )
        if (!resp.ok) { failed++; continue }
        const data = await resp.json()
        totalSynced += data.synced ?? 0
      } catch {
        failed++
      }
    }

    if (failed > 0) {
      setMessage(`${totalSynced} new transaction${totalSynced !== 1 ? 's' : ''} synced (${failed} account${failed !== 1 ? 's' : ''} failed)`)
    } else {
      setMessage(
        totalSynced === 0
          ? 'All accounts up to date'
          : `${totalSynced} new transaction${totalSynced !== 1 ? 's' : ''} synced`
      )
    }

    router.refresh()
    setLoading(false)
  }

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={handleSyncAll}
        disabled={loading || accountUids.length === 0}
        className="text-sm border border-slate-300 text-slate-700 rounded-md px-3 py-1.5 hover:bg-slate-50 disabled:opacity-50"
      >
        {loading ? message : 'Sync All'}
      </button>
      {!loading && message && (
        <span className="text-xs text-slate-500">{message}</span>
      )}
    </div>
  )
}
