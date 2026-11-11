"""Run on the operator's trusted computer; store output only in server secrets."""
import getpass
import hashlib
import secrets

password = getpass.getpass('운영자 비밀번호 (16자 이상): ')
if len(password) < 16 or password != getpass.getpass('비밀번호 확인: '):
    raise SystemExit('16자 이상이며 두 입력이 같아야 합니다.')
salt = secrets.token_bytes(16)
digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
print(f'scrypt${salt.hex()}${digest.hex()}')
