# Phương án lưu trữ PII — để Owner chọn

> **Tài liệu này KHÔNG chọn phương án nào.** Nó trình bày ba lựa chọn trung lập với đánh đổi
> thật, để Owner quyết định. Không có "phương án khuyến nghị".
>
> **OWNER DECISION REQUIRED.**
>
> **Không phải lời khuyên pháp lý.** Việt Nam có khung pháp lý về bảo vệ dữ liệu cá nhân. Tài liệu
> này **không** khẳng định yêu cầu pháp lý cụ thể nào và **không** thay thế việc rà soát bởi người
> có chuyên môn. Nếu Owner cần mốc thời hạn theo luật, phải hỏi người có chuyên môn — **không lấy
> con số trong tài liệu này làm căn cứ pháp lý**.
>
> Bối cảnh dữ liệu: [`docs/pii-data-map.md`](../pii-data-map.md).
> Hiện trạng: **chưa quyết ⇒ dữ liệu đang được giữ vô thời hạn.**

---

## 0. Ba thứ áp dụng cho MỌI phương án

1. **`audit_events` không xoá theo lead.** `lead_pk` có `ON DELETE SET NULL` nhưng `lead_id` và
   `gift_code` **nằm lại**. Nghĩa là: xoá lead **không** xoá hết dấu vết gắn với người đó. Mọi
   phương án dưới đây phải nói rõ xử lý phần này thế nào.
2. **IP khách nằm trong `audit_events.actor`** (`public:<ip>`). Đây là dữ liệu cá nhân và **không**
   tự biến mất khi xoá lead.
3. **Chưa có cơ chế xoá tự động.** Mọi phương án đều cần thêm việc (job dọn dẹp hoặc quy trình tay).
   Chi phí đó tính trong "tác động vận hành" bên dưới.

---

## OPTION A — MINIMAL

**Giữ tối thiểu, xoá sớm.**

| Mục | Nội dung |
|---|---|
| **Thời hạn** | Lead chưa nhận quà: **90 ngày**. Lead **đã** nhận quà: **180 ngày**. Log IP: **30 ngày** |
| **Cơ chế** | Job dọn dẹp định kỳ: lead quá hạn → xoá hẳn bản ghi; audit cũ → xoá `actor` (thay bằng `redacted`) |
| **Ưu điểm** | Ít dữ liệu nhất ⇒ rủi ro lộ nhỏ nhất. Dễ giải trình "chỉ giữ trong thời gian cần". Chi phí lưu thấp |
| **Nhược điểm** | **Mất khả năng phân tích dài hạn** — không đo được hiệu quả chiến dịch sau nửa năm. Không đối chiếu được khiếu nại muộn. Không truy vết được phát quà cũ nếu có tranh chấp |
| **Tác động vận hành** | Cần **một job định kỳ** + giám sát job đó. Cần quy trình khi luật sư/khách yêu cầu dữ liệu cũ hơn hạn (sẽ **không còn**) |
| **Xoá / ẩn danh** | Sớm và tự động. `audit_events.actor`: thay IP bằng `redacted` sau 30 ngày |
| **Tác động kiểm toán** | **Giảm mạnh.** Sau 30 ngày không còn biết thao tác đến từ IP nào. Sau 180 ngày không còn chi tiết lead để đối chiếu vết audit |

---

## OPTION B — STANDARD CRM

**Giữ theo vòng đời quan hệ khách hàng.**

