import ttkbootstrap as tb
from tkinter import messagebox
import sqlite3
from datetime import datetime, timedelta

# -------- APP --------
app = tb.Window(themename="darkly")
app.withdraw()

# -------- DB --------
conn = sqlite3.connect("sistema.db")
cursor = conn.cursor()

cursor.execute("""CREATE TABLE IF NOT EXISTS usuarios(
id INTEGER PRIMARY KEY AUTOINCREMENT,
username TEXT,
password TEXT)""")

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

conn.commit()

# usuario default
cursor.execute("SELECT * FROM usuarios WHERE username='admin'")
if not cursor.fetchone():
    cursor.execute("INSERT INTO usuarios VALUES(NULL,'admin','1234')")
    conn.commit()

# -------- FUNCIONES --------
def formato(x):
    return "{:,.0f}".format(x).replace(",", ".")

def calcular(pid):
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

    return total, abonado, saldo, atraso, excedente

# -------- NOTIFICACIONES --------
def actualizar_noti(label):
    hoy = datetime.now().date()
    total = prox = vencidos = 0

    cursor.execute("SELECT vencimiento FROM prestamos")
    for (v,) in cursor.fetchall():
        total += 1
        dias = (datetime.strptime(v,"%Y-%m-%d").date() - hoy).days

        if dias < 0:
            vencidos += 1
        elif dias <= 3:
            prox += 1

    if total == 0:
        texto = "⚪ No hay préstamos registrados"
    else:
        texto = f"📊 Total: {total}   🟡 Por vencer: {prox}   🔴 Vencidos: {vencidos}"

    label.config(text=texto)
    label.after(8000, lambda: actualizar_noti(label))

# -------- LOGIN --------
def login():
    cursor.execute("SELECT * FROM usuarios WHERE username=? AND password=?",
                   (user.get(), password.get()))
    if cursor.fetchone():
        login_win.destroy()
        app.deiconify()
    else:
        messagebox.showerror("Error","Datos incorrectos")

login_win = tb.Toplevel(app)
login_win.title("Login")
login_win.geometry("350x350")

tb.Label(login_win,text="Usuario").pack(pady=5)
user = tb.Entry(login_win)
user.pack()

tb.Label(login_win,text="Contraseña").pack(pady=5)
password = tb.Entry(login_win,show="*")
password.pack()

tb.Button(login_win,text="Ingresar",command=login).pack(pady=10)

# -------- PANEL --------
app.title("Sistema Contable PRO MAX")
app.geometry("1000x600")

tb.Label(app,text="SISTEMA CONTABLE",font=("Arial",20)).pack(pady=10)

frame = tb.Frame(app)
frame.pack(pady=20)

# -------- CLIENTES --------
def nuevo_cliente():
    win = tb.Toplevel(app)

    tb.Label(win,text="Nombre").pack(anchor="w")
    nombre = tb.Entry(win,width=40); nombre.pack()

    tb.Label(win,text="Teléfono").pack(anchor="w")
    telefono = tb.Entry(win,width=40); telefono.pack()

    tb.Label(win,text="Dirección").pack(anchor="w")
    direccion = tb.Entry(win,width=40); direccion.pack()

    def guardar():
        cursor.execute("INSERT INTO clientes VALUES(NULL,?,?,?)",
                       (nombre.get(),telefono.get(),direccion.get()))
        conn.commit()
        win.destroy()

    tb.Button(win,text="Guardar",command=guardar).pack(pady=10)

