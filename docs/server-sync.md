# `server-sync.py` Synchronous TCP File Server

## Gambaran Umum

Server paling sederhana dari keempat implementasi. Menggunakan pendekatan **synchronous/blocking** server hanya melayani **satu client sekaligus**. Selama client pertama belum selesai (disconnect), client kedua tidak akan pernah diproses meski sudah terhubung ke jaringan.

**Port:** `9000`  
**Direktori file:** `server_files/`  
**Model konkurensi:** Tidak ada single client, blocking penuh

**Cara menjalankan:**

```bash
python server-sync.py
```

---

## Konstanta & Inisialisasi

```python
HOST = '0.0.0.0'
PORT = 9000
FILES_DIR = 'server_files'

os.makedirs(FILES_DIR, exist_ok=True)
```

| Konstanta          | Keterangan                                                |
| ------------------ | --------------------------------------------------------- |
| `HOST = '0.0.0.0'` | Listen di semua network interface (bukan hanya localhost) |
| `PORT = 9000`      | Port yang digunakan server                                |
| `FILES_DIR`        | Folder tempat file yang diupload disimpan                 |

`'0.0.0.0'` berarti server menerima koneksi dari mana saja baik dari localhost maupun dari komputer lain di jaringan yang sama. Berbeda dengan `'127.0.0.1'` yang hanya menerima dari lokal.

---

## Fungsi-Fungsi

### `broadcast(clients, message, sender=None)`

```python
def broadcast(clients, message, sender=None):
```

**Tujuan:** Mengirim pesan ke semua client yang sedang terhubung, **kecuali** pengirimnya sendiri.

**Parameter:**
| Parameter | Tipe | Keterangan |
|-----------|------|------------|
| `clients` | `list` | List semua socket client yang aktif |
| `message` | `bytes` | Pesan yang akan dikirim |
| `sender` | `socket` atau `None` | Socket pengirim asli, dilewati saat broadcast |

**Detail implementasi:**

```python
for client in clients:
    if client != sender:
        try:
            client.sendall(message)
        except Exception:
            pass
```

`try/except` dipakai karena ada kemungkinan client sudah disconnect saat broadcast berjalan. Daripada crash, error diabaikan dengan `pass` client yang bermasalah akan dideteksi dan dibersihkan pada iterasi loop utama berikutnya.

> **Limitasi di server-sync:** Karena server hanya bisa handle satu client sekaligus, `clients` selalu berisi maksimal satu elemen. Broadcast tidak pernah benar-benar "menyebar" ke lebih dari satu orang. Fungsi ini tetap ditulis generik agar konsisten dengan server lainnya.

---

### `handle_client(conn, addr, clients)`

```python
def handle_client(conn, addr, clients):
```

**Tujuan:** Menangani semua komunikasi dengan **satu client** dari awal hingga disconnect.

**Parameter:**
| Parameter | Tipe | Keterangan |
|-----------|------|------------|
| `conn` | `socket` | Socket koneksi client |
| `addr` | `tuple` | `(IP, port)` client |
| `clients` | `list` | Referensi ke list semua client aktif |

**Alur keseluruhan:**

```
kirim welcome message
loop:
  recv(4096)  ← BLOCKING, tunggu perintah
  parse perintah
  jalankan perintah
  ulangi
disconnect → hapus dari clients → tutup socket
```

**Penanganan tiap perintah:**

#### `/list`

```python
files = os.listdir(FILES_DIR)
response = "Files on server:\n" + "\n".join(files) + "\n"
conn.sendall(response.encode())
```

Baca isi direktori `server_files/`, gabungkan jadi string, kirim ke client.

#### `/upload <filename>`

Proses upload menggunakan **3 tahap berurutan**:

```
Tahap 1: Terima nama file dari perintah
         → kirim "READY\n"

Tahap 2: Baca ukuran file (satu byte per satu sampai '\n')
         size_data = b""
         while not size_data.endswith(b"\n"):
             chunk = conn.recv(1)

Tahap 3: Terima isi file sebanyak file_size byte
         while received < file_size:
             chunk = conn.recv(min(4096, file_size - received))
             f.write(chunk)
```

`os.path.basename(filename)` digunakan untuk mencegah **path traversal attack** kalau client mengirim `/upload ../../etc/passwd`, `basename` akan mengambil hanya `passwd`-nya saja, bukan path lengkapnya.

#### `/download <filename>`

```
Tahap 1: Cek apakah file ada di server_files/
         jika tidak → kirim "ERROR: ...\n"

Tahap 2: Kirim "SIZE <ukuran>\n"

Tahap 3: Tunggu "ACK\n" dari client

Tahap 4: Kirim isi file dalam chunk 4096 byte
```

Handshake ACK memastikan client sudah siap menerima sebelum data dikirim.

#### Pesan biasa (selain `/list`, `/upload`, `/download`)

```python
msg = f"[{addr}] {command}\n".encode()
broadcast(clients, msg, sender=conn)
```

Diperlakukan sebagai pesan chat dan di-broadcast ke semua client lain.

**Penanganan disconnect:**

```python
except Exception as e:
    print(f"[!] Error with {addr}: {e}")
    break
...
clients.remove(conn)
conn.close()
```

Jika terjadi error apapun (client force-close, koneksi putus, dll), loop dihentikan dan socket dibersihkan.

---

### `main()`

```python
def main():
```

**Tujuan:** Setup server socket dan menjalankan accept loop.

**Setup socket:**

```python
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind((HOST, PORT))
server.listen(5)
```

| Kode              | Keterangan                                       |
| ----------------- | ------------------------------------------------ |
| `AF_INET`         | Gunakan IPv4                                     |
| `SOCK_STREAM`     | Gunakan TCP (bukan UDP)                          |
| `SO_REUSEADDR, 1` | Izinkan reuse port segera setelah server restart |
| `listen(5)`       | Antrian koneksi masuk maksimal 5                 |

**`SO_REUSEADDR` mengapa penting?**
Tanpa opsi ini, jika server di-restart, OS masih "memegang" port tersebut selama beberapa menit (TIME_WAIT state). `SO_REUSEADDR` memungkinkan port langsung dipakai ulang tanpa menunggu.

**Accept loop:**

```python
clients = []

while True:
    conn, addr = server.accept()   # BLOCKING tunggu di sini
    clients.append(conn)
    handle_client(conn, addr, clients)   # handle langsung, bukan di thread
```

**Inilah inti "synchronous":**
`handle_client()` dipanggil langsung di main loop tanpa thread atau async. Artinya `server.accept()` tidak akan pernah dipanggil lagi sampai `handle_client()` selesai (client disconnect). Client kedua yang mencoba connect akan masuk ke antrian `listen(5)` dan menunggu.

```
accept() → handle_client() [lama] → accept() → handle_client() → ...
             ↑ client lain nunggu di sini
```

---

## Diagram Alur

```
server.accept() ──── (client A connect) ────▶ handle_client(A)
                                                   │
                                          (client B connect)
                                          masuk antrian listen(5)
                                          MENUNGGU...
                                                   │
                                          client A disconnect
                                                   │
server.accept() ◀──────────────────────────────────┘
      │
      └──▶ handle_client(B)
```

## Kelebihan & Kekurangan

| Kelebihan                        | Kekurangan                                     |
| -------------------------------- | ---------------------------------------------- |
| Kode paling mudah dibaca         | Hanya 1 client aktif sekaligus                 |
| Tidak ada masalah race condition | Client lain harus antri                        |
| Tidak butuh state machine        | Tidak cocok untuk produksi                     |
| Mudah di-debug                   | Jika client "diam", semua client lain tertahan |
