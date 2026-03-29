import os
import sqlite3
from flask import Flask, render_template, request, redirect
from datetime import datetime, timedelta

app = Flask(__name__)

# ------------------------------
# CONEXIÓN A BASE DE DATOS
# ------------------------------
def conectar():
    db_url = os.getenv("DATABASE_URL")

    if db_url:
        import psycopg2
        return psycopg2.connect(db_url)

    # 🔥 fallback local (no rompe tu PC)
    return sqlite3.connect("sistema.db")

# ------------------------------
# INICIALIZAR BASE DE DATOS
# ------------------------------
def init_db():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes(
            id SERIAL PRIMARY KEY,
            nombre TEXT,
            telefono TEXT,
            direccion TEXT
        )
    """)

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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS abonos(
            id SERIAL PRIMARY KEY,
            prestamo_id INTEGER,
            monto REAL,
            fecha TEXT,
            tipo TEXT DEFAULT 'capital'
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

    if os.getenv("DATABASE_URL"):
        cursor.execute("SELECT total, vencimiento FROM prestamos WHERE id=%s", (pid,))
    else:
        cursor.execute("SELECT total, vencimiento FROM prestamos WHERE id=?", (pid,))

    data = cursor.fetchone()

    if not data:
        return 0,0,0,0,0

    total, venc = data

    if os.getenv("DATABASE_URL"):
        cursor.execute("SELECT SUM(monto) FROM abonos WHERE prestamo_id=%s AND tipo='capital'", (pid,))
    else:
        cursor.execute("SELECT SUM(monto) FROM abonos WHERE prestamo_id=? AND tipo='capital'", (pid,))

    abonado = cursor.fetchone()[0] or 0
    saldo = total - abonado

    hoy = datetime.now().date()
    venc = datetime.strptime(venc, "%Y-%m-%d").date()
    atraso = (hoy - venc).days if hoy > venc else 0

    conn.close()
    return total, abonado, saldo, atraso, 0

# ------------------------------
# PANEL PRINCIPAL
# ------------------------------
@app.route("/")
def panel():
    conn = conectar()
    cursor = conn.cursor()

    hoy = datetime.now().date()
    total = prox = vencidos = 0
    alertas = []

    capital_total = 0
    interes_hoy = 0
    capital_hoy = 0
    hoy_str = datetime.now().strftime("%Y-%m-%d")

    cursor.execute("""
        SELECT p.id, p.vencimiento, c.nombre, p.capital
        FROM prestamos p
        JOIN clientes c ON p.cliente_id = c.id
    """)

    for pid, venc_str, cliente, capital_p in cursor.fetchall():
        total_, abonado, saldo, atraso, _ = calcular(pid)

        capital_total += capital_p

        if saldo > 0:
            total += 1
            dias = (datetime.strptime(venc_str, "%Y-%m-%d").date() - hoy).days

            if dias < 0:
                vencidos += 1
            elif dias <= 3:
                prox += 1

            if dias == 2:
                alertas.append(f"⚠ {cliente} vence en 2 días")
            elif dias == 1:
                alertas.append(f"⚠ {cliente} vence MAÑANA")
            elif dias == 0:
                alertas.append(f"🚨 {cliente} vence HOY")

    cursor.execute("SELECT monto, tipo, fecha FROM abonos")

    for monto, tipo, fecha in cursor.fetchall():
        if hoy_str in fecha:
            if tipo == "interes":
                interes_hoy += monto
            elif tipo == "capital":
                capital_hoy += monto

    conn.close()

    return render_template("panel.html",
        total=total,
        prox=prox,
        vencidos=vencidos,
        alertas=alertas,
        capital_total=formato(capital_total),
        interes_hoy=formato(interes_hoy),
        capital_hoy=formato(capital_hoy)
    )

# ------------------------------
# CLIENTES
# ------------------------------
@app.route("/clientes", methods=["GET","POST"])
def clientes():
    conn = conectar()
    cursor = conn.cursor()

    if request.method == "POST":
        data = (request.form["nombre"], request.form["telefono"], request.form["direccion"])

        if os.getenv("DATABASE_URL"):
            cursor.execute("INSERT INTO clientes(nombre,telefono,direccion) VALUES (%s,%s,%s)", data)
        else:
            cursor.execute("INSERT INTO clientes(nombre,telefono,direccion) VALUES (?,?,?)", data)

        conn.commit()

    cursor.execute("SELECT * FROM clientes")
    lista = cursor.fetchall()

    conn.close()
    return render_template("clientes.html", clientes=lista)

# ------------------------------
# PRESTAMOS
# ------------------------------
@app.route("/prestamos", methods=["GET","POST"])
def prestamos():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM clientes")
    clientes = cursor.fetchall()

    if request.method == "POST":
        capital = float(request.form["capital"])
        interes = float(request.form["interes"])
        dias = int(request.form["dias"])
        total = capital + (capital * interes / 100)

        fecha = datetime.now()
        venc = fecha + timedelta(days=dias)

        data = (
            request.form["cliente"],
            capital,
            interes,
            dias,
            fecha.strftime("%Y-%m-%d"),
            venc.strftime("%Y-%m-%d"),
            total
        )

        if os.getenv("DATABASE_URL"):
            cursor.execute("""INSERT INTO prestamos(cliente_id, capital, interes, dias, fecha, vencimiento, total)
                              VALUES (%s,%s,%s,%s,%s,%s,%s)""", data)
        else:
            cursor.execute("""INSERT INTO prestamos(cliente_id, capital, interes, dias, fecha, vencimiento, total)
                              VALUES (?,?,?,?,?,?,?)""", data)

        conn.commit()

    cursor.execute("SELECT * FROM prestamos")
    lista = cursor.fetchall()

    conn.close()
    return render_template("prestamos.html", clientes=clientes, prestamos=lista)

# ------------------------------
# ABONOS
# ------------------------------
@app.route("/abonos", methods=["GET","POST"])
def abonos():
    conn = conectar()
    cursor = conn.cursor()

    mensaje = ""

    if request.method == "POST":
        pid = request.form.get("prestamo")
        monto = float(request.form.get("monto"))
        tipo = request.form.get("tipo")

        total, abonado, saldo, _, _ = calcular(pid)

        if tipo == "capital":
            if saldo <= 0:
                mensaje = "❌ Ya está pagado"
            elif monto > saldo:
                mensaje = "❌ Excede saldo"
            else:
                if os.getenv("DATABASE_URL"):
                    cursor.execute("INSERT INTO abonos VALUES (DEFAULT,%s,%s,%s,%s)",
                                   (pid, monto, datetime.now(), tipo))
                else:
                    cursor.execute("INSERT INTO abonos VALUES (NULL,?,?,?,?)",
                                   (pid, monto, datetime.now(), tipo))
                conn.commit()

        else:
            if os.getenv("DATABASE_URL"):
                cursor.execute("INSERT INTO abonos VALUES (DEFAULT,%s,%s,%s,%s)",
                               (pid, monto, datetime.now(), tipo))
            else:
                cursor.execute("INSERT INTO abonos VALUES (NULL,?,?,?,?)",
                               (pid, monto, datetime.now(), tipo))
            conn.commit()

    conn.close()
    return render_template("abonos.html", mensaje=mensaje)

# ------------------------------
# REPORTES
# ------------------------------
@app.route("/reportes", methods=["GET","POST"])
def reportes():
    conn = conectar()
    cursor = conn.cursor()

    fecha = request.form.get("fecha")

    interes_dia = capital_dia = 0
    interes_total = capital_total = 0

    cursor.execute("SELECT monto, tipo, fecha FROM abonos")

    for monto, tipo, f in cursor.fetchall():
        if tipo == "interes":
            interes_total += monto
        elif tipo == "capital":
            capital_total += monto

        if fecha and str(f).startswith(fecha):
            if tipo == "interes":
                interes_dia += monto
            elif tipo == "capital":
                capital_dia += monto

    conn.close()

    return render_template("reportes.html",
        fecha=fecha,
        interes_dia=formato(interes_dia),
        capital_dia=formato(capital_dia),
        interes_total=formato(interes_total),
        capital_total=formato(capital_total)
    )

# ------------------------------
# RUN
# ------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)