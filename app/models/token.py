from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TokenRevogado(Base):
    """Armazena JTIs de tokens JWT revogados via logout até expirarem."""

    __tablename__ = "tokens_revogados"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revogado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
