import os
import psycopg2
from flask import Flask, render_template, request, redirect
from datetime import datetime, timedelta

app = Flask(__name__)

# ------------------------------
# CONEXIÓN
# ------------------------------
def conectar():
    db_url = "postgresql://bd_prestamos_user:SxQ2cWHQaOFz65smYOuViKoJ2u85EjBQ@dpg-d73c825m5p6s73e6mnjg-a.virginia-postgres.render.com/bd_prestamos"
    try:
        return psycopg2.connect(db_url, sslmode="require")
    except Exception as e:
        print("Error conectando a PostgreSQL:", e)
        return None

# ------------------------------
# INIT DB
# ------------------------------
def init_db():
    conn = conectar()
    if not conn:
        print("No se pudo conectar a la base de datos.")
        return

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
            cliente_id INTEGER REFERENCES clientes(id),
            capital REAL,
            interes REAL,
            dias INTEGER,
            fecha DATE,
            vencimiento DATE,
            total REAL
        )
    """)
    cursor.execute("""
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
# FORMATO
# ------------------------------
def formato(x):
    return "{:,.0f}".format(x).replace(",", ".")

# ------------------------------
# CALCULAR SALDO Y ATRASO
# ------------------------------
def calcular(pid):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT total, vencimiento FROM prestamos WHERE id=%s", (pid,))
    data = cursor.fetchone()
    if not data:
        conn.close()
        return 0,0,0,0

    total, venc = data
    cursor.execute("SELECT SUM(monto) FROM abonos WHERE prestamo_id=%s AND tipo='capital'", (pid,))
    abonado = cursor.fetchone()[0] or 0
    saldo = total - abonado

    hoy = datetime.now().date()
    if isinstance(venc, str):
        venc = datetime.strptime(venc, "%Y-%m-%d").date()
    atraso = (hoy - venc).days if hoy > venc else 0
    conn.close()
    return total, abonado, saldo, atraso

# ------------------------------
# PANEL / DASHBOARD
# ------------------------------
@app.route("/")
def panel():
    conn = conectar()
    cursor = conn.cursor()

    hoy = datetime.now().date()

    # Totales
    cursor.execute("SELECT id, capital, interes, vencimiento FROM prestamos")
    total_activos = 0
    vencidos = 0
    prox_vencer = 0
    capital_prestado = 0
    capital_recogido = 0
    interes_recogido = 0

    prestamos_info = []

    for pid, capital, interes, venc in cursor.fetchall():
        total_, abonado, saldo, atraso = calcular(pid)
        capital_prestado += capital
        if saldo > 0:
            total_activos += 1
            dias = (venc - hoy) if isinstance(venc, datetime) else (datetime.fromisoformat(str(venc)).date() - hoy)
            dias = dias.days
            if dias < 0:
                vencidos += 1
            elif dias <= 3:
                prox_vencer += 1
        # Abonos
        cursor.execute("SELECT monto, tipo, fecha FROM abonos WHERE prestamo_id=%s", (pid,))
        abonos = cursor.fetchall()
        cap = sum([m for m,t,f in abonos if t=="capital"])
        int_ = sum([m for m,t,f in abonos if t=="interes"])
        capital_recogido += cap
        interes_recogido += int_

        prestamos_info.append({
            "id": pid,
            "capital": capital,
            "saldo": saldo,
            "abonado_capital": cap,
            "abonado_interes": int_,
            "vencimiento": venc,
            "abonos": [{"monto": m, "tipo": t, "fecha": f} for m,t,f in abonos]
        })

    conn.close()
    return render_template("panel.html",
        total_activos=total_activos,
        vencidos=vencidos,
        prox_vencer=prox_vencer,
        capital_prestado=capital_prestado,
        capital_recogido=capital_recogido,
        interes_recogido=interes_recogido,
        prestamos_info=prestamos_info,
        formato=formato,
        hoy=hoy
    )

