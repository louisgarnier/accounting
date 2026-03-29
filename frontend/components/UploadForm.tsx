'use client'

import { useState, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'

export default function UploadForm() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)
  const router = useRouter()

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const file = fileInputRef.current?.files?.[0]
    if (!file) return

    setLoading(true)
    setError('')

    const supabase = createClient()
    const { data: { session } } = await supabase.auth.getSession()

    const formData = new FormData()
    formData.append('file', file)

    try {
      const resp = await fetch(
        `${process.env.NEXT_PUBLIC_BACKEND_URL}/api/documents/upload`,
        {
          method: 'POST',
          headers: { Authorization: `Bearer ${session?.access_token}` },
          body: formData,
        }
      )

      if (resp.status === 409) {
        setError('This file has already been uploaded.')
        return
      }
      if (resp.status === 413) {
        setError('File is too large. Maximum size is 10MB.')
        return
      }
      if (resp.status === 422) {
        setError('Unsupported file type. Please upload a JPG, PNG, or PDF.')
        return
      }
      if (!resp.ok) {
        setError('Upload failed. Please try again.')
        return
      }

      const data = await resp.json()
      sessionStorage.setItem(`ocr_${data.document_id}`, JSON.stringify(data))
      router.push(`/documents/${data.document_id}/review`)
    } catch {
      setError('Upload failed. Please check your connection.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div
        className="border-2 border-dashed border-slate-300 rounded-xl p-8 text-center cursor-pointer hover:border-slate-400 transition-colors"
        onClick={() => fileInputRef.current?.click()}
      >
        <p className="text-slate-500 text-sm mb-2">
          {loading ? 'Uploading and running OCR…' : 'Tap to take a photo or choose a file'}
        </p>
        <p className="text-xs text-slate-400">JPG, PNG, PDF · Max 10MB</p>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp,application/pdf"
          capture="environment"
          className="hidden"
          onChange={() => {
            const form = fileInputRef.current?.closest('form') as HTMLFormElement
            form?.requestSubmit()
          }}
        />
      </div>

      {error && (
        <p className="text-sm text-red-600 text-center">{error}</p>
      )}

      {loading && (
        <div className="text-center">
          <div className="inline-block w-5 h-5 border-2 border-slate-300 border-t-slate-900 rounded-full animate-spin" />
          <p className="text-xs text-slate-400 mt-2">Running OCR…</p>
        </div>
      )}
    </form>
  )
}
