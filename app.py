import os
import psycopg2
from flask import Flask, render_template, request, redirect
from datetime import datetime, timedelta

app = Flask(__name__)

# ------------------------------
# CONEXIÓN
# ------------------------------
def conectar():
    db_url = os.getenv("DATABASE_URL")

    if not db_url:
        print("❌ DATABASE_URL no existe")
        return None

    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    try:
        return psycopg2.connect(db_url, sslmode="require")
    except Exception as e:
        print("❌ Error:", e)
        return None

# ------------------------------
# INIT DB
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

    cur.execute("SELECT total, vencimiento FROM prestamos WHERE id=%s", (pid,))
    data = cur.fetchone()

    if not data:
        return 0,0,0,0

    total, venc = data

    cur.execute("SELECT SUM(monto) FROM abonos WHERE prestamo_id=%s AND tipo='capital'", (pid,))
    abonado = cur.fetchone()[0] or 0

    saldo = total - abonado
    hoy = datetime.now().date()

    if isinstance(venc, str):
        venc = datetime.strptime(venc, "%Y-%m-%d").date()

    atraso = (hoy - venc).days if hoy > venc else 0

    return total, abonado, saldo, atraso

# ------------------------------
@app.route("/")
def panel():
    conn = conectar()
    if not conn:
        return "Error DB", 500

    cur = conn.cursor()
    hoy = datetime.now().date()

    cur.execute("SELECT id, capital, vencimiento FROM prestamos")
    prestamos = cur.fetchall()

    total_activos = por_vencer = vencidos = 0
    capital_total = 0

    for p in prestamos:
        pid, capital, venc = p
        _,_,saldo,_ = calcular(pid, conn)

        capital_total += capital

        if saldo > 0:
            total_activos += 1

            if isinstance(venc, str):
                venc = datetime.strptime(venc, "%Y-%m-%d").date()

            dias = (venc - hoy).days

            if dias < 0:
                vencidos += 1
            elif dias <= 3:
                por_vencer += 1

    conn.close()

    return render_template("panel.html",
        total_activos=total_activos,
        por_vencer=por_vencer,
        vencidos=vencidos,
        capital_total=formato(capital_total)
    )

# ------------------------------
@app.route("/clientes", methods=["GET","POST"])
def clientes():
    conn = conectar()
    cur = conn.cursor()

    if request.method == "POST":
        cur.execute(
            "INSERT INTO clientes(nombre,telefono,direccion) VALUES (%s,%s,%s)",
            (request.form["nombre"], request.form["telefono"], request.form["direccion"])
        )
        conn.commit()

    cur.execute("SELECT * FROM clientes")
    clientes = cur.fetchall()

    conn.close()
    return render_template("clientes.html", clientes=clientes)

# ------------------------------
@app.route("/prestamos", methods=["GET","POST"])
def prestamos():
    conn = conectar()
    cur = conn.cursor()

    cur.execute("SELECT * FROM clientes")
    clientes = cur.fetchall()

    if request.method == "POST":
        capital = float(request.form["capital"])
        interes = float(request.form["interes"])
        dias = int(request.form["dias"])

        total = capital + (capital * interes / 100)

        fecha = datetime.now()
        venc = fecha + timedelta(days=dias)

        cur.execute("""
        INSERT INTO prestamos(cliente_id,capital,interes,dias,fecha,vencimiento,total)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (request.form["cliente"], capital, interes, dias, fecha.date(), venc.date(), total))

        conn.commit()

    cur.execute("SELECT * FROM prestamos")
    prestamos = cur.fetchall()

    conn.close()
    return render_template("prestamos.html", clientes=clientes, prestamos=prestamos)

# ------------------------------
@app.route("/abonos", methods=["GET","POST"])
def abonos():
    conn = conectar()
    cur = conn.cursor()

    cur.execute("SELECT * FROM clientes")
    clientes = cur.fetchall()

    prestamos = []
    mensaje = ""

    if request.method == "POST":
        cliente_id = request.form.get("cliente")

        if cliente_id:
            cur.execute("SELECT id FROM prestamos WHERE cliente_id=%s", (cliente_id,))
            prestamos = cur.fetchall()

        if request.form.get("prestamo"):
            pid = request.form.get("prestamo")
            monto = float(request.form.get("monto"))
            tipo = request.form.get("tipo")

            cur.execute(
                "INSERT INTO abonos(prestamo_id,monto,fecha,tipo) VALUES (%s,%s,%s,%s)",
                (pid, monto, datetime.now(), tipo)
            )
            conn.commit()
            mensaje = "✅ Guardado"

    conn.close()

    return render_template("abonos.html", clientes=clientes, prestamos=prestamos, mensaje=mensaje)

# ------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)