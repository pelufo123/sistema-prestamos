import os
from flask import Flask, render_template, request, redirect
from datetime import datetime, timedelta

app = Flask(__name__)

# ------------------------------
# CONEXIÓN A BASE DE DATOS
# ------------------------------
def conectar():
    db_url = os.getenv("DATABASE_URL")  # PostgreSQL en Render
    if db_url:
        import psycopg2
        return psycopg2.connect(db_url)
    else:
        import sqlite3
        return sqlite3.connect("sistema.db")

# ------------------------------
# INICIALIZAR BASE DE DATOS
# ------------------------------
def init_db():
    conn = conectar()
    cursor = conn.cursor()

    # TABLA CLIENTES
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes(
            id SERIAL PRIMARY KEY,
            nombre TEXT,
            telefono TEXT,
            direccion TEXT
        )
    """)

    # TABLA PRESTAMOS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS prestamos(
            id SERIAL PRIMARY KEY,
            cliente_id INTEGER,
            capital REAL,
            interes REAL,
            dias INTEGER,
            fecha TEXT,
            vencimiento TEXT,
            total REAL
        )
    """)

    # TABLA ABONOS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS abonos(
            id SERIAL PRIMARY KEY,
            prestamo_id INTEGER,
            monto REAL,
            fecha TEXT,
            tipo TEXT DEFAULT 'Efectivo'
        )
    """)

    conn.commit()
    conn.close()

init_db()

# ------------------------------
# FUNCIONES AUXILIARES
# ------------------------------
def formato(x):
    return "{:,.0f}".format(x).replace(",", ".")

def calcular(pid):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT total, vencimiento FROM prestamos WHERE id=%s" if os.getenv("DATABASE_URL") else "SELECT total, vencimiento FROM prestamos WHERE id=?", (pid,))
    data = cursor.fetchone()
    if not data:
        return 0,0,0,0,0
    total, venc = data
    cursor.execute("SELECT SUM(monto) FROM abonos WHERE prestamo_id=%s" if os.getenv("DATABASE_URL") else "SELECT SUM(monto) FROM abonos WHERE prestamo_id=?", (pid,))
    abonado = cursor.fetchone()[0] or 0
    saldo = total - abonado
    excedente = 0
    if saldo < 0:
        excedente = abs(saldo)
        saldo = 0
    hoy = datetime.now().date()
    venc = datetime.strptime(venc, "%Y-%m-%d").date()
    atraso = (hoy - venc).days if hoy > venc else 0
    conn.close()
    return total, abonado, saldo, atraso, excedente

# ------------------------------
# RUTAS
# ------------------------------
@app.route("/")
def panel():
    conn = conectar()
    cursor = conn.cursor()
    hoy = datetime.now().date()
    total = 0
    prox = 0
    vencidos = 0
    alertas = []

    cursor.execute("""
        SELECT p.id, p.vencimiento, c.nombre
        FROM prestamos p
        JOIN clientes c ON p.cliente_id = c.id
    """)
    prestamos = cursor.fetchall()
    for p in prestamos:
        pid, vencimiento_str, cliente = p
        total_, abonado, saldo, atraso, extra = calcular(pid)
        if saldo > 0:
            total += 1
            vencimiento = datetime.strptime(vencimiento_str, "%Y-%m-%d").date()
            dias = (vencimiento - hoy).days
            if dias < 0:
                vencidos += 1
            elif dias <= 3:
                prox += 1
            if dias == 2:
                alertas.append(f"⚠ {cliente} tiene un préstamo que vence en 2 días")
            elif dias == 1:
                alertas.append(f"⚠ {cliente} tiene un préstamo que vence MAÑANA")
            elif dias == 0:
                alertas.append(f"🚨 {cliente} vence HOY")
    conn.close()
    return render_template("panel.html", total=total, prox=prox, vencidos=vencidos, alertas=alertas)

# (Aquí van tus rutas /clientes, /prestamos, /abonos, /editar_cliente, etc. igual que antes)

# ------------------------------
# RUN APP
# ------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Render asigna el puerto
    app.run(host="0.0.0.0", port=port, debug=True)