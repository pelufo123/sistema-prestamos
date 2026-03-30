# test_db.py
import os
from dotenv import load_dotenv
import psycopg2

# Cargar variables de entorno
load_dotenv()

db_url = os.getenv("DATABASE_URL")
print("DATABASE_URL leída:", db_url)

if not db_url:
    print("❌ No se encontró la variable de entorno DATABASE_URL")
else:
    try:
        conn = psycopg2.connect(db_url, sslmode="require")
        print("✅ Conexión a la base de datos exitosa")
        conn.close()
    except Exception as e:
        print("❌ Error conectando a la base de datos:", e)