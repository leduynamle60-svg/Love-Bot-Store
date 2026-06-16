# 💖 Love Bot Store — Hướng dẫn cài đặt

## 📁 Cấu trúc thư mục

```
love-bot-store/
├── bot.py                  ← Chạy file này để khởi động bot
├── config.py               ← ⚙️ ĐIỀN THÔNG TIN VÀO ĐÂY TRƯỚC
├── database.py             ← Tự động tạo store.db khi chạy
├── webhook_server.py       ← Nhận webhook SePay (tự khởi động)
├── requirements.txt
├── cogs/
│   ├── ticket.py           ← Hệ thống ticket
│   ├── order.py            ← Lệnh !order !qr !done
│   └── admin.py            ← Lệnh Founder
└── price_lists/
    ├── price_nicho.py      ← Script post catalogue Nicho
    ├── price_netflix.py    ← Script post catalogue Netflix
    ├── price_spotify.py    ← Script post catalogue Spotify
    └── price_decor.py      ← Script post catalogue Decor
```

---

## 🚀 Cài đặt lần đầu

### Bước 1 — Cài thư viện
```bash
pip install -r requirements.txt
```

### Bước 2 — Tạo Bot Discord
1. Vào https://discord.com/developers/applications
2. **New Application** → đặt tên **Love Bot Store**
3. Vào tab **Bot** → **Reset Token** → copy token
4. Bật các **Privileged Gateway Intents**:
   - ✅ Server Members Intent
   - ✅ Message Content Intent
5. Vào **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Permissions: `Administrator` (hoặc chọn từng quyền)
6. Mời bot vào server bằng URL vừa tạo

### Bước 3 — Điền config.py
Mở `config.py` và điền:
- `BOT_TOKEN` — Token bot vừa copy
- `GUILD_ID` — Chuột phải server → Copy Server ID
- `FOUNDER_ROLE_ID`, `SUPPORT_ROLE_ID` — Chuột phải role → Copy Role ID
- Các `CHANNEL_ID` tương ứng
- Thông tin ngân hàng SePay

> 💡 Để lấy ID: Vào Discord Settings → Advanced → bật **Developer Mode**
> Sau đó chuột phải vào bất kỳ thứ gì để thấy nút Copy ID

### Bước 4 — Cài đặt SePay
1. Đăng ký tại https://sepay.vn (gói miễn phí)
2. Liên kết tài khoản ngân hàng
3. Vào **Webhook** → điền URL: `http://YOUR_SERVER_IP:5000/webhook/sepay`
4. Copy **Webhook Secret** → dán vào `SEPAY_WEBHOOK_SECRET` trong config
5. Điền `BANK_BIN` theo ngân hàng:

| Ngân hàng | BIN    |
|-----------|--------|
| Vietcombank | 970436 |
| MB Bank     | 970422 |
| Techcombank | 970407 |
| BIDV        | 970418 |
| VPBank      | 970432 |
| Agribank    | 970405 |

### Bước 5 — Chạy bot
```bash
python bot.py
```

---

## 🛠️ Thiết lập kênh shop

### Gửi embed mở ticket
Trong Discord, dùng lệnh (với tài khoản có role Founder):
```
!setup_ticket #kênh-mua-hàng
```

### Post catalogue sản phẩm
1. Mở file `price_lists/price_nicho.py`
2. Điền `CHANNEL_ID` (ID kênh muốn gửi)
3. Điền thông tin sản phẩm vào `PRODUCTS`
4. Chạy: `python price_lists/price_nicho.py`

Làm tương tự với netflix, spotify, decor.

---

## 📋 Danh sách lệnh

### Trong Ticket (Support/Founder)
| Lệnh | Mô tả |
|------|-------|
| `!order <tên SP>` | Ghi đơn → gửi format vào #order |
| `!qr <số tiền>` | Tạo QR VietQR thanh toán tự động |
| `!done` | Hoàn tất → gửi form feedback cho khách |

### Founder
| Lệnh | Mô tả |
|------|-------|
| `!setup_ticket [#kênh]` | Gửi embed mở ticket |
| `!stats` | Thống kê đơn hàng & doanh thu |
| `!lookup <mã đơn>` | Tra cứu đơn hàng |
| `!help` | Xem tất cả lệnh |

---

## 🔄 Flow hoạt động

```
Khách vào kênh shop → xem catalogue → bấm [🛒 Mua hàng]
         ↓
Bot tạo kênh ticket + ping Support
         ↓
Support dùng !order <tên SP> → ghi đơn vào #order
         ↓
Support dùng !qr <số tiền> → bot gửi QR thanh toán
         ↓
Khách quét QR → chuyển khoản
         ↓
SePay webhook → bot tự xác nhận → ping Support
         ↓
Support giao hàng qua DM → dùng !done
         ↓
Khách chọn sao (1-5⭐) + viết feedback → gửi vào #feedback
         ↓
Bot gửi nút đóng ticket cho Support → Support đóng
```

---

## ❓ Lưu ý
- Webhook SePay cần server có IP public (hoặc dùng ngrok để test local)
- Test ngrok: `ngrok http 5000` → lấy URL → dán vào SePay webhook
- File `store.db` tự tạo khi chạy bot lần đầu, đừng xóa!