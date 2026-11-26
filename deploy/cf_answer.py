"""Reads a Cloudflare API answer that a token step's curl wrote to a file, and prints none of it.

    python3 -I deploy/cf_answer.py jwt <answer> <jwt-file>     the upload token: masked, then saved
    python3 -I deploy/cf_answer.py deployment <answer>         the deployment: its id and URL

It runs after the step has unset the Cloudflare secrets, so it never holds them. Standard library only.
"""
import json
import os
import re
import sys

TOKEN = re.compile(r'^[A-Za-z0-9._-]{1,8192}$')
SAFE = re.compile(r'^[A-Za-z0-9._:/-]{1,300}$')


def _result(answer):
    try:
        with open(answer) as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        raise SystemExit('the Cloudflare answer is not JSON')
    if not isinstance(doc, dict) or doc.get('success') is not True:
        raise SystemExit('Cloudflare refused the call')
    return doc.get('result')


def jwt(answer, out):
    result = _result(answer)
    token = result.get('jwt') if isinstance(result, dict) else None
    if not isinstance(token, str) or not TOKEN.fullmatch(token):
        raise SystemExit('the answer holds no upload token')
    # masked before anything else can print it; GitHub replaces it with *** from here on
    print(f'::add-mask::{token}', flush=True)
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as fh:
        fh.write(token)


def deployment(answer):
    result = _result(answer)
    ident = result.get('id') if isinstance(result, dict) else None
    url = result.get('url') if isinstance(result, dict) else None
    if not (isinstance(ident, str) and SAFE.fullmatch(ident) and isinstance(url, str) and SAFE.fullmatch(url)):
        raise SystemExit('the deployment answer has no id and URL')
    print(f'Deployed {ident} at {url}')


def main(argv):
    if len(argv) == 3 and argv[0] == 'jwt':
        jwt(argv[1], argv[2])
    elif len(argv) == 2 and argv[0] == 'deployment':
        deployment(argv[1])
    else:
        raise SystemExit('usage: cf_answer.py jwt <answer> <jwt-file> | deployment <answer>')


if __name__ == '__main__':
    main(sys.argv[1:])