def ver_clientes():
    win = tb.Toplevel(app)

    tabla = tb.Treeview(win,columns=("ID","Nombre","Teléfono","Dirección"),show="headings")
    tabla.pack(fill="both",expand=True)

    for col in tabla["columns"]:
        tabla.heading(col,text=col)
        tabla.column(col, anchor="center", width=130)

    def cargar():
        tabla.delete(*tabla.get_children())
        cursor.execute("SELECT * FROM clientes")
        for c in cursor.fetchall():
            tabla.insert("", "end", values=c)

    cargar()

    def editar():
        item = tabla.selection()
        if not item: return
        data = tabla.item(item)["values"]

        edit = tb.Toplevel(app)

        n = tb.Entry(edit); n.insert(0,data[1]); n.pack()
        t = tb.Entry(edit); t.insert(0,data[2]); t.pack()
        d = tb.Entry(edit); d.insert(0,data[3]); d.pack()

        def guardar():
            cursor.execute("UPDATE clientes SET nombre=?,telefono=?,direccion=? WHERE id=?",
                           (n.get(),t.get(),d.get(),data[0]))
            conn.commit()
            edit.destroy()
            cargar()

        tb.Button(edit,text="Guardar",command=guardar).pack()

    def eliminar():
        item = tabla.selection()
        if not item: return
        idc = tabla.item(item)["values"][0]
        cursor.execute("DELETE FROM clientes WHERE id=?", (idc,))
        conn.commit()
        cargar()

    def historial():
        item = tabla.selection()
        if not item: return
        cliente_id = tabla.item(item)["values"][0]

        win2 = tb.Toplevel(app)

        tabla2 = tb.Treeview(win2,
        columns=("Fecha","Prestamo","Abono","Saldo restante","Estado"),
        show="headings")
        tabla2.pack(fill="both",expand=True)

        for col in tabla2["columns"]:
            tabla2.heading(col,text=col)
            tabla2.column(col, anchor="center", width=120)

        cursor.execute("SELECT id,fecha,total FROM prestamos WHERE cliente_id=?", (cliente_id,))
        for p in cursor.fetchall():
            total,abonado,saldo,atraso,extra = calcular(p[0])

            estado = "PAGADO" if saldo<=0 else "VENCIDO" if atraso>0 else "ACTIVO"
            extra_txt = "EXCEDENTE" if extra>0 else ""

            tabla2.insert("", "end",
                values=(p[1],formato(total),formato(abonado),formato(saldo),
                        estado+" "+extra_txt))

    btn_frame = tb.Frame(win)
    btn_frame.pack(pady=10)

    tb.Button(btn_frame,text="Editar",width=15,command=editar).grid(row=0,column=0,padx=5)
    tb.Button(btn_frame,text="Eliminar",width=15,command=eliminar).grid(row=0,column=1,padx=5)
    tb.Button(btn_frame,text="Historial",width=15,command=historial).grid(row=0,column=2,padx=5)

# -------- PRESTAMOS --------
def nuevo_prestamo():
    win = tb.Toplevel(app)

    clientes = {}
    lista = []

    cursor.execute("SELECT id,nombre FROM clientes")
    for c in cursor.fetchall():
        txt = f"ID {c[0]} - {c[1]}"
        lista.append(txt)
        clientes[txt] = c[0]

    tb.Label(win,text="Cliente").pack(anchor="w")
    combo = tb.Combobox(win,values=lista,state="readonly")
    combo.pack()

    tb.Label(win,text="Dinero prestado").pack(anchor="w")
    capital = tb.Entry(win); capital.pack()

    tb.Label(win,text="Interés %").pack(anchor="w")
    interes = tb.Entry(win); interes.pack()

    tb.Label(win,text="Días").pack(anchor="w")
    dias = tb.Entry(win); dias.pack()

    def guardar():
        cliente_id = clientes.get(combo.get())
        if not cliente_id:
            messagebox.showerror("Error","Selecciona cliente")
            return

        cap = float(capital.get())
        inte = float(interes.get())
        d = int(dias.get())

        total = cap + cap*inte/100
        fecha = datetime.now()
        venc = fecha + timedelta(days=d)

        cursor.execute("INSERT INTO prestamos VALUES(NULL,?,?,?,?,?,?,?)",
                       (cliente_id,cap,inte,d,
                        fecha.strftime("%Y-%m-%d"),
                        venc.strftime("%Y-%m-%d"),
                        total))
        conn.commit()
        win.destroy()

    tb.Button(win,text="Guardar",command=guardar).pack(pady=10)

