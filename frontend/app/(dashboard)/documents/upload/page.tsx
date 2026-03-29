import Link from 'next/link'
import UploadForm from '@/components/UploadForm'

export default function UploadPage() {
  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <Link href="/documents" className="text-sm text-slate-500 hover:text-slate-700">
          ← Documents
        </Link>
      </div>
      <h2 className="text-base font-semibold text-slate-900 mb-6">Upload Receipt or Invoice</h2>
      <UploadForm />
    </div>
  )
}
