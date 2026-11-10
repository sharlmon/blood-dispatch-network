/** Clerk component styling to match the Blood Dispatch look. */
export const clerkAppearance = {
  variables: {
    colorPrimary: '#0a6b62',
    colorText: '#12202b',
    colorTextSecondary: '#4a5b68',
    colorBackground: '#ffffff',
    borderRadius: '14px',
    fontFamily: 'Manrope, system-ui, sans-serif'
  },
  elements: {
    rootBox: { width: '100%' },
    cardBox: { width: '100%', boxShadow: 'none', border: 'none' },
    card: { boxShadow: 'none', border: 'none', background: 'transparent', width: '100%', padding: '0' },
    footer: { background: 'transparent', boxShadow: 'none' },
    footerAction: { background: 'transparent' },
    formButtonPrimary: { borderRadius: '99px', minHeight: '48px', fontWeight: 800 }
  }
}
