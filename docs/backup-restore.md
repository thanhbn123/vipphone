# Sao lưu và phục hồi — VIP PHONE

> **Trạng thái: chuẩn bị xong ở mức repo. CHƯA có sao lưu tự động, CHƯA có staging/production.**
>
> Đã **chạy thật** một lượt sao lưu + phục hồi **tại máy** với PostgreSQL 16 — xem §2.
> Đó là **`LOCAL BACKUP/RESTORE TEST`**, **KHÔNG** phải sao lưu của staging hay production.
>
> Đo ngày **2026-10-02** trên `develop` = `074c644d175461d7071d110316d887d13347900b`.

---

## 1. Vì sao phải có mục này trước khi deploy

Toàn bộ dữ liệu khách của VIP PHONE — tên, số điện thoại, công ty, chapter BNI, gift code —
nằm trong **một** PostgreSQL. Gift code là thứ khách cầm trên tay. Mất database nghĩa là:

- Không tra được gift code ⇒ **khách đứng ở quầy mà không phát được quà**
- Mất vết `redeemed_by` ⇒ không biết ai đã phát gì
- Mất `leads` ⇒ mất luôn khả năng chống trùng, khách có thể xin quà nhiều lần

Không có bản sao lưu nào đã được kiểm thì **chưa có bản sao lưu nào**.

---

## 2. `LOCAL BACKUP/RESTORE TEST` — đã chạy thật

Chạy ngày 2026-10-02, PostgreSQL 16 trên macOS, database `vipphone_test`.

| Bước | Lệnh | Kết quả đo được |
|---|---|---|
| Tạo dữ liệu mẫu | `INSERT … generate_series(1,250)` | **250** lead |
| **Sao lưu** | `pg_dump -Fc -f /tmp/vp-backup-test.dump` | file **23 KB**, SHA-256 `4f1f2699ad6a3b7a…` |
| **Phục hồi** | `pg_restore -d vipphone_restore_probe --no-owner --no-privileges` | không lỗi |
| Kiểm số dòng | `SELECT count(*) FROM leads` | nguồn **250** = phục hồi **250** ✓ |
| Kiểm bảng | `pg_tables` | đủ `alembic_version`, `audit_events`, `iphone_models`, `leads` ✓ |
| Kiểm danh mục | `SELECT count(*) FROM iphone_models` | **28** ✓ |
| **Kiểm nội dung** | `md5(string_agg(gift_code\|\|full_name\|\|phone …))` | nguồn `94e4e85b318f9f96…` = phục hồi `94e4e85b318f9f96…` ✓ |

**Vì sao kiểm bằng md5 nội dung chứ không chỉ số dòng:** số dòng khớp mà nội dung lệch vẫn là
một bản phục hồi hỏng. Đếm dòng chỉ chứng minh *có 250 dòng*, không chứng minh *đúng 250 dòng ấy*.

**Phạm vi:** đây là phép đo **tại máy**, cùng máy chạy database, **không** qua mạng, **không**
qua nén/gateway, và **không** phải môi trường staging. Nó chứng minh **quy trình đúng**;
nó **không** chứng minh sao lưu trên hạ tầng thật chạy được.

---

## 3. Lệnh dùng thật

### 3.1 Sao lưu

```bash
# Định dạng custom (-Fc): nén sẵn, cho phép phục hồi CHỌN LỌC từng bảng, và
# song song được. Đừng dùng `-Fp` (SQL thô) cho bản sao lưu định kỳ.
pg_dump \
  --host "$PGHOST" --port "$PGPORT" --username "$PGUSER" --dbname "$PGDATABASE" \
  --format=custom \
  --file "/backup/vipphone-$(date -u +%Y%m%dT%H%M%SZ).dump"

# Ghi kèm mã băm để sau này biết file có hỏng không.
sha256sum /backup/vipphone-*.dump > /backup/vipphone-*.dump.sha256
```

**Mật khẩu:** dùng `~/.pgpass` (quyền `600`) hoặc `PGPASSWORD` từ secret manager.
**KHÔNG** đưa mật khẩu vào dòng lệnh — nó vào `ps` và vào lịch sử shell.

### 3.2 Phục hồi

