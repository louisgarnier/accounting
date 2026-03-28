'use client'

import { logout } from '@/app/login/actions'

export default function LogoutButton() {
  return (
    <form action={logout}>
      <button
        type="submit"
        className="text-sm text-slate-500 hover:text-slate-900"
      >
        Sign out
      </button>
    </form>
  )
}