| Mục | Nội dung |
|---|---|
| **Thời hạn** | Lead còn hoạt động: **giữ nguyên**. Lead không hoạt động **24 tháng** thì ẩn danh. Log IP: **12 tháng** |
| **Cơ chế** | Ẩn danh **tại chỗ** (giữ dòng, xoá trường định danh: `full_name`, `phone`, `company_name`, `referrer_name` → `NULL`/giá trị băm), **giữ** phần marketing attribution + trạng thái quà để thống kê |
| **Ưu điểm** | Cân bằng: vẫn phân tích được xu hướng nhiều năm vì **giữ số liệu tổng hợp**, mà **không còn định danh** cá nhân. Hợp với mô hình CRM/chăm sóc khách hàng |
| **Nhược điểm** | **Phức tạp hơn** — phải định nghĩa chính xác "ẩn danh" nghĩa là gì và test nó. Ẩn danh nửa vời (còn `gift_code` trỏ tới phiếu phát quà có tên trên giấy) **không** thật sự là ẩn danh |
| **Tác động vận hành** | Job ẩn danh định kỳ + test khẳng định trường định danh **thật sự** bị xoá. Cần quyết định: giữ lead "đang hoạt động" dựa vào tiêu chí nào (có mua? có tương tác?) |
| **Xoá / ẩn danh** | Ẩn danh theo lịch; xoá hẳn khi có yêu cầu. `audit_events`: giữ vết, thay `actor` chứa IP sau 12 tháng |
| **Tác động kiểm toán** | **Trung bình.** Vết thao tác còn, nhưng sau khi ẩn danh thì không còn nối được vết với một con người cụ thể |

---

## OPTION C — EXTENDED MARKETING

**Giữ lâu để khai thác tiếp thị.**

| Mục | Nội dung |
|---|---|
| **Thời hạn** | Lead: **60 tháng**. Log IP: **24 tháng** |
| **Cơ chế** | Không ẩn danh tự động. Chỉ xoá khi khách yêu cầu |
| **Ưu điểm** | Dữ liệu dài nhất cho phân tích vòng đời, tái kích hoạt, đo LTV. Không mất lịch sử khi tranh chấp |
| **Nhược điểm** | **Rủi ro cao nhất** — giữ định danh 5 năm. Nếu có sự cố lộ dữ liệu, phạm vi ảnh hưởng lớn nhất. Khó biện minh "chỉ giữ trong thời gian cần thiết" |
| **Tác động vận hành** | **Ít việc định kỳ nhất** (chỉ xử lý yêu cầu xoá) nhưng **cần quy trình xử lý yêu cầu xoá** cho số lượng lớn. Cần kiểm soát truy cập chặt hơn |
| **Xoá / ẩn danh** | Chỉ theo yêu cầu. Phải có người chịu trách nhiệm xử lý |
| **Tác động kiểm toán** | **Cao nhất** — còn đủ dữ liệu để truy vết nhiều năm, kể cả IP |

---

## Bảng so sánh nhanh

| | A — MINIMAL | B — STANDARD CRM | C — EXTENDED |
|---|---|---|---|
| Lead chưa nhận quà | 90 ngày | theo vòng đời | 60 tháng |
| Lead đã nhận quà | 180 ngày | ẩn danh sau 24 tháng | 60 tháng |
| Log IP | 30 ngày | 12 tháng | 24 tháng |
| Có ẩn danh tự động? | xoá hẳn | **có** | không |
| Công sức dựng ban đầu | vừa | **cao** | thấp |
| Công sức vận hành | vừa | vừa | thấp (nhưng rủi ro cao) |
| Phân tích dài hạn | kém | tốt | tốt nhất |
| Rủi ro khi lộ dữ liệu | thấp | vừa | **cao** |

---

## Cần Owner trả lời

1. **Chọn A, B hay C** — hoặc một biến thể (nói rõ số).
2. **"Đang hoạt động" định nghĩa thế nào** (chỉ áp dụng cho B): có mua hàng? có tương tác trong N
   tháng? hay luôn giữ nếu chưa nhận quà?
3. **Ai chịu trách nhiệm** xử lý yêu cầu xoá dữ liệu của khách.
4. **Có cần rà soát pháp lý không** — nếu có, tài liệu này **không** thay thế được.
5. **Dữ liệu trong `audit_events`** (`lead_id`, `gift_code`, `actor` chứa IP): xoá theo cùng mốc,
   hay giữ lâu hơn để kiểm toán? Hai mục tiêu này **đối nghịch nhau** và phải chọn.

## Việc repo-side sẽ làm SAU KHI Owner chọn

Chưa làm, vì làm trước là đoán hộ Owner:

- Migration thêm cột `anonymized_at` (nếu chọn B)
- Job dọn dẹp/ẩn danh định kỳ + test
- Endpoint xoá/ẩn danh theo yêu cầu + xác thực + audit
- Ghi mốc thời hạn vào `docs/pii-data-map.md` (thay chỗ `OWNER_DECISION`)
