import socket
import time
import platform
import os

HOST = '127.0.0.1'
PORT = 6969

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
while True:
    try:
        s.connect((HOST, PORT))
        s.shutdown(2)
    except:
        time.sleep(0.05)
        continue

    break

url = f'http://{HOST}:{PORT}'

system = platform.system()
if system == 'Windows':
    os.system(f'start "" {url}')
elif system == 'Darwin':
    os.system(f'open "" {url}')
else:
    os.system(f'xdg-open "" {url}')
