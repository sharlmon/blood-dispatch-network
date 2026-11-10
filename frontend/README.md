# frontend/ (Nuxt 4)

Owner: Frontend.

```bash
cd frontend
npm install
cp .env.example .env
npm run dev        # http://localhost:3000
```

| Path | Purpose |
|---|---|
| `app/pages/` | Routes: request entry, options list, confirmation, basic-phone view, results tab |
| `app/components/` | Shared UI components |
| `app/composables/` | API client helpers |
| `public/` | Static assets (results JSON can be served from here) |
| `tests/` | Frontend tests |

The API base URL is set via `NUXT_PUBLIC_API_BASE`.
