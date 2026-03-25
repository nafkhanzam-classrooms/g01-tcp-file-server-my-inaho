# `client.py` TCP File Server Client

## Gambaran Umum

Client ini terhubung ke salah satu dari empat server TCP yang tersedia. Ia menggunakan `select()` untuk memantau dua sumber input secara bersamaan **keyboard pengguna** dan **socket server** tanpa menggunakan background thread, sehingga tidak ada race condition saat membaca respons server.

**Port default:** `9000`  
**Direktori download:** `downloads/`

**Cara menjalankan:**

```bash
python client.py <host> <port>
# Contoh:
python client.py 127.0.0.1 9003
```

---

## Konstanta & Inisialisasi

```python
HOST = '127.0.0.1'
PORT = 9000
DOWNLOAD_DIR = 'downloads'

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
```

| Konstanta      | Nilai        | Keterangan                                 |
| -------------- | ------------ | ------------------------------------------ |
| `HOST`         | `127.0.0.1`  | Alamat server default (localhost)          |
| `PORT`         | `9000`       | Port server default                        |
| `DOWNLOAD_DIR` | `downloads/` | Folder tempat file hasil download disimpan |

`os.makedirs(..., exist_ok=True)` membuat folder `downloads/` otomatis saat program pertama kali dijalankan. Jika folder sudah ada, tidak error.

---

## Fungsi-Fungsi

### `recv_line(sock)`

```python
def recv_line(sock: socket.socket) -> bytes:
```

**Tujuan:** Membaca data dari socket **satu byte sekaligus** sampai ditemukan karakter newline (`\n`).

**Mengapa byte per byte?**
TCP adalah _stream protocol_ tidak ada batas antar "pesan". Kalau menggunakan `recv(4096)`, bisa saja satu panggilan membaca dua perintah sekaligus, atau perintah terpotong di tengah. Dengan membaca satu byte per satu, kita bisa berhenti tepat di `\n`.

**Alur:**

```
baca 1 byte
  ├── kosong (koneksi putus) → raise ConnectionError
  ├── '\n'                   → berhenti, return buffer
  └── karakter lain          → tambah ke buffer, ulangi
```

**Return:** `bytes` isi baris tanpa karakter `\n` di akhir (sudah di-`.strip()`).

---

### `recv_exact(sock, n)`

```python
def recv_exact(sock: socket.socket, n: int) -> bytes:
```

**Tujuan:** Membaca **tepat `n` byte** dari socket, tidak lebih tidak kurang.

**Mengapa perlu fungsi ini?**
`sock.recv(n)` tidak menjamin mengembalikan tepat `n` byte ia hanya mengembalikan _hingga_ `n` byte, tergantung buffer OS dan kondisi jaringan. Fungsi ini terus memanggil `recv()` sampai total byte yang terkumpul mencapai `n`.

```python
chunk = sock.recv(min(4096, n - len(buf)))
```

`min(4096, n - len(buf))` memastikan kita tidak membaca _melebihi_ sisa yang dibutuhkan.

> **Catatan:** Fungsi ini dideklarasikan tapi tidak dipakai langsung di versi final semua penerimaan file sudah ditangani di dalam `cmd_upload` dan `cmd_download`.

---

### `cmd_list(sock)`

```python
def cmd_list(sock: socket.socket):
```

**Tujuan:** Meminta dan menampilkan daftar file yang ada di server.

**Alur komunikasi:**

```
Client                  Server
  │── "/list\n" ──────▶│
  │◀── "Files on...\n" ─│
```

**Detail implementasi:**

1. Kirim string `/list\n` ke server.
2. Set timeout 3 detik agar tidak menunggu selamanya jika server lambat.
3. Kumpulkan respons sampai buffer diakhiri `\n`.
4. Cetak ke terminal.

Timeout menggunakan `sock.settimeout(3.0)` dan dikembalikan ke `None` di blok `finally` agar tidak mempengaruhi operasi berikutnya.

---

### `cmd_upload(sock, filepath)`

```python
def cmd_upload(sock: socket.socket, filepath: str):
```

**Tujuan:** Mengupload file lokal ke server.

**Alur komunikasi (5 langkah):**

```
Client                          Server
  │── "/upload nama.txt\n" ───▶│
  │◀── "READY\n" ──────────────│  ← tunggu ini dulu
  │── "1024\n" (ukuran) ──────▶│
  │── [isi file bytes...] ─────▶│
  │◀── "File '...' uploaded\n" ─│
```

**Detail tiap langkah:**

**Langkah 1 Validasi file lokal:**

```python
if not os.path.isfile(filepath):
    print(f"[!] File not found: {filepath}")
    return
```

Cek dulu apakah file benar-benar ada sebelum mengirim perintah apapun ke server.

**Langkah 2 Tunggu `READY`:**

```python
sock.settimeout(5.0)
ready = recv_line(sock)
```