```bash
# 1. Phục hồi vào database MỚI trước — không đè lên bản đang chạy.
createdb -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" vipphone_restore_check
pg_restore -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" \
  --dbname vipphone_restore_check --no-owner --no-privileges \
  /backup/vipphone-<mốc>.dump

# 2. KIỂM trước khi tin (xem §3.3).
# 3. Chỉ khi kiểm đạt mới đổi tên/trỏ ứng dụng sang.
```

### 3.3 Kiểm bản phục hồi — bắt buộc, không được bỏ

```sql
SELECT count(*) FROM leads;
SELECT count(*) FROM iphone_models;        -- phải là 28
SELECT count(*) FROM audit_events;
SELECT version_num FROM alembic_version;   -- phải khớp head của mã đang chạy
-- Và so nội dung, không chỉ số dòng:
SELECT md5(string_agg(gift_code||full_name||phone, ',' ORDER BY gift_code)) FROM leads;
```

Sau đó chạy `scripts/staging_preflight.sh` trỏ vào bản phục hồi — nó kiểm luôn migration head
và tính sẵn sàng.

---

## 4. RPO / RTO — ✅ OWNER ĐÃ CHỐT (2026-10-02)

| Chỉ số | Nghĩa | Giá trị |
|---|---|---|
| **RPO** | Mất tối đa bao nhiêu dữ liệu | **24 giờ** |
| **RTO** | Phục hồi xong trong bao lâu | **4 giờ** |
| Tần suất sao lưu | — | **hằng ngày** |
| Giữ bao nhiêu bản | — | **14 ngày + 4 tuần**, kiểm phục hồi **hằng tháng** |
| Lưu ở đâu (khác máy?) | — | **CHƯA QUYẾT** — `staging_backup.sh` lưu **cùng máy**; cần đích khác máy |

**Vì sao không tự chọn:** RPO/RTO là **mức chấp nhận rủi ro kinh doanh**, không phải thông số
kỹ thuật. Kỹ thuật dựng được cơ chế; chỉ Owner biết mất một ngày lead có sao không.

**Gợi ý khung để Owner chọn** (KHÔNG phải khuyến nghị, chỉ để dễ hình dung đánh đổi):

| Phương án | Tần suất | Mất tối đa | Chi phí / công |
|---|---|---|---|
| Cơ bản | mỗi ngày 1 lần | tới 24 giờ lead | thấp |
| Vừa | mỗi giờ | tới 1 giờ | cần lịch chạy + chỗ lưu |
| Chặt | WAL liên tục (PITR) | gần như 0 | cần cấu hình archive + dung lượng lớn hơn nhiều |

Với quy mô phát quà tại quầy, **mất vài giờ lead** khác hẳn **mất một ngày** — nhưng đó là
phán đoán kinh doanh, không phải kết luận kỹ thuật.

---

## 5. Ai chịu trách nhiệm

| Việc | Người | Trạng thái |
|---|---|---|
| Chạy sao lưu định kỳ | **OWNER_DECISION_REQUIRED** | chưa có |
| Kiểm bản sao lưu (thử phục hồi) | **OWNER_DECISION_REQUIRED** | chưa có |
| Phục hồi khi sự cố | **OWNER_DECISION_REQUIRED** | chưa có |
| Giữ khoá mã hoá | **OWNER_DECISION_REQUIRED** | chưa có |

**Sao lưu không được kiểm định kỳ thì không phải sao lưu.** Đề xuất tối thiểu: **mỗi tháng một
lần** chạy §3.2 + §3.3 vào database tạm rồi xoá. Chưa ai được giao việc này.

---

## 6. Mã hoá và nơi lưu

Bản dump chứa **đầy đủ PII** (tên, số điện thoại, công ty). Nó **không** được hưởng quyền
bảo vệ của database.

- **Mã hoá khi lưu (at rest):** khuyến nghị mạnh. `age` hoặc `gpg`:
  ```bash
  pg_dump … -Fc -f - | age -r "<khoá-công-khai>" > /backup/vipphone-<mốc>.dump.age
  ```
- **KHÔNG để bản dump chung máy với database.** Mất máy là mất cả hai.
- **KHÔNG commit bản dump vào git.** `.gitignore` nay đã chặn `*.dump`, `*.dump.age`,
  `*.dump.sha256`, `pg-backup/` — đã kiểm bằng `git check-ignore` (đạt). Trước lượt này thì **chưa** chặn.
