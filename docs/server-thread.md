# `server-thread.py` TCP File Server dengan `threading`

## Gambaran Umum

Server ini menggunakan **satu thread per client**. Setiap client yang connect akan mendapatkan thread Python sendiri yang menjalankan fungsi `handle_client()`. Main thread hanya bertugas menerima koneksi baru (`accept()`) dan men-spawn thread.

Karena tiap client punya thread sendiri, tidak diperlukan state machine kode bisa ditulis secara **linear dan blocking** seperti server-sync, tapi berjalan paralel untuk banyak client.

**Port:** `9003`  
**Direktori file:** `server_files/`  
**Model konkurensi:** Multi-threading satu thread per client

**Cara menjalankan:**

```bash
python server-thread.py
```

---

## Konstanta & Variabel Global

```python
HOST = '0.0.0.0'
PORT = 9003
FILES_DIR = 'server_files'

clients_lock = threading.Lock()
clients = []
```

| Variabel       | Tipe   | Keterangan                                |
| -------------- | ------ | ----------------------------------------- |
| `clients`      | `list` | List semua socket client yang aktif       |
| `clients_lock` | `Lock` | Mutex untuk melindungi akses ke `clients` |

**Mengapa `clients` perlu Lock?**

Tanpa Lock, dua thread bisa memodifikasi `clients` bersamaan:

```
Thread A: for client in clients:   ← sedang iterasi
Thread B: clients.remove(conn)     ← modifikasi di tengah iterasi!
```

Ini menyebabkan `RuntimeError: list changed size during iteration`. `Lock` memastikan hanya satu thread yang boleh mengakses `clients` pada satu waktu.

---

## Fungsi-Fungsi

### `broadcast(message, sender=None)`

```python
def broadcast(message, sender=None):
    with clients_lock:
        for client in clients:
            if client is not sender:
                try:
                    client.sendall(message)
                except Exception:
                    pass
```

**Tujuan:** Mengirim pesan ke semua client yang aktif, kecuali pengirim.

**`with clients_lock:`** ini adalah **context manager** untuk Lock. Setara dengan:

```python
clients_lock.acquire()
try:
    # kode di dalam with
finally:
    clients_lock.release()
```

Lock dipegang selama iterasi berlangsung. Thread lain yang ingin broadcast atau modifikasi `clients` harus menunggu sampai lock dilepas.

**`try/except` per client:**
Jika satu client sudah disconnect, `sendall()` akan raise exception. `pass` mengabaikan error tersebut kita tidak berhenti broadcast hanya karena satu client bermasalah.

---

### `recv_line(conn)`

```python
def recv_line(conn) -> bytes:
    buf = b""
    while not buf.endswith(b"\n"):
        ch = conn.recv(1)
        if not ch:
            break
        buf += ch
    return buf.strip()
```

**Tujuan:** Membaca data dari socket satu byte per satu sampai menemukan `\n`.

**Mengapa ada di server-thread tapi tidak di server-sync?**

Server-sync menggunakan `conn.recv(4096)` untuk membaca perintah ini cukup karena client hanya mengirim satu perintah pendek per iterasi. Di server-thread, karena thread berjalan paralel dan bisa ada data dari berbagai sumber yang "bercampur", lebih aman menggunakan `recv_line` yang berhenti tepat di `\n`.

Perbedaan kecil dari `recv_line` di `client.py`: versi ini menggunakan `while not buf.endswith(b"\n")` (cek akhir buffer), sementara client.py cek `if ch == b"\n"` (cek karakter terbaru). Keduanya ekuivalen tapi idiom yang sedikit berbeda.

---

### `handle_client(conn, addr)`

```python
def handle_client(conn, addr):
```

**Tujuan:** Menangani semua interaksi dengan **satu client** dari awal hingga disconnect. Berjalan di thread tersendiri.

**Parameter:**
| Parameter | Tipe | Keterangan |
|-----------|------|------------|
| `conn` | `socket` | Socket koneksi client |
| `addr` | `tuple` | `(IP, port)` client |

> Perhatikan: tidak ada parameter `clients` di sini fungsi mengakses variabel global `clients` langsung (dengan proteksi `clients_lock`).

**Struktur `try/finally`:**

```python
try:
    while True:
        line = recv_line(conn)
        # ... proses perintah
except Exception as e:
    print(f"[!] Error with {addr}: {e}")
finally:
    print(f"[-] Disconnected: {addr}")
    with clients_lock:
        if conn in clients:
            clients.remove(conn)
    conn.close()
```

`finally` **selalu** dijalankan, baik client disconnect secara normal maupun karena error. Ini memastikan socket selalu ditutup dan client selalu dihapus dari list tidak ada resource leak.

