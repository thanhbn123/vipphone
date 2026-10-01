/*!
 * VIP PHONE — cấu hình frontend.
 *
 * `apiBase` để trống nghĩa là gọi API CÙNG ORIGIN (mặc định, và là cách
 * triển khai được khuyến nghị: một tiến trình phục vụ cả API lẫn file tĩnh).
 *
 * Chỉ đổi giá trị này khi API nằm ở origin khác. Khi đó phải khai origin
 * đó trong CORS_ALLOWED_ORIGINS ở phía máy chủ.
 *
 * KHÔNG đặt secret ở đây — file này được phục vụ công khai cho mọi khách.
 */
"use strict";

window.VIPPHONE_CONFIG = {
  apiBase: "",
  //: Trần thời gian chờ một yêu cầu API (ms).
  requestTimeoutMs: 15000
};
