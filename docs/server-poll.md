# `server-poll.py` TCP File Server dengan `poll()`

## Gambaran Umum

Server ini secara konsep **identik dengan server-select**, namun menggunakan syscall `poll()` sebagai ganti `select()`. Perbedaan utama ada pada antarmuka pemantauan socket: `poll()` menggunakan **file descriptor (fd)** dan **event flag bitmask**, bukan set socket Python biasa.

**Port:** `9002`  
**Direktori file:** `server_files/`  
**Model konkurensi:** Single-threaded I/O multiplexing dengan `poll()` (Linux/macOS only)

**Cara menjalankan:**

```bash
python server-poll.py
```

> ⚠️ `select.poll()` tidak tersedia di Windows. Gunakan server-select.py jika di Windows.

---

## Perbedaan Utama: `poll()` vs `select()`

| Aspek               | `select()`           | `poll()`                       |
| ------------------- | -------------------- | ------------------------------ |
| Input               | 3 list socket Python | 1 list `(fd, events)`          |
| Output              | 3 list socket siap   | List `(fd, events)` yang aktif |
| Batas fd            | 1024 (di banyak OS)  | Tidak terbatas                 |
| Platform            | Cross-platform       | Linux/macOS only               |
| Identifikasi socket | Object socket Python | Integer file descriptor        |

Karena `poll()` bekerja dengan **file descriptor** (angka integer), perlu mapping tambahan:

```python
fd_to_sock = {}   # fd (int) → socket object
client_state = {} # fd (int) → dict state
```

---

## Konstanta & Variabel Global

```python
HOST = '0.0.0.0'
PORT = 9002
FILES_DIR = 'server_files'

fd_to_sock = {}    # mapping: file descriptor → socket object
client_state = {}  # mapping: file descriptor → state dict
```

**Mengapa pakai fd sebagai key, bukan socket object?**

`poll()` mengembalikan list `(fd, event)` hanya angka integer, bukan object Python. Kita perlu `fd_to_sock` untuk mengambil kembali socket object-nya agar bisa memanggil `sendall()`, `recv()`, dsb.

---

## Event Flag `poll()`

```python
POLL_IN_FLAGS  = select.POLLIN | select.POLLPRI
POLL_ERR_FLAGS = select.POLLERR | select.POLLHUP | select.POLLNVAL
```

| Flag       | Nilai                               | Keterangan                            |
| ---------- | ----------------------------------- | ------------------------------------- |
| `POLLIN`   | Data tersedia untuk dibaca          | Kondisi normal ada data masuk         |
| `POLLPRI`  | Data urgent/OOB tersedia            | Jarang dipakai, tapi aman diinclude   |
| `POLLERR`  | Terjadi error pada socket           | Error kondisi                         |
| `POLLHUP`  | Koneksi hang up (client disconnect) | Client menutup koneksi                |
| `POLLNVAL` | File descriptor tidak valid         | fd sudah ditutup tapi masih terdaftar |

`|` adalah operator bitwise OR menggabungkan beberapa flag menjadi satu nilai integer.

---

## Fungsi-Fungsi

### `get_addr(sock)`

```python
def get_addr(sock):
    try:
        return sock.getpeername()
    except Exception:
        return ('?', '?')
```

Sama dengan server-select mendapatkan alamat client dengan aman. Jika socket sudah closed, kembalikan `('?', '?')`.

---

### `broadcast(fd_to_sock, server_fd, sender_fd, message)`

```python
def broadcast(fd_to_sock, server_fd, sender_fd, message):
    for fd, sock in fd_to_sock.items():
        if fd != server_fd and fd != sender_fd:
            try:
                sock.sendall(message)
            except Exception:
                pass
```

**Tujuan:** Kirim pesan ke semua client kecuali server dan pengirim.

Berbeda dengan server-select yang menerima list socket, di sini parameternya adalah `fd_to_sock` (dictionary fd→socket) karena identifikasi dilakukan via fd integer. Logikanya sama persis.

---

### `process_command(fd, fd_to_sock, server_fd, raw)`

```python
def process_command(fd, fd_to_sock, server_fd, raw: bytes):
```

**Tujuan:** Memproses satu baris perintah lengkap dari client.

**Perbedaan dari server-select:** Menerima `fd` (integer) bukan socket langsung. Socket diambil dari mapping:

```python
sock = fd_to_sock[fd]
state = client_state[fd]
```

Logika penanganan perintah (`/list`, `/upload`, `/download`, broadcast) **identik** dengan `server-select.py`.

Perubahan state dilakukan melalui `client_state[fd].update(...)` menggunakan fd sebagai key.

---

### `handle_data(fd, fd_to_sock, server_fd)`

```python
def handle_data(fd, fd_to_sock, server_fd):
```

**Tujuan:** Dipanggil ketika `poll()` melaporkan ada data dari client. Membaca data, update buffer, lalu proses berdasarkan mode.

