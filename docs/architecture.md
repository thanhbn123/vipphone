# VIP PHONE — Architecture

> Trạng thái thật của từng phần: [`MASTER_STATUS.md`](MASTER_STATUS.md).
> Quyết định stack: [`adr/0001-stack-selection.md`](adr/0001-stack-selection.md).

## Funnel

QR / campaign link
→ Landing
→ Lead form
→ Validation
→ Gift code
→ Success page
→ Redeem page
→ Staff confirms gift
→ CRM/marketing later

## Hiện trạng (sau G01)

Client-only demo:

- HTML
- CSS
- Vanilla JavaScript (không build step)
- `localStorage` — **chỉ để demo, không phải nguồn chân lý**
- JSON configuration for iPhone models

Mọi thứ dưới đây trong mục "Production target" là **thiết kế đích, CHƯA có mã** cho tới khi
gate tương ứng hoàn tất. Không được coi là đã có.

## Production target

```
Trình duyệt
  │  (static: index.html, success.html, redeem.html, assets/)
  ▼
FastAPI  ──►  Gift Engine  ──►  PostgreSQL 16 (Alembic migration)
  │                │
  │                ├──► Audit log
  │                └──► Redeem engine (atomic, chống double-spend)
  │
  ├──► /admin/leads   (có xác thực)
  └──► CRM / Marketing / Analytics (qua webhook + dataLayer)
```

Một tiến trình phục vụ cả API lẫn file tĩnh → deploy và rollback đơn giản.

### API contract

`POST /api/leads`

Creates a lead and returns:

```json
{
  "lead_id": "...",
  "gift_code": "VIP-26-ABC123",
  "gift_status": "NEW"
}
```

`GET /api/gifts/{gift_code}`

Returns the minimum gift data needed by staff.

`POST /api/gifts/{gift_code}/redeem`

Transitions:

`NEW|CONFIRMED|READY → REDEEMED`

A `REDEEMED` code must never redeem twice.

## Security

Do not encode PII into QR.

QR should contain only a redeem URL + gift code/token.

Do not expose staff redeem endpoints publicly without authentication in production.
