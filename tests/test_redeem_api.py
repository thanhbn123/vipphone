"""Redeem engine — kịch bản bắt buộc 7, 8, 9 của G09.

Điểm quan trọng nhất của file này là `test_concurrent_redeem_*`: nhiều LUỒNG
THẬT cùng phát quà một mã, và phải chứng minh chỉ đúng MỘT lần ghi thắng.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select

from app.models import AuditEvent, GiftStatus, Lead
from app.services.redeem import redeem_gift

pytestmark = pytest.mark.integration


def create_lead(client, payload) -> dict:
    response = client.post("/api/leads", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def audit_types(db) -> list[str]:
    return [
        row[0] for row in db.execute(select(AuditEvent.event_type).order_by(AuditEvent.id)).all()
    ]


# ------------------------------------------------------------------ 7. thành công
def test_redeem_success(client, db, valid_lead_payload, staff_headers):
    created = create_lead(client, valid_lead_payload)

    response = client.post(f"/api/gifts/{created['gift_code']}/redeem", headers=staff_headers)

    assert response.status_code == 200, response.text
    body = response.json()

    assert body["gift_status"] == GiftStatus.REDEEMED.value
    assert body["already_redeemed"] is False
    assert body["redeemed_at"] is not None
    assert body["lead_id"] == created["lead_id"]

    lead = db.execute(select(Lead)).scalar_one()
    assert lead.gift_status == GiftStatus.REDEEMED.value
    assert lead.redeemed_at is not None
    # `redeemed_by` phải ĐỊNH DANH ĐƯỢC nhân viên, và không lộ khoá.
    assert lead.redeemed_by.startswith("staff:")
    assert len(lead.redeemed_by) == len("staff:") + 12


def test_redeem_writes_audit_trail(client, db, valid_lead_payload, staff_headers):
    created = create_lead(client, valid_lead_payload)
    client.post(f"/api/gifts/{created['gift_code']}/redeem", headers=staff_headers)

    assert audit_types(db) == [
        "LEAD_CREATED",
        "GIFT_CREATED",
        "GIFT_STATUS_CHANGED",
        "GIFT_REDEEMED",
    ]

    changed = db.execute(
        select(AuditEvent).where(AuditEvent.event_type == "GIFT_STATUS_CHANGED")
    ).scalar_one()
    assert changed.event_metadata["from_status"] == "NEW"
    assert changed.event_metadata["to_status"] == "REDEEMED"
    assert changed.actor.startswith("staff:")
    # Audit không được chứa PII.
    assert "phone" not in changed.event_metadata
    assert "full_name" not in changed.event_metadata


def test_redeem_requires_staff_auth(client, db, valid_lead_payload):
    created = create_lead(client, valid_lead_payload)
    response = client.post(f"/api/gifts/{created['gift_code']}/redeem")

    assert response.status_code == 401
    lead = db.execute(select(Lead)).scalar_one()
    assert lead.gift_status == GiftStatus.NEW.value, "không được đổi trạng thái"


def test_redeem_fails_closed_when_auth_not_configured(
    client, db, valid_lead_payload, staff_headers, monkeypatch
):
    from app import security

    created = create_lead(client, valid_lead_payload)
    monkeypatch.setattr(security.settings, "staff_api_keys", "")

    response = client.post(f"/api/gifts/{created['gift_code']}/redeem", headers=staff_headers)

    assert response.status_code == 503
    lead = db.execute(select(Lead)).scalar_one()
    assert lead.gift_status == GiftStatus.NEW.value


def test_redeem_rejects_bad_key(client, db, valid_lead_payload):
    created = create_lead(client, valid_lead_payload)
    response = client.post(
        f"/api/gifts/{created['gift_code']}/redeem",
        headers={"X-Staff-Key": "khoa-sai"},
    )
    assert response.status_code == 401
    assert db.execute(select(Lead)).scalar_one().gift_status == GiftStatus.NEW.value


def test_redeem_unknown_code_returns_404(client, staff_headers):
    response = client.post("/api/gifts/VIP-26-ZZZZZZ/redeem", headers=staff_headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "GIFT_NOT_FOUND"


def test_redeem_malformed_code_returns_404(client, staff_headers):
    response = client.post("/api/gifts/khong-phai-ma/redeem", headers=staff_headers)
    assert response.status_code == 404


def test_redeem_cancelled_gift_is_refused(client, db, valid_lead_payload, staff_headers):
    """Mã đã huỷ thì KHÔNG được phát quà."""
    created = create_lead(client, valid_lead_payload)
    lead = db.execute(select(Lead)).scalar_one()
    lead.gift_status = GiftStatus.CANCELLED.value
    db.commit()

    response = client.post(f"/api/gifts/{created['gift_code']}/redeem", headers=staff_headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "GIFT_CANCELLED"

    db.expire_all()
    lead = db.execute(select(Lead)).scalar_one()
    assert lead.gift_status == GiftStatus.CANCELLED.value
    assert lead.redeemed_at is None


@pytest.mark.parametrize("status", [GiftStatus.NEW, GiftStatus.CONFIRMED, GiftStatus.READY])
def test_redeem_allowed_from_all_redeemable_statuses(
    client, db, valid_lead_payload, staff_headers, status
):
    created = create_lead(client, valid_lead_payload)
    lead = db.execute(select(Lead)).scalar_one()
    lead.gift_status = status.value
    db.commit()

    response = client.post(f"/api/gifts/{created['gift_code']}/redeem", headers=staff_headers)
    assert response.status_code == 200, response.text
    assert response.json()["gift_status"] == GiftStatus.REDEEMED.value


# ------------------------------------------------------------- 8. redeem lần hai
def test_second_redeem_is_idempotent(client, db, valid_lead_payload, staff_headers):
    created = create_lead(client, valid_lead_payload)

    first = client.post(f"/api/gifts/{created['gift_code']}/redeem", headers=staff_headers)
    assert first.json()["already_redeemed"] is False
    first_at = first.json()["redeemed_at"]

    second = client.post(f"/api/gifts/{created['gift_code']}/redeem", headers=staff_headers)

    assert second.status_code == 200
    body = second.json()
    assert body["already_redeemed"] is True
    assert body["gift_status"] == GiftStatus.REDEEMED.value
    # `redeemed_at` KHÔNG được đổi.
    assert body["redeemed_at"] == first_at

    # Chỉ đúng MỘT sự kiện GIFT_REDEEMED.
    assert audit_types(db).count("GIFT_REDEEMED") == 1
    assert audit_types(db).count("GIFT_STATUS_CHANGED") == 1


def test_third_and_fourth_redeem_still_idempotent(client, db, valid_lead_payload, staff_headers):
    created = create_lead(client, valid_lead_payload)
    for _ in range(5):
        response = client.post(f"/api/gifts/{created['gift_code']}/redeem", headers=staff_headers)
        assert response.status_code == 200

    assert db.execute(select(func.count()).select_from(Lead)).scalar_one() == 1
    assert audit_types(db).count("GIFT_REDEEMED") == 1


# --------------------------------------------------------- 9. redeem đồng thời
def _redeem_in_thread(gift_code: str, actor: str, barrier: threading.Barrier):
    """Mỗi luồng dùng SESSION RIÊNG, giống hai nhân viên trên hai máy."""
    from app.db import SessionLocal

    barrier.wait(timeout=10)
    session = SessionLocal()
    try:
        result = redeem_gift(session, gift_code=gift_code, actor=actor)
        return result.already_redeemed
    finally:
        session.close()


def test_concurrent_redeem_only_one_wins(client, db, valid_lead_payload, engine):
    """N luồng cùng phát quà MỘT mã: đúng 1 lần thắng, không double-spend."""
    created = create_lead(client, valid_lead_payload)
    code = created["gift_code"]

    thread_count = 8
    barrier = threading.Barrier(thread_count)

    with ThreadPoolExecutor(max_workers=thread_count) as pool:
        futures = [
            pool.submit(_redeem_in_thread, code, f"staff:thread-{i}", barrier)
            for i in range(thread_count)
        ]
        results = [future.result(timeout=30) for future in futures]

    # ĐÚNG MỘT luồng nhận `already_redeemed = False`.
    assert results.count(False) == 1, (
        f"phải có đúng 1 lần ghi thắng, nhưng có {results.count(False)}: {results}"
    )
    assert results.count(True) == thread_count - 1

    # Trạng thái cuối cùng đúng.
    db.expire_all()
    lead = db.execute(select(Lead)).scalar_one()
    assert lead.gift_status == GiftStatus.REDEEMED.value
    assert lead.redeemed_at is not None

    # Audit: chỉ MỘT GIFT_REDEEMED, và chỉ MỘT GIFT_STATUS_CHANGED.
    types = audit_types(db)
    assert types.count("GIFT_REDEEMED") == 1, types
    assert types.count("GIFT_STATUS_CHANGED") == 1, types

    # `redeemed_by` ghi lại ĐÚNG luồng đã thắng.
    assert lead.redeemed_by.startswith("staff:thread-")


def test_concurrent_redeem_via_http(client, db, valid_lead_payload, engine):
    """Cùng một mã, gọi qua HTTP nhiều lần liên tiếp: lần đầu ghi, các lần sau idempotent."""
    from tests.conftest import STAFF_KEY

    created = create_lead(client, valid_lead_payload)
    headers = {"X-Staff-Key": STAFF_KEY}

    responses = [
        client.post(f"/api/gifts/{created['gift_code']}/redeem", headers=headers) for _ in range(4)
    ]

    assert [r.status_code for r in responses] == [200, 200, 200, 200]
    assert [r.json()["already_redeemed"] for r in responses] == [
        False,
        True,
        True,
        True,
    ]
    assert audit_types(db).count("GIFT_REDEEMED") == 1


def test_redeem_then_lookup_shows_redeemed(client, valid_lead_payload, staff_headers):
    created = create_lead(client, valid_lead_payload)
    client.post(f"/api/gifts/{created['gift_code']}/redeem", headers=staff_headers)

    body = client.get(f"/api/gifts/{created['gift_code']}", headers=staff_headers).json()
    assert body["gift_status"] == GiftStatus.REDEEMED.value
    assert body["redeemed_at"] is not None


def test_redeem_does_not_change_other_leads(client, db, valid_lead_payload, staff_headers):
    first = create_lead(client, valid_lead_payload)
    second = create_lead(client, {**valid_lead_payload, "phone": "0987654321"})

    client.post(f"/api/gifts/{first['gift_code']}/redeem", headers=staff_headers)

    db.expire_all()
    other = db.execute(select(Lead).where(Lead.gift_code == second["gift_code"])).scalar_one()
    assert other.gift_status == GiftStatus.NEW.value
    assert other.redeemed_at is None


# ==========================================================================
# CHỨNG MINH KHOÁ HÀNG — phép đo TẤT ĐỊNH
#
# ⚠️  VÌ SAO CẦN: test `test_concurrent_redeem_only_one_wins` ở trên **vẫn PASS
# khi bỏ `with_for_update()`** — đã đo thật, 5/5 lần PASS. Lý do: 8 luồng mất
# ~20ms để bắt tay kết nối (scram), nên các lệnh SELECT bị so le và cuộc đua
# không xảy ra. Nghĩa là test đó **không phân biệt được** có khoá hay không.
#
# Hai test dưới đây dùng phép đo TẤT ĐỊNH, không phụ thuộc may rủi:
#   1. khoá hàng có thật sự CHẶN một `SELECT … FOR UPDATE` khác không
#   2. câu SQL mà `redeem_gift` dùng có `FOR UPDATE` không
# ==========================================================================


def _lead_row_lock_holder(db, gift_code: str):
    """Giữ khoá hàng trên một session riêng (chưa commit)."""
    from sqlalchemy import text

    db.execute(text("SELECT id FROM leads WHERE gift_code = :c FOR UPDATE"), {"c": gift_code})
    return db


def test_row_lock_actually_blocks(client, db, valid_lead_payload, engine):
    """TẤT ĐỊNH: `SELECT … FOR UPDATE` phải CHẶN một `FOR UPDATE` khác.

    Nếu PostgreSQL không chặn, thì mọi lập luận về chống double-spend ở đây
    đều sai — nên phải đo chính cơ chế, không đoán.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.orm import Session

    created = create_lead(client, valid_lead_payload)
    code = created["gift_code"]

    holder = Session(engine, expire_on_commit=False)
    try:
        _lead_row_lock_holder(holder, code)

        other = Session(engine, expire_on_commit=False)
        try:
            # Đặt trần chờ để phép đo kết thúc nhanh và tất định.
            other.execute(text("SET LOCAL lock_timeout = '400ms'"))
            with pytest.raises(OperationalError) as excinfo:
                other.execute(
                    text("SELECT id FROM leads WHERE gift_code = :c FOR UPDATE"),
                    {"c": code},
                )
            assert "lock timeout" in str(excinfo.value).lower() or (
                "locknotavailable" in str(excinfo.value).lower()
            ), str(excinfo.value)
        finally:
            other.rollback()
            other.close()

        # Nhả khoá rồi thì phải lấy được ngay.
        holder.rollback()
        probe = Session(engine, expire_on_commit=False)
        try:
            probe.execute(text("SET LOCAL lock_timeout = '2s'"))
            probe.execute(
                text("SELECT id FROM leads WHERE gift_code = :c FOR UPDATE"),
                {"c": code},
            )
        finally:
            probe.rollback()
            probe.close()
    finally:
        holder.close()


