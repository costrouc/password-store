import io
import re
import pathlib
from typing import List
import subprocess
import time
import struct
import base64
import hmac
import hashlib
import urllib.parse

from ruamel.yaml import YAML


PASS_DIRECTORY = pathlib.Path('~/.password-store').expanduser()


class Rofi:
    ROFI_CMD = "rofi"

    def run(self, args: List[str], cmd: str = ROFI_CMD, stdin: bytes = None):
        process = subprocess.Popen(
            [cmd, *args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            encoding='utf-8'
        )
        stdout, stderr = process.communicate(stdin)
        return stdout, stderr

    def choice(self, choices: List[str] = None):
        stdout, _ = self.run(args=['-dmenu'], stdin="\n".join(choices))
        return stdout.strip()


class GPG:
    GPG_CMD = "gpg"

    def run(self, args: List[str], cmd: str = GPG_CMD, stdin: bytes = None) -> bytes:
        process = subprocess.Popen(
            [cmd, *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        stdout, stderr = process.communicate(stdin)
        return stdout, stderr

    def decrypt(self, path: pathlib.Path) -> bytes:
        stdout, _ =  self.run(args=["--decrypt", str(path)])
        return stdout


class Xdotool:
    XDOTOOL_CMD = "xdotool"

    def run(self, args: List[str], cmd: str = XDOTOOL_CMD, stdin: bytes = None):
        process = subprocess.Popen(
            [cmd, *args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = process.communicate(stdin)
        return stdout, stderr

    def type(self, text: str, delay: int = 12):
        self.run(args=[
            "type", "--delay", str(delay), "--clearmodifiers", "--file", "-",
        ], stdin=text.encode('utf-8'))


def list_password_files():
    for path in PASS_DIRECTORY.glob('**/*.gpg'):
        yield str(path.relative_to(PASS_DIRECTORY))[:-4]


def parse_password_file(path: pathlib.Path):
    contents = GPG().decrypt(path).decode('utf-8')

    match = re.match(r"""
       (?P<password>[^\n]*)\n
       (?:(?P<otp>[^-\n][^\n]*)\n)?
       (?:---+\n([\w\W]*)$)?
    """, contents, flags=re.X)

    password, otp, data = match.groups()
    if data is not None:
        data = YAML(typ='safe').load(data)
    else:
        data = {}

    return password, otp, flatten(data)


def flatten(d, parent_key='', sep='.'):
    items = {}
    for key, value in d.items():
        new_key = parent_key + sep + key if parent_key else key
        if isinstance(value, dict):
            items.update(flatten(value, parent_key=new_key, sep=sep))
        else:
            items[new_key] = value
    return items


def generate_totp(totp_uri: str):
    uri = urllib.parse.urlparse(totp_uri)
    secret = urllib.parse.parse_qs(uri.query)['secret'][0]
    secret = base64.b32decode(secret)
    counter = int(time.time()) // 30;
    counter = struct.pack('>Q', counter)
    hash = hmac.new(secret, counter, hashlib.sha1).digest()
    offset = hash[19] & 0xF
    password = (struct.unpack( '>I', hash[offset:offset + 4])[0] & 0x7FFFFFFF ) % 1000000
    return f'{password:06}'


if __name__ == "__main__":
    choice = Rofi().choice(list(list_password_files()))
    path = pathlib.Path(str(PASS_DIRECTORY / choice) + '.gpg')
    password, otp, data = parse_password_file(path)

    data['pass'] = password
    if otp is not None:
        data['otp'] = otp

    choice = Rofi().choice(list(data.keys()))
    if choice == 'otp':
        Xdotool().type(generate_totp(data[choice]))
    else:
        Xdotool().type(data[choice])
