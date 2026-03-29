'use client'

import { useState, useEffect } from 'react'
import { useRouter, useParams } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'

const LOW_CONFIDENCE = 0.7

type FieldConf = { date: number; amount: number; vendor: number }

function ConfidenceBadge({ confidence }: { confidence: number }) {
  if (confidence >= LOW_CONFIDENCE) return null
  return (
    <span className="ml-2 text-xs px-1.5 py-0.5 rounded bg-amber-100 text-amber-700">
      Low confidence — check this field
    </span>
  )
}

export default function ReviewPage() {
  const router = useRouter()
  const params = useParams()
  const documentId = params.id as string

  const [date, setDate] = useState('')
  const [amount, setAmount] = useState('')
  const [vendor, setVendor] = useState('')
  const [fieldConf, setFieldConf] = useState<FieldConf>({ date: 1, amount: 1, vendor: 1 })
  const [ocrStatus, setOcrStatus] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const raw = sessionStorage.getItem(`ocr_${documentId}`)
    if (raw) {
      const data = JSON.parse(raw)
      setDate(data.date || '')
      setAmount(data.amount !== null ? String(data.amount) : '')
      setVendor(data.vendor || '')
      setFieldConf(data.field_confidence || { date: 1, amount: 1, vendor: 1 })
      setOcrStatus(data.ocr_status || '')
    }
    setLoading(false)
  }, [documentId])

  async function handleConfirm(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError('')

    const supabase = createClient()
    const { data: { session } } = await supabase.auth.getSession()

    try {
      const resp = await fetch(
        `${process.env.NEXT_PUBLIC_BACKEND_URL}/api/documents/${documentId}/confirm`,
        {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${session?.access_token}`,
          },
          body: JSON.stringify({
            date: date || null,
            amount: amount ? parseFloat(amount) : null,
            vendor: vendor || null,
            category_id: null,
          }),
        }
      )

      if (!resp.ok) {
        setError('Failed to save. Please try again.')
        return
      }

      sessionStorage.removeItem(`ocr_${documentId}`)
      router.push('/documents?uploaded=1')
    } catch {
      setError('Failed to save. Please check your connection.')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className="text-center py-16 text-slate-400 text-sm">Loading…</div>
  }

  return (
    <div>
      <h2 className="text-base font-semibold text-slate-900 mb-2">Review Document</h2>

      {ocrStatus === 'failed' && (
        <div className="mb-4 text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
          OCR could not extract fields automatically. Please fill them in manually.
        </div>
      )}

      <form onSubmit={handleConfirm} className="space-y-5 mt-4">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Date
            <ConfidenceBadge confidence={fieldConf.date} />
          </label>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className={`w-full border rounded-md px-3 py-2 text-sm ${
              fieldConf.date < LOW_CONFIDENCE
                ? 'border-amber-400 bg-amber-50'
                : 'border-slate-300'
            }`}
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Amount
            <ConfidenceBadge confidence={fieldConf.amount} />
          </label>
          <input
            type="number"
            step="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="0.00"
            className={`w-full border rounded-md px-3 py-2 text-sm ${
              fieldConf.amount < LOW_CONFIDENCE
                ? 'border-amber-400 bg-amber-50'
                : 'border-slate-300'
            }`}
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Vendor
            <ConfidenceBadge confidence={fieldConf.vendor} />
          </label>
          <input
            type="text"
            value={vendor}
            onChange={(e) => setVendor(e.target.value)}
            placeholder="Vendor name"
            className={`w-full border rounded-md px-3 py-2 text-sm ${
              fieldConf.vendor < LOW_CONFIDENCE
                ? 'border-amber-400 bg-amber-50'
                : 'border-slate-300'
            }`}
          />
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}

        <button
          type="submit"
          disabled={saving}
          className="w-full bg-slate-900 text-white rounded-md py-2.5 text-sm font-medium disabled:opacity-50"
        >
          {saving ? 'Saving…' : 'Confirm & Save'}
        </button>
      </form>
    </div>
  )
}
