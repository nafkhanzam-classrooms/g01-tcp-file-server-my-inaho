# Dokumentasi Server Python — Berbagai Model Konkurensi

Keempat file ini mengimplementasikan **server TCP** dengan fungsionalitas yang sama (list, upload, download, broadcast pesan), namun menggunakan **model konkurensi yang berbeda-beda**. Semua server berbagi protokol pesan yang identik berbasis `struct` + JSON.

---

## Protokol Pesan (Shared Across All Servers)

Semua server menggunakan fungsi helper yang sama untuk komunikasi:

| Fungsi                 | Deskripsi                                                                  |
| ---------------------- | -------------------------------------------------------------------------- |
| `send_msg(sock, data)` | Kirim raw bytes dengan header 4-byte (big-endian) yang berisi panjang data |
| `recv_exact(sock, n)`  | Baca tepat `n` byte dari socket, loop hingga terpenuhi                     |
| `recv_msg(sock)`       | Baca header 4-byte lalu baca payload sesuai panjang                        |
| `send_json(sock, obj)` | Serialisasi dict ke JSON lalu kirim via `send_msg`                         |
| `recv_json(sock)`      | Terima pesan via `recv_msg` lalu parse sebagai JSON                        |

---

## 1. `server_sync.py` — Synchronous / Single-Client Server

> **Port:** `5001` | **Model:** Satu klien pada satu waktu (blocking)

### Deskripsi Umum

Server paling sederhana. Menerima satu koneksi, melayaninya hingga selesai, baru menerima koneksi berikutnya. **Tidak bisa menangani banyak klien secara bersamaan.**

---

### Fungsi-Fungsi

#### `handle_client(client_sock, client_addr)`

Menangani satu klien secara penuh dalam satu loop.

```
while True:
    msg = recv_json(client_sock)
    → dispatch berdasarkan msg["type"]
```

| Tipe Pesan   | Aksi                                                                     |
| ------------ | ------------------------------------------------------------------------ |
| `"list"`     | Kirim daftar file di `server_files/`                                     |
| `"upload"`   | Terima nama file, terima binary data, simpan ke disk                     |
| `"download"` | Baca file dari disk, kirim metadata JSON + binary data                   |
| `"message"`  | Print pesan, echo balik ke pengirim saja (tidak broadcast ke klien lain) |

> ⚠️ Karena single-client, pesan `"message"` hanya di-echo balik, bukan di-broadcast.

---

#### `main()`

Entry point server.

1. Buat direktori `server_files/` bila belum ada
2. Buat socket TCP, bind ke `127.0.0.1:5001`
3. Loop `accept()` → panggil `handle_client()` → tunggu selesai → `accept()` lagi

```python
while True:
    client_sock, client_addr = server.accept()
    handle_client(client_sock, client_addr)  # blocking!
```

---

### Kelebihan & Kekurangan

| Kelebihan                | Kekurangan                 |
| ------------------------ | -------------------------- |
| Kode paling sederhana    | Hanya 1 klien sekaligus    |
| Tidak ada race condition | Klien lain harus antri     |
| Mudah di-debug           | Tidak cocok untuk produksi |

---

## 2. `server_select.py` — I/O Multiplexing dengan `select()`

> **Port:** `5002` | **Model:** Banyak klien, satu thread, `select()` I/O multiplexing

### Deskripsi Umum

Menggunakan `select.select()` untuk memonitor banyak socket sekaligus dalam **satu thread**. Ketika ada socket yang siap dibaca, server memprosesnya satu per satu.

---

### Variabel Global

| Variabel        | Tipe   | Fungsi                                       |
| --------------- | ------ | -------------------------------------------- |
| `clients`       | `dict` | Memetakan `socket → {"addr": ...}`           |
| `input_sockets` | `list` | Daftar semua socket yang dipantau `select()` |

---

### Fungsi-Fungsi

#### `broadcast(sender_sock, message)`

Kirim pesan ke semua klien **kecuali pengirim**.

- Iterasi semua socket di `clients`
- Jika pengiriman gagal, tandai socket untuk dihapus
- Setelah iterasi, hapus socket yang gagal via `remove_client()`

#### `remove_client(sock, input_sockets)`

Bersihkan klien yang disconnect.

1. Hapus dari dict `clients`
2. Hapus dari list `input_sockets`
3. Tutup socket

#### `handle_client_data(sock, input_sockets)`

