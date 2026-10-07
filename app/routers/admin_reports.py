"""Báo cáo attribution — CHỈ số tổng hợp, KHÔNG PII. Thiết kế: `docs/attribution.md`.

Hai mô hình, KHÔNG trộn lẫn:

- `model=order`       — nhóm ĐƠN theo nguồn của chính lần đặt (last-touch lúc checkout):
                        "chiến dịch nào ra đơn", "referrer nào ra doanh thu".
- `model=first_touch` — nhóm KHÁCH theo nguồn đầu tiên (`customer_acquisition`) rồi cộng
                        đơn/doanh thu của khách đó: "kênh nào mang khách về".

Đơn `CANCELLED` không tính doanh thu. `paid_revenue` chỉ tính đơn `payment_status=PAID`.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import CustomerAcquisition, Order
from ..schemas import AttributionReportOut, AttributionReportRow
from ..security import require_staff

router = APIRouter(prefix="/api/admin/reports", tags=["admin-reports"])

DIMENSIONS = (
    "source",
    "campaign",
    "ref",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
)
VN = timezone(timedelta(hours=7))
CENT = Decimal("0.01")


@router.get("/attribution", response_model=AttributionReportOut)
def attribution_report(
    db: Session = Depends(get_db),
    actor: str = Depends(require_staff),
    model: str = Query(default="order", pattern="^(order|first_touch)$"),
    dimension: str = Query(default="source", pattern="^(" + "|".join(DIMENSIONS) + ")$"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
) -> AttributionReportOut:
    not_cancelled = Order.status != "CANCELLED"
    revenue = func.coalesce(func.sum(case((not_cancelled, Order.grand_total), else_=0)), 0)
    paid = func.coalesce(
        func.sum(
            case((not_cancelled & (Order.payment_status == "PAID"), Order.grand_total), else_=0)
        ),
        0,
    )
    order_count = func.count(Order.id).filter(not_cancelled)

    if model == "order":
        key = getattr(Order, dimension)
        stmt = select(
            key, func.count(func.distinct(Order.customer_id)), order_count, revenue, paid
        ).select_from(Order)
    else:
        key = getattr(CustomerAcquisition, dimension)
        stmt = (
            select(
                key,
                func.count(func.distinct(CustomerAcquisition.customer_id)),
                order_count,
                revenue,
                paid,
            )
            .select_from(CustomerAcquisition)
            .outerjoin(Order, Order.customer_id == CustomerAcquisition.customer_id)
        )

    # Lọc theo ngày giờ Việt Nam (đầu ngày from → hết ngày to).
    if date_from:
        stmt = stmt.where(Order.created_at >= datetime.combine(date_from, time.min, VN))
    if date_to:
        stmt = stmt.where(
            Order.created_at < datetime.combine(date_to + timedelta(days=1), time.min, VN)
        )

    rows = db.execute(stmt.group_by(key).order_by(revenue.desc(), key.asc().nulls_last())).all()
    return AttributionReportOut(
        model=model,
        dimension=dimension,
        rows=[
            AttributionReportRow(
                key=k,
                customers=int(c),
                orders=int(o),
                # SUM ra `0` khi không có doanh thu — chuẩn hoá 2 chữ số như mọi tiền khác.
                revenue=Decimal(r).quantize(CENT),
                paid_revenue=Decimal(p).quantize(CENT),
            )
            for k, c, o, r, p in rows
        ],
    )
