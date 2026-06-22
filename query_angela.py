import sqlite3

conn = sqlite3.connect('prestamos.db')
c = conn.cursor()

c.execute("SELECT id, cliente FROM prestamos WHERE cliente LIKE ?", ('%Angela%',))
result = c.fetchall()
print('Prestamos:', result)

if result:
    prestamo_id = result[0][0]
    c.execute('SELECT COUNT(*) FROM pagos WHERE prestamo_id=?', (prestamo_id,))
    count = c.fetchone()[0]
    print('Pagos:', count)
else:
    print('No se encontró el deudor Sra. Angela')

conn.close()