Proses satu pesan dari satu klien. Dipanggil ketika `select()` melaporkan socket siap baca.

| Tipe Pesan   | Aksi                          |
| ------------ | ----------------------------- |
| `"list"`     | Kirim daftar file             |
| `"upload"`   | Terima dan simpan file        |
| `"download"` | Kirim file ke klien           |
| `"message"`  | Broadcast ke semua klien lain |

Return `False` jika koneksi terputus atau error.

#### `main()`

Loop utama server berbasis `select()`.

```python
input_sockets = [server_socket]

while True:
    read_ready, _, _ = select.select(input_sockets, [], [])
    for sock in read_ready:
        if sock == server_socket:
            # Terima koneksi baru
            client_sock, addr = server_socket.accept()
            input_sockets.append(client_sock)
            clients[client_sock] = {"addr": addr}
        else:
            # Proses data dari klien yang sudah ada
            if not handle_client_data(sock, input_sockets):
                remove_client(sock, input_sockets)
```

---

### Kelebihan & Kekurangan

| Kelebihan                   | Kekurangan                              |
| --------------------------- | --------------------------------------- |
| Multi-client dalam 1 thread | Satu klien lambat bisa memblokir loop   |
| Portabel (Windows & Unix)   | Batas 1024 file descriptor (FD_SETSIZE) |
| Overhead rendah             | Tidak cocok untuk ribuan klien          |

---

## 3. `server_poll.py` — I/O Multiplexing dengan `poll()`

> **Port:** `5003` | **Model:** Banyak klien, satu thread, `poll()` I/O multiplexing (Linux/Unix only)

### Deskripsi Umum

Mirip dengan `select`, tapi menggunakan `select.poll()` yang merupakan Linux/Unix API. Keunggulan utama: **tidak ada batas jumlah file descriptor** seperti `select()`.

---

### Variabel Global

| Variabel   | Tipe          | Fungsi                                        |
| ---------- | ------------- | --------------------------------------------- |
| `fd_map`   | `dict`        | Memetakan `fd (int) → socket object`          |
| `clients`  | `dict`        | Memetakan `socket → {"addr": ..., "fd": ...}` |
| `poll_obj` | `select.poll` | Objek poll untuk monitoring event             |

---

### Fungsi-Fungsi

#### `broadcast(sender_sock, message)`

Kirim pesan ke semua klien kecuali pengirim. Klien yang gagal dimasukkan ke list `to_remove` lalu dihapus.

#### `remove_client(sock)`

Bersihkan klien yang disconnect.

1. Unregister fd dari `poll_obj`
2. Hapus dari `fd_map`
3. Hapus dari `clients`
4. Tutup socket

#### `handle_client_data(sock)`

Identik dengan versi `select`, menangani tipe pesan: `list`, `upload`, `download`, `message`.

#### `main()`

Loop utama server berbasis `poll()`.

```python
poll_obj = select.poll()
poll_obj.register(server.fileno(), select.POLLIN)
fd_map[server.fileno()] = server

while True:
    events = poll_obj.poll()
    for fd, event in events:
        sock = fd_map.get(fd)
        if sock is server:
            # Terima koneksi baru, register fd baru ke poll
        elif event & select.POLLIN:
            # Proses data klien
        if event & (select.POLLHUP | select.POLLERR | select.POLLNVAL):
            # Tangani error/disconnect
```

> `POLLHUP` = koneksi ditutup, `POLLERR` = error, `POLLNVAL` = fd tidak valid

---

### Perbedaan `select` vs `poll`

| Aspek    | `select`                 | `poll`                    |
| -------- | ------------------------ | ------------------------- |
| Platform | Windows + Unix           | Linux/Unix only           |
| Batas FD | ~1024                    | Tidak terbatas            |
| Input    | 3 set (read/write/error) | 1 list dengan event flags |
| Performa | Menurun saat banyak FD   | Lebih konstan             |

---

## 4. `server_thread.py` — Multi-threading Server

> **Port:** `5004` | **Model:** Setiap klien mendapat thread sendiri

### Deskripsi Umum

Setiap klien yang terkoneksi dijalankan di **thread terpisah**. Menggunakan `threading.Lock` untuk melindungi akses ke data kondisi dan socket bersama.

---

### Variabel Global

| Variabel       | Tipe             | Fungsi                                              |
| -------------- | ---------------- | --------------------------------------------------- |
| `clients`      | `dict`           | Memetakan `socket → {"addr": ..., "lock": Lock}`    |
| `clients_lock` | `threading.Lock` | Proteksi akses ke dict `clients` dari banyak thread |

