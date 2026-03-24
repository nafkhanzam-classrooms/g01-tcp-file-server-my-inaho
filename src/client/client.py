import socket
import struct
import json
import os
import sys
import threading

HOST = '127.0.0.1'
FILES_DIR = 'client_files'

def send_msg(sock, data):
    header = struct.pack(">I", len(data))
    sock.sendall(header + data)

def recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf

def recv_msg(sock):
    header = recv_exact(sock, 4)
    if not header:
        return None
    length = struct.unpack(">I", header)[0]
    if length == 0:
        return b""
    return recv_exact(sock, length)

def send_json(sock, obj):
    send_msg(sock, json.dumps(obj).encode('utf-8'))

def recv_json(sock):
    data = recv_msg(sock)
    if data is None:
        return None
    return json.loads(data.decode('utf-8'))


def receive_loop(sock):
    try:
        while True:
            msg = recv_json(sock)
            if msg is None:
                print("\n[Server disconnected]")
                os._exit(0)

            msg_type = msg.get("type", "")

            if msg_type == "broadcast":
                print(f"\n[{msg['sender']}]: {msg['content']}")

            elif msg_type == "list_response":
                files = msg.get("files", [])
                if files:
                    print("\nFiles on server:")
                    for f in files:
                        print(f"  📄 {f}")
                else:
                    print("\n(No files on server)")

            elif msg_type == "upload_ack":
                if msg.get("status") == "ok":
                    print(f"\nUpload berhasil: {msg.get('filename')}")
                else:
                    print(f"\nUpload gagal: {msg.get('message')}")

            elif msg_type == "download_response":
                if msg.get("status") == "error":
                    print(f"\nDownload gagal: {msg.get('message')}")
                else:
                    filename = msg["filename"]
                    file_data = recv_msg(sock)
                    if file_data is not None:
                        os.makedirs(FILES_DIR, exist_ok=True)
                        path = os.path.join(FILES_DIR, filename)
                        with open(path, 'wb') as f:
                            f.write(file_data)
                        print(f"\nDownloaded '{filename}' ({len(file_data)} bytes) → {path}")
                    else:
                        print("\nKoneksi terputus saat download")

            elif msg_type == "error":
                print(f"\nError: {msg.get('message')}")

            print("> ", end="", flush=True)
    except Exception as e:
        print(f"\n[Connection error] {e}")
        os._exit(1)

def main():
    if len(sys.argv) < 2:
        print("Usage: python client.py <port>")
        print("Contoh:")
        print("  python client.py 5001   # connect ke server-sync")
        print("  python client.py 5002   # connect ke server-select")
        print("  python client.py 5003   # connect ke server-poll")
        print("  python client.py 5004   # connect ke server-thread")
        sys.exit(1)

    try:
        port = int(sys.argv[1])
    except ValueError:
        print(f"Error: '{sys.argv[1]}' bukan port yang valid (harus angka)")
        sys.exit(1)

    os.makedirs(FILES_DIR, exist_ok=True)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((HOST, port))
    except ConnectionRefusedError:
        print(f"Tidak bisa connect ke {HOST}:{port}")
        print("   Pastikan server sudah berjalan di port tersebut.")
        sys.exit(1)

    print(f"Connected ke {HOST}:{port}")
    print("─" * 45)
    print("Commands:")
    print("  /list                - List file di server")
    print("  /upload <filename>   - Upload file ke server")
    print("  /download <filename> - Download file dari server")
    print("  /quit                - Disconnect")
    print("  <teks apapun>        - Broadcast pesan")
    print("─" * 45)

    t = threading.Thread(target=receive_loop, args=(sock,), daemon=True)
    t.start()

    try:
        while True:
            user_input = input("> ").strip()
            if not user_input:
                continue

            if user_input == "/quit":
                break

            elif user_input == "/list":
                send_json(sock, {"type": "list"})

            elif user_input.startswith("/upload "):
                filename = user_input[8:].strip()
                if not filename:
                    print("Usage: /upload <filename>")
                    continue
                filepath = os.path.join(FILES_DIR, filename)
                if not os.path.isfile(filepath):
                    print(f"File tidak ditemukan: {filepath}")
                    print(f"Letakkan file di folder '{FILES_DIR}/'")
                    continue
                with open(filepath, 'rb') as f:
                    file_data = f.read()
                send_json(sock, {
                    "type": "upload",
                    "filename": filename,
                    "size": len(file_data)
                })
                send_msg(sock, file_data)
                print(f"Uploading '{filename}' ({len(file_data)} bytes)...")

            elif user_input.startswith("/download "):
                filename = user_input[10:].strip()
                if not filename:
                    print("Usage: /download <filename>")
                    continue
                send_json(sock, {"type": "download", "filename": filename})

            else:
                send_json(sock, {"type": "message", "content": user_input})

    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        sock.close()
        print("\nDisconnected.")

if __name__ == '__main__':
    main()