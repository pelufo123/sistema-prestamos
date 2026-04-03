import os
import psycopg2
from flask import Flask, render_template, request, redirect, url_for
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
        conn = psycopg2.connect(db_url, sslmode="require")
        return conn
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
# 💲 FORMATO
# ------------------------------
def formato(x):
    try:
        return "{:,.0f}".format(x).replace(",", ".")
    except:
        return "0"

# ------------------------------
# 🔹 VALIDACIÓN
# ------------------------------
def cliente_valido(cliente_id):
    return cliente_id and str(cliente_id).isdigit()

# ------------------------------
# 🔥 INTERÉS DIARIO
# ------------------------------
def interes_hoy(pid, conn):
    cur = conn.cursor()
    hoy = datetime.now().date()

    cur.execute("""
        SELECT COUNT(*) FROM abonos
        WHERE prestamo_id=%s AND tipo='interes' AND DATE(fecha)=%s
    """, (pid, hoy))

    pago_hoy = cur.fetchone()[0]

    cur.execute("SELECT capital, interes FROM prestamos WHERE id=%s", (pid,))
    data = cur.fetchone()

    if not data:
        return 0

    capital, interes = data
    interes_total = capital * interes / 100

    return 0 if pago_hoy > 0 else interes_total

# ------------------------------
# 🧠 CÁLCULO
# ------------------------------
def calcular(pid, conn):
    cur = conn.cursor()

    cur.execute("SELECT capital, interes FROM prestamos WHERE id=%s", (pid,))
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
        return render_template("panel.html",
            capital_total="0",
            capital_dia="0",
            interes_dia="0",
            fecha=datetime.now().date(),
            por_vencer=[],
            vencidos=[]
        )

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
        if f.date() == fecha:
            if t == "capital":
                capital_dia += m
            else:
                interes_dia += m

    cur.execute("""
        SELECT p.id, p.vencimiento, c.nombre
        FROM prestamos p
        JOIN clientes c ON p.cliente_id = c.id
    """)

    por_vencer = []
    vencidos = []

    hoy = datetime.now().date()

    for pid, venc, nombre in cur.fetchall():

        cap_rest, _, _, _, _ = calcular(pid, conn)
        saldo = cap_rest + interes_hoy(pid, conn)

        if saldo <= 0:
            continue

        if isinstance(venc, str):
            venc = datetime.strptime(venc, "%Y-%m-%d").date()

        dias = (venc - hoy).days

        if dias < 0:
            vencidos.append((pid, nombre, abs(dias), formato(saldo)))
        elif dias <= 3:
            por_vencer.append((pid, nombre, dias, formato(saldo)))

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
# 🔥 RUTAS NUEVAS (AÑADIDAS)
# ------------------------------
@app.route("/inicio", methods=["GET","POST"])
def inicio():
    return redirect(url_for("panel"))

@app.route("/home")
def home():
    return redirect(url_for("panel"))

# ------------------------------
# 👥 CLIENTES
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
# ✏️ EDITAR CLIENTE
# ------------------------------
@app.route("/editar_cliente/<int:id>", methods=["GET","POST"])
def editar_cliente(id):
    conn = conectar()
    cur = conn.cursor()

    if request.method == "POST":
        cur.execute("""
            UPDATE clientes
            SET nombre=%s, telefono=%s, direccion=%s
            WHERE id=%s
        """, (
            request.form["nombre"],
            request.form["telefono"],
            request.form["direccion"],
            id
        ))
        conn.commit()
        conn.close()
        return redirect(url_for("clientes"))

    cur.execute("SELECT * FROM clientes WHERE id=%s", (id,))
    cliente = cur.fetchone()

    conn.close()
    return render_template("editar_cliente.html", cliente=cliente)

# ------------------------------
# 🗑 ELIMINAR CLIENTE
# ------------------------------
@app.route("/eliminar_cliente/<int:id>")
def eliminar_cliente(id):
    conn = conectar()
    cur = conn.cursor()

    cur.execute("DELETE FROM abonos WHERE prestamo_id IN (SELECT id FROM prestamos WHERE cliente_id=%s)", (id,))
    cur.execute("DELETE FROM prestamos WHERE cliente_id=%s", (id,))
    cur.execute("DELETE FROM clientes WHERE id=%s", (id,))

    conn.commit()
    conn.close()

    return redirect(url_for("clientes"))

# ------------------------------
# 📄 HISTORIAL
# ------------------------------
@app.route("/historial/<int:id>")
def historial(id):
    conn = conectar()
    cur = conn.cursor()

    cur.execute("SELECT nombre FROM clientes WHERE id=%s", (id,))
    cliente = cur.fetchone()

    cur.execute("""
        SELECT id, capital, total, fecha
        FROM prestamos
        WHERE cliente_id=%s
    """, (id,))
    prestamos = cur.fetchall()

    historial = []

    for p in prestamos:
        cur.execute("""
            SELECT monto, tipo, fecha
            FROM abonos
            WHERE prestamo_id=%s
        """, (p[0],))
        abonos = cur.fetchall()

        historial.append({
            "prestamo": p,
            "abonos": abonos
        })

    conn.close()

    return render_template("historial.html",
        cliente=cliente,
        historial=historial
    )

# ------------------------------
# 💼 PRÉSTAMOS
# ------------------------------
@app.route("/prestamos", methods=["GET","POST"])
def prestamos():
    conn = conectar()
    cur = conn.cursor()

    cur.execute("SELECT * FROM clientes")
    clientes = cur.fetchall()

    if request.method == "POST" and request.form.get("capital"):
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

    fecha_filtro = request.form.get("fecha")
    fecha_filtro = datetime.strptime(fecha_filtro, "%Y-%m-%d").date() if fecha_filtro else datetime.now().date()

    cur.execute("""
        SELECT p.id, c.nombre, p.capital, p.total, p.fecha
        FROM prestamos p
        JOIN clientes c ON p.cliente_id = c.id
        WHERE p.fecha=%s
    """, (fecha_filtro,))

    prestamos_dia = cur.fetchall()
    cantidad_dia = len(prestamos_dia)

    cur.execute("""
        SELECT p.id, c.nombre, p.total
        FROM prestamos p
        JOIN clientes c ON p.cliente_id = c.id
    """)

    prestamos = []

    for p in cur.fetchall():
        cap_rest, _, _, _, _ = calcular(p[0], conn)
        saldo = cap_rest + interes_hoy(p[0], conn)

        prestamos.append({
            "id": p[0],
            "cliente": p[1],
            "total": formato(p[2]),
            "saldo": formato(saldo)
        })

    conn.close()

    return render_template("prestamos.html",
        clientes=clientes,
        prestamos=prestamos,
        prestamos_dia=prestamos_dia,
        cantidad_dia=cantidad_dia,
        fecha_filtro=fecha_filtro
    )

# ------------------------------
# 💸 ABONOS
# ------------------------------
@app.route("/abonos", methods=["GET","POST"])
def abonos():
    conn = conectar()
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
            saldo = calcular(pid, conn)[0] + interes_hoy(pid, conn)
            if saldo > 0:
                prestamos.append((pid, nombre, formato(saldo)))

    if request.method == "POST" and request.form.get("prestamo"):

        pid = int(request.form.get("prestamo"))
        monto = float(request.form.get("monto"))
        tipo = request.form.get("tipo")

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
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)