# -------- ABONOS --------
def registrar_abono():
    win = tb.Toplevel(app)
    win.title("Registrar Abono")
    win.geometry("700x550")

    clientes = {}
    lista_clientes = []

    cursor.execute("SELECT id,nombre FROM clientes")
    for c in cursor.fetchall():
        txt = f"ID {c[0]} - {c[1]}"
        lista_clientes.append(txt)
        clientes[txt] = c[0]

    tb.Label(win,text="Seleccionar Cliente").pack(anchor="w")
    combo_cliente = tb.Combobox(win,values=lista_clientes,state="readonly")
    combo_cliente.pack(fill="x")

    tabla = tb.Treeview(win,
        columns=("ID","Fecha","Total","Abonado","Saldo","Estado"),
        show="headings")
    tabla.pack(fill="both",expand=True,pady=10)

    for col in tabla["columns"]:
        tabla.heading(col,text=col)
        tabla.column(col,anchor="center")

    frame_info = tb.Frame(win)
    frame_info.pack(fill="x")

    lbl_total = tb.Label(frame_info,text="💰 Total:")
    lbl_total.grid(row=0,column=0,sticky="w")

    lbl_abonado = tb.Label(frame_info,text="💵 Abonado:")
    lbl_abonado.grid(row=1,column=0,sticky="w")

    lbl_saldo = tb.Label(frame_info,text="📉 Saldo:")
    lbl_saldo.grid(row=2,column=0,sticky="w")

    lbl_extra = tb.Label(frame_info,text="")
    lbl_extra.grid(row=3,column=0,sticky="w")

    prestamo_actual={"id":None,"saldo":0}

    def cargar(event=None):
        tabla.delete(*tabla.get_children())
        cliente_id=clientes.get(combo_cliente.get())
        if not cliente_id:return

        cursor.execute("SELECT id,fecha,total FROM prestamos WHERE cliente_id=?", (cliente_id,))
        for p in cursor.fetchall():
            total,abonado,saldo,atraso,extra = calcular(p[0])
            estado="PAGO" if saldo<=0 else "VENCIDO" if atraso>0 else "ACTIVO"
            extra_txt="⚠ EXITOSO" if extra>0 else ""

            tabla.insert("", "end",
                values=(p[0],p[1],formato(total),
                        formato(abonado),formato(saldo),
                        estado+" "+extra_txt))

    combo_cliente.bind("<<ComboboxSelected>>",cargar)

    def seleccionar(event):
        item=tabla.selection()
        if not item:return

        pid=tabla.item(item)["values"][0]
        total,abonado,saldo,atraso,extra=calcular(pid)

        prestamo_actual["id"]=pid
        prestamo_actual["saldo"]=saldo

        lbl_total.config(text=f"💰 Total: {formato(total)}")
        lbl_abonado.config(text=f"💵 Abonado: {formato(abonado)}")
        lbl_saldo.config(text=f"📉 Pendiente por cancelar: {formato(saldo)}")

        if extra>0:
            lbl_extra.config(text=f"🟢 Saldo a favor del cliente: {formato(extra)}")
        elif atraso>0:
            lbl_extra.config(text=f"🔴 Atraso: {atraso} días")
        else:
            lbl_extra.config(text="")

    tabla.bind("<<TreeviewSelect>>",seleccionar)

    tb.Label(win,text="Monto").pack()
    monto=tb.Entry(win)
    monto.pack()

    def guardar():
        if prestamo_actual["id"] is None:
            messagebox.showerror("Error","Selecciona préstamo")
            return

        try:
            valor=float(monto.get())
        except:
            messagebox.showerror("Error","Monto inválido")
            return

        saldo=prestamo_actual["saldo"]

        if valor>saldo:
            excedente=valor-saldo
            resp=messagebox.askyesno("Advertencia",
                f"Está pagando más de lo debido\nSaldo: {formato(saldo)}\nExcedente: {formato(excedente)}\n¿Continuar?")
            if not resp:return

        cursor.execute("INSERT INTO abonos VALUES(NULL,?,?,?)",
                       (prestamo_actual["id"],valor,
                        datetime.now().strftime("%Y-%m-%d")))
        conn.commit()

        messagebox.showinfo("OK","Abono registrado")

        cargar()
        monto.delete(0,"end")
        lbl_total.config(text="💰 Total:")
        lbl_abonado.config(text="💵 Abonado:")
        lbl_saldo.config(text="📉 Saldo:")
        lbl_extra.config(text="")
        prestamo_actual["id"]=None

    tb.Button(win,text="Guardar Abono",command=guardar).pack(pady=10)

# -------- BOTONES --------
tb.Button(frame,text="Nuevo Cliente",width=25,command=nuevo_cliente).grid(row=0,column=0,padx=10,pady=10)
tb.Button(frame,text="Ver Clientes",width=25,command=ver_clientes).grid(row=0,column=1,padx=10,pady=10)
tb.Button(frame,text="Nuevo Préstamo",width=25,command=nuevo_prestamo).grid(row=1,column=0,padx=10,pady=10)
tb.Button(frame,text="Registrar Abono",width=25,command=registrar_abono).grid(row=1,column=1,padx=10,pady=10)

# -------- NOTIFICACIONES --------
noti = tb.Label(app,font=("Arial",12,"bold"))
noti.pack(side="bottom",fill="x",ipady=12)

def iniciar():
    actualizar_noti(noti)

app.after(1000,iniciar)

app.mainloop()