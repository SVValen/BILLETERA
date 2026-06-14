from fastapi import Request
from fastapi.responses import JSONResponse
from lib.supabase_client import get_supabase


async def get_telegram_id_from_request(request: Request) -> tuple[str | None, JSONResponse | None]:
    """
    Verifica el JWT de Supabase del header Authorization y retorna el telegram_id del usuario.
    Retorna (telegram_id, None) si OK, o (None, JSONResponse de error) si falla.
    """
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return None, JSONResponse({"error": "No autorizado"}, status_code=401)

    token = auth_header[7:]
    supabase = get_supabase()

    try:
        user_response = supabase.auth.get_user(token)
        if not user_response.user:
            return None, JSONResponse({"error": "Token inválido"}, status_code=401)
        user_id = user_response.user.id
    except Exception:
        return None, JSONResponse({"error": "Token inválido"}, status_code=401)

    result = (
        supabase.table("perfiles")
        .select("telegram_id")
        .eq("id", user_id)
        .execute()
    )

    if not result.data or not result.data[0].get("telegram_id"):
        return None, JSONResponse(
            {"error": "Perfil no configurado — vinculá tu Telegram ID primero"},
            status_code=403,
        )

    return result.data[0]["telegram_id"], None
