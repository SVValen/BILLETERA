import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Billetera',
  description: 'Asistente financiero personal',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body style={{ margin: 0, fontFamily: 'system-ui, sans-serif', background: '#f5f5f5' }}>
        {children}
      </body>
    </html>
  )
}
