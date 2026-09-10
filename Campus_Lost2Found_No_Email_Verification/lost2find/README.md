# Campus Lost2Found

A Flask + SQLite starter implementation of the Lost2Find campus lost-and-found requirements.

## Run locally

1. Install Python 3.10+.
2. Create/activate a virtual environment.
3. Run `pip install -r requirements.txt`.
4. Set an institution domain if desired: `set INSTITUTION_DOMAIN=yourcollege.edu` on Windows or `export INSTITUTION_DOMAIN=yourcollege.edu` on macOS/Linux.
5. Run `python app.py`.
6. Open `http://127.0.0.1:5000`.

### Management
- Select Management.
- On first use, create the management password.
- Default management username: `management`.
- Change the password from Settings.

### Students
- Register with the configured institution email domain.
- The demo prints the verification code on-screen as a flash message. For production, replace this with an email provider (SMTP/API).

## Included
- Role-based management/student access
- Password hashing and sessions
- Institution-domain validation and demo OTP verification
- Found-item upload with image type/size validation
- Search/filter by item name/category/location/ID/status
- Delete confirmation
- Appointment slot booking with duplicate-slot protection
- Booking confirmation and management collection workflow
- Item status: Available, Reserved, Collected
- Management dashboard statistics and settings

## Production hardening
Use HTTPS, a strong persistent SECRET_KEY, CSRF protection, rate limiting, real email delivery, a production database, object storage for photos, audit logs, backups, and stricter authorization/validation before deployment.
