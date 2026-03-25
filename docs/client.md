# `client.py` TCP File Server Client

## Gambaran Umum

Klien ini digunakan untuk terhubung ke salah satu dari empat implementasi server TCP yang tersedia (Sync, Thread, Select, Poll). Berbeda dengan server, klien ini menggunakan **satu background thread (`threading.Thread`)** untuk memantau *socket penerima* agar bisa mendengarkan pesan balasan secara asinkron dari server, selagi *main thread* melayani input ketikan pengguna (`sys.stdin` atau `input()`).

**Host default:** `127.0.0.1`  
**Direktori data:** `client_files/`

**Cara menjalankan:**

```bash
python src/client/client.py <port>
# Contoh: Koneksi ke server thread (5004)
python src/client/client.py 5004
```

> **Catatan Port:**
> 5001 = Server Sync
> 5002 = Server Select
> 5003 = Server Poll
> 5004 = Server Thread

---

## Pembungkus Protokol JSON

Protokol antara Klien dan Server adalah *Length-Prefixed JSON* (persis seperti yang dijelaskan di sisi server):
1. Setiap pesan dibungkus tipe kamus bawaan `{"type": "nama_perintah", ...}`
2. Pesan JSON dienkode lalu dipasang header panjang ukuran `len(data)` menggunakan format *4-byte Big-Endian Unsigned Int* dengan modul struct.
3. Klien menggunakan `send_json()` dan merekonstruksi dengan `recv_json()` menggunakan loop pembaca `recv_exact()`.

---

## Logika Klien

Aplikasi `client.py` dibagi menjadi 2 Thread utama:

### 1. Main Thread (Input Pengguna)
Sub-proses utama ditugaskan hanya untuk membaca CLI terminal secara blocking. Setelah parsing selesai, ia akan dibungkus dan dikirimkan lewat Socket (`send_json`).

```python
        while True:
            user_input = input("> ").strip()
            ...
            
            # /list
            if user_input == "/list":
                send_json(sock, {"type": "list"})
                
            # /upload
            elif user_input.startswith("/upload "):
                ... 
                with open(filepath, 'rb') as f:
                    file_data = f.read()
                # 1. Kirim Header Spesifikasi Upload JSON
                send_json(sock, {
                    "type": "upload",
                    "filename": filename,
                    "size": len(file_data)
                })
                # 2. Kirim Binary Upload langsung berurutan Header 4-byte
                send_msg(sock, file_data)
                
            # /download
            elif user_input.startswith("/download "):
                send_json(sock, {"type": "download", "filename": filename})
                
            # chat/message biasa
            else:
                send_json(sock, {"type": "message", "content": user_input})
```


### 2. Receive Loop (Menerima Pesan Server)
Segera setelah Socket terhubung, Script Python menjalankan Deamon Thread `receive_loop(sock)`. Fungsinya cuma satu: mem-blocking `recv_json` untuk menerjemahkan balasan yang dikirim oleh server agar diprint di layar tanpa harus menunggu aksi input pengguna.

```python
    t = threading.Thread(target=receive_loop, args=(sock,), daemon=True)
    t.start()
```

Kondisi `daemon=True` digunakan agar begitu main program (Terminal Input utama) ditekan Ctrl-C, maka Thread penerima latar belakang ini otomatis dimatikan seketika.

#### Penanganan Tipe JSON di Receive Loop

```python
    while True:
        msg = recv_json(sock)
        msg_type = msg.get("type", "")

        if msg_type == "broadcast":
            print(f"\n[{msg['sender']}]: {msg['content']}")
            ...
```

Di dalam thread terpisah ini, klien menindaklanjuti secara sinkronus untuk menguraikan aksi:
- Jika `msg_type` == "list_response", list di-print as teks.
- Jika `msg_type` == "upload_ack", ditampilkan notifikasi 'Upload Berhasil/Gagal'.
- Jika `msg_type` == "download_response", maka ia akan siap-siap melakukan *blocking tambahan* terhadap socket untuk **secara utuh** mengunduh paket binary `file_data = recv_msg(sock)` dan diletakkan ke `client_files/`.

---

## Kelebihan Desain Klien Ini

| Kelebihan | Keterangan |
|-----------|------------|
| Multi-tasking (Read+Write) mulus | Selagi mengetik Input (> ), pesan pemberitahuan/broadcast server tetap muncul dari atas |
| Terbebas dari limitasi `select` OS | Desain *worker read-only thread* ini jauh lebih bersahabat di Windows ketimbang `poll()` atau `select()` |
