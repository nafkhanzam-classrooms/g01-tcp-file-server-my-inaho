# `server-select.py` TCP File Server dengan `select()`

## Gambaran Umum

Server ini menggunakan `select()` untuk melayani **banyak client sekaligus** dengan hanya **satu thread**. Alih-alih menunggu satu client hingga selesai, server memantau semua socket sekaligus dan bereaksi hanya ketika ada data yang benar-benar tersedia.

Karena satu thread tidak bisa memblok menunggu satu client, setiap operasi multi-langkah (seperti upload) harus dipecah menjadi **state machine** per client.

**Port:** `9001`  
**Direktori file:** `server_files/`  
**Model konkurensi:** Single-threaded I/O multiplexing dengan `select()`

**Cara menjalankan:**

```bash
python server-select.py
```

---

## Konstanta & Variabel Global

```python
HOST = '0.0.0.0'
PORT = 9001
FILES_DIR = 'server_files'

client_state = {}  # conn (socket) -> dict state
```

**`client_state`** adalah dictionary yang menyimpan "posisi" tiap client dalam proses yang sedang berjalan:

```python
# Contoh isi client_state untuk satu client:
{
    <socket>: {
        'mode': 'upload_data',   # tahap saat ini
        'filename': 'foto.jpg',  # nama file
        'file_size': 204800,     # ukuran total
        'received': 81920,       # sudah diterima
        'filepath': 'server_files/foto.jpg',
        'buf': b''               # sisa data yang belum diproses
    }
}
```

Mode yang mungkin:
| Mode | Keterangan |
|------|------------|
| `'command'` | Menunggu perintah baru dari client |
| `'upload_size'` | Menunggu angka ukuran file setelah `/upload` |
| `'upload_data'` | Sedang menerima isi file |
| `'download_ack'` | Menunggu ACK dari client sebelum kirim file |

---

## Fungsi-Fungsi

### `broadcast(clients, message, sender_sock, server_sock)`

```python
def broadcast(clients, message, sender_sock, server_sock):
```

**Tujuan:** Kirim pesan ke semua client, kecuali pengirim dan server socket itu sendiri.

```python
for sock in clients:
    if sock is not server_sock and sock is not sender_sock:
        try:
            sock.sendall(message)
        except Exception:
            pass
```

`clients` di sini adalah `sockets_list` yang berisi **semua socket termasuk server socket** maka perlu eksplisit mengecualikan `server_sock`.

---

### `get_addr(sock)`

```python
def get_addr(sock):
    try:
        return sock.getpeername()
    except Exception:
        return ('?', '?')
```

**Tujuan:** Mendapatkan alamat `(IP, port)` dari sebuah socket dengan aman. Jika socket sudah disconnect dan `getpeername()` gagal, kembalikan `('?', '?')` daripada crash.

---

### `process_command(sock, clients, server_sock, raw)`

```python
def process_command(sock, clients, server_sock, raw: bytes):
```

**Tujuan:** Memproses **satu baris perintah lengkap** yang sudah diterima dari client.

**Parameter:**
| Parameter | Keterangan |
|-----------|------------|
| `sock` | Socket client pengirim perintah |
| `clients` | List semua socket aktif |
| `server_sock` | Socket server (untuk dikecualikan dari broadcast) |
| `raw` | Raw bytes satu baris perintah |

**Mengapa fungsi ini terpisah dari `handle_data`?**
`handle_data` menangani penerimaan data mentah dan mengelola buffer. Baru setelah satu baris lengkap terkumpul, `process_command` dipanggil untuk mengeksekusi logika bisnis. Pemisahan ini membuat kode lebih modular.

**Penanganan perintah:**

#### `/list`

Langsung kirim daftar file tidak ada state yang perlu diubah.

#### `/upload <filename>`

```python
sock.sendall(b"READY\n")
client_state[sock] = {
    'mode': 'upload_size',
    'filename': os.path.basename(filename),
    'buf': b''
}
```

Kirim `READY` ke client, lalu **ubah mode client ke `upload_size`**. Mulai saat ini, data berikutnya dari client ini akan diinterpretasikan sebagai ukuran file, bukan perintah baru.

#### `/download <filename>`

```python
sock.sendall(f"SIZE {file_size}\n".encode())
client_state[sock] = {
    'mode': 'download_ack',
    ...
}
```

Kirim ukuran file, ubah mode ke `download_ack`. Tunggu ACK dari client di iterasi berikutnya.

#### Pesan biasa

Langsung broadcast, tidak ada perubahan state.

---

### `handle_data(sock, clients, server_sock)`

```python
def handle_data(sock, clients, server_sock):
```

**Tujuan:** Dipanggil setiap kali `select()` melaporkan ada data baru dari sebuah client socket. Fungsi ini membaca data, menambahkannya ke buffer, lalu memproses berdasarkan mode client saat ini.

**Return:** `True` jika client masih hidup, `False` jika disconnect.

**Alur utama:**

```python
data = sock.recv(4096)
if not data:
    return False  # client disconnect

state['buf'] += data
# proses berdasarkan mode...
```

#### Mode `command`

```python
while b'\n' in state['buf']:
    line, state['buf'] = state['buf'].split(b'\n', 1)
    process_command(sock, clients, server_sock, line)
    mode = state.get('mode', 'command')
    if mode != 'command':
        break
```

Selama ada `\n` di buffer, ekstrak baris dan proses. Setelah `process_command` dipanggil, cek apakah mode berubah (misalnya jadi `upload_size`). Jika ya, hentikan loop sisa buffer akan diproses di iterasi berikutnya dengan mode baru.

