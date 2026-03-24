import socket
import struct
import json
import os

HOST = '127.0.0.1'
PORT = 5001
FILES_DIR = 'server_files'

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

def handle_client(client_sock, client_addr):
    print(f"[+] Connected: {client_addr}")
    try:
        while True:
            msg = recv_json(client_sock)
            if msg is None:
                break

            msg_type = msg.get("type", "")

            if msg_type == "list":
                files = os.listdir(FILES_DIR) if os.path.isdir(FILES_DIR) else []
                send_json(client_sock, {"type": "list_response", "files": files})

            elif msg_type == "upload":
                filename = msg["filename"]
                file_data = recv_msg(client_sock)
                if file_data is not None:
                    path = os.path.join(FILES_DIR, filename)
                    with open(path, 'wb') as f:
                        f.write(file_data)
                    print(f"'{filename}' uploaded ({len(file_data)} bytes)")
                    send_json(client_sock, {
                        "type": "upload_ack", "status": "ok", "filename": filename
                    })

            elif msg_type == "download":
                filename = msg["filename"]
                path = os.path.join(FILES_DIR, filename)
                if os.path.isfile(path):
                    with open(path, 'rb') as f:
                        file_data = f.read()
                    send_json(client_sock, {
                        "type": "download_response",
                        "filename": filename,
                        "size": len(file_data)
                    })
                    send_msg(client_sock, file_data)
                    print(f"'{filename}' dikirim ke {client_addr}")
                else:
                    send_json(client_sock, {
                        "type": "download_response",
                        "status": "error",
                        "message": f"File '{filename}' tidak ditemukan"
                    })

            elif msg_type == "message":
                content = msg["content"]
                print(f"  [{client_addr}]: {content}")
                send_json(client_sock, {
                    "type": "broadcast",
                    "sender": str(client_addr),
                    "content": content
                })

    except Exception as e:
        print(f"  Error: {e}")
    finally:
        client_sock.close()
        print(f"[-] Disconnected: {client_addr}")

def main():
    os.makedirs(FILES_DIR, exist_ok=True)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(5)

    print(f"[Sync Server] Listening on {HOST}:{PORT}")
    print("  Hanya bisa handle 1 client pada satu waktu!\n")

    try:
        while True:
            client_sock, client_addr = server.accept()
            handle_client(client_sock, client_addr)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server.close()

if __name__ == '__main__':
    main()