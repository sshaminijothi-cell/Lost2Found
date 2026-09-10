from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3, os, secrets
from datetime import datetime, date

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, 'lost2find.db')
UPLOADS = os.path.join(BASE, 'static', 'uploads')
os.makedirs(UPLOADS, exist_ok=True)
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
ALLOWED = {'png','jpg','jpeg','webp'}
INSTITUTION_DOMAIN = os.environ.get('INSTITUTION_DOMAIN', 'grt.edu.in')

SCHEMA = '''
CREATE TABLE IF NOT EXISTS management (id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT, profile_photo TEXT);
CREATE TABLE IF NOT EXISTS students (id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT UNIQUE, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, verified INTEGER DEFAULT 0, profile_photo TEXT);
CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, category TEXT NOT NULL, photo TEXT, description TEXT, location TEXT, date_found TEXT, uploaded_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Available');
CREATE TABLE IF NOT EXISTS visits (id INTEGER PRIMARY KEY AUTOINCREMENT, booking_id TEXT UNIQUE NOT NULL, student_id INTEGER NOT NULL, item_id INTEGER NOT NULL, visiting_date TEXT NOT NULL, visiting_time TEXT NOT NULL, booking_status TEXT DEFAULT 'Confirmed', collection_status TEXT DEFAULT 'Pending', created_at TEXT NOT NULL, FOREIGN KEY(student_id) REFERENCES students(id), FOREIGN KEY(item_id) REFERENCES items(id));
'''

def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def init_db():
    c=db(); c.executescript(SCHEMA)
    if not c.execute('SELECT 1 FROM management LIMIT 1').fetchone():
        c.execute('INSERT INTO management(username,password_hash) VALUES (?,?)', ('management', None))
    c.commit(); c.close()

def login_required(role):
    def deco(fn):
        from functools import wraps
        @wraps(fn)
        def wrap(*a,**kw):
            if session.get('role') != role: return redirect(url_for('landing'))
            return fn(*a,**kw)
        return wrap
    return deco

@app.route('/')
def landing(): return render_template('landing.html')

@app.route('/management/login', methods=['GET','POST'])
def mgmt_login():
    c=db(); m=c.execute('SELECT * FROM management LIMIT 1').fetchone(); c.close()
    if request.method=='POST':
        if not m['password_hash']:
            return redirect(url_for('mgmt_setup'))
        if request.form.get('username') == m['username'] and check_password_hash(m['password_hash'], request.form.get('password','')):
            session.clear(); session['role']='management'; session['mgmt_id']=m['id']; return redirect(url_for('mgmt_dashboard'))
        flash('Invalid management credentials.','error')
    return render_template('management_login.html', first_time=not bool(m['password_hash']))

@app.route('/management/setup', methods=['GET','POST'])
def mgmt_setup():
    c=db(); m=c.execute('SELECT * FROM management LIMIT 1').fetchone()
    if m['password_hash']:
        return redirect(url_for('mgmt_login'))
    if request.method=='POST':
        p=request.form.get('password',''); cp=request.form.get('confirm','')
        if len(p)<8: flash('Password must be at least 8 characters.','error')
        elif p!=cp: flash('Passwords do not match.','error')
        else:
            c.execute('UPDATE management SET password_hash=? WHERE id=?',(generate_password_hash(p),m['id'])); c.commit(); c.close(); flash('Password created. Please sign in.','success'); return redirect(url_for('mgmt_login'))
    c.close(); return render_template('management_setup.html')

@app.route('/management/dashboard')
@login_required('management')
def mgmt_dashboard():
    c=db(); stats={
      'total':c.execute('SELECT COUNT(*) n FROM items').fetchone()['n'],
      'available':c.execute("SELECT COUNT(*) n FROM items WHERE status='Available'").fetchone()['n'],
      'collected':c.execute("SELECT COUNT(*) n FROM items WHERE status='Collected'").fetchone()['n'],
      'pending':c.execute("SELECT COUNT(*) n FROM visits WHERE collection_status='Pending'").fetchone()['n']}
    recent=c.execute('SELECT * FROM items ORDER BY uploaded_at DESC LIMIT 6').fetchall(); c.close()
    return render_template('management_dashboard.html',stats=stats,recent=recent)