**Return:** `True` jika masih terhubung, `False` jika disconnect.

**Perbedaan dari server-select:**

- Menerima `fd` (int) bukan `sock` (socket)
- State diakses via `client_state[fd]`
- Socket diambil via `fd_to_sock[fd]`

Logika state machine (mode `command` → `upload_size` → `upload_data` → `download_ack`) **identik** dengan server-select.

**Detail kecil yang berbeda inisialisasi file saat upload:**

```python
# server-poll.py
open(filepath, 'wb').close()  # bersihkan file lama
state.update({'mode': 'upload_data', ...})
```

Server poll secara eksplisit membuat/mengosongkan file terlebih dahulu sebelum mulai menulis, agar tidak ada sisa data dari upload sebelumnya.

---

### `remove_client(fd, poller, fd_to_sock)`

```python
def remove_client(fd, poller, fd_to_sock):
```

**Tujuan:** Membersihkan semua resource milik client yang disconnect atau error.

```python
def remove_client(fd, poller, fd_to_sock):
    addr = get_addr(fd_to_sock[fd])
    print(f"[-] Disconnected: {addr}")
    poller.unregister(fd)    # ← hapus dari pantauan poll
    fd_to_sock[fd].close()   # ← tutup socket
    del fd_to_sock[fd]       # ← hapus dari mapping
    del client_state[fd]     # ← hapus state
```

Fungsi ini **tidak ada** di server-select (cleanup dilakukan inline di `main()`). Di server-poll, karena cleanup perlu dilakukan dari dua tempat (`POLL_ERR_FLAGS` dan setelah `handle_data` return `False`), lebih rapi dibuat fungsi tersendiri.

`poller.unregister(fd)` wajib dipanggil jika fd tidak di-unregister, `poll()` akan terus melaporkan event untuk fd yang sudah closed, menyebabkan error.

---

### `main()`

```python
def main():
```

**Tujuan:** Setup server dan menjalankan event loop berbasis `poll()`.

**Setup poller:**

```python
poller = select.poll()
poller.register(server_fd, select.POLLIN)
fd_to_sock[server_fd] = server
```

`server.fileno()` mengembalikan file descriptor integer dari server socket. Poller di-register dengan fd ini, bukan dengan object socket-nya langsung.

**Event loop:**

```python
while True:
    events = poller.poll(1000)  # timeout 1000ms = 1 detik

    for fd, event in events:
        if fd == server_fd:
            # ada client baru
            conn, addr = server.accept()
            cfd = conn.fileno()
            poller.register(cfd, POLL_IN_FLAGS)
            fd_to_sock[cfd] = conn
            client_state[cfd] = {'mode': 'command', 'buf': b''}

        elif event & POLL_ERR_FLAGS:
            # error pada client
            remove_client(fd, poller, fd_to_sock)

        elif event & POLL_IN_FLAGS:
            # ada data dari client
            alive = handle_data(fd, fd_to_sock, server_fd)
            if not alive:
                remove_client(fd, poller, fd_to_sock)
```

**Perbedaan pengecekan event vs select:**

`select()` mengembalikan "socket mana yang siap", sementara `poll()` mengembalikan "fd mana yang punya event apa". Maka pengecekan menggunakan **bitwise AND**:

```python
event & POLL_ERR_FLAGS   # apakah ada flag error yang aktif?
event & POLL_IN_FLAGS    # apakah ada flag data-masuk yang aktif?
```

Urutan pengecekan penting: error dicek lebih dulu (`elif event & POLL_ERR_FLAGS`) sebelum data (`elif event & POLL_IN_FLAGS`), karena socket yang error tidak boleh dibaca.

**Register client baru:**

```python
conn.setblocking(True)
cfd = conn.fileno()
poller.register(cfd, POLL_IN_FLAGS)
```

Socket baru diset blocking (`setblocking(True)`) karena `handle_data` menggunakan `recv()` yang blocking. Yang non-blocking hanya `poller.poll()` itu sendiri (dengan timeout).

---

## Diagram Alur `main()`

```
poller.poll(1000ms)
       │
       ├── fd == server_fd ──▶ accept() → register fd baru ke poller
       │
       ├── event & ERR_FLAGS ──▶ remove_client()
       │
       └── event & IN_FLAGS ──▶ handle_data()
                                     │
                                     ├── return False ──▶ remove_client()
                                     └── return True  ──▶ lanjut
```

---

## Kelebihan & Kekurangan

| Kelebihan                                                   | Kekurangan                                        |
| ----------------------------------------------------------- | ------------------------------------------------- |
| Tidak ada batas jumlah fd (tidak seperti select)            | Linux/macOS only                                  |
| Handle banyak client dalam satu thread                      | Kode lebih verbose karena harus mapping fd↔socket |
| Event-based, efisien                                        | Sama seperti select: state machine wajib          |
| `POLLHUP` dan `POLLNVAL` memberikan info error lebih detail | Lebih sulit di-debug dibanding threading          |
