'use client'

import { useState } from 'react'
import { createClient } from '@/lib/supabase/client'

const BANKS = [
  { name: 'BNP Paribas', country: 'FR' },
  { name: 'Société Générale', country: 'FR' },
  { name: 'Crédit Agricole', country: 'FR' },
  { name: 'LCL', country: 'FR' },
  { name: "Caisse d'Épargne", country: 'FR' },
  { name: 'Banque Populaire', country: 'FR' },
  { name: 'La Banque Postale', country: 'FR' },
  { name: 'HSBC France', country: 'FR' },
  { name: 'Revolut', country: 'FR' },
]

export default function ConnectBankPage() {
  const [selectedBank, setSelectedBank] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleConnect() {
    if (!selectedBank) return
    setLoading(true)
    setError('')

    const bank = BANKS.find((b) => b.name === selectedBank)!
    const supabase = createClient()
    const {
      data: { session },
    } = await supabase.auth.getSession()

    try {
      const resp = await fetch(
        `${process.env.NEXT_PUBLIC_BACKEND_URL}/api/banking/connect`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${session?.access_token}`,
          },
          body: JSON.stringify({
            bank_name: bank.name,
            bank_country: bank.country,
          }),
        }
      )
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}))
        throw new Error(body.detail || `HTTP ${resp.status}`)
      }
      const { url } = await resp.json()
      window.location.href = url
    } catch (e) {
      setError(`Could not connect: ${e instanceof Error ? e.message : 'unknown error'}`)
      setLoading(false)
    }
  }

  return (
    <div className="max-w-sm mx-auto py-8">
      <h2 className="text-base font-semibold text-slate-900 mb-1">
        Connect your bank
      </h2>
      <p className="text-sm text-slate-500 mb-6">
        You will be redirected to authorise access. This is a one-time setup.
      </p>

      <label className="block text-sm font-medium text-slate-700 mb-1">
        Select your bank
      </label>
      <select
        value={selectedBank}
        onChange={(e) => setSelectedBank(e.target.value)}
        className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm mb-4 bg-white"
      >
        <option value="">— choose a bank —</option>
        {BANKS.map((b) => (
          <option key={b.name} value={b.name}>
            {b.name}
          </option>
        ))}
      </select>

      {error && <p className="text-sm text-red-600 mb-3">{error}</p>}

      <button
        onClick={handleConnect}
        disabled={!selectedBank || loading}
        className="w-full bg-slate-900 text-white text-sm font-medium rounded-md px-4 py-2 disabled:opacity-50"
      >
        {loading ? 'Redirecting…' : 'Connect'}
      </button>
    </div>
  )
}
