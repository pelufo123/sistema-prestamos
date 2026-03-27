import os
import sqlite3  # fallback si no hay DATABASE_URL
from flask import Flask, render_template, request, redirect
from datetime import datetime, timedelta

app = Flask(__name__)

# ------------------------------
# CONEXIÓN A BASE DE DATOS
# ------------------------------
def conectar():
    db_url = os.getenv("DATABASE_URL")  # intenta leer la variable de entorno

    if db_url:  # si existe DATABASE_URL (PostgreSQL)
        import psycopg2
        return psycopg2.connect(db_url)  # conecta a PostgreSQL en Render

    # SQLite local (modo fallback)
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
            fecha TEXT
        )
    """)

    # 🔥 Añadir columna tipo si no existe
    try:
        cursor.execute("ALTER TABLE abonos ADD COLUMN tipo TEXT DEFAULT 'Efectivo'")
    except:
        pass  # ignora si ya existe

    conn.commit()
    conn.close()

init_db()

# ------------------------------
# FORMATO NUMÉRICO
# ------------------------------
def formato(x):
    return "{:,.0f}".format(x).replace(",", ".")

# ------------------------------
# CÁLCULO DE SALDOS
# ------------------------------
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

    cursor.execute("""
        SELECT p.id, p.vencimiento, c.nombre
        FROM prestamos p
        JOIN clientes c ON p.cliente_id = c.id
    """)
    prestamos = cursor.fetchall()

    for p in prestamos:
        pid = p[0]
        vencimiento = datetime.strptime(p[1], "%Y-%m-%d").date()
        cliente = p[2]

        total_, abonado, saldo, atraso, extra = calcular(pid)

        if saldo > 0:
            total += 1
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

    return render_template("panel.html",
                           total=total,
                           prox=prox,
                           vencidos=vencidos,
                           alertas=alertas)

# ------------------------------
# RUTAS CLIENTES
# ------------------------------
@app.route("/clientes", methods=["GET","POST"])
def clientes():
    conn = conectar()
    cursor = conn.cursor()

    if request.method == "POST":
        cursor.execute("INSERT INTO clientes(nombre, telefono, direccion) VALUES (%s,%s,%s)" if os.getenv("DATABASE_URL") else "INSERT INTO clientes(nombre, telefono, direccion) VALUES (?,?,?)",
                       (request.form["nombre"],
                        request.form["telefono"],
                        request.form["direccion"]))
        conn.commit()

    cursor.execute("SELECT * FROM clientes")
    lista = cursor.fetchall()

    resumen = []
    for c in lista:
        cursor.execute("SELECT id FROM prestamos WHERE cliente_id=%s" if os.getenv("DATABASE_URL") else "SELECT id FROM prestamos WHERE cliente_id=?", (c[0],))
        prestamos_c = cursor.fetchall()
        saldo_total = 0
        for p in prestamos_c:
            total, abonado, saldo, atraso, extra = calcular(p[0])
            saldo_total += saldo
        resumen.append(saldo_total)

    conn.close()
    return render_template("clientes.html", clientes=lista, resumen=resumen, formato=formato)

# ------------------------------
# EDITAR CLIENTE
# ------------------------------
@app.route("/editar_cliente/<int:id>", methods=["GET","POST"])
def editar_cliente(id):
    conn = conectar()
    cursor = conn.cursor()

    if request.method == "POST":
        cursor.execute("UPDATE clientes SET nombre=%s, telefono=%s, direccion=%s WHERE id=%s" if os.getenv("DATABASE_URL") else "UPDATE clientes SET nombre=?, telefono=?, direccion=? WHERE id=?",
                       (request.form["nombre"],
                        request.form["telefono"],
                        request.form["direccion"],
                        id))
        conn.commit()
        return redirect("/clientes")

    cursor.execute("SELECT * FROM clientes WHERE id=%s" if os.getenv("DATABASE_URL") else "SELECT * FROM clientes WHERE id=?", (id,))
    cliente = cursor.fetchone()
    conn.close()
    return render_template("editar_cliente.html", cliente=cliente)

# ------------------------------
# ELIMINAR CLIENTE
# ------------------------------
@app.route("/eliminar_cliente/<int:id>")
def eliminar_cliente(id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM clientes WHERE id=%s" if os.getenv("DATABASE_URL") else "DELETE FROM clientes WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect("/clientes")

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

        cursor.execute("""INSERT INTO prestamos(cliente_id, capital, interes, dias, fecha, vencimiento, total)
                          VALUES (%s,%s,%s,%s,%s,%s,%s)""" if os.getenv("DATABASE_URL") else """INSERT INTO prestamos(cliente_id, capital, interes, dias, fecha, vencimiento, total)
                          VALUES (?,?,?,?,?,?,?)""",
                       (request.form["cliente"],
                        capital,
                        interes,
                        dias,
                        fecha.strftime("%Y-%m-%d"),
                        venc.strftime("%Y-%m-%d"),
                        total))
        conn.commit()

    cursor.execute("SELECT * FROM prestamos")
    lista = cursor.fetchall()
    conn.close()
    return render_template("prestamos.html", clientes=clientes, prestamos=lista, formato=formato)

# ------------------------------
# ABONOS
# ------------------------------
@app.route("/abonos", methods=["GET","POST"])
def abonos():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clientes")
    clientes = cursor.fetchall()
    prestamos = []
    historial = []
    mensaje = ""

    fecha_filtro = request.form.get("fecha_filtro")

    if request.method == "POST":
        cliente = request.form.get("cliente")
        prestamo_id = request.form.get("prestamo")
        monto = request.form.get("monto")
        tipo = request.form.get("tipo")

        # Mostrar solo los que deben
        if cliente and not prestamo_id:
            cursor.execute("SELECT id, fecha, total FROM prestamos WHERE cliente_id=%s ORDER BY id DESC" if os.getenv("DATABASE_URL") else "SELECT id, fecha, total FROM prestamos WHERE cliente_id=? ORDER BY id DESC", (cliente,))
            data = cursor.fetchall()
            for p in data:
                total, abonado, saldo, atraso, extra = calcular(p[0])
                if saldo <= 0:
                    continue
                estado = "VENCIDO" if atraso>0 else "ACTIVO"
                prestamos.append({
                    "id": p[0],
                    "fecha": p[1],
                    "saldo": formato(saldo),
                    "estado": estado
                })

        # Validación abono
        if prestamo_id and monto:
            monto = float(monto)
            total, abonado, saldo, atraso, extra = calcular(prestamo_id)
            if saldo <= 0:
                mensaje = "❌ Este préstamo ya está PAGADO"
            elif monto > saldo:
                mensaje = f"❌ No puede abonar más del saldo ({formato(saldo)})"
            else:
                cursor.execute("INSERT INTO abonos(prestamo_id, monto, fecha, tipo) VALUES (%s,%s,%s,%s)" if os.getenv("DATABASE_URL") else "INSERT INTO abonos(prestamo_id, monto, fecha, tipo) VALUES (?,?,?,?)",
                               (prestamo_id,
                                monto,
                                datetime.now().strftime("%Y-%m-%d %H:%M"),
                                tipo))
                conn.commit()

    # Historial
    query = """
        SELECT a.id, a.monto, a.tipo, a.fecha, c.nombre, p.cliente_id
        FROM abonos a
        JOIN prestamos p ON a.prestamo_id = p.id
        JOIN clientes c ON p.cliente_id = c.id
    """

    params = ()
    if fecha_filtro:
        query += " WHERE a.fecha LIKE %s" if os.getenv("DATABASE_URL") else " WHERE a.fecha LIKE ?"
        params = (f"{fecha_filtro}%",)

    query += " ORDER BY a.id DESC"

    cursor.execute(query, params)
    data_hist = cursor.fetchall()

    for h in data_hist:
        historial.append({
            "id": h[0],
            "monto": formato(h[1]),
            "tipo": h[2],
            "fecha": h[3],
            "cliente": h[4],
            "prestamo": h[5]
        })

    hoy = datetime.now().strftime("%Y-%m-%d")
    abonos_hoy = [h for h in historial if hoy in h["fecha"]]

    conn.close()

    return render_template("abonos.html",
                           clientes=clientes,
                           prestamos=prestamos,
                           historial=historial,
                           abonos_hoy=abonos_hoy,
                           mensaje=mensaje)

# ------------------------------
# ELIMINAR ABONO
# ------------------------------
@app.route("/eliminar_abono/<int:id>")
def eliminar_abono(id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM abonos WHERE id=%s" if os.getenv("DATABASE_URL") else "DELETE FROM abonos WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect("/abonos")

# ------------------------------
# HISTORIAL
# ------------------------------
@app.route("/historial/<int:id>")
def historial(id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("SELECT id, fecha, total FROM prestamos WHERE cliente_id=%s" if os.getenv("DATABASE_URL") else "SELECT id, fecha, total FROM prestamos WHERE cliente_id=?", (id,))
    prestamos = cursor.fetchall()
    data = []

    for p in prestamos:
        total, abonado, saldo, atraso, extra = calcular(p[0])
        cursor.execute("SELECT id, monto, tipo, fecha FROM abonos WHERE prestamo_id=%s ORDER BY id DESC" if os.getenv("DATABASE_URL") else "SELECT id, monto, tipo, fecha FROM abonos WHERE prestamo_id=? ORDER BY id DESC", (p[0],))
        abonos = cursor.fetchall()
        lista_abonos = [{"id": a[0], "monto": formato(a[1]), "tipo": a[2], "fecha": a[3]} for a in abonos]

        data.append({
            "prestamo_id": p[0],
            "fecha": p[1],
            "total": formato(total),
            "abonado": formato(abonado),
            "saldo": formato(saldo),
            "estado": "PAGADO" if saldo<=0 else "VENCIDO" if atraso>0 else "ACTIVO",
            "abonos": lista_abonos
        })

    conn.close()
    return render_template("historial.html", data=data)

# ------------------------------
# RUN APP
# ------------------------------
if __name__ == "__main__":
    # Permite acceso desde cualquier IP (Render)
    app.run(host="0.0.0.0", port=5000, debug=True)