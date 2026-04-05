from passlib.context import CryptContext
pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
hash_str = pwd_context.hash('test123')
with open('/app/app/valid_hash.txt', 'w') as f:
    f.write(hash_str)
