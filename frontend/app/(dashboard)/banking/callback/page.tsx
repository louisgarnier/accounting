import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'

export default async function BankingCallbackPage({
  searchParams,
}: {
  searchParams: Promise<{ code?: string; error?: string; state?: string }>
}) {
  const params = await searchParams

  if (params.error || !params.code) {
    redirect('/banking?bank_error=1')
  }

  const supabase = await createClient()
  const {
    data: { session },
  } = await supabase.auth.getSession()

  if (!session) {
    redirect('/login')
  }

  const resp = await fetch(
    `${process.env.NEXT_PUBLIC_BACKEND_URL}/api/banking/sessions`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${session.access_token}`,
      },
      body: JSON.stringify({ code: params.code }),
      cache: 'no-store',
    }
  )

  if (!resp.ok) {
    redirect('/transactions?bank_error=1')
  }

  redirect('/banking?bank_connected=1')
}
