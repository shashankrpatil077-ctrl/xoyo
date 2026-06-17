from http.server import HTTPServer, SimpleHTTPRequestHandler
import ssl, os

os.chdir('/home/shashank/xoyo/frontend')

server = HTTPServer(('0.0.0.0', 8090), SimpleHTTPRequestHandler)
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain(certfile='ssl/cert.pem', keyfile='ssl/key.pem')
server.socket = ctx.wrap_socket(server.socket, server_side=True)
print('HTTPS server running on port 8090...')
server.serve_forever()
