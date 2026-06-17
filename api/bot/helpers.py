import re
from .constants import _STOP_WORDS
from lib.supabase_client import get_supabase
from lib.parser import categorize_from_keywords


def _detect_currency(text: str) -> str:
    from .constants import DOLLAR_KEYWORDS
    words = set(text.lower().split())
    return "USD" if words & DOLLAR_KEYWORDS else "ARS"


def _extract_keywords(descripcion: str) -> list[str]:
    """Extrae palabras útiles de una descripción para aprender a categorizar."""
    clean = re.sub(r'\(cuota \d+/\d+\)', '', descripcion)
    clean = re.sub(r'\(USD.*?\)', '', clean)
    clean = re.sub(r'@ \$[\d.,]+.*', '', clean)
    words = re.findall(r'[a-záéíóúüñA-ZÁÉÍÓÚÜÑ]{4,}', clean.lower())
    return [w for w in words if w not in _STOP_WORDS]


async def _save_learned_keywords(descripcion: str, categoria_id: int, usuario_id: str) -> None:
    """Guarda las palabras de la descripción como keywords aprendidas para ese usuario."""
    words = _extract_keywords(descripcion)
    if not words:
        return
    supabase = get_supabase()
    for word in words[:6]:
        try:
            supabase.table("keywords_aprendidas").upsert(
                {"usuario_id": usuario_id, "keyword": word, "categoria_id": categoria_id},
                on_conflict="usuario_id,keyword",
            ).execute()
        except Exception:
            pass


async def _categorize(descripcion: str, usuario_id: str) -> int:
    """Categoriza usando keywords hardcodeadas primero, luego las aprendidas por el usuario."""
    cat_id = categorize_from_keywords(descripcion)
    if cat_id != 7:
        return cat_id

    words = _extract_keywords(descripcion)
    if not words:
        return 7

    supabase = get_supabase()
    r = (
        supabase.table("keywords_aprendidas")
        .select("keyword, categoria_id")
        .eq("usuario_id", usuario_id)
        .in_("keyword", words)
        .execute()
    )
    if r.data:
        kw_to_cat = {row["keyword"]: row["categoria_id"] for row in r.data}
        for word in words:
            if word in kw_to_cat:
                return kw_to_cat[word]

    return 7
