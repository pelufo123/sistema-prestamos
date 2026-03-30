import os
import psycopg2
from flask import Flask, render_template, request, redirect, jsonify, send_file
from datetime import datetime, timedelta
import io
import csv

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
# FORMATO ENTEROS
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
    if isinstance(venc, datetime):
        venc_date = venc.date()
    else:
        venc_date = venc
    atraso = (hoy - venc_date).days if hoy > venc_date else 0
    conn.close()
    return total, abonado, saldo, atraso

# ------------------------------
# DASHBOARD
# ------------------------------
@app.route("/")
def panel():
    return render_template("panel.html")

# ------------------------------
# API para actualizar dashboard
# ------------------------------
@app.route("/api/dashboard")
def api_dashboard():
    conn = conectar()
    cursor = conn.cursor()
    hoy = datetime.now().date()

    total_activos = prox_vencer = vencidos = 0
    capital_prestado = capital_recogido_hoy = interes_recogido_hoy = 0

    cursor.execute("SELECT id, capital, interes, vencimiento FROM prestamos")
    prestamos_info = []

    for pid, capital, interes, venc in cursor.fetchall():
        total_, abonado, saldo, atraso = calcular(pid)
        capital_prestado += capital
        if saldo > 0:
            total_activos += 1
            venc_date = venc if isinstance(venc, datetime) else datetime.fromisoformat(str(venc)).date()
            dias = (venc_date - hoy).days
            if dias < 0:
                vencidos += 1
            elif dias <= 3:
                prox_vencer += 1

        # Abonos
        cursor.execute("SELECT monto, tipo, fecha FROM abonos WHERE prestamo_id=%s", (pid,))
        abonos = cursor.fetchall()
        abonado_capital = abonado_interes = 0
        for m, t, f in abonos:
            f_date = f.date() if isinstance(f, datetime) else f
            if t == "capital":
                abonado_capital += m
            else:
                abonado_interes += m
            if f_date == hoy:
                if t == "capital":
                    capital_recogido_hoy += m
                else:
                    interes_recogido_hoy += m

        prestamos_info.append({
            "id": pid,
            "capital": int(capital),
            "saldo": int(saldo),
            "abonado_capital": int(abonado_capital),
            "abonado_interes": int(abonado_interes),
            "vencimiento": venc_date.strftime("%Y-%m-%d"),
            "abonos": [{"monto": int(m), "tipo": t, "fecha": f.strftime("%Y-%m-%d %H:%M")} for m,t,f in abonos]
        })

    conn.close()
    return jsonify({
        "total_activos": total_activos,
        "prox_vencer": prox_vencer,
        "vencidos": vencidos,
        "capital_prestado": int(capital_prestado),
        "capital_recogido_hoy": int(capital_recogido_hoy),
        "interes_recogido_hoy": int(interes_recogido_hoy),
        "prestamos_info": prestamos_info
    })

# ------------------------------
# Resto de CRUD clientes, prestamos, abonos y reportes
# ------------------------------
@app.route("/clientes", methods=["GET","POST"])
def clientes():
    conn = conectar()
    cursor = conn.cursor()
    if request.method=="POST":
        cursor.execute("INSERT INTO clientes(nombre,telefono,direccion) VALUES (%s,%s,%s)",
                       (request.form["nombre"],request.form["telefono"],request.form["direccion"]))
        conn.commit()
    cursor.execute("SELECT * FROM clientes")
    clientes = cursor.fetchall()
    conn.close()
    return render_template("clientes.html", clientes=clientes)

@app.route("/editar_cliente/<int:id>", methods=["GET","POST"])
def editar_cliente(id):
    conn = conectar()
    cursor = conn.cursor()
    if request.method=="POST":
        cursor.execute("UPDATE clientes SET nombre=%s,telefono=%s,direccion=%s WHERE id=%s",
                       (request.form["nombre"],request.form["telefono"],request.form["direccion"],id))
        conn.commit()
        conn.close()
        return redirect("/clientes")
    cursor.execute("SELECT * FROM clientes WHERE id=%s",(id,))
    cliente = cursor.fetchone()
    conn.close()
    return render_template("editar_cliente.html", cliente=cliente)

@app.route("/eliminar_cliente/<int:id>")
def eliminar_cliente(id):
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM clientes WHERE id=%s",(id,))
    conn.commit()
    conn.close()
    return redirect("/clientes")

@app.route("/reportes")
def reportes():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.nombre, p.capital, p.interes, p.fecha, p.vencimiento, p.total
        FROM prestamos p
        JOIN clientes c ON c.id = p.cliente_id
    """)
    data = cursor.fetchall()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Cliente","Capital","Interes","Fecha","Vencimiento","Total"])
    writer.writerows(data)
    output.seek(0)
    return send_file(io.BytesIO(output.getvalue().encode()), mimetype="text/csv", download_name="reporte.csv", as_attachment=True)

if __name__=="__main__":
    port = int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0", port=port)