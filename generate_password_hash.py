import hashlib, getpass

pw = getpass.getpass("Unesi lozinku: ")
pw2 = getpass.getpass("Potvrdi lozinku: ")

if pw != pw2:
    print("❌ Lozinke se ne podudaraju!")
else:
    h = hashlib.sha256(pw.encode()).hexdigest()
    print(f"\n✅ Hash:\n{h}")
    print(f"\nDodaj u .env:\nAPP_PASSWORD_HASH={h}")
