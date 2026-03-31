import os
import psycopg2
from flask import Flask, render_template, request, redirect
from datetime import datetime, timedelta

app = Flask(__name__)

# ------------------------------
def conectar():
    db_url = os.getenv("DATABASE_URL")

    if not db_url:
        print("❌ No hay DATABASE_URL")
        return None

    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    try:
        return psycopg2.connect(db_url, sslmode="require")
    except Exception as e:
        print("❌ Error conexión:", e)
        return None

# ------------------------------
def init_db():
    conn = conectar()
    if not conn:
        return

    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS clientes(
        id SERIAL PRIMARY KEY,
        nombre TEXT,
        telefono TEXT,
        direccion TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS prestamos(
        id SERIAL PRIMARY KEY,
        cliente_id INTEGER REFERENCES clientes(id),
        capital REAL,
        interes REAL,
        dias INTEGER,
        fecha DATE,
        vencimiento DATE,
        total REAL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS abonos(
        id SERIAL PRIMARY KEY,
        prestamo_id INTEGER REFERENCES prestamos(id),
        monto REAL,
        fecha TIMESTAMP,
        tipo TEXT
    )
    """)

    conn.commit()
    conn.close()

init_db()

# ------------------------------
def formato(x):
    return "{:,.0f}".format(x).replace(",", ".")

# ------------------------------
def calcular(pid, conn):
    cur = conn.cursor()

    cur.execute("SELECT total FROM prestamos WHERE id=%s", (pid,))
    data = cur.fetchone()

    if not data:
        return 0, 0, 0, 0

    total = data[0]

    cur.execute("SELECT SUM(monto) FROM abonos WHERE prestamo_id=%s AND tipo='capital'", (pid,))
    abonado_capital = cur.fetchone()[0] or 0

    cur.execute("SELECT SUM(monto) FROM abonos WHERE prestamo_id=%s AND tipo='interes'", (pid,))
    abonado_interes = cur.fetchone()[0] or 0

    saldo = total - abonado_capital  # 🔥 CLAVE

    return total, abonado_capital, abonado_interes, saldo

# ------------------------------
@app.route("/", methods=["GET","POST"])
def panel():
    conn = conectar()
    if not conn:
        return "Error DB", 500

    cur = conn.cursor()
    hoy = datetime.now().date()

    fecha = request.form.get("fecha")
    if fecha:
        fecha = datetime.strptime(fecha, "%Y-%m-%d").date()
    else:
        fecha = hoy

    # CAPITAL TOTAL
    cur.execute("SELECT SUM(capital) FROM prestamos")
    capital_total = cur.fetchone()[0] or 0

    # PAGOS DEL DIA
    cur.execute("SELECT monto, tipo, fecha FROM abonos")
    capital_dia = 0
    interes_dia = 0

    for m, t, f in cur.fetchall():
        if f.date() == fecha:
            if t == "capital":
                capital_dia += m
            else:
                interes_dia += m

    # ALERTAS
    cur.execute("SELECT id, vencimiento FROM prestamos")
    proximos = 0
    vencidos = 0

    for pid, venc in cur.fetchall():
        total, ab_cap, ab_int, saldo = calcular(pid, conn)

        if saldo <= 0:
            continue

        dias = (venc - hoy).days

        if 0 <= dias <= 2:
            proximos += 1
        elif dias < 0:
            vencidos += 1

    conn.close()

    return render_template("panel.html",
        capital_total=formato(capital_total),
        capital_dia=formato(capital_dia),
        interes_dia=formato(interes_dia),
        proximos=proximos,
        vencidos=vencidos,
        fecha=fecha
    )

# ------------------------------
@app.route("/prestamos")
def prestamos():
    conn = conectar()
    cur = conn.cursor()

    cur.execute("""
        SELECT p.id, c.nombre, p.total
        FROM prestamos p
        JOIN clientes c ON p.cliente_id = c.id
    """)

    prestamos_raw = cur.fetchall()

    prestamos = []
    for p in prestamos_raw:
        total, ab_cap, ab_int, saldo = calcular(p[0], conn)

        prestamos.append({
            "id": p[0],
            "cliente": p[1],
            "total": formato(total),
            "abonado": formato(ab_cap),
            "saldo": formato(saldo)
        })

    conn.close()

    return render_template("prestamos.html", prestamos=prestamos)

# ------------------------------
@app.route("/abonos", methods=["GET","POST"])
def abonos():
    conn = conectar()
    cur = conn.cursor()

    cur.execute("SELECT * FROM clientes")
    clientes = cur.fetchall()

    prestamos = []
    mensaje = ""

    cliente_id = request.form.get("cliente")

    if cliente_id:
        cur.execute("""
            SELECT p.id, p.total
            FROM prestamos p
            WHERE p.cliente_id=%s
        """, (cliente_id,))
        data = cur.fetchall()

        for p in data:
            total, ab_cap, ab_int, saldo = calcular(p[0], conn)

            if saldo > 0:
                prestamos.append((p[0], formato(saldo)))  # 🔥 MUESTRA SALDO REAL

    if request.method == "POST" and request.form.get("prestamo"):
        pid = int(request.form.get("prestamo"))
        monto = float(request.form.get("monto"))
        tipo = request.form.get("tipo")

        total, ab_cap, ab_int, saldo = calcular(pid, conn)

        if tipo == "capital" and monto > saldo:
            mensaje = "❌ Excede saldo"
        else:
            cur.execute(
                "INSERT INTO abonos(prestamo_id,monto,fecha,tipo) VALUES (%s,%s,%s,%s)",
                (pid, monto, datetime.now(), tipo)
            )
            conn.commit()
            mensaje = "✅ Guardado"

    conn.close()

    return render_template("abonos.html",
        clientes=clientes,
        prestamos=prestamos,
        mensaje=mensaje,
        cliente_id=cliente_id
    )

# ------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)