export type ToastTone = 'ok' | 'info' | 'warn' | 'error'
export interface Toast { id: number; title: string; body?: string; tone: ToastTone; ms: number }

let seq = 0

/** App-wide toasts. Call toast({ title, body?, tone? }) from anywhere; <ToastHost /> shows them. */
export function useToast() {
  const toasts = useState<Toast[]>('toasts', () => [])
  function dismiss(id: number) { toasts.value = toasts.value.filter(t => t.id !== id) }
  function toast(t: { title: string; body?: string; tone?: ToastTone; ms?: number }) {
    const item: Toast = { id: ++seq, title: t.title, body: t.body, tone: t.tone ?? 'info', ms: t.ms ?? 4200 }
    toasts.value = [...toasts.value.slice(-3), item]
    if (import.meta.client && item.ms > 0) setTimeout(() => dismiss(item.id), item.ms)
    return item.id
  }
  return { toasts, toast, dismiss }
}