@app.route('/management/items/upload', methods=['GET','POST'])
@login_required('management')
def upload_item():
    if request.method=='POST':
        name=request.form.get('name','').strip(); category=request.form.get('category','').strip(); desc=request.form.get('description','').strip(); loc=request.form.get('location','').strip(); found=request.form.get('date_found','')
        f=request.files.get('photo'); filename=None
        if f and f.filename:
            ext=f.filename.rsplit('.',1)[-1].lower() if '.' in f.filename else ''
            if ext not in ALLOWED: flash('Only PNG, JPG, JPEG and WEBP images are allowed.','error'); return render_template('upload_item.html')
            filename=secure_filename(f"{secrets.token_hex(8)}.{ext}"); f.save(os.path.join(UPLOADS,filename))
        if not name or not category or not loc or not found: flash('Please fill all required fields.','error'); return render_template('upload_item.html')
        c=db(); c.execute('INSERT INTO items(name,category,photo,description,location,date_found,uploaded_at,status) VALUES(?,?,?,?,?,?,?,?)',(name,category,filename,desc,loc,found,datetime.now().strftime('%Y-%m-%d %H:%M:%S'),'Available')); c.commit(); c.close(); flash('Item uploaded successfully.','success'); return redirect(url_for('mgmt_items'))
    return render_template('upload_item.html')

@app.route('/management/items')
@login_required('management')
def mgmt_items():
    q=request.args.get('q','').strip(); status=request.args.get('status','')
    c=db(); sql='SELECT * FROM items WHERE 1=1'; args=[]
    if q: sql += ' AND (name LIKE ? OR category LIKE ? OR location LIKE ? OR CAST(id AS TEXT)=?)'; args += [f'%{q}%']*3+[q]
    if status: sql += ' AND status=?'; args.append(status)
    sql+=' ORDER BY uploaded_at DESC'; items=c.execute(sql,args).fetchall(); c.close(); return render_template('management_items.html',items=items,q=q,status=status)

@app.route('/management/items/<int:item_id>/delete', methods=['POST'])
@login_required('management')
def delete_item(item_id):
    c=db(); item=c.execute('SELECT * FROM items WHERE id=?',(item_id,)).fetchone()
    if item:
        c.execute('DELETE FROM visits WHERE item_id=?',(item_id,)); c.execute('DELETE FROM items WHERE id=?',(item_id,)); c.commit()
        if item['photo']:
            try: os.remove(os.path.join(UPLOADS,item['photo']))
            except OSError: pass
        flash('Item deleted.','success')
    c.close(); return redirect(url_for('mgmt_items'))

@app.route('/management/requests')
@login_required('management')
def requests_page():
    c=db(); rows=c.execute('''SELECT v.*, s.name student_name, s.email, i.name item_name, i.status item_status FROM visits v JOIN students s ON s.id=v.student_id JOIN items i ON i.id=v.item_id ORDER BY v.created_at DESC''').fetchall(); c.close(); return render_template('requests.html',rows=rows)

@app.route('/management/requests/<int:visit_id>/collect', methods=['POST'])
@login_required('management')
def mark_collected(visit_id):
    c=db(); v=c.execute('SELECT * FROM visits WHERE id=?',(visit_id,)).fetchone()
    if v:
        c.execute("UPDATE visits SET collection_status='Collected', booking_status='Completed' WHERE id=?",(visit_id,)); c.execute("UPDATE items SET status='Collected' WHERE id=?",(v['item_id'],)); c.commit(); flash('Item marked as collected.','success')
    c.close(); return redirect(url_for('requests_page'))

@app.route('/management/settings', methods=['GET','POST'])
@login_required('management')
def mgmt_settings():
    c=db(); m=c.execute('SELECT * FROM management LIMIT 1').fetchone()
    if request.method=='POST':
        current=request.form.get('current',''); new=request.form.get('new',''); confirm=request.form.get('confirm','')
        if not check_password_hash(m['password_hash'],current): flash('Current password is incorrect.','error')
        elif len(new)<8 or new!=confirm: flash('New password must be 8+ characters and match confirmation.','error')
        else: c.execute('UPDATE management SET password_hash=? WHERE id=?',(generate_password_hash(new),m['id'])); c.commit(); flash('Password changed.','success')
    c.close(); return render_template('management_settings.html',m=m)

@app.route('/student/login', methods=['GET','POST'])
def student_login():
    if request.method=='POST':
        email=request.form.get('email','').strip().lower(); p=request.form.get('password','')
        if '@' not in email or email.rsplit('@',1)[1] != INSTITUTION_DOMAIN: flash(f'Use your institution email (@{INSTITUTION_DOMAIN}).','error'); return render_template('student_login.html')
        c=db(); s=c.execute('SELECT * FROM students WHERE email=?',(email,)).fetchone()
        if s and check_password_hash(s['password_hash'],p):
            session.clear(); session['role']='student'; session['student_id']=s['id']; return redirect(url_for('student_home'))
        flash('Invalid email or password.','error')
    return render_template('student_login.html')

