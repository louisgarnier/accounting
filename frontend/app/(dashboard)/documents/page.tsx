import Link from 'next/link'
import { createClient } from '@/lib/supabase/server'

type Document = {
  id: string
  original_filename: string | null
  stored_filename: string | null
  date: string | null
  amount: number | null
  vendor: string | null
  ocr_status: string
  source: string
  created_at: string
}

export default async function DocumentsPage({
  searchParams,
}: {
  searchParams: Promise<{ uploaded?: string }>
}) {
  const supabase = await createClient()
  const params = await searchParams

  const { data: documents, error } = await supabase
    .from('documents')
    .select('id, original_filename, stored_filename, date, amount, vendor, ocr_status, source, created_at')
    .order('created_at', { ascending: false })

  if (error) {
    return (
      <div className="text-red-600 text-sm">
        Failed to load documents. Please try again.
      </div>
    )
  }

  return (
    <div>
      {params.uploaded && (
        <div className="mb-4 text-sm text-green-700 bg-green-50 border border-green-200 rounded-md px-3 py-2">
          Document uploaded successfully.
        </div>
      )}

      <div className="flex items-center justify-between mb-6">
        <h2 className="text-base font-semibold text-slate-900">
          Documents
          {documents && documents.length > 0 && (
            <span className="ml-2 text-sm font-normal text-slate-500">
              {documents.length} total
            </span>
          )}
        </h2>
        <Link
          href="/documents/upload"
          className="text-sm bg-slate-900 text-white rounded-md px-3 py-1.5"
        >
          + Upload
        </Link>
      </div>

      {!documents || documents.length === 0 ? (
        <div className="text-center py-16">
          <p className="text-slate-500 text-sm">No documents yet.</p>
          <Link
            href="/documents/upload"
            className="mt-4 inline-block text-sm text-slate-900 underline"
          >
            Upload your first receipt
          </Link>
        </div>
      ) : (
        <ul className="space-y-2">
          {(documents as Document[]).map((doc) => (
            <li
              key={doc.id}
              className="bg-white rounded-lg border border-slate-200 px-4 py-3 flex items-center justify-between"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium text-slate-900 truncate">
                  {doc.vendor || doc.original_filename || 'Unknown'}
                </p>
                <p className="text-xs text-slate-500 mt-0.5">
                  {doc.date || '—'}
                  {doc.source && ` · ${doc.source}`}
                </p>
              </div>
              <div className="flex items-center gap-3 ml-4 shrink-0">
                {doc.ocr_status === 'failed' && (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-red-50 text-red-700">
                    OCR failed
                  </span>
                )}
                <span className="text-sm font-medium text-slate-900 tabular-nums">
                  {doc.amount !== null ? `${doc.amount >= 0 ? '+' : ''}${doc.amount.toFixed(2)}` : '—'}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