# ------------------------------
# CLIENTES CRUD
# ------------------------------
@app.route("/clientes", methods=["GET","POST"])
def clientes():
    conn = conectar()
    cursor = conn.cursor()
    if request.method == "POST":
        cursor.execute("INSERT INTO clientes(nombre,telefono,direccion) VALUES (%s,%s,%s)",
                       (request.form["nombre"], request.form["telefono"], request.form["direccion"]))
        conn.commit()

    cursor.execute("SELECT * FROM clientes")
    clientes = cursor.fetchall()

    resumen = []
    for c in clientes:
        cursor.execute("SELECT id FROM prestamos WHERE cliente_id=%s", (c[0],))
        prestamos = cursor.fetchall()
        saldo_total = 0
        for p in prestamos:
            _,_,saldo,_ = calcular(p[0])
            saldo_total += saldo
        resumen.append(saldo_total)

    conn.close()
    return render_template("clientes.html", clientes=clientes, resumen=resumen, formato=formato)

@app.route("/editar_cliente/<int:id>", methods=["GET","POST"])
def editar_cliente(id):
    conn = conectar()
    cursor = conn.cursor()
    if request.method == "POST":
        cursor.execute("UPDATE clientes SET nombre=%s, telefono=%s, direccion=%s WHERE id=%s",
                       (request.form["nombre"], request.form["telefono"], request.form["direccion"], id))
        conn.commit()
        conn.close()
        return redirect("/clientes")

    cursor.execute("SELECT * FROM clientes WHERE id=%s", (id,))
    cliente = cursor.fetchone()
    conn.close()
    return render_template("editar_cliente.html", cliente=cliente)

@app.route("/eliminar_cliente/<int:id>")
def eliminar_cliente(id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM clientes WHERE id=%s", (id,))
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
        cursor.execute("""
            INSERT INTO prestamos(cliente_id,capital,interes,dias,fecha,vencimiento,total)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (
            request.form["cliente"],
            capital,
            interes,
            dias,
            fecha.date(),
            venc.date(),
            total
        ))
        conn.commit()

    cursor.execute("SELECT * FROM prestamos")
    prestamos = cursor.fetchall()
    conn.close()
    return render_template("prestamos.html", clientes=clientes, prestamos=prestamos)

# ------------------------------
# ABONOS
# ------------------------------
@app.route("/abonos", methods=["GET","POST"])
def abonos():
    conn = conectar()
    cursor = conn.cursor()
    mensaje = ""
    cursor.execute("SELECT * FROM clientes")
    clientes = cursor.fetchall()

    prestamos = []
    cliente_id = request.form.get("cliente")
    if cliente_id:
        cursor.execute("SELECT id, fecha FROM prestamos WHERE cliente_id=%s", (cliente_id,))
        data = cursor.fetchall()
        for p in data:
            _,_,saldo,_ = calcular(p[0])
            if saldo > 0:
                prestamos.append(p)

    if request.method == "POST" and request.form.get("prestamo"):
        pid = request.form.get("prestamo")
        monto = float(request.form.get("monto"))
        tipo = request.form.get("tipo")
        _,_,saldo,_ = calcular(pid)
        if tipo == "capital" and monto > saldo:
            mensaje = "❌ Excede saldo"
        else:
            cursor.execute("INSERT INTO abonos(prestamo_id,monto,fecha,tipo) VALUES (%s,%s,%s,%s)",
                           (pid, monto, datetime.now(), tipo))
            conn.commit()
            mensaje = "✅ Abono guardado"

    conn.close()
    return render_template("abonos.html",
        clientes=clientes,
        prestamos=prestamos,
        mensaje=mensaje
    )

# ------------------------------
# HISTORIAL
# ------------------------------
@app.route("/historial/<int:id>")
def historial(id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT id, fecha FROM prestamos WHERE cliente_id=%s", (id,))
    prestamos = cursor.fetchall()

    data = []
    for p in prestamos:
        _, abonado, saldo, _ = calcular(p[0])
        cursor.execute("SELECT monto,tipo,fecha FROM abonos WHERE prestamo_id=%s", (p[0],))
        abonos = cursor.fetchall()
        data.append({
            "prestamo": p[0],
            "fecha": p[1],
            "saldo": formato(saldo),
            "abonado": formato(abonado),
            "abonos": abonos
        })
    conn.close()
    return render_template("historial.html", data=data)

# ------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)