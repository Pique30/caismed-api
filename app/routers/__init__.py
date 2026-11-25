"""Routers (endpoints) da API CaisMed."""

from app.routers import admin, auth, catalogo, consultas, health, notificacoes, triagens

__all__ = [
    "admin",
    "auth",
    "catalogo",
    "consultas",
    "health",
    "notificacoes",
    "triagens",
]
