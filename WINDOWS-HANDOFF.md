# Phantom Browser — Windows hand-off

## Cài lần đầu

1. Giải nén toàn bộ bundle vào một thư mục cố định. Không chạy file `.exe` trực tiếp trong ZIP. Giữ `WebView2Loader.dll` nằm cạnh `phantom-browser.exe`.
2. Cài Python 3.11+ từ python.org và bật **Add Python to PATH**.
3. Mở PowerShell tại thư mục vừa giải nén, chạy:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\windows-setup.ps1
   ```

4. Sửa `.env`, điền proxy thật nếu cần.
5. Khởi tạo database:

   ```powershell
   .\.venv\Scripts\python.exe -m phantom.cli init
   ```

6. Chạy `phantom-browser.exe`.

## Smoke test Phase 2

- Tạo một profile trong GUI.
- Bấm Launch; Camoufox phải mở và status chuyển sang `running`.
- Mở một trang kiểm tra IP, xác nhận exit IP là proxy.
- Đăng nhập một tài khoản test, đóng bằng nút Stop.
- Launch lại cùng profile, xác nhận session/cookie còn nguyên.
- Xác nhận Stop không để lại Firefox/Camoufox process trong Task Manager.

Nếu Windows báo thiếu `WebView2Loader.dll`, bundle chưa được giải nén đủ hoặc file DLL đã bị antivirus cách ly. Kiểm tra DLL nằm ngay cạnh file EXE.

Nếu app không tìm thấy sidecar, kiểm tra `phantom-browser.exe`, `.venv`, `src`,
`pyproject.toml` có nằm cùng một thư mục hay không. Có thể override đường dẫn bằng
biến môi trường `PHANTOM_REPO`.