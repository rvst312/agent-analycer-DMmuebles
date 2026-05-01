import logging
from typing import Any, Dict, List

from db.models import ComponentFeedbackModel
from db.persistence import async_session_maker
from sqlalchemy import select

logger = logging.getLogger(__name__)


async def get_recent_corrections(cliente_id: str, n: int = 3) -> List[List[Dict[str, Any]]]:
    """
    Returns up to n lists of corrected components from recent feedback.
    Prioritises client-specific corrections, then fills up with corrections from other clients.
    Returns [] on any DB error so the caller degrades gracefully.
    """
    try:
        async with async_session_maker() as session:
            # Client-specific first
            res = await session.execute(
                select(ComponentFeedbackModel)
                .where(ComponentFeedbackModel.cliente_id == cliente_id)
                .order_by(ComponentFeedbackModel.created_at.desc())
                .limit(n)
            )
            client_records = res.scalars().all()
            examples = [r.componentes_corregidos for r in client_records]

            # Fill with general pool if needed
            remaining = n - len(examples)
            if remaining > 0:
                res2 = await session.execute(
                    select(ComponentFeedbackModel)
                    .where(ComponentFeedbackModel.cliente_id != cliente_id)
                    .order_by(ComponentFeedbackModel.created_at.desc())
                    .limit(remaining)
                )
                others = res2.scalars().all()
                examples.extend(r.componentes_corregidos for r in others)

        logger.info(f"vision_feedback: {len(examples)} few-shot examples loaded for cliente={cliente_id}")
        return examples
    except Exception as e:
        logger.warning(f"vision_feedback: could not load corrections ({e}), proceeding without examples")
        return []
