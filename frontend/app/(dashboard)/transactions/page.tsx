import { createClient } from '@/lib/supabase/server'

type Transaction = {
  id: string
  date: string
  amount: number
  description: string
  currency: string
  source_bank: string | null
  matches: { id: string }[] | null
}

export default async function TransactionsPage() {
  const supabase = await createClient()

  const { data: transactions, error } = await supabase
    .from('transactions')
    .select('id, date, amount, description, currency, source_bank, matches(id)')
    .order('date', { ascending: false })

  if (error) {
    return (
      <div className="text-red-600 text-sm">
        Failed to load transactions. Please try again.
      </div>
    )
  }

  if (!transactions || transactions.length === 0) {
    return (
      <div className="text-center py-16">
        <p className="text-slate-500 text-sm">No transactions yet.</p>
        <p className="text-slate-400 text-xs mt-2">
          Transactions will appear here once Enable Banking syncs your account.
        </p>
      </div>
    )
  }

  return (
    <div>
      <h2 className="text-base font-semibold text-slate-900 mb-4">
        Transactions
        <span className="ml-2 text-sm font-normal text-slate-500">
          {transactions.length} total
        </span>
      </h2>

      <ul className="space-y-2">
        {(transactions as Transaction[]).map((txn) => {
          const matched = txn.matches !== null && txn.matches.length > 0
          return (
            <li
              key={txn.id}
              className="bg-white rounded-lg border border-slate-200 px-4 py-3 flex items-center justify-between"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium text-slate-900 truncate">
                  {txn.description}
                </p>
                <p className="text-xs text-slate-500 mt-0.5">
                  {txn.date}
                  {txn.source_bank && ` · ${txn.source_bank}`}
                </p>
              </div>
              <div className="flex items-center gap-3 ml-4 shrink-0">
                <span
                  className={`text-xs px-2 py-0.5 rounded-full ${
                    matched
                      ? 'bg-green-50 text-green-700'
                      : 'bg-amber-50 text-amber-700'
                  }`}
                >
                  {matched ? 'Matched' : 'Unmatched'}
                </span>
                <span className="text-sm font-medium text-slate-900 tabular-nums">
                  {txn.amount < 0 ? '-' : '+'}
                  {Math.abs(txn.amount).toFixed(2)} {txn.currency}
                </span>
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
