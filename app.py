from flask import Flask, render_template, request, redirect
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__)

# -------- DB --------
def conectar():
    return sqlite3.connect("sistema.db")

def init_db():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""CREATE TABLE IF NOT EXISTS clientes(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT,
    telefono TEXT,
    direccion TEXT)""")

    cursor.execute("""CREATE TABLE IF NOT EXISTS prestamos(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER,
    capital REAL,
    interes REAL,
    dias INTEGER,
    fecha TEXT,
    vencimiento TEXT,
    total REAL)""")

    cursor.execute("""CREATE TABLE IF NOT EXISTS abonos(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prestamo_id INTEGER,
    monto REAL,
    fecha TEXT)""")

    # 🔥 AÑADIR TIPO (SIN BORRAR)
    try:
        cursor.execute("ALTER TABLE abonos ADD COLUMN tipo TEXT DEFAULT 'Efectivo'")
    except:
        pass

    conn.commit()
    conn.close()

init_db()

# -------- FORMATO --------
def formato(x):
    return "{:,.0f}".format(x).replace(",", ".")

# -------- CALCULO --------
def calcular(pid):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("SELECT total,vencimiento FROM prestamos WHERE id=?", (pid,))
    data = cursor.fetchone()

    if not data:
        return 0,0,0,0,0

    total, venc = data

    cursor.execute("SELECT SUM(monto) FROM abonos WHERE prestamo_id=?", (pid,))
    abonado = cursor.fetchone()[0] or 0

    saldo = total - abonado
    excedente = 0

    if saldo < 0:
        excedente = abs(saldo)
        saldo = 0

    hoy = datetime.now().date()
    venc = datetime.strptime(venc,"%Y-%m-%d").date()
    atraso = (hoy - venc).days if hoy > venc else 0

    conn.close()
    return total, abonado, saldo, atraso, excedente

# -------- PANEL (MEJORADO FINAL) --------
@app.route("/")
def panel():
    conn = conectar()
    cursor = conn.cursor()

    hoy = datetime.now().date()

    total = 0
    prox = 0
    vencidos = 0
    alertas = []

    prestamos = cursor.execute("""
        SELECT p.id, p.vencimiento, c.nombre
        FROM prestamos p
        JOIN clientes c ON p.cliente_id = c.id
    """).fetchall()

    for p in prestamos:
        pid = p[0]
        vencimiento = datetime.strptime(p[1], "%Y-%m-%d").date()
        cliente = p[2]

        total_, abonado, saldo, atraso, extra = calcular(pid)

        # 🔥 SOLO CONTAR SI HAY DEUDA
        if saldo > 0:

            total += 1
            dias = (vencimiento - hoy).days

            if dias < 0:
                vencidos += 1

            elif dias <= 3:
                prox += 1

            # 🔥 ALERTAS COMPLETAS
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

# -------- CLIENTES --------
@app.route("/clientes", methods=["GET","POST"])
def clientes():
    conn = conectar()
    cursor = conn.cursor()

    if request.method == "POST":
        cursor.execute("INSERT INTO clientes(nombre,telefono,direccion) VALUES(?,?,?)",
                       (request.form["nombre"],
                        request.form["telefono"],
                        request.form["direccion"]))
        conn.commit()

    lista = cursor.execute("SELECT * FROM clientes").fetchall()

    resumen = []
    for c in lista:
        prestamos = cursor.execute("SELECT id FROM prestamos WHERE cliente_id=?", (c[0],)).fetchall()
        saldo_total = 0

        for p in prestamos:
            total, abonado, saldo, atraso, extra = calcular(p[0])
            saldo_total += saldo

        resumen.append(saldo_total)

    conn.close()

    return render_template("clientes.html", clientes=lista, resumen=resumen, formato=formato)

# -------- EDITAR --------
@app.route("/editar_cliente/<int:id>", methods=["GET","POST"])
def editar_cliente(id):
    conn = conectar()
    cursor = conn.cursor()

    if request.method == "POST":
        cursor.execute("""UPDATE clientes SET nombre=?,telefono=?,direccion=? WHERE id=?""",
                       (request.form["nombre"],
                        request.form["telefono"],
                        request.form["direccion"],
                        id))
        conn.commit()
        return redirect("/clientes")

    cliente = cursor.execute("SELECT * FROM clientes WHERE id=?", (id,)).fetchone()
    conn.close()

    return render_template("editar_cliente.html", cliente=cliente)

# -------- ELIMINAR --------
@app.route("/eliminar_cliente/<int:id>")
def eliminar_cliente(id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM clientes WHERE id=?", (id,))
    conn.commit()
    conn.close()

    return redirect("/clientes")

# -------- PRESTAMOS --------
@app.route("/prestamos", methods=["GET","POST"])
def prestamos():
    conn = conectar()
    cursor = conn.cursor()

    clientes = cursor.execute("SELECT * FROM clientes").fetchall()

    if request.method == "POST":
        capital = float(request.form["capital"])
        interes = float(request.form["interes"])
        dias = int(request.form["dias"])

        total = capital + (capital * interes / 100)

        fecha = datetime.now()
        venc = fecha + timedelta(days=dias)

        cursor.execute("""INSERT INTO prestamos(cliente_id,capital,interes,dias,fecha,vencimiento,total)
                          VALUES(?,?,?,?,?,?,?)""",
                       (request.form["cliente"],
                        capital,
                        interes,
                        dias,
                        fecha.strftime("%Y-%m-%d"),
                        venc.strftime("%Y-%m-%d"),
                        total))
        conn.commit()

    lista = cursor.execute("SELECT * FROM prestamos").fetchall()
    conn.close()

    return render_template("prestamos.html", clientes=clientes, prestamos=lista, formato=formato)

# -------- ABONOS --------
@app.route("/abonos", methods=["GET","POST"])
def abonos():
    conn = conectar()
    cursor = conn.cursor()

    clientes = cursor.execute("SELECT * FROM clientes").fetchall()
    prestamos = []
    historial = []
    mensaje = ""

    fecha_filtro = request.form.get("fecha_filtro")

    if request.method == "POST":

        cliente = request.form.get("cliente")
        prestamo_id = request.form.get("prestamo")
        monto = request.form.get("monto")
        tipo = request.form.get("tipo")

        # 🔥 MOSTRAR SOLO LOS QUE DEBEN
        if cliente and not prestamo_id:
            data = cursor.execute("""
                SELECT id, fecha, total 
                FROM prestamos 
                WHERE cliente_id=?
                ORDER BY id DESC
            """, (cliente,)).fetchall()

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

        # 🔥 VALIDACIÓN
        if prestamo_id and monto:
            monto = float(monto)

            total, abonado, saldo, atraso, extra = calcular(prestamo_id)

            if saldo <= 0:
                mensaje = "❌ Este préstamo ya está PAGADO"
            elif monto > saldo:
                mensaje = f"❌ No puede abonar más del saldo ({formato(saldo)})"
            else:
                cursor.execute("""INSERT INTO abonos(prestamo_id,monto,fecha,tipo)
                                  VALUES(?,?,?,?)""",
                               (prestamo_id,
                                monto,
                                datetime.now().strftime("%Y-%m-%d %H:%M"),
                                tipo))
                conn.commit()

    query = """
        SELECT a.id, a.monto, a.tipo, a.fecha,
               c.nombre,
               p.id
        FROM abonos a
        JOIN prestamos p ON a.prestamo_id = p.id
        JOIN clientes c ON p.client_id = c.id
    """

    # 🔥 CORRECCIÓN SEGURA (NO BORRAR)
    query = query.replace("p.client_id", "p.cliente_id")

    params = ()

    if fecha_filtro:
        query += " WHERE a.fecha LIKE ?"
        params = (f"{fecha_filtro}%",)

    query += " ORDER BY a.id DESC"

    data_hist = cursor.execute(query, params).fetchall()

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

# -------- ELIMINAR ABONO --------
@app.route("/eliminar_abono/<int:id>")
def eliminar_abono(id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM abonos WHERE id=?", (id,))
    conn.commit()
    conn.close()

    return redirect("/abonos")

# -------- HISTORIAL --------
@app.route("/historial/<int:id>")
def historial(id):
    conn = conectar()
    cursor = conn.cursor()

    prestamos = cursor.execute("""
        SELECT id,fecha,total 
        FROM prestamos 
        WHERE cliente_id=?
    """, (id,)).fetchall()

    data = []

    for p in prestamos:
        total, abonado, saldo, atraso, extra = calcular(p[0])

        abonos = cursor.execute("""
            SELECT id,monto,tipo,fecha 
            FROM abonos 
            WHERE prestamo_id=?
            ORDER BY id DESC
        """, (p[0],)).fetchall()

        lista_abonos = []
        for a in abonos:
            lista_abonos.append({
                "id": a[0],
                "monto": formato(a[1]),
                "tipo": a[2],
                "fecha": a[3]
            })

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

# -------- RUN --------
if __name__ == "__main__":
    # 🔥 ORIGINAL (SE MANTIENE, NO BORRAR)
    # app.run(debug=True)

    # 🔥 NUEVO: PERMITE ACCESO DESDE CELULAR
    app.run(host="0.0.0.0", port=5000, debug=True)