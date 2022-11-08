import sys
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
import webbrowser

import ruamel.yaml


PASS_DIRECTORY = pathlib.Path('~/.password-store').expanduser()


class Command:
    DEFAULT_COMMAND = None

    @classmethod
    def run(cls, args: List[str] = None, cmd: str = None, stdin: bytes = None):
        cmd = cmd or cls.DEFAULT_COMMAND
        args = args or []
        process = subprocess.Popen(
            [cmd, *args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = process.communicate(stdin)
        return stdout, stderr


class Rofi(Command):
    DEFAULT_COMMAND = "rofi"

    @classmethod
    def choice(cls, choices: List[str] = None):
        stdin = "\n".join(choices).encode('utf-8')
        stdout, _ = cls.run(args=['-dmenu'], stdin=stdin)
        return stdout.decode('utf-8').strip()


class GPG(Command):
    DEFAULT_COMMAND = "gpg"

    @classmethod
    def decrypt(cls, path: pathlib.Path) -> bytes:
        stdout, _ =  cls.run(args=["--decrypt", str(path)])
        return stdout


class Xdotool(Command):
    DEFAULT_COMMAND = "xdotool"

    @classmethod
    def type(cls, text: str, delay: int = 12):
        cls.run(args=[
            "type", "--delay", str(delay), "--clearmodifiers", "--file", "-",
        ], stdin=text.encode('utf-8'))


def list_password_files():
    files = []

    for path in PASS_DIRECTORY.glob('**/*.gpg'):
        files.append(str(path.relative_to(PASS_DIRECTORY))[:-4])

    return sorted(files)


def parse_password_file(path: pathlib.Path):
    contents = GPG().decrypt(path).decode('utf-8')

    match = re.fullmatch(r"""
       ^
       (?P<password>[^\n]*)\n
       (?:(?P<otp>[^-\n][^\n]*)\n)?
       (?:---+\n([\w\W]*))?
       $
    """, contents, flags=re.X)

    password, otp, data = match.groups()
    if data is not None:
        try:
            data = ruamel.yaml.YAML(typ='safe').load(data)
        except ruamel.yaml.YAMLError:
            data = {}
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


def main():
    # choose password file
    choice = Rofi.choice(list_password_files())
    if choice == '':
        sys.exit(1)

    # decrypt and read password file
    path = pathlib.Path(str(PASS_DIRECTORY / choice) + '.gpg')
    password, otp, data = parse_password_file(path)

    data['pass'] = password
    if otp is not None:
        data['otp'] = otp

    # choose field within password file
    choice = Rofi.choice(list(data.keys()))
    if choice == '':
        sys.exit(1)
    elif choice == 'otp':
        Xdotool.type(generate_totp(data[choice]))
    elif choice == 'url':
        webbrowser.open_new_tab(data[choice])
    else:
        Xdotool.type(str(data[choice]))


if __name__ == "__main__":
    main()
