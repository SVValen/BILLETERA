import type { Metadata, Viewport } from 'next'
import { Syne, Inter } from 'next/font/google'
import './globals.css'

const syne = Syne({ subsets: ['latin'], weight: ['700', '800'], variable: '--font-syne' })
const inter = Inter({ subsets: ['latin'], weight: ['400', '500', '600'], variable: '--font-inter' })

export const metadata: Metadata = {
  title: 'Billetera',
  description: 'Asistente financiero personal',
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className={`${syne.variable} ${inter.variable}`}>
      <body>{children}</body>
    </html>
  )
}
