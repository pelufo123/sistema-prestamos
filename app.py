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

    # 🔥 CORRECCIÓN IMPORTANTE
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

    saldo = total - abonado_capital

    return total, abonado_capital, abonado_interes, saldo

# ------------------------------
@app.route("/", methods=["GET","POST"])
def panel():
    conn = conectar()
    if not conn:
        return "Error DB", 500

    cur = conn.cursor()

    fecha = request.form.get("fecha")
    if fecha:
        fecha = datetime.strptime(fecha, "%Y-%m-%d").date()
    else:
        fecha = datetime.now().date()

    cur.execute("SELECT SUM(capital) FROM prestamos")
    capital_total = cur.fetchone()[0] or 0

    cur.execute("SELECT monto, tipo, fecha FROM abonos")

    capital_dia = 0
    interes_dia = 0

    for m, t, f in cur.fetchall():
        if f.date() == fecha:
            if t == "capital":
                capital_dia += m
            else:
                interes_dia += m

    conn.close()

    return render_template("panel.html",
        capital_total=formato(capital_total),
        capital_dia=formato(capital_dia),
        interes_dia=formato(interes_dia),
        fecha=fecha
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

    resumen = []
    for c in clientes:
        cur.execute("SELECT SUM(capital) FROM prestamos WHERE cliente_id=%s", (c[0],))
        total = cur.fetchone()[0] or 0
        resumen.append(total)

    conn.close()

    return render_template("clientes.html", clientes=clientes, resumen=resumen, formato=formato)

# ------------------------------
@app.route("/editar_cliente/<int:id>", methods=["GET","POST"])
def editar_cliente(id):
    conn = conectar()
    cur = conn.cursor()

    if request.method == "POST":
        cur.execute("""
            UPDATE clientes SET nombre=%s, telefono=%s, direccion=%s WHERE id=%s
        """, (request.form["nombre"], request.form["telefono"], request.form["direccion"], id))
        conn.commit()
        conn.close()
        return redirect("/clientes")

    cur.execute("SELECT * FROM clientes WHERE id=%s", (id,))
    cliente = cur.fetchone()

    conn.close()
    return render_template("editar_cliente.html", cliente=cliente)

# ------------------------------
@app.route("/eliminar_cliente/<int:id>")
def eliminar_cliente(id):
    conn = conectar()
    cur = conn.cursor()

    cur.execute("DELETE FROM clientes WHERE id=%s", (id,))
    conn.commit()

    conn.close()
    return redirect("/clientes")

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

    # 🔥 CORREGIDO
    cur.execute("""
        SELECT p.id, c.nombre, p.total
        FROM prestamos p
        JOIN clientes c ON p.cliente_id = c.id
    """)

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

    cliente_id = request.form.get("cliente")

    if cliente_id:
        cur.execute("""
            SELECT p.id, c.nombre, p.total
            FROM prestamos p
            JOIN clientes c ON p.cliente_id = c.id
            WHERE c.id=%s
        """, (cliente_id,))
        prestamos = cur.fetchall()

    if request.method == "POST" and request.form.get("prestamo"):
        pid = request.form.get("prestamo")
        monto = float(request.form.get("monto"))
        tipo = request.form.get("tipo")

        total, abonado_cap, abonado_int, saldo = calcular(pid, conn)

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