Server perlu persiapan sebelum menerima data. Client harus menunggu konfirmasi `READY` dulu. Jika timeout 5 detik, operasi dibatalkan.

**Langkah 3 Kirim ukuran file:**

```python
sock.sendall(f"{file_size}\n".encode())
```

Server perlu tahu berapa byte yang akan diterima agar bisa tahu kapan file selesai diterima.

**Langkah 4 Kirim isi file dalam chunk:**

```python
chunk = f.read(4096)
sock.sendall(chunk)
```

File dikirim 4096 byte sekaligus (bukan sekaligus semua) untuk menghindari penggunaan memori berlebihan pada file besar. Progress ditampilkan di terminal dengan `\r` (overwrite baris yang sama).

**Langkah 5 Baca konfirmasi:**
Setelah semua byte terkirim, server mengirim pesan konfirmasi yang dicetak ke terminal.

---

### `cmd_download(sock, filename)`

```python
def cmd_download(sock: socket.socket, filename: str):
```

**Tujuan:** Mendownload file dari server ke folder `downloads/`.

**Alur komunikasi (4 langkah):**

```
Client                          Server
  │── "/download nama.txt\n" ─▶│
  │◀── "SIZE 1024\n" ───────────│  ← atau "ERROR: ...\n"
  │── "ACK\n" ────────────────▶│
  │◀── [isi file bytes...] ─────│
```

**Detail penting:**

**Membaca respons SIZE vs ERROR:**

```python
if response_str.startswith("ERROR"):
    print(f"[!] {response_str}")
    return
if not response_str.startswith("SIZE "):
    ...
file_size = int(response_str[5:])  # ambil angka setelah "SIZE "
```

**Kenapa ada ACK?**
Handshake sederhana untuk memastikan client sudah siap menerima sebelum server mulai mengirim data biner. Tanpa ACK, server bisa saja mulai kirim data sementara client belum membuka file untuk ditulis.

**Menerima file:**

```python
while received < file_size:
    chunk = sock.recv(min(4096, file_size - received))
```

`min(4096, file_size - received)` memastikan kita tidak membaca _lebih dari sisa_ yang diharapkan penting agar byte dari perintah berikutnya tidak ikut terbaca sebagai isi file.

---

### `print_help()`

```python
def print_help():
```

**Tujuan:** Mencetak daftar perintah yang tersedia ke terminal. Dipanggil saat program pertama kali berjalan dan saat pengguna mengetik `/help`.

---

### `main()`

```python
def main():
```

**Tujuan:** Fungsi utama setup koneksi dan menjalankan event loop.

**Alur:**

**1. Parse argumen CLI:**

```python
if len(sys.argv) >= 2: host = sys.argv[1]
if len(sys.argv) >= 3: port = int(sys.argv[2])
```

Memungkinkan koneksi ke server manapun tanpa edit kode.

**2. Buat koneksi TCP:**

```python
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((host, port))
```

**3. Set non-blocking:**

```python
sock.setblocking(False)
```

Ini krusial agar `select()` bisa bekerja. Dalam mode non-blocking, `sock.recv()` tidak akan menunggu ia langsung return atau raise `BlockingIOError` jika tidak ada data.

**4. Event loop dengan `select()`:**

```python
readable, _, _ = select.select([sock, sys.stdin], [], [], 0.5)
```

`select()` menerima dua list di sini:

- `sock` socket ke server
- `sys.stdin` keyboard pengguna

OS memantau keduanya. Jika ada data masuk dari server (broadcast, dll), `sock` masuk ke `readable`. Jika pengguna mengetik sesuatu, `sys.stdin` masuk ke `readable`. Timeout `0.5` detik agar loop tidak hang selamanya.

**5. Handle data dari server (broadcast):**

```python
if source is sock:
    data = sock.recv(4096)
    for line in data.split(b"\n"):
        print(f"\r[Server] {line.decode()}")
```

Pesan broadcast dari client lain dicetak langsung.

**6. Handle input keyboard:**

```python
elif source is sys.stdin:
    command = sys.stdin.readline().strip()
    sock.setblocking(True)   # ← penting!
    try:
        if cmd == '/list': cmd_list(sock)
        elif cmd == '/upload': cmd_upload(sock, ...)
        elif cmd == '/download': cmd_download(sock, ...)
        else: sock.sendall(...)
    finally:
        sock.setblocking(False)  # ← kembalikan
```

**Mengapa `setblocking(True)` sebelum perintah file?**
Fungsi seperti `recv_line()` menggunakan loop `recv(1)` yang mengasumsikan socket dalam mode _blocking_ (menunggu sampai data ada). Kalau socket masih non-blocking, `recv(1)` akan raise `BlockingIOError` bahkan ketika data sedang dalam perjalanan. Jadi kita switch ke blocking saat operasi file, lalu switch balik ke non-blocking setelah selesai (di `finally` agar selalu dijalankan meski terjadi error).
