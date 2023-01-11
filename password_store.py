import sys
import os
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
import argparse
import tempfile
import datetime

import ruamel.yaml
import pytesseract


class PasswordStore:
    PASS_DIRECTORY = os.environ.get('PASSWORD_STORE', pathlib.Path('~/.password-store').expanduser())

    @staticmethod
    def list_files():
        files = []

        for path in PasswordStore.PASS_DIRECTORY.glob('**/*.gpg'):
            files.append(str(path.relative_to(PasswordStore.PASS_DIRECTORY))[:-4])

        return sorted(files)

    @staticmethod
    def parse_file(path: pathlib.Path):
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

        data['pass'] = password
        if otp is not None:
            data['otp'] = otp

        return flatten(data)


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
        stdout, stderr = process.communicate(input=stdin)
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


class Spectacle(Command):
    DEFAULT_COMMAND = "spectacle"

    @classmethod
    def capture(cls, filename: str):
        cls.run(args=['--region', '-w', '--background', '--nonotify', '--output', filename])

    @classmethod
    def clipboard(cls):
        cls.run(args=['--region', '-w', '--background', '--nonotify', '--copy-image'])


class QRReader(Command):
    DEFAULT_COMMAND = "zbarimg"

    @classmethod
    def read(cls, filename):
        stdout, stderr = cls.run(args=[filename])
        return stdout[:-1].decode('utf-8')


class XClip(Command):
    DEFAULT_COMMAND = "xclip"

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
        if stdin:
            process.stdin.write(stdin)
            process.stdin.close()
            process.wait()
        else:
            stdout, stderr = process.communicate()
            return stdout, stderr

    @classmethod
    def set(cls, text: str):
        cls.run(args=['-selection', 'clipboard'], stdin=text.encode('utf-8'))

    @classmethod
    def get(cls):
        stdout, stderr = cls.run(args=['-selection', 'clipboard', '-o'])
        return stdout.decode('utf-8')


def flatten(d, parent_key='', sep='.'):
    items = {}
    for key, value in d.items():
        new_key = parent_key + sep + key if parent_key else key
        if isinstance(value, dict):
            items.update(flatten(value, parent_key=new_key, sep=sep))
        else:
            items[new_key] = value
    return items


def get_nested_attr(d, attr, sep='.'):
    _ = d
    for key in attr.split(sep):
        _ = _[key]
    return _


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


def cli():
    parser = argparse.ArgumentParser(
        prog='password-store'
    )
    parser.set_defaults(func=None)
    subparsers = parser.add_subparsers()

    parser_rofi = subparsers.add_parser('rofi', help='rofi')
    parser_rofi.set_defaults(func=handle_rofi_command)

    parser_get = subparsers.add_parser('get', help='get')
    parser_get.add_argument('file', type=str)
    parser_get.add_argument('key', type=str)
    parser_get.set_defaults(func=handle_get_command)

    args = parser.parse_args()
    if args.func is None:
        parser.print_help()
        sys.exit(1)

    args.func(args)


def handle_get_command(args):
    # decrypt and read password file
    path = pathlib.Path(str(PasswordStore.PASS_DIRECTORY / args.file) + '.gpg')
    data = PasswordStore.parse_file(path)

    print(get_nested_attr(data, args.key), end='')


def action_read_qrcode_to_clipboard_text():
    with tempfile.NamedTemporaryFile(suffix='.png') as temporaryfile:
        time.sleep(1)
        Spectacle.capture(temporaryfile.name)
        output = QRReader.read(temporaryfile.name)
        XClip.set(output)


def action_screenshot_to_clipboard_text():
    with tempfile.NamedTemporaryFile(suffix='.png') as temporaryfile:
        time.sleep(1)
        Spectacle.capture(temporaryfile.name)
        text = pytesseract.image_to_string(temporaryfile.name, lang='eng', config="--psm 6 --oem 3")
        XClip.set(text)

def action_screenshot_to_clipboard_image():
    Spectacle.clipboard()


def action_screenshot_to_clipboard_filename():
    filename = pathlib.Path.home() / 'Pictures' / 'screenshots' / f'{datetime.datetime.now().isoformat()}.png'
    Spectacle.capture(str(filename))
    XClip.set(str(filename))


def action_type_clipboard():
    text = XClip.get()
    Xdotool.type(text)


def handle_rofi_command(args):
    actions = {
        'action::read-qrcode': action_read_qrcode_to_clipboard_text,
        'action::ocr-screenshot': action_screenshot_to_clipboard_text,
        'action::type-clipboard': action_type_clipboard,
        'action::copy-screenshot': action_screenshot_to_clipboard_image,
        'action::file-screenshot': action_screenshot_to_clipboard_filename,
    }

    # choose password file
    choice = Rofi.choice(PasswordStore.list_files() + list(actions))
    if choice == '':
        sys.exit(1)
    elif choice in actions:
        actions[choice]()
        sys.exit(0)

    # decrypt and read password file
    path = pathlib.Path(str(PasswordStore.PASS_DIRECTORY / choice) + '.gpg')
    data = PasswordStore.parse_file(path)

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
    cli()