- Quyền file: `600`, chủ sở hữu là tài khoản chạy sao lưu.

---

## 7. Chưa làm — ghi thẳng

| # | Việc | Trạng thái |
|---|---|---|
| 1 | Lịch sao lưu tự động | **CHƯA CÓ** |
| 2 | Thử phục hồi trên staging | **CHƯA THỂ** (chưa có staging) |
| 3 | Mã hoá bản dump | **CHƯA CÓ** |
| 4 | Lưu bản dump ở máy khác | **CHƯA CÓ** |
| 5 | Đo thời gian phục hồi thật (RTO) | **CHƯA ĐO** — mới đo trên 250 dòng, dữ liệu thật sẽ khác |
| 6 | Diễn tập phục hồi có người khác làm theo tài liệu | **CHƯA** |
| 7 | Kiểm `.gitignore` có chặn `*.dump` | **ĐÃ LÀM** — đã chặn `*.dump`, `*.dump.age`, `*.dump.sha256`, `pg-backup/` |

Mục **5** đáng lưu ý: 250 dòng phục hồi gần như tức thì. Với dữ liệu thật, con số sẽ khác và
**chưa ai đo**.

## Sao lưu tự động staging → NAS (2026-10-10, D-005)

`scripts/staging_backup.sh` chạy **trên máy staging** bằng cron của user `deploy` (không sudo). Mỗi lượt:
dump DB `-Fc` + kiểm `pg_restore --list` · tar volume ảnh · sha256 · bản tuần (Chủ nhật) · **chép sang NAS và so
sha256 hai đầu** · xoay vòng 14 ngày / 4 tuần ở **cả hai** nơi.

- NAS gắn tại `/mnt/vip-nas` (CIFS tới `100.120.9.63` qua Tailscale, `uid=deploy`) do **root làm một lần** bằng
  script ngoài repo (vault `production/staging-160-22-170-20/gan-tailscale-nas.sh`). Đích:
  `/mnt/vip-nas/vip-vault/viporder-staging/vipphone/{daily,weekly}` — cùng quy ước "mỗi máy một thư mục" của VIP Vault.
- Chỉ coi NAS là đã gắn khi `mountpoint -q` đúng. NAS chưa gắn hoặc sha256 lệch ⇒ bản trên máy **vẫn giữ**, in
  `⚠`, **thoát mã 3** (cron ghi log; không bao giờ báo OK giả).
- Đã thử thật trên staging 2026-10-10 bằng thư mục tạm: NAS gắn ⇒ mã 0, khớp sha256 · 3 lượt giữ 2 ⇒ còn 2 ở mỗi
  nơi · NAS chưa gắn ⇒ mã 3, 0 tệp ghi nhầm · bản chép bị làm hỏng ⇒ báo LỆCH, mã 3 · tên DB có `prod` ⇒ từ chối.

### Đường (b) — không cần root: Tailscale trong container + smbclient (2026-10-10, đang dùng)

Root của staging không vào được từ máy Owner, nên NAS **không** gắn thành ổ. Thay vào đó:
- container `vipphone-tailscale` (ảnh `tailscale/tailscale`, mạng riêng của container, `TS_ACCEPT_DNS=false`,
  volume `vipphone-tailscale-state`) — máy `viporder-staging-vipphone` trong tailnet của Owner;
- tài khoản NAS ở `~deploy/.config/vip-nas/cred` (600), Owner nhập trên máy chủ, không qua hội thoại;
- `scripts/nas_smb_push.sh` chạy trong ảnh `vipphone-smbclient:alpine3.20` với `--network container:vipphone-tailscale`:
  put tên tạm → rename → put `.sha256` → **tải lại từ NAS và so sha256** → xoay vòng trên NAS.
- Đích: share `data` (cùng share VIP Vault), `vip-vault/viporder-staging/vipphone/{daily,weekly}`.

Thử thật 2026-10-10 trên thư mục NAS riêng (đã xoá): 3 lượt giữ 2 ⇒ NAS còn đúng 2 bản, mỗi bản tải lại khớp ·
NAS sai địa chỉ ⇒ "không tải được", mã 3 · không có container ⇒ cảnh báo, mã 3.

