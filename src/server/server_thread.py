import socket
import struct
import json
import os
import threading

HOST = '127.0.0.1'
PORT = 5004
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
clients_lock = threading.Lock()

def broadcast(sender_sock, message):
    with clients_lock:
        targets = [(sock, info) for sock, info in clients.items()
                    if sock != sender_sock]
    for sock, info in targets:
        try:
            with info["lock"]:
                send_json(sock, message)
        except:
            remove_client(sock)

def remove_client(sock):
    with clients_lock:
        if sock in clients:
            addr = clients[sock]["addr"]
            del clients[sock]
            try:
                sock.close()
            except:
                pass
            print(f"[-] Disconnected: {addr}")

class ClientThread(threading.Thread):
    def __init__(self, client_sock, client_addr):
        threading.Thread.__init__(self, daemon=True)
        self.sock = client_sock
        self.addr = client_addr

    def run(self):
        print(f"[+] Connected: {self.addr} (Thread: {self.name})")

        with clients_lock:
            clients[self.sock] = {
                "addr": self.addr,
                "lock": threading.Lock()
            }

        try:
            while True:
                msg = recv_json(self.sock)
                if msg is None:
                    break

                msg_type = msg.get("type", "")

                if msg_type == "list":
                    files = os.listdir(FILES_DIR) if os.path.isdir(FILES_DIR) else []
                    with clients[self.sock]["lock"]:
                        send_json(self.sock, {"type": "list_response", "files": files})

                elif msg_type == "upload":
                    filename = msg["filename"]
                    file_data = recv_msg(self.sock)
                    if file_data is not None:
                        path = os.path.join(FILES_DIR, filename)
                        with open(path, 'wb') as f:
                            f.write(file_data)
                        print(f"'{filename}' uploaded ({len(file_data)} bytes)")
                        with clients[self.sock]["lock"]:
                            send_json(self.sock, {
                                "type": "upload_ack",
                                "status": "ok",
                                "filename": filename
                            })
                    else:
                        break

                elif msg_type == "download":
                    filename = msg["filename"]
                    path = os.path.join(FILES_DIR, filename)
                    if os.path.isfile(path):
                        with open(path, 'rb') as f:
                            file_data = f.read()
                        with clients[self.sock]["lock"]:
                            send_json(self.sock, {
                                "type": "download_response",
                                "filename": filename,
                                "size": len(file_data)
                            })
                            send_msg(self.sock, file_data)
                        print(f"'{filename}' dikirim ke {self.addr}")
                    else:
                        with clients[self.sock]["lock"]:
                            send_json(self.sock, {
                                "type": "download_response",
                                "status": "error",
                                "message": f"File '{filename}' tidak ditemukan"
                            })

                elif msg_type == "message":
                    content = msg["content"]
                    print(f"  [{self.addr}]: {content}")
                    broadcast(self.sock, {
                        "type": "broadcast",
                        "sender": str(self.addr),
                        "content": content
                    })

        except Exception as e:
            print(f"  Error ({self.addr}): {e}")
        finally:
            remove_client(self.sock)

class Server:
    def __init__(self):
        self.host = HOST
        self.port = PORT
        self.server = None
        self.threads = []

    def open_socket(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((self.host, self.port))
        self.server.listen(5)

    def run(self):
        os.makedirs(FILES_DIR, exist_ok=True)
        self.open_socket()

        print(f"[Thread Server] Listening on {self.host}:{self.port}")
        print("Setiap client mendapat thread sendiri\n")

        try:
            while True:
                client_sock, client_addr = self.server.accept()
                t = ClientThread(client_sock, client_addr)
                t.start()
                self.threads.append(t)
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            self.server.close()
            for t in self.threads:
                t.join(timeout=1)

if __name__ == '__main__':
    server = Server()
    server.run()