**Penanganan tiap perintah:**

#### `/list`

```python
files = os.listdir(FILES_DIR)
response = ("Files on server:\n" + "\n".join(files) + "\n") if files else "No files on server.\n"
conn.sendall(response.encode())
```

Identik dengan server lainnya.

#### `/upload <filename>`

```python
conn.sendall(b"READY\n")

size_line = recv_line(conn)           # ← blocking, tunggu ukuran file
file_size = int(size_line.strip())

received = 0
with open(filepath, 'wb') as f:
    while received < file_size:
        chunk = conn.recv(min(4096, file_size - received))
        f.write(chunk)
        received += len(chunk)
```

Karena berjalan di thread sendiri, boleh **blocking** thread ini bisa menunggu data dari satu client tanpa mempengaruhi client lain yang di-handle thread berbeda.

Bandingkan dengan server-select/poll yang harus menyimpan state dan menunggu di `select()/poll()` di sini cukup `recv_line(conn)` dan tunggu.

#### `/download <filename>`

```python
conn.sendall(f"SIZE {file_size}\n".encode())

ack = recv_line(conn)           # ← tunggu ACK
if ack == b"ACK":
    with open(filepath, 'rb') as f:
        while True:
            chunk = f.read(4096)
            if not chunk: break
            conn.sendall(chunk)
```

Sama boleh blocking karena thread ini dedikasi untuk satu client.

#### Pesan biasa

```python
msg = f"[{addr}] {command}\n".encode()
broadcast(msg, sender=conn)
```

---

### `main()`

```python
def main():
```

**Tujuan:** Setup server dan spawn thread untuk setiap client baru.

**Accept loop:**

```python
while True:
    conn, addr = server.accept()
    with clients_lock:
        clients.append(conn)
    t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
    t.start()
```

**`daemon=True`** menjadikan thread sebagai _daemon thread_. Artinya: jika main thread berhenti (program dimatikan dengan Ctrl+C), semua daemon thread akan ikut dihentikan secara otomatis. Tanpa `daemon=True`, program tidak akan benar-benar exit selama masih ada thread yang berjalan.

**Urutan operasi saat client baru:**

1. `server.accept()` terima koneksi, dapatkan `conn` dan `addr`
2. `with clients_lock: clients.append(conn)` tambahkan ke list (dengan lock)
3. Buat thread baru dengan `target=handle_client`
4. `t.start()` mulai jalankan thread
5. Main loop langsung kembali ke `server.accept()` siap terima client berikutnya

---

## Diagram Konkurensi

```
Main Thread
───────────────────────────────────────────────────▶
accept() → spawn T1 → accept() → spawn T2 → accept() → ...

Thread T1 (Client A)         Thread T2 (Client B)
─────────────────────────    ─────────────────────────
recv_line() [tunggu]         recv_line() [tunggu]
  ← "/list"                    ← "/upload foto.jpg"
kirim daftar file            kirim READY
recv_line() [tunggu]         recv_line() [tunggu ukuran]
  ← "/download x.txt"          ← "20480"
kirim SIZE                   terima 20480 bytes...
tunggu ACK                   ...
kirim file                   ...selesai, kirim konfirmasi
...                          recv_line() [tunggu]
```

Semua thread berjalan **benar-benar paralel** (GIL Python masih ada, tapi untuk I/O-bound seperti `recv()` dan `sendall()`, GIL dilepas sementara).

---

## Kelebihan & Kekurangan

| Kelebihan                           | Kekurangan                                     |
| ----------------------------------- | ---------------------------------------------- |
| Kode paling mudah dibaca & dipahami | Setiap client = 1 thread (mahal di memori)     |
| Tidak perlu state machine           | 10.000 client = 10.000 thread (tidak scalable) |
| Setiap client truly isolated        | Perlu Lock untuk shared resource               |
| Blocking I/O aman digunakan         | Race condition mungkin jika lupa Lock          |
| Cocok untuk jumlah client sedang    | GIL Python membatasi paralelisme sejati        |

---

## Perbandingan Keempat Server

```
┌─────────────────┬────────┬──────────┬──────────────────────────┐
│ Server          │ Thread │ Blocking │ Keterangan               │
├─────────────────┼────────┼──────────┼──────────────────────────┤
│ server-sync     │ 1      │ Ya       │ 1 client sekaligus       │
│ server-select   │ 1      │ Tidak    │ Banyak client, state m.  │
│ server-poll     │ 1      │ Tidak    │ Sama select, fd-based    │
│ server-thread   │ N      │ Ya       │ 1 thread per client      │
└─────────────────┴────────┴──────────┴──────────────────────────┘
```
