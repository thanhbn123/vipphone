/*!
 * VIP PHONE — trang nhân viên: tra cứu gift code qua API và xác nhận phát quà.
 *
 * ⚠️  TÌNH TRẠNG XÁC THỰC NHÂN VIÊN
 * Trang này gọi API có xác thực bằng khoá nhân viên (`X-Staff-Key`). Nếu máy
 * chủ CHƯA cấu hình `STAFF_API_KEYS`, API trả 503 và trang nói thẳng ra —
 * fail closed, không mở toang.
 *
 * ⚠️  XÁC NHẬN PHÁT QUÀ
 * Việc xác nhận (`POST /api/gifts/{code}/redeem`) được hoàn thiện ở gate G03
 * với giao dịch nguyên tử ở server. Trước khi route đó tồn tại, trang báo rõ
 * chức năng chưa khả dụng thay vì giả vờ thành công.
 *
 * ⚠️  KHOÁ NHÂN VIÊN — SỐNG TRONG PHIÊN, KHÔNG LƯU LÂU DÀI
 * Khoá chỉ được ghi vào `sessionStorage` (bộ nhớ tạm của TAB, mất khi đóng tab).
 * TUYỆT ĐỐI không ghi vào `localStorage`/cookie/indexedDB — khoá nằm lại trên
 * máy là khoá dùng được cho người kế tiếp mở máy đó. Có test E2E đo hành vi này
 * bằng trình duyệt thật, và đối chứng âm của nó ở docs/MASTER_STATUS.md §20.
 *
 * ⚠️  QUÉT QR — CHỈ KHI THẬT SỰ HỖ TRỢ
 * Nút quét chỉ được HIỆN sau khi `VPQrScan.isSupported()` trả `true`. Không hỗ
 * trợ thì nút nằm im (thuộc tính `hidden`) và trang nói thẳng lý do. Không có
 * nhánh nào hiện nút rồi bấm vào không có gì xảy ra.
 */
"use strict";

