import os
import psycopg2
from flask import Flask, render_template, request, redirect
from datetime import datetime, timedelta

app = Flask(__name__)

# ------------------------------
# 🔌 CONEXIÓN DB
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
# 🧱 CREAR TABLAS
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
# 💰 FORMATO
# ------------------------------
def formato(x):
    return "{:,.0f}".format(x).replace(",", ".")

# ------------------------------
# 🧮 CALCULAR
# ------------------------------
def calcular(pid, conn):
    cur = conn.cursor()

    cur.execute("SELECT capital, interes FROM prestamos WHERE id=%s", (int(pid),))
    data = cur.fetchone()

    if not data:
        return 0,0,0,0,0

    capital, interes = data
    interes_total = capital * interes / 100

    cur.execute("SELECT SUM(monto) FROM abonos WHERE prestamo_id=%s AND tipo='capital'", (pid,))
    abonado_capital = cur.fetchone()[0] or 0

    cur.execute("SELECT SUM(monto) FROM abonos WHERE prestamo_id=%s AND tipo='interes'", (pid,))
    abonado_interes = cur.fetchone()[0] or 0

    capital_restante = capital - abonado_capital
    interes_restante = interes_total - abonado_interes
    saldo_total = capital_restante + interes_restante

    return capital_restante, interes_restante, saldo_total, abonado_capital, abonado_interes

# ------------------------------
# 📊 PANEL
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

    # 🔥 NUEVO: CAPITAL REAL (DESCUENTA ABONOS)
    cur.execute("SELECT id FROM prestamos")
    prestamos_ids = cur.fetchall()

    capital_total = 0
    for p in prestamos_ids:
        cap_rest, _, _, _, _ = calcular(p[0], conn)
        capital_total += cap_rest

    # 🔥 DIARIO
    cur.execute("SELECT monto, tipo, fecha FROM abonos")

    capital_dia = 0
    interes_dia = 0

    for m, t, f in cur.fetchall():
        if f.date() == fecha:
            if t == "capital":
                capital_dia += m
            else:
                interes_dia += m

    # 🔥 ALERTAS
    cur.execute("SELECT id, vencimiento FROM prestamos")

    por_vencer = []
    vencidos = []

    hoy = datetime.now().date()

    for pid, venc in cur.fetchall():

        cap_rest, int_rest, saldo, _, _ = calcular(pid, conn)

        if saldo <= 0:
            continue

        if isinstance(venc, str):
            venc = datetime.strptime(venc, "%Y-%m-%d").date()

        dias = (venc - hoy).days

        if dias < 0:
            vencidos.append((pid, abs(dias), formato(saldo)))
        elif dias <= 3:
            por_vencer.append((pid, dias, formato(saldo)))

    conn.close()

    return render_template("panel.html",
        capital_total=formato(capital_total),
        capital_dia=formato(capital_dia),
        interes_dia=formato(interes_dia),
        fecha=fecha,
        por_vencer=por_vencer,
        vencidos=vencidos
    )

# ------------------------------
# 💵 ABONOS (MEJORADO)
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
        data = cur.fetchall()

        for p in data:
            cap_rest, int_rest, saldo, _, _ = calcular(p[0], conn)

            if saldo > 0:
                prestamos.append((p[0], p[1], formato(saldo)))

    # 🔥 NUEVA LÓGICA
    if request.method == "POST" and request.form.get("prestamo"):
        pid = int(request.form.get("prestamo"))
        monto = float(request.form.get("monto"))
        tipo = request.form.get("tipo")

        cap_rest, int_rest, saldo, _, _ = calcular(pid, conn)

        hoy = datetime.now().date()

        # 🔥 SOLO 1 INTERÉS POR DÍA
        if tipo == "interes":
            cur.execute("""
                SELECT COUNT(*) FROM abonos
                WHERE prestamo_id=%s AND tipo='interes' AND DATE(fecha)=%s
            """, (pid, hoy))

            if cur.fetchone()[0] > 0:
                mensaje = "❌ Ya pagó interés hoy"
            elif monto > int_rest:
                mensaje = "❌ Excede interés"
            else:
                cur.execute(
                    "INSERT INTO abonos(prestamo_id,monto,fecha,tipo) VALUES (%s,%s,%s,%s)",
                    (pid, monto, datetime.now(), tipo)
                )
                conn.commit()
                mensaje = "✅ Interés registrado"

        elif tipo == "capital":
            if monto > cap_rest:
                mensaje = "❌ Excede capital pendiente"
            else:
                cur.execute(
                    "INSERT INTO abonos(prestamo_id,monto,fecha,tipo) VALUES (%s,%s,%s,%s)",
                    (pid, monto, datetime.now(), tipo)
                )
                conn.commit()
                mensaje = "✅ Capital abonado"

    conn.close()

    return render_template("abonos.html",
        clientes=clientes,
        prestamos=prestamos,
        mensaje=mensaje,
        cliente_id=cliente_id
    )

# ------------------------------
# 🔥 HISTORIAL MEJORADO
# ------------------------------
@app.route("/historial/<int:id>")
def historial(id):
    conn = conectar()

    if not conn:
        return "Error DB", 500

    cur = conn.cursor()

    cur.execute("SELECT * FROM clientes WHERE id=%s", (id,))
    if not cur.fetchone():
        conn.close()
        return "❌ Cliente no existe"

    cur.execute("""
        SELECT id, fecha
        FROM prestamos
        WHERE cliente_id=%s
    """, (id,))

    prestamos = cur.fetchall()

    data = []

    for p in prestamos:
        pid = p[0]

        cap_rest, int_rest, saldo, ab_cap, ab_int = calcular(pid, conn)

        # 🔥 CONTADOR INTERÉS
        cur.execute("""
            SELECT COUNT(*) FROM abonos
            WHERE prestamo_id=%s AND tipo='interes'
        """, (pid,))
        cantidad_interes = cur.fetchone()[0]

        cur.execute("""
            SELECT monto, tipo, fecha
            FROM abonos
            WHERE prestamo_id=%s
            ORDER BY fecha DESC
        """, (pid,))

        abonos = cur.fetchall()

        data.append({
            "prestamo": pid,
            "fecha": p[1],
            "capital_restante": formato(cap_rest),
            "interes_restante": formato(int_rest),
            "saldo": formato(saldo),
            "abonado_capital": formato(ab_cap),
            "abonado_interes": formato(ab_int),
            "cantidad_interes": cantidad_interes,
            "abonos": [(formato(a[0]), a[1], a[2]) for a in abonos]
        })

    conn.close()

    return render_template("historial.html", data=data)

# ------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)