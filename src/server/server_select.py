import socket
import select
import struct
import json
import os

HOST = '127.0.0.1'
PORT = 5002
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

clients = {}

def broadcast(sender_sock, message):
    to_remove = []
    for sock in clients:
        if sock != sender_sock:
            try:
                send_json(sock, message)
            except:
                to_remove.append(sock)
    for sock in to_remove:
        remove_client(sock, input_sockets)

def remove_client(sock, input_sockets):
    if sock in clients:
        addr = clients[sock]["addr"]
        del clients[sock]
        if sock in input_sockets:
            input_sockets.remove(sock)
        try:
            sock.close()
        except:
            pass
        print(f"[-] Disconnected: {addr}")

def handle_client_data(sock, input_sockets):
    info = clients.get(sock)
    if not info:
        return False

    msg = recv_json(sock)
    if msg is None:
        return False

    msg_type = msg.get("type", "")
    addr = info["addr"]

    if msg_type == "list":
        files = os.listdir(FILES_DIR) if os.path.isdir(FILES_DIR) else []
        send_json(sock, {"type": "list_response", "files": files})

    elif msg_type == "upload":
        filename = msg["filename"]
        file_data = recv_msg(sock)
        if file_data is not None:
            path = os.path.join(FILES_DIR, filename)
            with open(path, 'wb') as f:
                f.write(file_data)
            print(f"'{filename}' uploaded ({len(file_data)} bytes)")
            send_json(sock, {"type": "upload_ack", "status": "ok", "filename": filename})
        else:
            return False

    elif msg_type == "download":
        filename = msg["filename"]
        path = os.path.join(FILES_DIR, filename)
        if os.path.isfile(path):
            with open(path, 'rb') as f:
                file_data = f.read()
            send_json(sock, {
                "type": "download_response",
                "filename": filename,
                "size": len(file_data)
            })
            send_msg(sock, file_data)
            print(f"'{filename}' dikirim ke {addr}")
        else:
            send_json(sock, {
                "type": "download_response",
                "status": "error",
                "message": f"File '{filename}' tidak ditemukan"
            })

    elif msg_type == "message":
        content = msg["content"]
        print(f"  [{addr}]: {content}")
        broadcast(sock, {
            "type": "broadcast",
            "sender": str(addr),
            "content": content
        })

    return True

input_sockets = []

def main():
    global input_sockets
    os.makedirs(FILES_DIR, exist_ok=True)

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen(5)

    print(f"[Select Server] Listening on {HOST}:{PORT}")
    print("Multiple clients via select() I/O multiplexing\n")

    input_sockets = [server_socket]

    try:
        while True:
            read_ready, _, _ = select.select(input_sockets, [], [])

            for sock in read_ready:
                if sock == server_socket:
                    client_sock, client_addr = server_socket.accept()
                    input_sockets.append(client_sock)
                    clients[client_sock] = {"addr": client_addr}
                    print(f"[+] Connected: {client_addr}")
                else:
                    if not handle_client_data(sock, input_sockets):
                        remove_client(sock, input_sockets)

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        for sock in input_sockets:
            sock.close()

if __name__ == '__main__':
    main()