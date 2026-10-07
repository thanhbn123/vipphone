"""G13 — API quản trị khách hàng. Staff-protected, KHÔNG có đường công khai.

Không có endpoint công khai nào cho khách hàng: khách không tự đăng nhập ở G13,
nên mọi đường tra cứu đều phải qua nhân viên. Đây là chủ ý, không phải thiếu sót —
mở một đường công khai ở đây là mở luôn khả năng DÒ RA khách của người khác.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Customer, CustomerAcquisition, CustomerDevice, Lead
from ..schemas import (
    CustomerAcquisitionOut,
    CustomerDetailOut,
    CustomerDeviceOut,
    CustomerGiftOut,
    CustomerOut,
)
from ..security import require_staff
from ..services.gifts import mask_phone

router = APIRouter(prefix="/api/admin/customers", tags=["admin-customers"])


@router.get("", response_model=list[CustomerOut])
def list_customers(
    db: Session = Depends(get_db),
    actor: str = Depends(require_staff),
    phone: str | None = Query(default=None, max_length=20),
    status: str | None = Query(default=None, max_length=20),
    device: str | None = Query(default=None, max_length=64),
    source: str | None = Query(default=None, max_length=32),
    gift_status: str | None = Query(default=None, max_length=20),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[CustomerOut]:
    stmt = select(Customer)
    if phone:
        from ..phone import normalize_phone

        digits = normalize_phone(phone)
        stmt = stmt.where(Customer.phone_normalized.like(f"%{digits[-9:]}%"))
    if status:
        stmt = stmt.where(Customer.status == status)
    if device:
        stmt = stmt.where(
            Customer.id.in_(
                select(CustomerDevice.customer_id).where(CustomerDevice.model_code == device)
            )
        )
    if source:
        stmt = stmt.where(
            Customer.id.in_(
                select(CustomerAcquisition.customer_id).where(CustomerAcquisition.source == source)
            )
        )
    if gift_status:
        stmt = stmt.where(
            Customer.id.in_(select(Lead.customer_id).where(Lead.gift_status == gift_status))
        )
    stmt = stmt.order_by(Customer.created_at.desc(), Customer.id.desc()).limit(limit).offset(offset)

    return [
        CustomerOut(
            customer_id=c.customer_id,
            full_name=c.full_name,
            phone_masked=mask_phone(c.phone_normalized),
            status=c.status,
            marketing_consent=c.marketing_consent,
            created_at=c.created_at,
        )
        for c in db.execute(stmt).scalars()
    ]


@router.get("/{customer_id}", response_model=CustomerDetailOut)
def get_customer(
    customer_id: uuid.UUID,
    db: Session = Depends(get_db),
    actor: str = Depends(require_staff),
) -> CustomerDetailOut:
    customer = db.execute(
        select(Customer).where(Customer.customer_id == customer_id)
    ).scalar_one_or_none()
    if customer is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy khách hàng.")

    devices = (
        db.execute(
            select(CustomerDevice)
            .where(CustomerDevice.customer_id == customer.id)
            .order_by(CustomerDevice.is_primary.desc(), CustomerDevice.id)
        )
        .scalars()
        .all()
    )
    acq = db.execute(
        select(CustomerAcquisition).where(CustomerAcquisition.customer_id == customer.id)
    ).scalar_one_or_none()
    gifts = (
        db.execute(
            select(Lead)
            .where(Lead.customer_id == customer.id)
            .order_by(Lead.created_at.desc(), Lead.id.desc())
        )
        .scalars()
        .all()
    )

    return CustomerDetailOut(
        customer_id=customer.customer_id,
        full_name=customer.full_name,
        phone_masked=mask_phone(customer.phone_normalized),
        status=customer.status,
        marketing_consent=customer.marketing_consent,
        created_at=customer.created_at,
        email=customer.email,
        company_name=customer.company_name,
        bni_chapter=customer.bni_chapter,
        consent_updated_at=customer.consent_updated_at,
        devices=[CustomerDeviceOut.model_validate(d) for d in devices],
        acquisition=CustomerAcquisitionOut.model_validate(acq) if acq else None,
        gift_history=[
            CustomerGiftOut(
                gift_code=le.gift_code,
                iphone_model=le.iphone_model,
                gift_status=le.gift_status,
                created_at=le.created_at,
                redeemed_at=le.redeemed_at,
            )
            for le in gifts
        ],
        # G16 chưa làm. Trả [] thay vì bịa đơn hàng — xem ADR-0002 §4.
        orders=[],
    )
