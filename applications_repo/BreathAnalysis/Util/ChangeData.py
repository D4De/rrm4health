import json
import random

def hex_to_int(h):
    """Converte stringa esadecimale tipo '0x1234' in int (con segno 16 bit)."""
    val = int(h, 16)
    if val >= 0x8000:  # gestisce valori signed 16 bit
        val -= 0x10000
    return val

def int_to_hex(i):
    """Converte int signed in stringa esadecimale tipo '0x1234'."""
    return hex((i + (1 << 16)) % (1 << 16))

def varia_valore(hex_val, ampiezza=10):
    """Aggiunge una piccola variazione casuale al valore esadecimale."""
    val = hex_to_int(hex_val)
    val_mod = val + random.randint(-ampiezza, ampiezza)
    return int_to_hex(val_mod)

def process_payload(record):

    if record["imuid"] in ["02", "03"]:
        for key in ["ax", "ay", "az", "gx", "gy", "gz", "mx", "my", "mz"]:
            record[key] = varia_valore(record[key])


    #print(f"File salvato come {output_file}")
    return record

