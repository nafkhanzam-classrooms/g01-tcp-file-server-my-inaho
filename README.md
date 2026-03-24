[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/mRmkZGKe)

# Network Programming - Assignment G01

## Anggota Kelompok

| Nama                   | NRP        | Kelas |
| ---------------------- | ---------- | ----- |
| Hamzah Ali Abdillah    | 5025241023 | C     |
| Danish Faiq Ibad Yuadi | 5025241038 | C     |

## Link Youtube (Unlisted)

Link ditaruh di bawah ini

```

```

## Penjelasan Program

# TCP File Server

Proyek ini merupakan implementasi aplikasi *Client-Server* berbasis protokol TCP untuk manajemen dan transfer file. 

## 1. Arsitektur Server (Port `900X`)

Proyek ini menggunakan 4 pendekatan server TCP yang berbeda untuk menangani koneksi klien.

| File Server | Pendekatan | Penjelasan |
| :--- | :--- | :--- |
| `server-sync.py`<br> | **Synchronous / Blocking** | Bentuk server TCP paling dasar. Hanya melayani **satu klien pada satu waktu**. Jika ada klien lain yang mencoba terhubung, koneksinya akan masuk ke fase *blocked* sampai klien pertama selesai. |
| `server-select.py`<br> | **Multiplexed I/O** | Menangani banyak klien secara bersamaan dalam satu *thread*. Menggunakan *loop* `select.select()` untuk memantau banyak *socket* sekaligus dan memprosesnya melalui *state machine* jika ada *socket* yang siap dibaca. |
| `server-poll.py`<br> | **System Call** | Mirip dengan pendekatan `select`, namun menggunakan `select.poll()` beserta *event flags*. Lebih efisien untuk skala koneksi yang besar, tetapi spesifik hanya untuk sistem operasi berbasis Linux. |
| `server-thread.py`<br> | **Multi-threading** | Membuat sebuah *daemon thread* baru setiap kali ada klien yang terhubung. Untuk mencegah *race condition* pada data yang dibagikan antar klien, arsitektur ini menggunakan mekanisme *lock*. |

---

## 2. Implementasi Klien

**`client.py`** bertindak sebagai *interface* utama bagi pengguna untuk terhubung ke salah satu server di atas.

* **Cara Menjalankan**: Eksekusi melalui command line dengan format `python client.py <host> <port>`.
* **Concurrency Architechture**: Klien menggunakan *background thread*. *Main thread* menangani *input* dari pengguna, sementara *background thread* selalu aktif mendengarkan pesan masuk dari server secara *real-time*.
* **Command yang Didukung**:
  1. `/list`: Meminta dan menampilkan daftar file yang tersedia di direktori server.
  2. `/upload <filepath>`: Mengirim file lokal ke server. Klien akan membagi file menjadi *chunks* jaringan dan menampilkan *progress* upload.
  3. `/download <filename>`: Mengunduh file dari server ke folder lokal `downloads/`, dilengkapi dengan visualisasi persentase *progress* download.

## Screenshot Hasil
