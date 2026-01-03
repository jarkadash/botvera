from datetime import datetime, timedelta
from sqlalchemy import select, and_
from database.models import Orders
from math import ceil
from openpyxl import Workbook
from openpyxl.styles import PatternFill
import os
from typing import Tuple
import pandas as pd
from openpyxl.utils.dataframe import dataframe_to_rows
from logger import logger


def is_auto_closed(ticket) -> bool:
    if not ticket.description:
        return False
    description = ticket.description.strip()
    return any(reason in description for reason in [
        "Авто-закрытие (Заблокировал бота)",
        "Авто-закрытие (Клиент не ответил)"
    ])

def get_calculated_period(today=None):
    if today is None:
        today = datetime.now()

    year = today.year
    month = today.month
    day = today.day

    if 11 <= day <= 25:
        start_date = datetime(year, month, 11)
        end_date = datetime(year, month, 25)

    elif day >= 26:
        start_date = datetime(year, month, 26)

        if month == 12:
            end_date = datetime(year + 1, 1, 10)
        else:
            end_date = datetime(year, month + 1, 10)

    else:
        if month == 1:
            start_date = datetime(year - 1, 12, 26)
        else:
            start_date = datetime(year, month - 1, 26)

        end_date = datetime(year, month, 10)

    if end_date < start_date:
        raise ValueError(
            f"Invalid calculated period: {start_date.date()} -> {end_date.date()}"
        )

    return start_date.date(), end_date.date()



def order_to_dict(order) -> dict:
    return {
        "id": order.id,
        "client_id": order.client_id,
        "support_id": order.support_id,
        "service_name": order.service_name,
        "status": order.status,
        "created_at": order.created_at,
        "accept_at": order.accept_at,
        "completed_at": order.completed_at,
        "stars": order.stars,
        "deleted": getattr(order, "deleted", None),
    }

async def filter_tickets_for_statistics(session, support_id: int, start_date: datetime.date, end_date: datetime.date):
    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.max.time())

    stmt = select(Orders).where(
        and_(
            Orders.support_id == support_id,
            Orders.created_at >= start_dt,
            Orders.created_at <= end_dt
        )
    )

    result = await session.execute(stmt)
    all_tickets = result.scalars().all()

    included = []
    excluded = []
    technical_seen = {}

    for ticket in all_tickets:
        if ticket.status != 'closed':
            excluded.append((ticket, 'статус не closed'))
            continue

        if ticket.support_id is None:
            excluded.append((ticket, 'support_id пустой'))
            continue

        if is_auto_closed(ticket):
            excluded.append((ticket, 'автоматически закрыт'))
            continue

        if ticket.service_name == "Техническая помощь / Technical Support":
            key = (ticket.support_id, ticket.client_id, ticket.created_at.date())
            if key not in technical_seen:
                technical_seen[key] = []
            technical_seen[key].append(ticket)
            continue

        included.append(ticket)

    for key, tickets in technical_seen.items():
        sorted_tickets = sorted(tickets, key=lambda t: t.created_at)

        valid_tickets = []
        for ticket in sorted_tickets:
            if is_auto_closed(ticket):
                excluded.append((ticket, 'автоматически закрыт (бот/молчание)'))
                continue
            if not ticket.accept_at or not ticket.completed_at:
                excluded.append((ticket, 'нет времени выполнения'))
                continue
            duration = ceil((ticket.completed_at - ticket.accept_at).total_seconds() / 60)
            if duration < 5:
                excluded.append((ticket, f'длительность {duration} мин < 5 мин'))
                continue
            valid_tickets.append(ticket)

        for i, ticket in enumerate(valid_tickets):
            if i == 1:
                excluded.append((ticket, 'пересозданный'))
            else:
                included.append(ticket)

    logger.info(f"[FILTER FINAL] support_id={support_id} => included={len(included)} excluded={len(excluded)}")
    return included, excluded

