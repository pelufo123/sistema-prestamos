import os
import psycopg2
from flask import Flask, render_template, request, redirect, url_for, session
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "clave_super_segura"

# ------------------------------
# 🔐 PROTEGER RUTAS
# ------------------------------
@app.before_request
def proteger_rutas():

    rutas_libres = [
        "login",
        "static"
    ]

    # 🔥 evitar errores endpoint None
    if request.endpoint is None:
        return

    # 🔥 permitir rutas libres
    if request.endpoint in rutas_libres:
        return

    # 🔥 validar sesión
    if not session.get("usuario"):
        return redirect(url_for("login"))
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

#323 2879658
# ------------------------------
def init_db():
    conn = conectar()

    if not conn:
        print("❌ No hay conexión a la base de datos")
        return

    cur = conn.cursor()

    try:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE,
            password TEXT
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id SERIAL PRIMARY KEY,
            nombre TEXT,
            telefono TEXT,
            direccion TEXT,
            usuario TEXT
        );
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
            total REAL,
            usuario TEXT
        );
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS abonos(
            id SERIAL PRIMARY KEY,
            prestamo_id INTEGER REFERENCES prestamos(id),
            monto REAL,
            fecha TIMESTAMP,
            tipo TEXT,
            mes INTEGER,
            usuario TEXT
        );
        """)

        conn.commit()
        print("✅ Base de datos lista")

    except Exception as e:
        print("❌ Error en DB:", e)

    finally:
        conn.close()

def crear_admin():
    conn = conectar()
    if not conn:
        return

    cur = conn.cursor()

    try:
        cur.execute("SELECT * FROM usuarios WHERE username=%s", ("admin",))
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO usuarios (username, password) VALUES (%s, %s)",
                ("admin", "1234")
            )
            conn.commit()
            print("✅ admin creado")
    except Exception as e:
        print("Error creando admin:", e)

    finally:
        conn.close()
# ------------------------------
# 💲 FORMATO
# ------------------------------
def formato(x):
    try:
        return "{:,.0f}".format(x).replace(",", ".")
    except:
        return "0"
# ------------------------------
# 📆 MESES DE ATRASO
# ------------------------------
def meses_atraso(fecha_inicio):
    hoy = datetime.now().date()

    if isinstance(fecha_inicio, str):
        fecha_inicio = datetime.strptime(fecha_inicio, "%Y-%m-%d").date()

    return (hoy.year - fecha_inicio.year) * 12 + (hoy.month - fecha_inicio.month)
# ------------------------------
# 🔹 VALIDACIÓN
# ------------------------------
def cliente_valido(cliente_id):
    return cliente_id and str(cliente_id).isdigit()

# ------------------------------
def interes_acumulado(pid, conn):
    cur = conn.cursor()

    cur.execute("SELECT capital, interes, fecha FROM prestamos WHERE id=%s", (pid,))
    data = cur.fetchone()

    if not data:
        return 0, 0

    capital, interes, fecha = data

    # 🔥 meses reales transcurridos
    meses = meses_atraso(fecha)

    if meses < 1:
        return 0, 0

    # 🔥 interés total generado
    interes_total = capital * (interes / 100) * meses

    # 🔥 interés ya pagado
    cur.execute("""
        SELECT SUM(monto)
        FROM abonos
        WHERE prestamo_id=%s AND tipo='interes'
    """, (pid,))
    pagado = cur.fetchone()[0] or 0

    deuda = interes_total - pagado

    if deuda < 0:
        deuda = 0

    return deuda, meses
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
# ------------------------------
# ------------------------------
# 🧠 CÁLCULO
# ------------------------------
def calcular(pid, conn):
    cur = conn.cursor()

    cur.execute("SELECT capital, interes, fecha FROM prestamos WHERE id=%s", (pid,))
    data = cur.fetchone()

    if not data:
        return 0, 0, 0, 0, 0

    capital, interes, fecha = data

    # 📅 meses transcurridos
    meses = meses_atraso(fecha)

    # 💰 interés total generado
    interes_total = capital * (interes / 100) * meses

    # 💸 interés pagado
    cur.execute("""
        SELECT SUM(monto)
        FROM abonos
        WHERE prestamo_id=%s AND tipo='interes'
    """, (pid,))
    abonado_interes = cur.fetchone()[0] or 0

    interes_restante = interes_total - abonado_interes
    if interes_restante < 0:
        interes_restante = 0

    # 💸 capital pagado
    cur.execute("""
        SELECT SUM(monto)
        FROM abonos
        WHERE prestamo_id=%s AND tipo='capital'
    """, (pid,))
    abonado_capital = cur.fetchone()[0] or 0

    capital_restante = capital - abonado_capital
    if capital_restante < 0:
        capital_restante = 0

    # 🔥 TOTAL REAL
    saldo_total = capital_restante + interes_restante

    return capital_restante, interes_restante, saldo_total, abonado_capital, abonado_interes

def meses_disponibles(pid, conn):
    cur = conn.cursor()

    # 📅 obtener fecha del préstamo
    cur.execute("SELECT fecha FROM prestamos WHERE id=%s", (pid,))
    data = cur.fetchone()

    if not data:
        return []

    fecha = data[0]

    if isinstance(fecha, str):
        fecha = datetime.strptime(fecha, "%Y-%m-%d")

    hoy = datetime.now()

    # 🔢 meses transcurridos
    total_meses = (hoy.year - fecha.year) * 12 + (hoy.month - fecha.month)

    if total_meses < 1:
        return []

    # 📌 meses ya pagados
    cur.execute("""
        SELECT mes FROM abonos
        WHERE prestamo_id=%s AND tipo='interes'
    """, (pid,))

    pagados = [m[0] for m in cur.fetchall()]

    # 🔥 generar meses válidos
    meses = []
    for i in range(1, total_meses + 1):
        if i not in pagados:
            meses.append(i)

    return meses

# ------------------------------
# 👤 GANANCIA POR CLIENTE
# ------------------------------
def ganancia_por_cliente(conn):
    cur = conn.cursor()

    cur.execute("""
        SELECT c.id, c.nombre
        FROM clientes c
    """)

    resultado = []

    for cid, nombre in cur.fetchall():

        cur.execute("""
            SELECT SUM(capital)
            FROM prestamos
            WHERE cliente_id=%s
        """, (cid,))
        capital = cur.fetchone()[0] or 0

        cur.execute("""
            SELECT SUM(a.monto)
            FROM abonos a
            JOIN prestamos p ON a.prestamo_id = p.id
            WHERE p.cliente_id=%s AND a.tipo='interes'
        """, (cid,))
        interes = cur.fetchone()[0] or 0

        cur.execute("""
            SELECT SUM(a.monto)
            FROM abonos a
            JOIN prestamos p ON a.prestamo_id = p.id
            WHERE p.cliente_id=%s AND a.tipo='capital'
        """, (cid,))
        recuperado = cur.fetchone()[0] or 0

        deuda = capital - recuperado

        resultado.append({
            "nombre": nombre,
            "capital": capital,
            "recuperado": recuperado,
            "interes": interes,
            "deuda": deuda
        })

    return resultado

# ------------------------------
# 🏠 INICIO
# ------------------------------
@app.route("/")
def inicio():
    return redirect(url_for("panel"))


# ------------------------------
# 📊 PANEL PRINCIPAL
# ------------------------------
@app.route("/panel", methods=["GET", "POST"])
def panel():

    conn = conectar()

    if conn is None:
        return "Error de conexión", 500

    cur = conn.cursor()

    # 🔥 FILTRO
    tipo = request.form.get("tipo") or "dia"
    fecha_str = request.form.get("fecha")

    if fecha_str:
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
    else:
        fecha = datetime.now().date()

    # =============================
    # 💰 CAPITAL TOTAL
    # =============================
    capital_total = 0

    cur.execute("SELECT id FROM prestamos")
    for (pid,) in cur.fetchall():
        cap_rest, _, _, _, _ = calcular(pid, conn)
        if cap_rest > 0:
            capital_total += cap_rest

    # =============================
    # 📅 HOY
    # =============================
    cur.execute("""
        SELECT monto, tipo FROM abonos
        WHERE DATE(fecha) = %s
    """, (fecha,))

    capital_dia = 0
    interes_dia = 0

    for m, t in cur.fetchall():
        if t == "capital":
            capital_dia += m
        else:
            interes_dia += m

    # =============================
    # 📆 MES
    # =============================
    inicio_mes = fecha.replace(day=1)

    cur.execute("""
        SELECT monto, tipo FROM abonos
        WHERE DATE(fecha) >= %s AND DATE(fecha) <= %s
    """, (inicio_mes, fecha))

    capital_mes = 0
    interes_mes = 0

    for m, t in cur.fetchall():
        if t == "capital":
            capital_mes += m
        else:
            interes_mes += m

    # =============================
    # 📈 ACUMULADO
    # =============================
    cur.execute("""
        SELECT monto, tipo FROM abonos
        WHERE DATE(fecha) <= %s
    """, (fecha,))

    capital_acumulado = 0
    interes_acumulado = 0

    for m, t in cur.fetchall():
        if t == "capital":
            capital_acumulado += m
        else:
            interes_acumulado += m

    # =============================
    # ⚠️ VENCIMIENTOS
    # =============================
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

    # =============================
    # 👥 CLIENTES
    # =============================
    clientes_ganancia = ganancia_por_cliente(conn)

    # =============================
    # 📋 PRÉSTAMOS (PARA ABONAR)
    # =============================
    cur.execute("""
        SELECT p.id, c.nombre, p.capital, p.interes
        FROM prestamos p
        JOIN clientes c ON p.cliente_id = c.id
    """)

    prestamos = []

    rows = cur.fetchall()

    for pid, nombre, capital, interes in rows:
        interes_mensual = capital * (interes / 100)

        prestamos.append({
            "id": pid,
            "nombre": nombre,
            "interes_mensual": interes_mensual
        })

    # 🔧 VARIABLES NECESARIAS
    capital = capital_dia
    interes = interes_dia

    cur.close()
    conn.close()

    return render_template(
        "panel.html",
        fecha=fecha,
        tipo=tipo,
        clientes_ganancia=clientes_ganancia,

        capital=formato(capital),
        interes=formato(interes),
        capital_total=formato(capital_total),

        capital_dia=formato(capital_dia),
        interes_dia=formato(interes_dia),

        capital_mes=formato(capital_mes),
        interes_mes=formato(interes_mes),

        capital_acumulado=formato(capital_acumulado),
        interes_acumulado=formato(interes_acumulado),

        por_vencer=por_vencer,
        vencidos=vencidos,

        prestamos=prestamos
    )


# ------------------------------
# 👥 CLIENTES
# ------------------------------
@app.route("/clientes", methods=["GET","POST"])
def clientes():

    conn = conectar()
    cur = conn.cursor()

    if request.method == "POST":
        cur.execute(
            "INSERT INTO clientes(nombre,telefono,direccion,usuario) VALUES (%s,%s,%s,%s)",
            (
                request.form["nombre"],
                request.form["telefono"],
                request.form["direccion"],
                session.get("usuario")
            )
        )
        conn.commit()

    # 🔹 Mostrar clientes
    cur.execute("SELECT * FROM clientes")
    clientes = cur.fetchall()

    resumen = []
    for c in clientes:
        cur.execute("SELECT SUM(capital) FROM prestamos WHERE cliente_id=%s", (c[0],))
        total = cur.fetchone()[0] or 0
        resumen.append(total)

    conn.close()

    return render_template(
        "clientes.html",
        clientes=clientes,
        resumen=resumen,
        formato=formato
    )
# ------------------------------
# 🔐 LOGIN
# ------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    conn = conectar()

    if not conn:
        return "Error de conexión a la base de datos"

    cur = conn.cursor()

    if request.method == "POST":
        try:
            user = request.form["username"]
            password = request.form["password"]

            cur.execute(
                "SELECT * FROM usuarios WHERE username=%s AND password=%s",
                (user, password)
            )
            usuario = cur.fetchone()

            if usuario:
                session["usuario"] = user
                return redirect(url_for("panel"))
            else:
                return render_template("login.html", error="Credenciales incorrectas")

        except Exception as e:
            return f"Error en login: {e}"

        finally:
            conn.close()

    # 🔹 GET (cuando entra por primera vez)
    conn.close()
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))
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

@app.route("/guardar_abono", methods=["POST"])
def guardar_abono():
    try:
        prestamo_id = request.form.get("prestamo_id")
        meses = int(request.form.get("meses"))
        interes_mensual = float(request.form.get("interes_mensual"))

        monto = meses * interes_mensual

        conn = conectar()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO abonos (prestamo_id, monto, tipo, fecha)
            VALUES (%s, %s, %s, NOW())
        """, (prestamo_id, monto, "interes"))

        conn.commit()
        conn.close()

        return {"ok": True}

    except Exception as e:
        print("ERROR GUARDAR ABONO:", e)
        return {"ok": False}
    
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

    # 🔹 clientes
    cur.execute("SELECT * FROM clientes")
    clientes = cur.fetchall()

    # =============================
    # 🔥 GUARDAR PRÉSTAMO (SIN DÍAS)
    # =============================
    if request.method == "POST":

        try:
            capital = float(request.form["capital"])
            interes = float(request.form["interes"])

            fecha = datetime.strptime(request.form["fecha"], "%Y-%m-%d")
            venc = datetime.strptime(request.form["vencimiento"], "%Y-%m-%d")

            if venc <= fecha:
                conn.close()
                return "❌ La fecha de vencimiento debe ser mayor"

            total = capital + (capital * interes / 100)

            cur.execute("""
                INSERT INTO prestamos (cliente_id, capital, interes, fecha, vencimiento, total)
                VALUES (%s,%s,%s,%s,%s,%s)
            """, (
                request.form["cliente"],
                capital,
                interes,
                fecha.date(),
                venc.date(),
                total
            ))

            conn.commit()

        except Exception as e:
            print("ERROR:", e)

    # =============================
    # 🔍 FILTRO POR FECHA
    # =============================
    fecha_filtro = request.args.get("fecha")

    if fecha_filtro:
        fecha_filtro = datetime.strptime(fecha_filtro, "%Y-%m-%d").date()
    else:
        fecha_filtro = datetime.now().date()

    cur.execute("""
        SELECT p.id, c.nombre, p.capital, p.total, p.fecha
        FROM prestamos p
        JOIN clientes c ON p.cliente_id = c.id
        WHERE p.fecha = %s
    """, (fecha_filtro,))

    prestamos_dia = cur.fetchall()
    cantidad_dia = len(prestamos_dia)

    # =============================
    # 📋 LISTA GENERAL
    # =============================
    cur.execute("""
        SELECT p.id, c.nombre, p.total
        FROM prestamos p
        JOIN clientes c ON p.cliente_id = c.id
    """)

    prestamos_lista = []

    for p in cur.fetchall():
        cap_rest, _, _, _, _ = calcular(p[0], conn)
        saldo = cap_rest + interes_hoy(p[0], conn)

        prestamos_lista.append({
            "id": p[0],
            "cliente": p[1],
            "total": formato(p[2]),
            "saldo": formato(saldo)
        })

    conn.close()

    return render_template(
        "prestamos.html",
        clientes=clientes,
        prestamos=prestamos_lista,
        prestamos_dia=prestamos_dia,
        cantidad_dia=cantidad_dia,
        fecha=fecha_filtro
    )


