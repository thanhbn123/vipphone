# Lead Schema

| Field | Type | Notes |
|---|---|---|
| lead_id | string/UUID | unique |
| gift_code | string | unique public gift code |
| full_name | string | required |
| phone | string | required |
| iphone_model | string | required |
| iphone_year | integer | required |
| case_color | string | required |
| company_name | string | optional |
| bni_chapter | string | optional |
| referrer_name | string | optional |
| source | string | optional |
| campaign | string | optional |
| utm_source | string | optional |
| utm_medium | string | optional |
| utm_campaign | string | optional |
| utm_content | string | optional |
| ref | string | optional |
| consent | boolean | required |
| created_at | datetime | UTC ISO 8601 |
| gift_status | enum | NEW / CONFIRMED / READY / REDEEMED / CANCELLED |
| redeemed_at | datetime/null | set once |
| redeemed_by | string/null | staff identity in production |
