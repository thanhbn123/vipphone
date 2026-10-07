"""G13 — Liên kết lead vào khách hàng.

Xem `docs/adr/0002-customer-identity.md`. Ba luật quan trọng:

1. Danh tính = SĐT chuẩn hoá (`app.phone.normalize_phone`). KHÔNG dùng email —
   gộp nhầm hai khách là sai không sửa được.
2. KHÔNG ghi đè lịch sử: trường đã có giá trị thì giữ nguyên, chỉ điền khi NULL.
3. Liên kết là việc PHỤ. Lỗi ở đây KHÔNG được làm hỏng việc tạo lead — nhưng
   phải GHI LOG, cấm nuốt lỗi (§12.2 vault).
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Customer, CustomerAcquisition, CustomerDevice, IphoneModel, Lead
from ..phone import normalize_phone

logger = logging.getLogger(__name__)


def _fill_if_empty(current: str | None, new: str | None) -> str | None:
    """Chỉ điền khi đang trống. Không bao giờ ghi đè giá trị đã có."""
    return current if current else new


def find_or_create_customer(db: Session, lead: Lead) -> Customer:
    """Tìm khách theo SĐT chuẩn hoá; chưa có thì tạo.

    Chống đua: `phone_normalized` UNIQUE ở tầng DB. Hai request đồng thời cùng SĐT
    thì một cái thắng, cái kia `IntegrityError` -> đọc lại bản đã có. Không dựa vào
    "SELECT thấy chưa có rồi INSERT" vì đó chính là khe hở của cuộc đua.
    """
    phone = normalize_phone(lead.phone)
    customer = db.execute(
        select(Customer).where(Customer.phone_normalized == phone)
    ).scalar_one_or_none()

    if customer is None:
        customer = Customer(
            full_name=lead.full_name,
            phone_normalized=phone,
            email=lead.email,
            company_name=lead.company_name,
            bni_chapter=lead.bni_chapter,
            status="ACTIVE",
            marketing_consent=bool(lead.consent),
        )
        if lead.consent:
            from datetime import UTC, datetime

            customer.consent_updated_at = datetime.now(UTC)
        db.add(customer)
        try:
            db.flush()
        except IntegrityError:
            # Request khác vừa tạo xong. Đọc lại bản của họ.
            db.rollback()
            customer = db.execute(
                select(Customer).where(Customer.phone_normalized == phone)
            ).scalar_one()
            return customer
        return customer

    # Khách đã có: chỉ ĐIỀN KHI TRỐNG, không ghi đè lịch sử.
    customer.full_name = _fill_if_empty(customer.full_name, lead.full_name)
    customer.email = _fill_if_empty(customer.email, lead.email)
    customer.company_name = _fill_if_empty(customer.company_name, lead.company_name)
    customer.bni_chapter = _fill_if_empty(customer.bni_chapter, lead.bni_chapter)

    # Consent MỘT CHIỀU: chỉ bật lên, KHÔNG tự tắt. Tắt consent là quyết định
    # pháp lý, không phải hệ quả phụ của việc một lead không tích ô.
    if lead.consent and not customer.marketing_consent:
        from datetime import UTC, datetime

        customer.marketing_consent = True
        customer.consent_updated_at = datetime.now(UTC)

    return customer


def attach_device(db: Session, customer: Customer, lead: Lead, *, is_new_lead: bool) -> None:
    """Ghi máy khách đang dùng. Máy CHÍNH = máy của lead MỚI NHẤT.

    `model_code` tra qua `iphone_models.display_name` — `leads.iphone_model` lưu tên
    hiển thị, không phải mã. Không tra được thì để NULL và GHI LOG (không im lặng).
    """
    model_code: str | None = None
    model = db.execute(
        select(IphoneModel)
        .where(IphoneModel.display_name == lead.iphone_model)
        .order_by(IphoneModel.sort_order, IphoneModel.id)
        .limit(1)
    ).scalar_one_or_none()
    if model is not None:
        model_code = model.model_code
    else:
        logger.warning(
            "G13: iphone_model %r không khớp iphone_models.display_name -> model_code NULL",
            lead.iphone_model,
        )

    existing = None
    if model_code is not None:
        existing = db.execute(
            select(CustomerDevice).where(
                CustomerDevice.customer_id == customer.id,
                CustomerDevice.model_code == model_code,
            )
        ).scalar_one_or_none()

    if existing is None:
        # Bỏ cờ primary của máy cũ TRƯỚC khi đặt máy mới, nếu không partial unique
        # index `uq_customer_devices_one_primary` sẽ chặn.
        if is_new_lead:
            for device in db.execute(
                select(CustomerDevice).where(
                    CustomerDevice.customer_id == customer.id,
                    CustomerDevice.is_primary.is_(True),
                )
            ).scalars():
                device.is_primary = False
        db.add(
            CustomerDevice(
                customer_id=customer.id,
                brand="Apple",
                model_code=model_code,
                display_name=lead.iphone_model,
                year=lead.iphone_year,
                is_primary=is_new_lead,
            )
        )
        db.flush()
    elif is_new_lead and not existing.is_primary:
        for device in db.execute(
            select(CustomerDevice).where(
                CustomerDevice.customer_id == customer.id,
                CustomerDevice.is_primary.is_(True),
            )
        ).scalars():
            device.is_primary = False
        db.flush()
        existing.is_primary = True


def attach_acquisition(db: Session, customer: Customer, lead: Lead) -> None:
    """FIRST-TOUCH: chỉ ghi lần đầu. Lead sau KHÔNG ghi đè — nguồn gốc là giá trị."""
    existing = db.execute(
        select(CustomerAcquisition).where(CustomerAcquisition.customer_id == customer.id)
    ).scalar_one_or_none()
    if existing is not None:
        return
    db.add(
        CustomerAcquisition(
            customer_id=customer.id,
            source=lead.source,
            referrer_name=lead.referrer_name,
            ref=lead.ref,
            utm_source=lead.utm_source,
            utm_medium=lead.utm_medium,
            utm_campaign=lead.utm_campaign,
            utm_content=lead.utm_content,
            campaign=lead.campaign,
            acquired_via="LEAD",
            first_gift_code=lead.gift_code,
            first_seen_at=lead.created_at,
        )
    )
    db.flush()


def link_lead_to_customer(db: Session, lead: Lead, *, is_new_lead: bool = True) -> Customer | None:
    """Điểm vào duy nhất. Gọi SAU khi lead đã có id và gift_code.

    KHÔNG ném lỗi ra ngoài: liên kết khách là việc phụ, không được làm hỏng việc
    tạo lead. Nhưng lỗi PHẢI được ghi log — cấm nuốt lỗi.
    """
    try:
        customer = find_or_create_customer(db, lead)
        lead.customer_id = customer.id
        attach_device(db, customer, lead, is_new_lead=is_new_lead)
        attach_acquisition(db, customer, lead)
        db.flush()
        return customer
    except Exception:
        logger.exception("G13: liên kết lead %s vào customer thất bại", lead.gift_code)
        db.rollback()
        return None


def find_or_create_customer_by_contact(
    db: Session, *, full_name: str, phone: str, email: str | None
) -> Customer:
    """G16 — khách theo SĐT chuẩn hoá, dùng TRONG một giao dịch đang mở (checkout).

    Khác `find_or_create_customer`: cuộc đua được xử lý bằng SAVEPOINT
    (`begin_nested`), KHÔNG `db.rollback()` — rollback toàn phần ở đây sẽ xoá
    luôn khoá giỏ hàng và mọi việc checkout đã làm trong cùng giao dịch.

    Cùng luật G13: chỉ ĐIỀN KHI TRỐNG, không ghi đè lịch sử. Đặt hàng KHÔNG bật
    `marketing_consent` — đồng ý nhận tiếp thị là quyết định riêng của khách.
    """
    canonical = normalize_phone(phone)
    customer = db.execute(
        select(Customer).where(Customer.phone_normalized == canonical)
    ).scalar_one_or_none()
    if customer is not None:
        customer.full_name = _fill_if_empty(customer.full_name, full_name)
        customer.email = _fill_if_empty(customer.email, email)
        return customer

    candidate = Customer(
        full_name=full_name,
        phone_normalized=canonical,
        email=email,
        status="ACTIVE",
        marketing_consent=False,
    )
    try:
        with db.begin_nested():
            db.add(candidate)
            db.flush()
        return candidate
    except IntegrityError:
        # Request khác vừa tạo cùng SĐT — đọc lại bản của họ.
        return db.execute(
            select(Customer).where(Customer.phone_normalized == canonical)
        ).scalar_one()


def attach_acquisition_from_order(db: Session, customer: Customer, order) -> None:
    """FIRST-TOUCH cho khách đến THẲNG cửa hàng (chưa từng để lại lead).

    Khách đã có first-touch (từ lead hay đơn trước) ⇒ KHÔNG đụng tới — ghi đè
    first-touch là làm mất đúng thứ báo cáo "kênh nào mang khách về" cần.
    """
    existing = db.execute(
        select(CustomerAcquisition.id).where(CustomerAcquisition.customer_id == customer.id)
    ).first()
    if existing is not None:
        return
    with db.begin_nested():
        db.add(
            CustomerAcquisition(
                customer_id=customer.id,
                source=order.source,
                campaign=order.campaign,
                ref=order.ref,
                utm_source=order.utm_source,
                utm_medium=order.utm_medium,
                utm_campaign=order.utm_campaign,
                utm_content=order.utm_content,
                acquired_via="ORDER",
                first_order_id=order.id,
            )
        )
        db.flush()