# ------------------------------
# 💸 ABONOS
# ------------------------------
# ------------------------------
# 💸 ABONOS
# ------------------------------
@app.route("/abonos", methods=["GET", "POST"])
def abonos():

    conn = conectar()

    if not conn:
        return "Error conexión DB"

    cur = conn.cursor()

    # =============================
    # 👥 CLIENTES
    # =============================
    cur.execute("SELECT * FROM clientes")
    clientes = cur.fetchall()

    prestamos = []
    mensaje = ""

    cliente_id = request.form.get("cliente") or request.args.get("cliente")

    # =============================
    # 🔍 CARGAR PRÉSTAMOS
    # =============================
    if cliente_valido(cliente_id):

        try:

            cur.execute("""
                SELECT p.id, c.nombre
                FROM prestamos p
                JOIN clientes c
                ON p.cliente_id = c.id
                WHERE c.id = %s
            """, (cliente_id,))

            resultados = cur.fetchall()

            for fila in resultados:

                pid = fila[0]
                nombre = fila[1]

                cap_rest, int_rest, total, _, _ = calcular(pid, conn)

                if total > 0:

                    # 🔥 meses pendientes
                    try:
                        meses = meses_disponibles(pid, conn)
                    except:
                        meses = []

                    # 🔥 interés mensual
                    cur.execute("""
                        SELECT capital, interes
                        FROM prestamos
                        WHERE id = %s
                    """, (pid,))

                    data = cur.fetchone()

                    if data:

                        capital_original = data[0]
                        tasa = data[1]

                        interes_mensual = capital_original * (tasa / 100)

                    else:

                        interes_mensual = 0

                    prestamos.append({

                        "id": pid,
                        "nombre": nombre,

                        "capital": formato(cap_rest),
                        "interes": formato(int_rest),
                        "total": formato(total),

                        "meses": meses,

                        "interes_mensual": formato(interes_mensual),
                        "interes_mensual_raw": interes_mensual
                    })

        except Exception as e:

            print("Error cargando préstamos:", e)

    # =============================
    # 💾 GUARDAR ABONO
    # =============================
    if request.method == "POST":

        # 🔥 si solo seleccionó cliente
        if not request.form.get("prestamo"):

            conn.close()

            return render_template(
                "abonos.html",
                clientes=clientes,
                prestamos=prestamos,
                mensaje=mensaje,
                cliente_id=cliente_id
            )

        try:

            pid = int(request.form.get("prestamo"))

            monto = float(request.form.get("monto") or 0)

            tipo = request.form.get("tipo")

            # 🔥 capital no usa mes
            if tipo == "capital":

                mes_pagado = 0

            else:

                mes_pagado = int(request.form.get("mes") or 0)

            # 🔥 cálculo actual
            cap_rest, int_rest, _, _, _ = calcular(pid, conn)

            # =============================
            # 🔥 VALIDACIONES
            # =============================
            if tipo == "capital" and monto > cap_rest:

                mensaje = "❌ Excede capital"

            elif tipo == "interes" and monto > int_rest:

                mensaje = "❌ Excede interés"

            else:

                cur.execute("""
                    INSERT INTO abonos (
                        prestamo_id,
                        monto,
                        fecha,
                        tipo,
                        mes
                    )
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    pid,
                    monto,
                    datetime.now(),
                    tipo,
                    mes_pagado
                ))

                conn.commit()

                conn.close()

                return redirect(
                    url_for(
                        "abonos",
                        cliente=cliente_id
                    )
                )

        except Exception as e:

            print("Error abonos:", e)

            mensaje = "❌ Error en datos"

    conn.close()

    return render_template(
        "abonos.html",
        clientes=clientes,
        prestamos=prestamos,
        mensaje=mensaje,
        cliente_id=cliente_id
    )

# ------------------------------
# 🔥 OBTENER INTERÉS AUTOMÁTICO
# ------------------------------
@app.route("/obtener_interes")
def obtener_interes():

    prestamo_id = request.args.get("prestamo_id")

    conn = conectar()

    if not conn:
        return {"interes": 0}

    cur = conn.cursor()

    try:

        cur.execute("""
            SELECT capital, interes
            FROM prestamos
            WHERE id=%s
        """, (prestamo_id,))

        data = cur.fetchone()

        if data:

            capital = data[0]
            interes = data[1]

            interes_mensual = capital * (interes / 100)

        else:

            interes_mensual = 0

    except Exception as e:

        print("ERROR obtener_interes:", e)

        interes_mensual = 0

    finally:

        cur.close()
        conn.close()

    return {"interes": interes_mensual}
# ------------------------------
if __name__ == "__main__":
    init_db()
    crear_admin()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)