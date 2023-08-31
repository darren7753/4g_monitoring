import os
from cryptography.fernet import Fernet

def encrypt_file(filename, encrypted_filename, key_filename):
    # Load or generate a key
    if not os.path.exists(key_filename):
        key = Fernet.generate_key()
        with open(key_filename, "wb") as key_file:
            key_file.write(key)
    else:
        with open(key_filename, "rb") as key_file:
            key = key_file.read()

    cipher = Fernet(key)

    # Read the file to encrypt
    with open(filename, "rb") as file:
        file_data = file.read()

    # Encrypt the file data
    encrypted_data = cipher.encrypt(file_data)

    # Write encrypted data to the new file
    with open(encrypted_filename, "wb") as encrypted_file:
        encrypted_file.write(encrypted_data)

    print(f"{filename} has been encrypted as {encrypted_filename} using key in {key_filename}")

# Usage
encrypt_file("monitoring-396408-6282add4508b.json", "encrypted_credentials.enc", "encryption_key.key")