(function () {
  var STAFF_KEY_STORAGE = "vipphone_staff_key_v1";

  var util = window.VPUtil;
  var track = window.VPTrack.track;
  var config = window.VIPPHONE_CONFIG || {};

  var form = document.getElementById("redeemForm");
  var codeInput = document.getElementById("redeemCode");
  var keyInput = document.getElementById("staffKey");
  var result = document.getElementById("redeemResult");

  var scanToggle = document.getElementById("scanToggle");
  var scanPanel = document.getElementById("scanPanel");
  var scanVideo = document.getElementById("scanVideo");
  var scanStop = document.getElementById("scanStop");
  var scanStatus = document.getElementById("scanStatus");
  var scanUnsupported = document.getElementById("scanUnsupported");

  if (!form || !codeInput || !result) return;

  function apiBase() {
    return config.apiBase || "";
  }

  function readStaffKey() {
    if (keyInput && keyInput.value.trim()) return keyInput.value.trim();
    try {
      return sessionStorage.getItem(STAFF_KEY_STORAGE) || "";
    } catch (err) {
      return "";
    }
  }

  function rememberStaffKey(key) {
    if (!key) return;
    try {
      // CHỈ sessionStorage. Xem ghi chú đầu file: khoá không được sống lâu hơn
      // phiên làm việc của tab này.
      sessionStorage.setItem(STAFF_KEY_STORAGE, key);
    } catch (err) {
      /* chế độ riêng tư */
    }
  }

  /* ------------------------------------------------------------ quét QR */

  function setScanStatus(message) {
    if (scanStatus) scanStatus.textContent = message || "";
  }

  /** Rút gift code ra khỏi nội dung QR. Nội dung QR là URL công khai `/redeem?code=…`. */
  function giftCodeFromScannedText(text) {
    var raw = String(text || "").trim();
    if (!raw) return "";

    var candidate = raw;
    var match = raw.match(/[?&]code=([^&\s]+)/);
    if (match) {
      try {
        candidate = decodeURIComponent(match[1]);
      } catch (err) {
        candidate = match[1];
      }
    } else if (raw.indexOf("/") !== -1) {
      // URL không có tham số `code` — không phải phiếu quà của VIP PHONE.
      var parts = raw.split("/");
      candidate = parts[parts.length - 1];
    }

    return util.normalizeGiftCode(candidate);
  }

  function handleScannedText(text) {
    var code = giftCodeFromScannedText(text);
    hideScanPanel();

    if (!code || !util.isWellFormedGiftCode(code)) {
      setScanStatus(
        "Mã QR này không phải phiếu quà VIP PHONE (định dạng VIP-YY-XXXXXX). Thử lại hoặc nhập tay."
      );
      track("vipphone_gift_lookup_failed", { reason: "QR_NOT_GIFT_CODE" });
      return;
    }

    codeInput.value = code;
    setScanStatus("Đã đọc mã từ QR: " + code);
    lookup(code);
  }

  function showScanPanel() {
    if (!scanPanel) return;
    scanPanel.hidden = false;
    if (scanToggle) scanToggle.setAttribute("aria-expanded", "true");
    setScanStatus("Đang mở camera…");
    window.VPQrScan.start(
      scanVideo,
      handleScannedText,
      function (message) {
        hideScanPanel();
        setScanStatus(message);
      }
    );
  }

  function hideScanPanel() {
    window.VPQrScan.stop();
    if (scanPanel) scanPanel.hidden = true;
    if (scanToggle) scanToggle.setAttribute("aria-expanded", "false");
  }

  function initScanner() {
    if (!scanToggle || !scanPanel || !scanVideo) return;

    var supported =
      window.VPQrScan &&
      typeof window.VPQrScan.isSupported === "function" &&
      typeof window.VPQrScan.start === "function";

    if (!supported) {
      // Không có module quét → coi như KHÔNG hỗ trợ. Không hiện nút.
      if (scanUnsupported) scanUnsupported.hidden = false;
      return;
    }

    window.VPQrScan.isSupported().then(function (ok) {
      if (!ok || !window.VPQrScan.cameraAvailable()) {
        // ẨN nút, và nói rõ vì sao. Không có "nút trang trí".
        scanToggle.hidden = true;
        if (scanUnsupported) scanUnsupported.hidden = false;
        return;
      }
      scanToggle.hidden = false;
      if (scanUnsupported) scanUnsupported.hidden = true;
    });

    scanToggle.addEventListener("click", function () {
      if (scanPanel.hidden) {
        showScanPanel();
      } else {
        hideScanPanel();
        setScanStatus("");
      }
    });

    if (scanStop) {
      scanStop.addEventListener("click", function () {
        hideScanPanel();
        setScanStatus("");
      });
    }

    window.addEventListener("pagehide", hideScanPanel);
  }

  /* ------------------------------------------------------------ hiển thị */

  function renderBox(kind, message) {
    result.innerHTML = "";
    var box = document.createElement("div");
    box.className = "status " + kind;
    box.setAttribute("role", kind === "bad" ? "alert" : "status");
    box.textContent = message;
    result.appendChild(box);
  }

  function formatDateTime(value) {
    if (!value) return "không rõ thời điểm";
    var date = new Date(value);
    if (isNaN(date.getTime())) return "không rõ thời điểm";
    return date.toLocaleString("vi-VN");
  }

  function renderGift(gift) {
    result.innerHTML = "";

    var rows = [
      ["Khách", gift.full_name],
      ["Số điện thoại", gift.phone_masked],
      ["Dòng máy", gift.iphone_model + " (" + gift.iphone_year + ")"],
      ["Màu ốp", gift.case_color],
      ["Trạng thái", gift.gift_status]
    ];

    var list = document.createElement("ul");
    list.className = "detail-list";
    rows.forEach(function (row) {
      var li = document.createElement("li");
      var strong = document.createElement("strong");
      strong.textContent = row[0] + ": ";
      li.appendChild(strong);
      li.appendChild(document.createTextNode(String(row[1] || "—")));
      list.appendChild(li);
    });
    result.appendChild(list);

    if (gift.gift_status === "CANCELLED") {
      renderBox("bad", "Mã quà này đã bị huỷ. Không phát quà.");
      return;
    }

    if (gift.gift_status === "REDEEMED") {
      renderBox(
        "warn",
        "Mã này đã được nhận quà lúc " +
          formatDateTime(gift.redeemed_at) +
          ". Không phát lại."
      );
      return;
    }

    var button = document.createElement("button");
    button.type = "button";
    button.className = "primary-btn";
    button.id = "confirmRedeem";
    button.textContent = "XÁC NHẬN ĐÃ PHÁT QUÀ";
    button.addEventListener("click", function () {
      confirmRedeem(gift.gift_code, button);
    });
    result.appendChild(button);
  }

  /* -------------------------------------------------------------- tra cứu */

  function lookup(rawCode) {
    var code = util.normalizeGiftCode(rawCode);

    if (!code) {
      renderBox("bad", "Vui lòng nhập mã nhận quà.");
      return;
    }

    if (!util.isWellFormedGiftCode(code)) {
      renderBox("bad", "Mã quà không đúng định dạng VIP-YY-XXXXXX.");
      track("vipphone_gift_lookup_failed", { reason: "MALFORMED_CODE" });
      return;
    }

    var key = readStaffKey();
    var headers = key ? { "X-Staff-Key": key } : {};

    renderBox("warn", "Đang tra cứu…");

    fetch(apiBase() + "/api/gifts/" + encodeURIComponent(code), { headers: headers })
      .then(function (response) {
        if (response.status === 200) {
          rememberStaffKey(key);
          return response.json().then(function (gift) {
            renderGift(gift);
            track("vipphone_gift_lookup", {
              gift_code: gift.gift_code,
              gift_status: gift.gift_status
            });
          });
        }

        if (response.status === 401) {
          renderBox(
            "bad",
            "Cần khoá truy cập nhân viên hợp lệ. Nhập khoá ở ô phía trên rồi thử lại."
          );
          return;
        }

        if (response.status === 503) {
          renderBox(
            "warn",
            "Máy chủ chưa cấu hình xác thực nhân viên (STAFF_API_KEYS), nên khu vực " +
              "nhân viên đang đóng. Liên hệ người quản trị hệ thống."
          );
          return;
        }

        if (response.status === 404) {
          renderBox("bad", "Không tìm thấy mã quà.");
          track("vipphone_gift_lookup_failed", { reason: "NOT_FOUND" });
          return;
        }

        renderBox("bad", "Không tra cứu được mã quà. Vui lòng thử lại.");
      })
      .catch(function () {
        renderBox("bad", "Không kết nối được máy chủ. Vui lòng kiểm tra mạng.");
      });
  }

  /* -------------------------------------------------------- xác nhận phát */

  function confirmRedeem(giftCode, button) {
    var key = readStaffKey();
    var headers = { "Content-Type": "application/json" };
    if (key) headers["X-Staff-Key"] = key;

    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.textContent = "ĐANG GHI…";

    fetch(apiBase() + "/api/gifts/" + encodeURIComponent(giftCode) + "/redeem", {
      method: "POST",
      headers: headers,
      body: JSON.stringify({})
    })
      .then(function (response) {
        if (response.status === 200) {
          return response.json().then(function (body) {
            var already = body.already_redeemed === true;
            track("vipphone_gift_redeemed", {
              gift_code: util.normalizeGiftCode(giftCode),
              gift_status: "REDEEMED",
              already_redeemed: already
            });
            renderBox(
              "ok",
              already
                ? "Mã này đã được xác nhận phát quà trước đó. Không ghi thêm lần nữa."
                : "Đã xác nhận phát quà thành công."
            );
          });
        }

        if (response.status === 404 || response.status === 405 || response.status === 501) {
          renderBox(
            "warn",
            "Chức năng xác nhận phát quà chưa khả dụng trên máy chủ này. " +
              "Vui lòng ghi nhận thủ công và báo lại quản trị."
          );
          button.disabled = false;
          button.textContent = "XÁC NHẬN ĐÃ PHÁT QUÀ";
          return;
        }

        if (response.status === 401 || response.status === 503) {
          renderBox("bad", "Phiên nhân viên không hợp lệ. Nhập lại khoá rồi thử lại.");
          return;
        }

        renderBox("bad", "Không xác nhận được. Vui lòng thử lại.");
      })
      .catch(function () {
        renderBox("bad", "Không kết nối được máy chủ. Vui lòng kiểm tra mạng.");
        button.disabled = false;
        button.textContent = "XÁC NHẬN ĐÃ PHÁT QUÀ";
      });
  }

  /* ------------------------------------------------------------ khởi động */

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    lookup(codeInput.value);
  });

  initScanner();

  if (keyInput) {
    try {
      var storedKey = sessionStorage.getItem(STAFF_KEY_STORAGE);
      if (storedKey) keyInput.value = storedKey;
    } catch (err) {
      /* chế độ riêng tư */
    }
  }

  var initialCode = new URLSearchParams(window.location.search).get("code");
  if (initialCode) {
    codeInput.value = util.normalizeGiftCode(initialCode);
    lookup(initialCode);
  } else if (keyInput && !keyInput.value) {
    keyInput.focus();
  } else {
    codeInput.focus();
  }
})();
