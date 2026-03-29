'use client'

import { useState, useEffect } from 'react'
import { createClient } from '@/lib/supabase/client'

interface Bank {
  name: string
  country: string
}

export default function ConnectBankPage() {
  const [banks, setBanks] = useState<Bank[]>([])
  const [selectedBank, setSelectedBank] = useState('')
  const [country, setCountry] = useState('FR')
  const [loading, setLoading] = useState(false)
  const [loadingBanks, setLoadingBanks] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    async function fetchBanks() {
      setLoadingBanks(true)
      setError('')
      setBanks([])
      setSelectedBank('')
      try {
        const supabase = createClient()
        const {
          data: { session },
        } = await supabase.auth.getSession()
        const resp = await fetch(
          `${process.env.NEXT_PUBLIC_BACKEND_URL}/api/banking/aspsps?country=${country}`,
          {
            headers: { Authorization: `Bearer ${session?.access_token}` },
          }
        )
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        const data = await resp.json()
        setBanks(data.aspsps || [])
      } catch (e) {
        setError(`Could not load banks: ${e instanceof Error ? e.message : 'unknown error'}`)
      } finally {
        setLoadingBanks(false)
      }
    }
    fetchBanks()
  }, [country])

  async function handleConnect() {
    if (!selectedBank) return
    setLoading(true)
    setError('')

    const bank = banks.find((b) => b.name === selectedBank)!
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
        Country
      </label>
      <select
        value={country}
        onChange={(e) => setCountry(e.target.value)}
        className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm mb-4 bg-white"
      >
        <option value="FR">France</option>
        <option value="GB">United Kingdom</option>
        <option value="DE">Germany</option>
        <option value="ES">Spain</option>
        <option value="IT">Italy</option>
      </select>

      <label className="block text-sm font-medium text-slate-700 mb-1">
        Select your bank
      </label>
      <select
        value={selectedBank}
        onChange={(e) => setSelectedBank(e.target.value)}
        className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm mb-4 bg-white"
        disabled={loadingBanks}
      >
        <option value="">
          {loadingBanks ? 'Loading banks…' : '— choose a bank —'}
        </option>
        {banks.map((b) => (
          <option key={b.name} value={b.name}>
            {b.name}
          </option>
        ))}
      </select>

      {error && <p className="text-sm text-red-600 mb-3">{error}</p>}

      <button
        onClick={handleConnect}
        disabled={!selectedBank || loading || loadingBanks}
        className="w-full bg-slate-900 text-white text-sm font-medium rounded-md px-4 py-2 disabled:opacity-50"
      >
        {loading ? 'Redirecting…' : 'Connect'}
      </button>
    </div>
  )
}
