import Link from 'next/link'
import LogoutButton from '@/components/LogoutButton'

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-200 px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <h1 className="text-lg font-semibold text-slate-900">Accounting</h1>
          <nav className="flex gap-4">
            <Link
              href="/transactions"
              className="text-sm text-slate-600 hover:text-slate-900"
            >
              Transactions
            </Link>
            <Link
              href="/documents"
              className="text-sm text-slate-600 hover:text-slate-900"
            >
              Documents
            </Link>
            <Link
              href="/banking"
              className="text-sm text-slate-600 hover:text-slate-900"
            >
              Banks
            </Link>
          </nav>
        </div>
        <LogoutButton />
      </header>
      <main className="px-4 py-6 max-w-2xl mx-auto">{children}</main>
    </div>
  )
}