def test_redeem_service_query_uses_for_update():
    """TẤT ĐỊNH: câu SQL mà `redeem_gift` thật sự dùng phải có `FOR UPDATE`."""
    from app.services.redeem import locked_lead_query

    compiled = str(
        locked_lead_query("VIP-26-ABCDEF").compile(compile_kwargs={"literal_binds": True})
    ).upper()

    assert "FOR UPDATE" in compiled, compiled


def test_redeem_service_blocks_on_the_lock_not_on_the_update(
    client, db, valid_lead_payload, engine
):
    """TẤT ĐỊNH + PHÂN BIỆT ĐƯỢC: service phải CHỜ Ở CÂU `SELECT … FOR UPDATE`.

    ⚠️  VÌ SAO VIẾT KIỂU NÀY: bản đầu của test này chỉ kiểm "service có ném lỗi
    khoá không". Nó **PASS cả khi bỏ `with_for_update()`** — vì lúc đó service
    chờ ở câu `UPDATE` thay vì câu `SELECT`, và cả hai đều ném cùng loại lỗi.
    Đã đo: 1 trong 3 test tất định không phân biệt được.

    Cách phân biệt: giữ khoá hàng, cho service chạy ở luồng riêng, rồi hỏi
    `pg_stat_activity` xem backend đang chờ **ĐANG CHẠY CÂU GÌ**. Có
    `FOR UPDATE` trong câu đó nghĩa là service thật sự khoá hàng TRƯỚC khi đọc;
    nếu chỉ thấy `UPDATE` thì nghĩa là nó đã đọc dữ liệu cũ rồi mới ghi — đúng
    cái lỗi double-spend cần chặn.
    """
    import threading
    import time

    from sqlalchemy import text
    from sqlalchemy.orm import Session

    created = create_lead(client, valid_lead_payload)
    code = created["gift_code"]

    holder = Session(engine, expire_on_commit=False)
    blocker_result: dict[str, object] = {}

    def run_service() -> None:
        session = Session(engine, expire_on_commit=False)
        try:
            blocker_result["value"] = redeem_gift(
                session, gift_code=code, actor="staff:blocked"
            ).already_redeemed
        except Exception as exc:
            blocker_result["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            session.close()

    try:
        _lead_row_lock_holder(holder, code)

        thread = threading.Thread(target=run_service, daemon=True)
        thread.start()

        # Chờ backend kia vào trạng thái chờ khoá, rồi đọc câu nó đang chạy.
        waited_query = ""
        deadline = time.time() + 10
        while time.time() < deadline:
            with engine.connect() as probe:
                rows = probe.execute(
                    text(
                        "SELECT query FROM pg_stat_activity "
                        "WHERE wait_event_type = 'Lock' AND query ILIKE '%leads%'"
                    )
                ).all()
            if rows:
                waited_query = " ".join(str(r[0]) for r in rows).upper()
                break
            time.sleep(0.1)

        assert waited_query, "Không thấy backend nào chờ khoá — không đo được cơ chế khoá hàng."
        assert "FOR UPDATE" in waited_query, (
            "Service đang chờ ở câu KHÔNG có FOR UPDATE, nghĩa là nó đã ĐỌC "
            f"dữ liệu cũ trước khi ghi (double-spend). Câu đang chờ: {waited_query[:200]}"
        )

        # Nhả khoá: luồng kia phải hoàn tất bình thường.
        holder.rollback()
        thread.join(timeout=15)
        assert not thread.is_alive(), "luồng service không thoát sau khi nhả khoá"
    finally:
        if holder.in_transaction():
            holder.rollback()
        holder.close()

    assert blocker_result.get("value") is False, blocker_result
    assert blocker_result.get("error") is None, blocker_result

    db.expire_all()
    assert audit_types(db).count("GIFT_REDEEMED") == 1
