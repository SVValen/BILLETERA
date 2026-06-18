"""
Cron semanal: Alertas de plan_renta
Ejecutar los lunes 08:00 AR (cada semana)
Resumen de rendimiento e instrucciones
"""
import os
from datetime import datetime, timedelta
from lib.supabase_client import get_supabase
from api.bot.tg import _send

# Importar desde os env
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CRON_SECRET = os.environ.get("CRON_SECRET", "")


async def enviar_alertas_plan_renta():
    """Envía alertas semanales a usuarios con plan_renta activos."""
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN no configurado")
        return

    supabase = get_supabase()

    # Obtener todos los usuarios con posiciones_rf abiertas (plan_renta)
    pos_r = supabase.table("posiciones_rf").select("usuario_id, COUNT(*)").eq("estado", "abierta").group_by("usuario_id").execute()

    usuarios = list(set([p["usuario_id"] for p in (pos_r.data or [])]))

    print(f"📢 Enviando alertas a {len(usuarios)} usuarios con RF abierta...")

    for user_id in usuarios:
        try:
            # Obtener chat_id (en realidad user_id es telegram_id en nuestro caso)
            # Guardamos user_id como telegram_id en la tabla usuarios
            user_r = supabase.table("usuarios").select("telegram_id, chat_id").eq("telegram_id", int(user_id)).limit(1).execute()
            
            if not user_r.data:
                continue

            chat_id = int(user_id)  # En Telegram, chat_id == user_id para DMs

            # Obtener posiciones RF del usuario
            pos_user_r = supabase.table("posiciones_rf").select(
                "*, instrumentos_rf(nombre, tipo, tna_actual)"
            ).eq("usuario_id", user_id).eq("estado", "abierta").execute()

            posiciones = pos_user_r.data or []

            if not posiciones:
                continue

            # Calcular resumen
            total_ars = sum(p["monto_ars"] for p in posiciones)
            total_usd = sum(p.get("monto_usd", 0) for p in posiciones)

            lines = ["📊 *Alerta semanal de Renta Fija*\n"]

            lines.append(f"💰 *Tu inversión RF*\n")
            lines.append(f"  Total: ${total_ars:,.0f} ARS (≈${total_usd:,.0f} USD)")
            lines.append(f"  Posiciones abiertas: {len(posiciones)}\n")

            # Detallar cada posición
            lines.append("*📄 Posiciones:*")
            for p in posiciones:
                inst = p.get("instrumentos_rf") or {}
                nombre = inst.get("nombre") or "instrumento"
                tna = p.get("tna_contratada") or inst.get("tna_actual") or 0
                venc = p.get("fecha_vencimiento")

                # Calcular rendimiento semanal (aprox)
                if isinstance(tna, (int, float)):
                    rdto_semanal = (tna / 100 / 52) * p["monto_ars"]
                    lines.append(f"  • {nombre}: ${p['monto_ars']:,.0f} @ {tna:.1f}% TNA")
                    lines.append(f"    Esta semana: ~${rdto_semanal:,.0f}")
                else:
                    lines.append(f"  • {nombre}: ${p['monto_ars']:,.0f}")

            lines.append("\n_/liquidez para ver detalles | /plan_renta para nuevo plan_")

            # Enviar
            await _send(chat_id, "\n".join(lines), TELEGRAM_BOT_TOKEN)
            print(f"✅ Alerta enviada a usuario {user_id}")

        except Exception as e:
            print(f"❌ Error enviando alerta a {user_id}: {e}")


# Ejecutar cuando se llama desde Vercel/GitHub
if __name__ == "__main__":
    import asyncio
    asyncio.run(enviar_alertas_plan_renta())
