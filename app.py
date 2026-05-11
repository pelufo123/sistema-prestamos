import os
import psycopg2
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
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

    # 🔥 evitar errores
    if request.endpoint is None:
        return

    # 🔥 permitir login y archivos static
    if request.endpoint in rutas_libres:
        return

    # 🔥 si NO hay sesión → login
    if "usuario" not in session:
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
def calcular(pid, conn):

    cur = conn.cursor()

    cur.execute("""
        SELECT capital, interes, fecha
        FROM prestamos
        WHERE id=%s
    """, (pid,))

    data = cur.fetchone()

    if not data:
        return 0, 0, 0, 0, 0

    capital_original, interes, fecha = data

    # =====================================
    # 💸 CAPITAL ABONADO
    # =====================================

    cur.execute("""
        SELECT SUM(monto)
        FROM abonos
        WHERE prestamo_id=%s
        AND tipo='capital'
    """, (pid,))

    abonado_capital = cur.fetchone()[0] or 0

    capital_restante = capital_original - abonado_capital

    if capital_restante < 0:
        capital_restante = 0

    # =====================================
    # 📆 MESES TRANSCURRIDOS
    # =====================================

    meses = meses_atraso(fecha)

    if meses < 0:
        meses = 0

    # =====================================
    # 🔥 INTERÉS SOBRE CAPITAL RESTANTE
    # =====================================

    interes_mensual_actual = capital_restante * (interes / 100)

    interes_total = interes_mensual_actual * meses

    # =====================================
    # 💰 INTERÉS PAGADO
    # =====================================

    cur.execute("""
        SELECT SUM(monto)
        FROM abonos
        WHERE prestamo_id=%s
        AND tipo='interes'
    """, (pid,))

    abonado_interes = cur.fetchone()[0] or 0

    interes_restante = interes_total - abonado_interes

    if interes_restante < 0:
        interes_restante = 0

    # =====================================
    # 💵 TOTAL
    # =====================================

    saldo_total = capital_restante + interes_restante

    return (
        capital_restante,
        interes_restante,
        saldo_total,
        abonado_capital,
        abonado_interes
    )

def meses_disponibles(pid, conn):

    cur = conn.cursor()

    # 🔥 obtener fecha préstamo
    cur.execute("""
        SELECT fecha
        FROM prestamos
        WHERE id=%s
    """, (pid,))

    data = cur.fetchone()

    if not data:
        return []

    fecha = data[0]

    hoy = datetime.now()

    # 🔥 permitir hasta 24 meses adelantados
    total_meses = 24

    # 🔥 meses ya pagados
    cur.execute("""
        SELECT mes
        FROM abonos
        WHERE prestamo_id=%s
        AND tipo='interes'
    """, (pid,))

    pagados = [m[0] for m in cur.fetchall()]

    meses = []

    nombres = [
        "Enero",
        "Febrero",
        "Marzo",
        "Abril",
        "Mayo",
        "Junio",
        "Julio",
        "Agosto",
        "Septiembre",
        "Octubre",
        "Noviembre",
        "Diciembre"
    ]

    for i in range(1, total_meses + 1):

        if i not in pagados:

            fecha_mes = fecha + timedelta(days=i * 30)

            nombre_mes = nombres[fecha_mes.month - 1]

            texto = f"{nombre_mes} {fecha_mes.year}"

            meses.append({
                "numero": i,
                "texto": texto
            })

    return meses

# ------------------------------
# 🏠 INICIO
# ------------------------------
@app.route("/")
def inicio():

    # 🔥 si NO ha iniciado sesión
    if "usuario" not in session:
        return redirect(url_for("login"))

    # 🔥 si ya inició sesión
    return redirect(url_for("panel"))
