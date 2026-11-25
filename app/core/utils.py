import re
import unicodedata
from datetime import date, datetime

from fastapi import status

from app.core.config import get_settings
from app.core.exceptions import ApiException

_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")


def so_digitos(value: str | None) -> str:
    return re.sub(r"\D", "", str(value or ""))


def sem_acento(value: str | None) -> str:
    normalized = unicodedata.normalize("NFD", str(value or ""))
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn").lower()


def email_valido(value: str | None) -> bool:
    return bool(_EMAIL_RE.match((value or "").strip()))


def cpf_valido(cpf: str | None) -> bool:
    digits = so_digitos(cpf)
    if len(digits) != 11 or len(set(digits)) == 1:
        return False

    def _dv(length: int) -> int:
        total = sum(int(digits[i]) * (length + 1 - i) for i in range(length))
        rem = (total * 10) % 11
        return 0 if rem == 10 else rem

    return _dv(9) == int(digits[9]) and _dv(10) == int(digits[10])


def now_app_tz() -> datetime:
    return datetime.now(get_settings().tz)


def today_app_tz() -> date:
    return now_app_tz().date()


def js_weekday(d: date) -> int:
    """Converte weekday Python (0=Seg..6=Dom) para o padrão JS/mobile (0=Dom..6=Sáb)."""
    return (d.weekday() + 1) % 7


def parse_iso_date(value: str, *, field_label: str = "data") -> date:
    try:
        return date.fromisoformat(value.strip())
    except (ValueError, AttributeError) as exc:
        raise ApiException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Formato inválido para {field_label}. Use AAAA-MM-DD.",
        ) from exc


def parse_hhmm(value: str) -> int:
    match = _HHMM_RE.match((value or "").strip())
    if not match:
        raise ApiException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Horário inválido. Use o formato HH:MM.",
        )
    return int(match.group(1)) * 60 + int(match.group(2))


def minutes_to_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def format_date_br(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def hours_until(target_date: date, hora: str) -> float:
    """Retorna quantas horas faltam (no fuso da aplicação) até a data/hora da consulta."""
    minutes = parse_hhmm(hora)
    tz = get_settings().tz
    target_dt = datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        minutes // 60,
        minutes % 60,
        tzinfo=tz,
    )
    return (target_dt - now_app_tz()).total_seconds() / 3600.0