**Mengapa pakai buffer `state['buf']`?**

TCP bisa mengirim data dalam potongan sembarangan. Contoh:

```
recv() pertama → b"/upload foto"          ← perintah belum lengkap
recv() kedua   → b".jpg\n1024\nhello"     ← perintah lengkap + data berikutnya
```

Buffer mengakumulasi semua data masuk sampai ada baris lengkap (`\n`).

#### Mode `upload_size`

```python
if b'\n' in state['buf']:
    size_line, state['buf'] = state['buf'].split(b'\n', 1)
    file_size = int(size_line.strip())
    state.update({'mode': 'upload_data', 'file_size': file_size, 'received': 0, ...})
    mode = 'upload_data'  # fall through ke blok berikutnya
```

Ekstrak angka ukuran file, siapkan counter `received`, pindah ke mode `upload_data`. Perhatikan `mode = 'upload_data'` diset secara lokal agar **bisa langsung fall through** ke blok `upload_data` di bawahnya dalam panggilan yang sama berguna jika data file sudah ikut masuk bersamaan dengan ukurannya.

#### Mode `upload_data`

```python
remaining = state['file_size'] - state['received']
chunk = state['buf'][:remaining]
state['buf'] = state['buf'][remaining:]

with open(filepath, 'ab') as f:
    f.write(chunk)
state['received'] += len(chunk)

if state['received'] >= state['file_size']:
    # upload selesai!
    client_state[sock] = {'mode': 'command', 'buf': leftover}
```

`state['buf'][:remaining]` memotong buffer hanya sebanyak yang dibutuhkan. Sisa buffer (`state['buf'][remaining:]`) disimpan kembali bisa saja sudah berisi awal perintah berikutnya dari client.

File dibuka dengan mode `'ab'` (append binary) agar bisa menerima data dalam beberapa panggilan `handle_data` yang berbeda.

#### Mode `download_ack`

```python
if b'\n' in state['buf']:
    ack_line, state['buf'] = state['buf'].split(b'\n', 1)
    if ack_line.strip() == b'ACK':
        with open(filepath, 'rb') as f:
            while True:
                chunk = f.read(4096)
                if not chunk: break
                sock.sendall(chunk)
    client_state[sock] = {'mode': 'command', 'buf': state['buf']}
```

Tunggu baris ACK dari client. Jika diterima, kirim seluruh isi file, lalu kembali ke mode `command`.

> **Catatan:** Pengiriman file di sini bersifat **blocking** (loop `sendall`). Untuk file besar, ini bisa memblok `select()` loop sebentar. Untuk produksi, pengiriman besar sebaiknya juga di-chunk secara async.

---

### `main()`

```python
def main():
```

**Tujuan:** Setup server dan menjalankan event loop berbasis `select()`.

**Setup socket:** (sama dengan server-sync, lihat dokumentasi server-sync.md)

**Event loop:**

```python
sockets_list = [server]   # dimulai hanya dengan server socket

while True:
    readable, _, exceptional = select.select(sockets_list, [], sockets_list, 1.0)
```

`select()` menerima tiga list:

1. **readable** socket yang ingin dipantau untuk data masuk
2. **writable** socket yang ingin dipantau untuk siap ditulis (kosong, tidak dipakai)
3. **exceptional** socket yang ingin dipantau untuk kondisi error

Timeout `1.0` detik jika tidak ada event selama 1 detik, `select()` return dengan list kosong dan loop berlanjut. Ini mencegah loop hang selamanya.

**Handle socket readable:**

```python
for sock in readable:
    if sock is server:
        conn, addr = server.accept()
        sockets_list.append(conn)
        client_state[conn] = {'mode': 'command', 'buf': b''}
        conn.sendall(b"Welcome to the TCP File Server!\n")
    else:
        alive = handle_data(sock, sockets_list, server)
        if not alive:
            sockets_list.remove(sock)
            client_state.pop(sock, None)
            sock.close()
```

Jika socket yang readable adalah `server`, berarti ada client baru panggil `accept()`. Jika bukan `server`, berarti ada data baru dari client yang sudah terhubung panggil `handle_data()`.

**Handle socket exceptional (error):**

```python
for sock in exceptional:
    sockets_list.remove(sock)
    client_state.pop(sock, None)
    sock.close()
```

Bersihkan socket yang mengalami error.

---

## Diagram State Machine per Client

```
          connect
             │
             ▼
        ┌─────────┐
        │ command │ ◀─────────────────────────────┐
        └─────────┘                               │
             │                                    │
    ┌────────┴────────┐                           │
    │                 │                           │
  /upload           /download              selesai / kembali
    │                 │                           │
    ▼                 ▼                           │
┌──────────┐    ┌──────────────┐                  │
│upload_   │    │ download_ack │                  │
│  size    │    └──────────────┘                  │
└──────────┘          │ ACK diterima              │
    │ angka diterima   │ kirim file ───────────────┘
    ▼                  │
┌──────────┐           │
│upload_   │           │
│  data    │           │
└──────────┘           │
    │ selesai           │
    └───────────────────┘
```

---

## Kelebihan & Kekurangan

| Kelebihan                                 | Kekurangan                                                              |
| ----------------------------------------- | ----------------------------------------------------------------------- |
| Bisa handle banyak client                 | Kode lebih kompleks (state machine)                                     |
| Single-threaded, tidak ada race condition | Satu operasi blocking bisa memperlambat semua client                    |
| Efisien di memori                         | Tidak tersedia di Windows untuk socket (`select` pada Windows terbatas) |
| Skalabel untuk I/O-bound workload         | Sulit di-debug karena alur tidak linier                                 |
