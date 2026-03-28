import LogoutButton from '@/components/LogoutButton'

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-200 px-4 py-3 flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-900">Accounting</h1>
        <LogoutButton />
      </header>
      <main className="px-4 py-6 max-w-2xl mx-auto">{children}</main>
    </div>
  )
}
