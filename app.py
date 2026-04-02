import os
import psycopg2
from flask import Flask, render_template, request, redirect
from datetime import datetime, timedelta

app = Flask(__name__)

# ------------------------------
# 🔌 CONEXIÓN A BASE DE DATOS
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
# 🗄 CREACIÓN DE TABLAS
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
# 💲 FORMATO DE DINERO
# ------------------------------
def formato(x):
    try:
        return "{:,.0f}".format(x).replace(",", ".")
    except:
        return "0"

# ------------------------------
# 🔹 FUNCIONES EXTRA (NUEVAS)
# ------------------------------

def cliente_valido(cliente_id):
    return cliente_id and str(cliente_id).isdigit()

def interes_hoy(pid, conn):
    cur = conn.cursor()
    hoy = datetime.now().date()

    cur.execute("""
        SELECT COUNT(*) FROM abonos
        WHERE prestamo_id=%s AND tipo='interes' AND DATE(fecha)=%s
    """, (pid, hoy))

    pago_hoy = cur.fetchone()[0] or 0

    cur.execute("SELECT capital, interes FROM prestamos WHERE id=%s", (pid,))
    data = cur.fetchone()

    if not data:
        return 0

    capital, interes = data
    interes_total = capital * interes / 100

    return 0 if pago_hoy > 0 else interes_total

def saldo_real(pid, conn):
    cap_rest, _, _, _, _ = calcular(pid, conn)
    return cap_rest + interes_hoy(pid, conn)

# ------------------------------
# 🧠 CÁLCULO PRINCIPAL
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

    hoy = datetime.now().date()

    cur.execute("""
        SELECT SUM(monto) FROM abonos 
        WHERE prestamo_id=%s AND tipo='interes' AND DATE(fecha)=%s
    """, (pid, hoy))

    abonado_interes_hoy = cur.fetchone()[0] or 0

    capital_restante = capital - abonado_capital

    interes_restante = interes_total - abonado_interes_hoy
    if interes_restante < 0:
        interes_restante = 0

    saldo_total = capital_restante + interes_restante

    cur.execute("SELECT SUM(monto) FROM abonos WHERE prestamo_id=%s AND tipo='interes'", (pid,))
    abonado_interes_total = cur.fetchone()[0] or 0

    return capital_restante, interes_restante, saldo_total, abonado_capital, abonado_interes_total

# ------------------------------
# 🏠 PANEL
# ------------------------------
@app.route("/", methods=["GET","POST"])
def panel():
    conn = conectar()
    if not conn:
        return "Error DB", 500

    cur = conn.cursor()

    fecha = request.form.get("fecha")
    fecha = datetime.strptime(fecha, "%Y-%m-%d").date() if fecha else datetime.now().date()

    cur.execute("SELECT SUM(capital) FROM prestamos")
    total_prestado = cur.fetchone()[0] or 0

    cur.execute("SELECT SUM(monto) FROM abonos WHERE tipo='capital'")
    total_abonado = cur.fetchone()[0] or 0

    capital_total = total_prestado - total_abonado

    cur.execute("SELECT monto, tipo, fecha FROM abonos")

    capital_dia = 0
    interes_dia = 0

    for m, t, f in cur.fetchall():
        if f and f.date() == fecha:
            if t == "capital":
                capital_dia += m or 0
            else:
                interes_dia += m or 0

    cur.execute("SELECT id, vencimiento FROM prestamos")

    por_vencer = []
    vencidos = []

    hoy = datetime.now().date()

    for pid, venc in cur.fetchall():
        saldo = saldo_real(pid, conn)

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
# 💸 ABONOS (ARREGLADO)
# ------------------------------
@app.route("/abonos", methods=["GET","POST"])
def abonos():
    conn = conectar()
    if not conn:
        return "Error DB", 500

    cur = conn.cursor()

    cur.execute("SELECT * FROM clientes")
    clientes = cur.fetchall()

    prestamos = []
    mensaje = ""

    cliente_id = request.form.get("cliente") or request.args.get("cliente")

    if cliente_valido(cliente_id):

        cur.execute("""
            SELECT p.id, c.nombre
            FROM prestamos p
            JOIN clientes c ON p.cliente_id = c.id
            WHERE c.id=%s
        """, (cliente_id,))

        for pid, nombre in cur.fetchall():
            saldo = saldo_real(pid, conn)

            if saldo > 0:
                prestamos.append((pid, nombre, formato(saldo)))

    # 🔥 GUARDAR ABONO
    if request.method == "POST":

        if not request.form.get("prestamo"):
            conn.close()
            return redirect("/abonos")

        try:
            pid = int(request.form.get("prestamo"))
            monto = float(request.form.get("monto"))
            tipo = request.form.get("tipo")
        except:
            mensaje = "❌ Datos inválidos"
            conn.close()
            return render_template("abonos.html",
                clientes=clientes,
                prestamos=prestamos,
                mensaje=mensaje,
                cliente_id=cliente_id
            )

        cap_rest, int_rest, _, _, _ = calcular(pid, conn)

        if tipo == "interes":
            hoy = datetime.now().date()

            cur.execute("""
                SELECT COUNT(*) FROM abonos
                WHERE prestamo_id=%s AND tipo='interes' AND DATE(fecha)=%s
            """, (pid, hoy))

            if cur.fetchone()[0] > 0:
                mensaje = "❌ Ya pagó interés hoy"

        if tipo == "capital" and monto > cap_rest:
            mensaje = "❌ Excede capital"
        elif tipo == "interes" and monto > int_rest:
            mensaje = "❌ Excede interés"
        elif mensaje == "":
            cur.execute("""
                INSERT INTO abonos(prestamo_id,monto,fecha,tipo)
                VALUES (%s,%s,%s,%s)
            """, (pid, monto, datetime.now(), tipo))
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
# 📊 HISTORIAL
# ------------------------------
@app.route("/historial/<int:id>")
def historial(id):
    conn = conectar()
    cur = conn.cursor()

    cur.execute("SELECT * FROM clientes WHERE id=%s", (id,))
    if not cur.fetchone():
        return "❌ Cliente no existe"

    cur.execute("SELECT id, fecha FROM prestamos WHERE cliente_id=%s", (id,))
    prestamos = cur.fetchall()

    data = []

    for pid, fecha in prestamos:

        cap_rest, int_rest, _, ab_cap, ab_int = calcular(pid, conn)

        interes = interes_hoy(pid, conn)
        saldo = cap_rest + interes

        cur.execute("""
            SELECT monto, tipo, fecha
            FROM abonos WHERE prestamo_id=%s
            ORDER BY fecha DESC
        """, (pid,))

        abonos = cur.fetchall()

        cur.execute("""
            SELECT COUNT(*) FROM abonos
            WHERE prestamo_id=%s AND tipo='interes'
        """, (pid,))

        pagos_interes = cur.fetchone()[0]

        data.append({
            "prestamo": pid,
            "fecha": fecha,
            "capital_restante": formato(cap_rest),
            "interes_restante": formato(int_rest),
            "interes_hoy": formato(interes),
            "saldo": formato(saldo),
            "abonado_capital": formato(ab_cap),
            "abonado_interes": formato(ab_int),
            "abonos": abonos,
            "pagos_interes": pagos_interes
        })

    conn.close()

    return render_template("historial.html", data=data)

# ------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)