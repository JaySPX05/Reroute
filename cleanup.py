from reroute import db

conn = db.connect()
cur = conn.cursor()
cur.execute("SELECT CURRENT_USER FROM DUMMY")
user = cur.fetchone()[0]
print("Connected as", user)

if user != "HACKFEST0249":
    print("Not the 0249 account, nothing to clean up. Stopping.")
else:
    for table in db.TABLES + list(db.RUNTIME_DDL):
        try:
            cur.execute(f'DROP TABLE "{table.upper()}"')
            print("removed", table)
        except Exception:
            print("not there", table)
    conn.commit()
conn.close()