@app.route('/student/register', methods=['GET','POST'])
def student_register():
    if request.method=='POST':
        name=request.form.get('name','').strip(); sid=request.form.get('student_id','').strip(); email=request.form.get('email','').strip().lower(); p=request.form.get('password','')
        if '@' not in email or email.rsplit('@',1)[1] != INSTITUTION_DOMAIN: flash(f'Only @{INSTITUTION_DOMAIN} emails are accepted.','error')
        elif len(p)<8: flash('Password must be at least 8 characters.','error')
        else:
            c=db();
            try:
                c.execute('INSERT INTO students(student_id,name,email,password_hash,verified) VALUES(?,?,?,?,1)',(sid,name,email,generate_password_hash(p))); c.commit(); c.close(); flash('Account created successfully. Please sign in.','success'); return redirect(url_for('student_login'))
            except sqlite3.IntegrityError: c.close(); flash('Student ID or email already exists.','error')
    return render_template('student_register.html',domain=INSTITUTION_DOMAIN)

@app.route('/student/home')
@login_required('student')
def student_home():
    q=request.args.get('q','').strip(); cat=request.args.get('category','')
    c=db(); sql="SELECT * FROM items WHERE status IN ('Available','Reserved')"; args=[]
    if q: sql+=' AND (name LIKE ? OR category LIKE ? OR location LIKE ?)'; args += [f'%{q}%']*3
    if cat: sql+=' AND category=?'; args.append(cat)
    sql+=' ORDER BY uploaded_at DESC'; items=c.execute(sql,args).fetchall(); cats=c.execute("SELECT DISTINCT category FROM items WHERE status IN ('Available','Reserved') ORDER BY category").fetchall(); s=c.execute('SELECT * FROM students WHERE id=?',(session['student_id'],)).fetchone(); c.close(); return render_template('student_home.html',items=items,cats=cats,s=s,q=q,cat=cat)

@app.route('/student/item/<int:item_id>')
@login_required('student')
def item_details(item_id):
    c=db(); item=c.execute('SELECT * FROM items WHERE id=?',(item_id,)).fetchone(); c.close();
    if not item: return redirect(url_for('student_home'))
    return render_template('item_details.html',item=item)

SLOTS=['10:00 AM – 10:15 AM','10:30 AM – 10:45 AM','11:00 AM – 11:15 AM','2:00 PM – 2:15 PM','3:00 PM – 3:15 PM']
@app.route('/student/item/<int:item_id>/schedule', methods=['GET','POST'])
@login_required('student')
def schedule(item_id):
    c=db(); item=c.execute('SELECT * FROM items WHERE id=?',(item_id,)).fetchone()
    if not item or item['status']=='Collected': c.close(); return redirect(url_for('student_home'))
    if request.method=='POST':
        d=request.form.get('date'); slot=request.form.get('slot')
        if not d or not slot or slot not in SLOTS or d < date.today().isoformat(): flash('Choose a valid future date and time slot.','error')
        else:
            exists=c.execute("SELECT 1 FROM visits WHERE item_id=? AND visiting_date=? AND visiting_time=? AND booking_status='Confirmed'",(item_id,d,slot)).fetchone()
            if exists: flash('That time slot is already booked for this item.','error')
            else:
                bid='L2F-'+secrets.token_hex(4).upper(); c.execute('INSERT INTO visits(booking_id,student_id,item_id,visiting_date,visiting_time,created_at) VALUES(?,?,?,?,?,?)',(bid,session['student_id'],item_id,d,slot,datetime.now().isoformat())); c.execute("UPDATE items SET status='Reserved' WHERE id=?",(item_id,)); c.commit(); c.close(); return redirect(url_for('confirmation',booking_id=bid))
    c.close(); return render_template('schedule.html',item=item,slots=SLOTS,min_date=date.today().isoformat())

@app.route('/student/confirmation/<booking_id>')
@login_required('student')
def confirmation(booking_id):
    c=db(); r=c.execute('''SELECT v.*, s.name student_name, i.name item_name, i.id item_id FROM visits v JOIN students s ON s.id=v.student_id JOIN items i ON i.id=v.item_id WHERE v.booking_id=? AND v.student_id=?''',(booking_id,session['student_id'])).fetchone(); c.close();
    if not r: return redirect(url_for('student_home'))
    return render_template('confirmation.html',r=r)

@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('landing'))

@app.errorhandler(413)
def too_large(e): flash('Image is too large. Maximum size is 5 MB.','error'); return redirect(request.referrer or url_for('landing'))

init_db()
if __name__=='__main__': app.run(debug=True)
