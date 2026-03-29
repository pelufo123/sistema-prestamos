import os
from flask import Flask, render_template, request, redirect
from datetime import datetime, timedelta

app = Flask(__name__)

# ------------------------------
# CONEXIÓN A BASE DE DATOS
# ------------------------------
def conectar():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise Exception("❌ DATABASE_URL no configurada")
    
    import psycopg2
    return psycopg2.connect(db_url)

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

    cursor.execute("SELECT total, vencimiento FROM prestamos WHERE id=%s", (pid,))
    data = cursor.fetchone()

    if not data:
        return 0,0,0,0,0

    total, venc = data

    # 🔥 SOLO RESTA CAPITAL (IMPORTANTE)
    cursor.execute("SELECT SUM(monto) FROM abonos WHERE prestamo_id=%s AND tipo='capital'", (pid,))
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
# PANEL PRINCIPAL
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

    # 🔥 NUEVAS VARIABLES
    capital_total = 0
    interes_hoy = 0
    capital_hoy = 0
    hoy_str = datetime.now().strftime("%Y-%m-%d")

    cursor.execute("""
        SELECT p.id, p.vencimiento, c.nombre, p.capital
        FROM prestamos p
        JOIN clientes c ON p.cliente_id = c.id
    """)

    prestamos = cursor.fetchall()

    for p in prestamos:
        pid, vencimiento_str, cliente, capital_prestado = p

        total_, abonado, saldo, atraso, extra = calcular(pid)

        # 🔥 SUMAR CAPITAL TOTAL
        capital_total += capital_prestado

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

    # 🔥 ABONOS DEL DÍA
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
                           capital_hoy=formato(capital_hoy))

# ------------------------------
# ABONOS (ACTUALIZADO)
# ------------------------------
@app.route("/abonos", methods=["GET","POST"])
def abonos():
    conn = conectar()
    cursor = conn.cursor()

    mensaje = ""

    if request.method == "POST":
        prestamo_id = request.form.get("prestamo")
        monto = request.form.get("monto")
        tipo = request.form.get("tipo")

        if prestamo_id and monto and tipo:
            monto = float(monto)

            total, abonado, saldo, atraso, extra = calcular(prestamo_id)

            if tipo == "capital":
                if saldo <= 0:
                    mensaje = "❌ Este préstamo ya está pagado"
                elif monto > saldo:
                    mensaje = f"❌ No puede abonar más del saldo ({formato(saldo)})"
                else:
                    cursor.execute(
                        "INSERT INTO abonos(prestamo_id, monto, fecha, tipo) VALUES (%s,%s,%s,%s)",
                        (prestamo_id, monto, datetime.now().strftime("%Y-%m-%d %H:%M"), tipo)
                    )
                    conn.commit()

            elif tipo == "interes":
                cursor.execute(
                    "INSERT INTO abonos(prestamo_id, monto, fecha, tipo) VALUES (%s,%s,%s,%s)",
                    (prestamo_id, monto, datetime.now().strftime("%Y-%m-%d %H:%M"), tipo)
                )
                conn.commit()

    conn.close()
    return render_template("abonos.html", mensaje=mensaje)

# ------------------------------
# RUN APP
# ------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)