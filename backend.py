import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect("sistema.db", check_same_thread=False)
cursor = conn.cursor()

# -------- TABLAS --------
cursor.execute("""CREATE TABLE IF NOT EXISTS clientes(
id INTEGER PRIMARY KEY AUTOINCREMENT,
nombre TEXT,
telefono TEXT,
direccion TEXT)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS prestamos(
id INTEGER PRIMARY KEY AUTOINCREMENT,
cliente_id INTEGER,
capital REAL,
interes REAL,
dias INTEGER,
fecha TEXT,
vencimiento TEXT,
total REAL)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS abonos(
id INTEGER PRIMARY KEY AUTOINCREMENT,
prestamo_id INTEGER,
monto REAL,
fecha TEXT)""")

conn.commit()

# -------- FUNCIONES --------
def formato(x):
    return "{:,.0f}".format(x).replace(",", ".")

def obtener_clientes():
    cursor.execute("SELECT * FROM clientes")
    return cursor.fetchall()

def agregar_cliente(nombre, telefono, direccion):
    cursor.execute("INSERT INTO clientes VALUES(NULL,?,?,?)",
                   (nombre, telefono, direccion))
    conn.commit()

def editar_cliente(id, nombre, telefono, direccion):
    cursor.execute("""UPDATE clientes 
                      SET nombre=?, telefono=?, direccion=? 
                      WHERE id=?""",
                   (nombre, telefono, direccion, id))
    conn.commit()

def eliminar_cliente(id):
    cursor.execute("DELETE FROM clientes WHERE id=?", (id,))
    conn.commit()

def prestamos_cliente(cliente_id):
    cursor.execute("SELECT id, fecha, total FROM prestamos WHERE cliente_id=?", (cliente_id,))
    return cursor.fetchall()

def agregar_prestamo(cliente_id, capital, interes, dias):
    total = capital + capital * interes / 100
    fecha = datetime.now()
    venc = fecha + timedelta(days=dias)

    cursor.execute("""INSERT INTO prestamos 
    VALUES(NULL,?,?,?,?,?,?,?)""",
                   (cliente_id, capital, interes, dias,
                    fecha.strftime("%Y-%m-%d"),
                    venc.strftime("%Y-%m-%d"),
                    total))
    conn.commit()

def calcular(prestamo_id):
    cursor.execute("SELECT total,vencimiento FROM prestamos WHERE id=?", (prestamo_id,))
    total, venc = cursor.fetchone()

    cursor.execute("SELECT SUM(monto) FROM abonos WHERE prestamo_id=?", (prestamo_id,))
    abonado = cursor.fetchone()[0] or 0

    saldo = total - abonado
    extra = 0

    if saldo < 0:
        extra = abs(saldo)
        saldo = 0

    hoy = datetime.now().date()
    venc = datetime.strptime(venc, "%Y-%m-%d").date()
    atraso = (hoy - venc).days if hoy > venc else 0

    return total, abonado, saldo, atraso, extra

def registrar_abono(prestamo_id, monto):
    cursor.execute("INSERT INTO abonos VALUES(NULL,?,?,?)",
                   (prestamo_id, monto, datetime.now().strftime("%Y-%m-%d")))
    conn.commit()