---

### Fungsi-Fungsi

#### `broadcast(sender_sock, message)`

Kirim pesan ke semua klien kecuali pengirim secara thread-safe.

```python
with clients_lock:
    targets = [(sock, info) for sock, info in clients.items()
               if sock != sender_sock]
for sock, info in targets:
    with info["lock"]:  # Lock per-klien untuk kirim data
        send_json(sock, message)
```

> Dua level locking: `clients_lock` untuk membaca dict, `info["lock"]` untuk menulis ke socket.

#### `remove_client(sock)`

Hapus klien dari dict `clients` secara thread-safe dengan `clients_lock`, lalu tutup socket.

---

### Kelas `ClientThread(threading.Thread)`

Setiap klien dijalankan dalam instance kelas ini.

#### `__init__(self, client_sock, client_addr)`

Inisialisasi thread dengan socket dan alamat klien. `daemon=True` agar thread otomatis mati saat program utama berhenti.

#### `run(self)`

Method utama yang dijalankan saat thread dimulai.

1. Daftarkan klien ke dict `clients` dengan lock-nya sendiri
2. Loop `recv_json()` → dispatch pesan
3. Tangani tipe pesan: `list`, `upload`, `download`, `message`
4. Di `finally`: panggil `remove_client()`

Setiap operasi kirim (`send_json`, `send_msg`) dibungkus `with clients[self.sock]["lock"]` untuk mencegah dua thread menulis ke socket yang sama secara bersamaan.

---

### Kelas `Server`

Kelas wrapper untuk manajemen server.

#### `__init__(self)`

Inisialisasi atribut `host`, `port`, `server`, dan list `threads`.

#### `open_socket(self)`

Buat socket TCP, set `SO_REUSEADDR`, bind, dan listen.

#### `run(self)`

Loop utama: `accept()` → buat `ClientThread` → `start()`.

```python
while True:
    client_sock, client_addr = self.server.accept()
    t = ClientThread(client_sock, client_addr)
    t.start()
    self.threads.append(t)
```

Saat `KeyboardInterrupt`, tutup server socket dan `join()` semua thread.

---

### Kelebihan & Kekurangan

| Kelebihan                    | Kekurangan                          |
| ---------------------------- | ----------------------------------- |
| Truly concurrent             | Overhead pembuatan thread           |
| Klien saling tidak memblokir | Potensi race condition (butuh lock) |
| Mudah dipahami alurnya       | Tidak scalable untuk ribuan klien   |
| Cocok untuk I/O-bound tasks  | Memory usage lebih tinggi           |

---

## Perbandingan Keempat Server

| Aspek                 | `server_sync`     | `server_select`  | `server_poll`    | `server_thread` |
| --------------------- | ----------------- | ---------------- | ---------------- | --------------- |
| **Port**              | 5001              | 5002             | 5003             | 5004            |
| **Model**             | Synchronous       | I/O Multiplexing | I/O Multiplexing | Multi-threading |
| **API Utama**         | —                 | `select()`       | `poll()`         | `threading`     |
| **Klien bersamaan**   | 1                 | Banyak           | Banyak           | Banyak          |
| **Jumlah Thread**     | 1                 | 1                | 1                | N (per klien)   |
| **Broadcast**         | Tidak (echo saja) | Ya               | Ya               | Ya              |
| **Platform**          | Semua             | Semua            | Linux/Unix       | Semua           |
| **Kompleksitas kode** | Rendah            | Sedang           | Sedang           | Tinggi          |
| **Thread-safety**     | N/A               | N/A              | N/A              | Lock diperlukan |

---

## Alur Pesan (Message Flow)

```
Client                          Server
  |                               |
  |-- {"type": "list"} ---------->| --> os.listdir()
  |<- {"type": "list_response"} --|
  |                               |
  |-- {"type": "upload",          |
  |    "filename": "x.txt"} ----->|
  |-- [binary file data] -------->| --> simpan ke disk
  |<- {"type": "upload_ack"} -----|
  |                               |
  |-- {"type": "download",        |
  |    "filename": "x.txt"} ----->| --> baca dari disk
  |<- {"type": "download_response"}
  |<- [binary file data] ---------|
  |                               |
  |-- {"type": "message",         |
  |    "content": "halo"} ------->| --> broadcast ke klien lain
```
