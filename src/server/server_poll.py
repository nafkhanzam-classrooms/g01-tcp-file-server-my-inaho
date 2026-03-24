import socket
import select
import struct
import json
import os

HOST = '127.0.0.1'
PORT = 5003
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

fd_map = {}
clients = {}
poll_obj = None

def broadcast(sender_sock, message):
    to_remove = []
    for sock in list(clients.keys()):
        if sock != sender_sock:
            try:
                send_json(sock, message)
            except:
                to_remove.append(sock)
    for sock in to_remove:
        remove_client(sock)

def remove_client(sock):
    if sock in clients:
        info = clients[sock]
        fd = info["fd"]
        try:
            poll_obj.unregister(fd)
        except:
            pass
        if fd in fd_map:
            del fd_map[fd]
        del clients[sock]
        try:
            sock.close()
        except:
            pass
        print(f"[-] Disconnected: {info['addr']}")

def handle_client_data(sock):
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
            print(f" '{filename}' dikirim ke {addr}")
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

def main():
    global poll_obj
    os.makedirs(FILES_DIR, exist_ok=True)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(5)

    print(f"[Poll Server] Listening on {HOST}:{PORT}")
    print("Multiple clients via poll() — Linux/Unix only\n")

    poll_obj = select.poll()
    poll_obj.register(server.fileno(), select.POLLIN)
    fd_map[server.fileno()] = server

    try:
        while True:
            events = poll_obj.poll()

            for fd, event in events:
                sock = fd_map.get(fd)
                if sock is None:
                    continue

                if sock is server:
                    conn, addr = server.accept()
                    conn_fd = conn.fileno()
                    fd_map[conn_fd] = conn
                    poll_obj.register(conn_fd, select.POLLIN)
                    clients[conn] = {"addr": addr, "fd": conn_fd}
                    print(f"[+] Connected: {addr}")

                elif event & select.POLLIN:
                    if not handle_client_data(sock):
                        remove_client(sock)

                if event & (select.POLLHUP | select.POLLERR | select.POLLNVAL):
                    remove_client(sock)

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        for fd, sock in list(fd_map.items()):
            try:
                sock.close()
            except:
                pass

if __name__ == '__main__':
    main()