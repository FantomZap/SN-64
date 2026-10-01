"""Keep this PC's user-folder paths out of the repository (plain Python, run from the repo root).

KiCad netlists, check reports and notes pick up absolute paths such as C:\\Users\\<name>\\..., which
puts the Windows account name on a public repository. This replaces the user-folder prefix in every
tracked text file with a neutral form, in all four spellings (C:\\Users\\name, the JSON-escaped
C:\\\\Users\\\\name, C:/Users/name and /c/Users/name):

    PowerShell scripts   'C:\\Users\\name\\x'  ->  "$env:USERPROFILE\\x"   (single quotes become double)
    shell scripts        /c/Users/name/x and C:/Users/name/x  ->  $HOME/x
    everything else      ->  %USERPROFILE%\\x   (or $HOME/x for the /c/ spelling)

The name is taken from this PC at run time and is never written into this file.

  python tools/scrub_local_paths.py            rewrite tracked files in place
  python tools/scrub_local_paths.py --check    list offenders and exit 1 (used by the pre-commit hook)
"""
import re
import subprocess
import sys
from pathlib import Path

NAME = re.escape(Path.home().name)
SEP = r'(?:\\\\|\\|/)+'
WIN = re.compile(r'[A-Za-z]:' + SEP + 'Users' + SEP + NAME + r'(?![A-Za-z0-9_])')
MSYS = re.compile(r'/[A-Za-z]/Users/' + NAME + r'(?![A-Za-z0-9_])')
ANY = re.compile(WIN.pattern + '|' + MSYS.pattern)
PS_QUOTED = re.compile(r"'" + WIN.pattern + r"([^'$`\"]*)'")


def tracked():
    out = subprocess.run(['git', 'ls-files', '-z'], capture_output=True, check=True).stdout
    return [Path(p.decode('utf-8')) for p in out.split(b'\0') if p]


def scrub(path, text):
    suffix = path.suffix.lower()
    if suffix == '.ps1':
        text = PS_QUOTED.sub(lambda m: '"$env:USERPROFILE' + m.group(1) + '"', text)
        text = WIN.sub('$env:USERPROFILE', text)
    elif suffix in ('.sh', '.bash', '.mk') or path.name == 'Makefile':
        text = WIN.sub('$HOME', text)
    else:
        text = WIN.sub('%USERPROFILE%', text)
    return MSYS.sub('$HOME', text)


def main():
    check = '--check' in sys.argv
    bad, changed = [], []
    for p in tracked():
        try:
            raw = p.read_bytes()
        except OSError:
            continue
        if b'\0' in raw[:8192]:
            continue                      # binary
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError:
            continue
        if not ANY.search(text):
            continue
        if check:
            bad.append(p)
            continue
        new = scrub(p, text)
        if new != text:
            p.write_bytes(new.encode('utf-8'))
            changed.append(p)
        if ANY.search(new):
            bad.append(p)
    if check:
        for p in bad:
            print(f'local user-folder path in {p.as_posix()}')
        print(f'{len(bad)} file(s) contain this PC\'s user-folder path' if bad else 'no local user-folder paths')
        return 1 if bad else 0
    print(f'scrubbed {len(changed)} file(s)' + (f'; {len(bad)} still contain the path: {[b.as_posix() for b in bad]}' if bad else ''))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
