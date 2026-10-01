# VIP PHONE — Architecture

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

## Starter architecture

Client-only demo:

- HTML
- CSS
- Vanilla JavaScript
- `localStorage`
- JSON configuration for iPhone models

## Production target

Frontend
→ API
→ PostgreSQL
→ CRM / Marketing / Analytics

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
