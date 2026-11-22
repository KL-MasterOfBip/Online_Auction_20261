import atexit
import glob
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
TEST_PORT = int(os.environ.get("AUCTION_TEST_PORT", "18090"))
CFLAGS = ["-std=c11", "-Wall", "-Wextra", "-Wpedantic", "-g"]

_build_dir = None


def build_binaries():
    global _build_dir
    if _build_dir is not None:
        return _build_dir
    _build_dir = tempfile.mkdtemp(prefix="auction_items_build_")
    server_sources = sorted(
        path for path in glob.glob(os.path.join(SRC, "*.c"))
        if os.path.basename(path) != "client.c"
    )
    server_cmd = ["gcc"] + CFLAGS + ["-DPORT=%d" % TEST_PORT] + server_sources \
        + ["-I", SRC, "-o", os.path.join(_build_dir, "auction_server")]
    result = subprocess.run(server_cmd, capture_output=True, text=True)
    if result.returncode != 0 or result.stderr.strip():
        raise RuntimeError("Server build failed or has warnings:\n" + result.stderr)
    client_cmd = ["gcc"] + CFLAGS + [os.path.join(SRC, "client.c"),
                                    "-o", os.path.join(_build_dir, "client")]
    result = subprocess.run(client_cmd, capture_output=True, text=True)
    if result.returncode != 0 or result.stderr.strip():
        raise RuntimeError("Client build failed or has warnings:\n" + result.stderr)
    return _build_dir


def cleanup_build():
    global _build_dir
    if _build_dir is not None:
        shutil.rmtree(_build_dir, ignore_errors=True)
        _build_dir = None


atexit.register(cleanup_build)


class TestClient:
    def __init__(self, port=TEST_PORT):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=3)
        self.buffer = b""
        self.greeting = self.read_line()

    def send_raw(self, data):
        self.sock.sendall(data)

    def send(self, line):
        self.sock.sendall((line + "\n").encode())

    def read_line(self, timeout=3):
        self.sock.settimeout(timeout)
        while b"\n" not in self.buffer:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("Connection closed by server")
            self.buffer += chunk
        line, self.buffer = self.buffer.split(b"\n", 1)
        return line.decode()

    def cmd(self, line):
        self.send(line)
        return self.read_line()

    def read_until(self, end_marker):
        lines = []
        while True:
            line = self.read_line()
            lines.append(line)
            if line == end_marker:
                return lines

    def list_items(self, room_id):
        self.send("LIST_ITEMS %s" % room_id)
        first = self.read_line()
        if first != "OK ITEM_LIST":
            return [first]
        return [first] + self.read_until("END_ITEM_LIST")

    def has_data(self, wait=0.3):
        if self.buffer:
            return True
        self.sock.settimeout(wait)
        try:
            chunk = self.sock.recv(4096)
        except socket.timeout:
            return False
        if not chunk:
            return False
        self.buffer += chunk
        return True

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class ServerTestCase(unittest.TestCase):
    password = "pw1234"

    @classmethod
    def setUpClass(cls):
        cls.build_dir = build_binaries()

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        self.work_dir = tempfile.mkdtemp(prefix="auction_items_run_")
        self.log_path = os.path.join(self.work_dir, "auction_server.log")
        self.server = subprocess.Popen(
            [os.path.join(self.build_dir, "auction_server")],
            cwd=self.work_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.clients = []
        self._wait_for_server()

    def tearDown(self):
        for client in self.clients:
            client.close()
        self.server.terminate()
        try:
            self.server.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.server.kill()
        shutil.rmtree(self.work_dir, ignore_errors=True)

    def _wait_for_server(self):
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                probe = socket.create_connection(("127.0.0.1", TEST_PORT), timeout=1)
                probe.close()
                time.sleep(0.05)
                return
            except OSError:
                time.sleep(0.05)
        self.fail("Server did not start")

    def connect(self):
        client = TestClient()
        self.clients.append(client)
        return client

    def make_user(self, username):
        client = self.connect()
        self.assertEqual(client.cmd("REGISTER %s %s" % (username, self.password)),
                         "OK Account registered")
        self.assertEqual(client.cmd("LOGIN %s %s" % (username, self.password)),
                         "OK Login successful")
        return client

    def make_room(self, client, name):
        response = client.cmd("CREATE_ROOM %s" % name)
        match = re.match(r"OK ROOM_CREATED ID: (\d+)$", response)
        self.assertIsNotNone(match, response)
        return int(match.group(1))

    def add_item(self, client, room_id, name, start=100000, buy_now=500000):
        response = client.cmd("ADD_ITEM %s %s %s %s" % (room_id, name, start, buy_now))
        match = re.match(r"OK ITEM_ADDED ID: (\d+)$", response)
        self.assertIsNotNone(match, response)
        return int(match.group(1))

    def read_log(self):
        with open(self.log_path) as log_file:
            return log_file.read()

    def item_lines(self, client, room_id):
        lines = client.list_items(room_id)
        self.assertEqual(lines[0], "OK ITEM_LIST", lines)
        return [line for line in lines if line.startswith("ITEM ")]


def run_main():
    unittest.main(verbosity=2)