# =============================
# 👥 GANANCIA POR CLIENTE
# =============================
def ganancia_por_cliente(conn):

    cur = conn.cursor()

    cur.execute("""
        SELECT id, nombre
        FROM clientes
    """)

    resultado = []

    clientes = cur.fetchall()

    for cliente in clientes:

        cid = cliente[0]
        nombre = cliente[1]

        # 🔥 TOTAL PRESTADO
        cur.execute("""
            SELECT SUM(capital)
            FROM prestamos
            WHERE cliente_id=%s
        """, (cid,))

        capital = cur.fetchone()[0] or 0

        # 🔥 TOTAL CAPITAL RECUPERADO
        cur.execute("""
            SELECT SUM(a.monto)
            FROM abonos a
            JOIN prestamos p
            ON a.prestamo_id = p.id
            WHERE p.cliente_id=%s
            AND a.tipo='capital'
        """, (cid,))

        recuperado = cur.fetchone()[0] or 0

        # 🔥 TOTAL INTERÉS GANADO
        cur.execute("""
            SELECT SUM(a.monto)
            FROM abonos a
            JOIN prestamos p
            ON a.prestamo_id = p.id
            WHERE p.cliente_id=%s
            AND a.tipo='interes'
        """, (cid,))

        interes = cur.fetchone()[0] or 0

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
# 📊 PANEL PRINCIPAL
# ------------------------------
@app.route("/panel", methods=["GET", "POST"])
def panel():

    conn = conectar()

    if conn is None:
        return "Error de conexión", 500

    cur = conn.cursor()

    # =============================
    # 🔥 FILTRO FECHA
    # =============================
    tipo = request.form.get("tipo") or "dia"

    fecha_str = request.form.get("fecha")

    if fecha_str:

        fecha = datetime.strptime(
            fecha_str,
            "%Y-%m-%d"
        ).date()

    else:

        fecha = datetime.now().date()

    # =============================
    # 💰 CAPITAL EN CALLE
    # =============================
    capital_total = 0

    cur.execute("SELECT id FROM prestamos")

    for (pid,) in cur.fetchall():

        cap_rest, _, _, _, _ = calcular(pid, conn)

        if cap_rest > 0:

            capital_total += cap_rest

    # =============================
    # 📅 CAPITAL E INTERÉS DEL DÍA
    # =============================
    cur.execute("""
        SELECT monto, tipo
        FROM abonos
        WHERE DATE(fecha) = %s
    """, (fecha,))

    capital_dia = 0
    interes_dia = 0

    for monto, tipo_pago in cur.fetchall():

        if tipo_pago == "capital":

            capital_dia += monto

        else:

            interes_dia += monto

    # =============================
    # 📆 CAPITAL E INTERÉS MES
    # =============================
    inicio_mes = fecha.replace(day=1)

    cur.execute("""
        SELECT monto, tipo
        FROM abonos
        WHERE DATE(fecha) >= %s
        AND DATE(fecha) <= %s
    """, (inicio_mes, fecha))

    capital_mes = 0
    interes_mes = 0

    for monto, tipo_pago in cur.fetchall():

        if tipo_pago == "capital":

            capital_mes += monto

        else:

            interes_mes += monto

    # =============================
    # 📈 ACUMULADO TOTAL
    # =============================
    cur.execute("""
        SELECT monto, tipo
        FROM abonos
        WHERE DATE(fecha) <= %s
    """, (fecha,))

    capital_acumulado = 0
    interes_acumulado = 0

    for monto, tipo_pago in cur.fetchall():

        if tipo_pago == "capital":

            capital_acumulado += monto

        else:

            interes_acumulado += monto

    # =============================
    # ⚠️ PRÓXIMOS Y VENCIDOS
    # =============================
    cur.execute("""
        SELECT
            p.id,
            p.fecha,
            c.nombre

        FROM prestamos p

        JOIN clientes c
        ON p.cliente_id = c.id
    """)

    por_vencer = []
    vencidos = []

    hoy = datetime.now().date()

    for pid, fecha_inicio, nombre in cur.fetchall():

        # 🔥 saldo real actualizado
        cap_rest, int_rest, _, _, _ = calcular(pid, conn)

        saldo = cap_rest + int_rest

        # 🔥 si ya terminó
        if saldo <= 0:
            continue

        # 🔥 vencimiento automático 30 días
        fecha_vencimiento = fecha_inicio + timedelta(days=30)

        # 🔥 días restantes
        dias_restantes = (
            fecha_vencimiento - hoy
        ).days

        # =============================
        # 🔴 VENCIDOS
        # =============================
        if dias_restantes < 0:

            dias_atraso = abs(dias_restantes)

            vencidos.append((
                pid,
                nombre,
                dias_atraso,
                formato(saldo)
            ))

        # =============================
        # 🟠 PRÓXIMOS A VENCER
        # =============================
        elif dias_restantes <= 5:

            por_vencer.append((
                pid,
                nombre,
                dias_restantes,
                formato(saldo)
            ))

    # =============================
    # 👥 GANANCIA CLIENTES
    # =============================
    clientes_ganancia = ganancia_por_cliente(conn)

    # =============================
    # 📋 PRÉSTAMOS ACTIVOS
    # =============================
    cur.execute("""
        SELECT
            p.id,
            c.nombre,
            p.capital,
            p.interes

        FROM prestamos p

        JOIN clientes c
        ON p.cliente_id = c.id
    """)

    prestamos = []

    rows = cur.fetchall()

    for pid, nombre, capital, interes in rows:

        # =========================
        # CÁLCULO
        # =========================
        capital_restante, interes_restante, saldo_total, _, _ = calcular(pid, conn)

        # =========================
        # FECHA DEL PRÉSTAMOS
        # =========================
        cur.execute("""
            SELECT fecha
            FROM prestamos
            WHERE id=%s
        """, (pid,))

        fecha_prestamo = cur.fetchone()[0]

        # =========================
        # MESES PAGADOS
        # =========================
        cur.execute("""
            SELECT mes
            FROM abonos
            WHERE prestamo_id=%s
            AND tipo='interes'
            ORDER BY mes ASC
        """, (pid,))

        meses_pagados = [x[0] for x in cur.fetchall()]

        # =========================
        # GENERAR 24 MESES
        # =========================
        meses = []

        fecha_base = fecha_prestamo

        for i in range(24):

            mes_num = i + 1

            nueva_fecha = fecha_base + relativedelta(months=i)

            texto = nueva_fecha.strftime("%B %Y").capitalize()

            meses.append({
                "numero": mes_num,
                "texto": texto
            })

        # =========================
        # SIGUIENTE MES PENDIENTE
        # =========================
        siguiente_mes = 1

        while siguiente_mes in meses_pagados:
            siguiente_mes += 1

        # =========================
        # TEXTO DEL SIGUIENTE MES
        # =========================
        siguiente_mes_texto = ""

        for m in meses:
            if m["numero"] == siguiente_mes:
                siguiente_mes_texto = m["texto"]

        # =========================
        # ÚLTIMO MES PAGADO
        # =========================
        ultimo_pagado = ""

        if meses_pagados:

            ultimo_num = max(meses_pagados)

            for m in meses:
                if m["numero"] == ultimo_num:
                    ultimo_pagado = m["texto"]

        # =========================
        # GUARDAR
        # =========================
        prestamos.append({

            "id": pid,
            "nombre": nombre,

            "capital": formato(capital_restante),
            "interes": formato(interes_restante),
            "total": formato(saldo_total),

            "interes_num": interes_restante,

            "meses": meses,

            "siguiente_mes": siguiente_mes,
            "siguiente_mes_texto": siguiente_mes_texto,

            "ultimo_pagado": ultimo_pagado
        })

    # =============================
    # 🔧 VARIABLES
    # =============================
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
        return "Error de conexión DB"

    cur = conn.cursor()

    if request.method == "POST":

        user = request.form["username"]
        password = request.form["password"]

        cur.execute("""
            SELECT * FROM usuarios
            WHERE username=%s AND password=%s
        """, (user, password))

        usuario = cur.fetchone()

        if usuario:

            session["usuario"] = user

            return redirect(url_for("panel"))

        else:

            return render_template(
                "login.html",
                error="Credenciales incorrectas"
            )

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

    cur.execute(
        "SELECT nombre FROM clientes WHERE id=%s",
        (id,)
    )

    cliente = cur.fetchone()

    cur.execute("""
        SELECT id, capital, total, fecha
        FROM prestamos
        WHERE cliente_id=%s
        ORDER BY id DESC
    """, (id,))

    prestamos = cur.fetchall()

    historial = []

    for p in prestamos:

        cur.execute("""
            SELECT monto, tipo, fecha
            FROM abonos
            WHERE prestamo_id=%s
            ORDER BY fecha DESC
        """, (p[0],))

        abonos = cur.fetchall()

        historial.append({
            "prestamo": p,
            "abonos": abonos
        })

    conn.close()

    return render_template(
        "historial.html",
        cliente=cliente,
        historial=historial,
        formato=formato
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

    cliente_id = (
        request.form.get("cliente")
        or request.args.get("cliente")
    )

    # =============================
    # 🔍 CARGAR PRÉSTAMOS
    # =============================
    if cliente_valido(cliente_id):

        try:

            cur.execute("""
                SELECT
                    p.id,
                    c.nombre,
                    p.fecha
                FROM prestamos p
                JOIN clientes c
                ON p.cliente_id = c.id
                WHERE c.id = %s
            """, (cliente_id,))

            resultados = cur.fetchall()

            for fila in resultados:

                pid = fila[0]
                nombre = fila[1]
                fecha_prestamo = fila[2]

                # =============================
                # 💰 CALCULAR SALDOS
                # =============================
                cap_rest, int_rest, total, _, _ = calcular(
                    pid,
                    conn
                )

                cap_rest = round(cap_rest)
                int_rest = round(int_rest)
                total = round(total)

                if total <= 0:
                    continue

                # =============================
                # 📈 INTERÉS MENSUAL
                # =============================
                cur.execute("""
                    SELECT capital, interes
                    FROM prestamos
                    WHERE id=%s
                """, (pid,))

                data = cur.fetchone()

                if data:

                    capital_original = float(data[0])
                    tasa = float(data[1])

                    interes_mensual = round(
                        capital_original *
                        (tasa / 100)
                    )

                else:

                    interes_mensual = 0

                # =============================
                # 📅 MESES TRANSCURRIDOS
                # =============================
                meses_transcurridos = meses_atraso(
                    fecha_prestamo
                )

                if meses_transcurridos < 1:
                    meses_transcurridos = 1

                # 🔥 PERMITIR ADELANTAR
                meses_totales = (
                    meses_transcurridos + 24
                )

                # =============================
                # 📌 MESES PAGADOS
                # =============================
                cur.execute("""
                    SELECT DISTINCT mes
                    FROM abonos
                    WHERE prestamo_id=%s
                    AND tipo='interes'
                    AND mes IS NOT NULL
                    ORDER BY mes ASC
                """, (pid,))

                meses_pagados_db = [

                    int(x[0])

                    for x in cur.fetchall()

                    if x[0] is not None

                ]

                # =============================
                # 📌 ÚLTIMO MES PAGADO
                # =============================
                ultimo_mes_pagado = "Sin pagos"

                if meses_pagados_db:

                    ultimo_num = max(
                        meses_pagados_db
                    )

                    fecha_ultimo = (
                        fecha_prestamo +
                        relativedelta(
                            months=ultimo_num - 1
                        )
                    )

                    ultimo_mes_pagado = (
                        fecha_ultimo.strftime(
                            "%B %Y"
                        ).capitalize()
                    )

                # =============================
                # 📋 GENERAR MESES
                # 🔥 OCULTAR PAGADOS
                # =============================
                meses = []

                for i in range(
                    1,
                    meses_totales + 1
                ):

                    # 🔥 SI YA ESTÁ PAGADO
                    # NO MOSTRAR
                    if i in meses_pagados_db:
                        continue

                    fecha_mes = (
                        fecha_prestamo +
                        relativedelta(
                            months=i - 1
                        )
                    )

                    texto_mes = (
                        fecha_mes.strftime(
                            "%B %Y"
                        ).capitalize()
                    )

                    meses.append({

                        "numero": i,
                        "texto": texto_mes

                    })

                # =============================
                # 📆 CANTIDAD MESES PAGADOS
                # =============================
                cantidad_meses = len(
                    meses_pagados_db
                )

                # =============================
                # ➕ AGREGAR
                # =============================
                prestamos.append({

                    "id": pid,
                    "nombre": nombre,

                    "capital":
                        formato(cap_rest),

                    "interes":
                        formato(int_rest),

                    "total":
                        formato(total),

                    "capital_num":
                        cap_rest,

                    "interes_num":
                        interes_mensual,

                    "total_num":
                        total,

                    "meses":
                        meses,

                    "interes_mensual":
                        formato(interes_mensual),

                    "interes_mensual_raw":
                        interes_mensual,

                    "ultimo_mes_pagado":
                        ultimo_mes_pagado,

                    "cantidad_meses":
                        cantidad_meses

                })

        except Exception as e:

            print(
                "Error cargando préstamos:",
                e
            )

    # =============================
    # 💾 GUARDAR ABONO
    # =============================
    if request.method == "POST":

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

            pid = int(
                request.form.get(
                    "prestamo"
                )
            )

            monto = float(
                request.form.get(
                    "monto"
                )
                .replace(".", "")
                .replace(",", "")
            )

            tipo = request.form.get(
                "tipo"
            )

            # =============================
            # 📅 MES PAGADO
            # =============================
            if tipo == "capital":

                mes_pagado = 0

            else:

                mes_pagado = int(
                    request.form.get(
                        "mes"
                    ) or 0
                )

            # =============================
            # 💰 VALIDACIONES
            # =============================
            cap_rest, int_rest, _, _, _ = calcular(
                pid,
                conn
            )

            if (
                tipo == "capital"
                and monto > cap_rest
            ):

                mensaje = (
                    "❌ Excede capital"
                )

            elif (
                tipo == "interes"
                and monto <= 0
            ):

                mensaje = (
                    "❌ Valor inválido"
                )

            else:

                # =====================================
                # 🔥 INTERÉS
                # GUARDAR TODOS LOS MESES
                # =====================================
                if tipo == "interes":

                    for mes_actual in range(
                        1,
                        mes_pagado + 1
                    ):

                        # 🔥 VALIDAR DUPLICADO
                        cur.execute("""
                            SELECT id
                            FROM abonos
                            WHERE prestamo_id=%s
                            AND tipo='interes'
                            AND mes=%s
                        """, (

                            pid,
                            mes_actual

                        ))

                        existe = cur.fetchone()

                        # 🔥 SI NO EXISTE
                        if not existe:

                            cur.execute("""
                                INSERT INTO abonos (

                                    prestamo_id,
                                    monto,
                                    fecha,
                                    tipo,
                                    mes

                                )
                                VALUES (

                                    %s,
                                    %s,
                                    %s,
                                    %s,
                                    %s

                                )
                            """, (

                                pid,
                                interes_mensual,
                                datetime.now(),
                                "interes",
                                mes_actual

                            ))

                else:

                    # =====================================
                    # 💰 ABONO CAPITAL
                    # =====================================
                    cur.execute("""
                        INSERT INTO abonos (

                            prestamo_id,
                            monto,
                            fecha,
                            tipo,
                            mes

                        )
                        VALUES (

                            %s,
                            %s,
                            %s,
                            %s,
                            %s

                        )
                    """, (

                        pid,
                        round(monto),
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

            print(
                "Error abonos:",
                e
            )

            mensaje = (
                "❌ Error en datos"
            )

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
    mes = request.args.get("mes")

    conn = conectar()

    if not conn:
        return jsonify({"interes": 0})

    cur = conn.cursor()

    try:

        # =============================
        # VALIDAR SI YA PAGÓ ESE MES
        # =============================
        if mes:

            cur.execute("""
                SELECT COUNT(*)
                FROM abonos
                WHERE prestamo_id=%s
                AND tipo='interes'
                AND mes=%s
            """, (

                prestamo_id,
                mes

            ))

            ya_pagado = cur.fetchone()[0]

            if ya_pagado > 0:

                return jsonify({
                    "interes": 0
                })

        # =============================
        # OBTENER DATOS
        # =============================
        cur.execute("""
            SELECT capital, interes
            FROM prestamos
            WHERE id=%s
        """, (prestamo_id,))

        data = cur.fetchone()

        if data:

            capital = float(data[0])
            interes = float(data[1])

            interes_mensual = (
                capital *
                (interes / 100)
            )

        else:

            interes_mensual = 0

    except Exception as e:

        print("ERROR obtener_interes:", e)

        interes_mensual = 0

    finally:

        cur.close()
        conn.close()

    return jsonify({

        "interes":
        round(interes_mensual, 2)

    })
if __name__ == "__main__":
    init_db()
    crear_admin()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)