import socket
from threading import Thread
from argparse import ArgumentParser

# try to import C parser then fallback in pure python parser.
try:
    from http_parser.parser import HttpParser
except ImportError:
    from http_parser.pyparser import HttpParser


class HttpProxy:
    BUFFER_SIZE = 8192

    def __init__(self, host="0.0.0.0", port=3000, max_clients=50):
        self.host = host
        self.port = port
        self.max_clients = max_clients

    def run(self):
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.bind((self.host, self.port))
        client_socket.listen(self.max_clients)
        print(f"Proxy running - {self.host}:{self.port}")
        while True:
            source, addr = client_socket.accept()
            print(f"Accept from {addr[0]}:{addr[1]}")
            Thread(target=self.handle_request, args=(source,)).start()
    
    def handle_request(self, source):
        data = self.recv_all(source)
        # data = source.recv(self.buffer_size)

        if not data:
            source.close()
            return
        
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        p = HttpParser()
        p.execute(data, len(data))

        headers = p.get_headers()
        if ':' in headers['Host']:
            host, port = headers['Host'].split(':')
        else:
            host = headers['Host']
            port = 80
        port = int(port)

        if p.get_method() == 'CONNECT':
            self.https_tunnel(host, port, source, server)
        else:
            # connect to dest
            try:
                server.connect((host, port))
            except:
                print(f"Could not connect to {host}:{port}")
                server.close()
                source.close()
                return 

            # send data to dest
            server.sendall(data)

            # accumulate response from dest
            response = self.recv_all(server)

            # send response to src
            source.sendall(response)

            server.close()
            source.close()

    def https_tunnel(self, host, port, source, server):
        try:
            server.connect((host, port))
            reply = ("HTTP/1.1 200 Connection established\r\n"
                    "ProxyServer-agent: MyProxy\r\n\r\n")
            source.sendall(reply.encode())
        except socket.error as err:
            print(f"Could not establish https tunnel with {host}:{port}. {err}")
            server.close()
            source.close()
            return
        
        source.setblocking(False)
        server.setblocking(False)
        while True:
            # from source to dest
            try:
                data = source.recv(self.BUFFER_SIZE)
                if not data:
                    server.close()
                    source.close()
                    break
                server.sendall(data)
            except socket.error:
                pass
            # from dest to source
            try:
                reply = server.recv(self.BUFFER_SIZE)
                if not reply:
                    server.close()
                    source.close()
                    break
                source.sendall(reply)
            except socket.error:
                pass
    
    def recv_all(self, sock):
        data = sock.recv(self.BUFFER_SIZE)

        p = HttpParser()
        p.execute(data, len(data))

        response_headers = p.get_headers()
        if p.is_chunked():
            # chunked transfer encoding
            while not data.endswith(b'0\r\n\r\n'):
                chunk = sock.recv(self.BUFFER_SIZE)
                data += chunk
        elif 'Content-Length' in response_headers:  
            while len(data) < int(response_headers['Content-Length']):
                data += sock.recv(self.BUFFER_SIZE)
        
        return data

if __name__ == "__main__":
    parser = ArgumentParser()

    parser.add_argument(
        "-h"
        "--hostname",
        help="Hostname to bind to",
        dest="h",
        type=str,
        default="0.0.0.0"
    )
    parser.add_argument(
        "-p"
        "--port",
        help="Port to bind to",
        dest="p",
        type=int,
        default=3000
    )
    parser.add_argument(
        "-c"
        "--max-clients",
        help="Maximum number of clients",
        dest="c",
        type=int,
        default=50
    )

    args = parser.parse_args()

    HttpProxy(args.h, args.p, args.c).run()