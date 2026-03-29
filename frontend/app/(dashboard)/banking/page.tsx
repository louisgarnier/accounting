import Link from 'next/link'
import { createClient } from '@/lib/supabase/server'
import BankSyncButton from '@/components/BankSyncButton'

type Connection = {
  account_uid: string
  account_name: string | null
  account_iban: string | null
  institution_name: string | null
  last_synced: string | null
}

export default async function BanksPage() {
  const supabase = await createClient()
  const { data: { session } } = await supabase.auth.getSession()

  const resp = await fetch(
    `${process.env.NEXT_PUBLIC_BACKEND_URL}/api/banking/connections`,
    {
      headers: { Authorization: `Bearer ${session?.access_token}` },
      cache: 'no-store',
    }
  )
  const data = resp.ok ? await resp.json() : { connections: [] }
  const connections: Connection[] = data.connections

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-base font-semibold text-slate-900">
          Connected Banks
          {connections.length > 0 && (
            <span className="ml-2 text-sm font-normal text-slate-500">
              {connections.length} account{connections.length !== 1 ? 's' : ''}
            </span>
          )}
        </h2>
        <Link
          href="/banking/connect"
          className="text-sm bg-slate-900 text-white rounded-md px-3 py-1.5"
        >
          + Add Bank
        </Link>
      </div>

      {connections.length === 0 ? (
        <div className="text-center py-16">
          <p className="text-slate-500 text-sm">No banks connected yet.</p>
          <Link
            href="/banking/connect"
            className="mt-4 inline-block text-sm text-slate-900 underline"
          >
            Connect your first bank
          </Link>
        </div>
      ) : (
        <ul className="space-y-3">
          {connections.map((conn) => (
            <li
              key={conn.account_uid}
              className="bg-white rounded-lg border border-slate-200 px-4 py-3 flex items-center justify-between"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium text-slate-900">
                  {conn.institution_name}
                  {conn.account_name && (
                    <span className="ml-1.5 text-slate-500 font-normal">
                      — {conn.account_name}
                    </span>
                  )}
                </p>
                <p className="text-xs text-slate-400 mt-0.5">
                  {conn.account_iban || conn.account_uid}
                  {conn.last_synced && (
                    <> · Last synced {new Date(conn.last_synced).toLocaleDateString()}</>
                  )}
                  {!conn.last_synced && ' · Never synced'}
                </p>
              </div>
              <div className="flex items-center gap-4 ml-4 shrink-0">
                <BankSyncButton accountUid={conn.account_uid} />
                <RemoveButton accountUid={conn.account_uid} accessToken={session?.access_token ?? ''} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function RemoveButton({ accountUid, accessToken }: { accountUid: string; accessToken: string }) {
  async function handleRemove() {
    'use server'
    await fetch(
      `${process.env.NEXT_PUBLIC_BACKEND_URL}/api/banking/connections/${accountUid}`,
      {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${accessToken}` },
        cache: 'no-store',
      }
    )
  }

  return (
    <form action={handleRemove}>
      <button
        type="submit"
        className="text-xs text-red-500 hover:text-red-700"
      >
        Remove
      </button>
    </form>
  )
}
