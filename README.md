# CreativeFlow

A workspace for a design or social-media studio. Send a quote, run the creative review, collect the payment and deliver the files, all from one place. Your client gets a private link on their phone: no app and no account for one-off projects.

> **This is a test version.** Everything you see after installing is made-up sample data (studios, clients, prices, payments). Nothing is connected to a real bank, WhatsApp or email account.

```
Quote → Design → Review → Changes → Approval → Invoice → UPI payment → Delivery
```

## What it does

- **Quotes.** Build a quote, send it by WhatsApp or link, the client accepts on their phone. PDF and image downloads with a payment QR.
- **Creative review.** Upload a design; the client sees a watermarked low-resolution preview, asks for changes or approves, per design. The original stays private.
- **Invoices and payment.** An invoice with a UPI QR for the exact amount. Files are released only after you confirm the payment. Advances and part payments are taken off the invoice.
- **Monthly clients.** A content calendar per client: you plan the post and reel dates, the client adds what they want in each one, your team uploads the creative, the client reviews and chats on every post, and you mark it posted. Progress shows how much of the plan is done and how much is left.
- **Team.** Add employees and give each one only the clients they work on.

## Try it (about 3 minutes)

You need **Python 3.10+** and **Node 18+** (`brew install python node` on a Mac; on Windows or Linux install both from their websites).

```bash
git clone https://github.com/surajmoon6/creativeflow.git
cd creativeflow
./dev.sh
```

Open **http://localhost:5173**. The first run sets everything up and fills it with sample data.

**Sign in as a studio owner** in either way:

- Click **Create a test account**, use any name and a made-up email (like `you@example.com`) and a password of 8 or more characters. You land in a studio full of sample work.
- Or use the ready-made account:

  | | |
  |---|---|
  | Email | `admin@creativeflow.local` |
  | Password | `creativeflow-demo` |

**See what a monthly client sees.** Sign out, then sign in with the sample client:

| | |
|---|---|
| Email | `neha@spiceroutecafe.example` |
| Password | `SpiceRoute-demo-26` |

(That login opens the calendar for the made-up client "Spice Route Café".) For one-off projects, the terminal prints each sample project's client link; open one to see the client's review page.

Prefer one process instead of two? Run `./start.sh` and open **http://localhost:5001**.

Everything runs on your own computer and the data stays in `backend/creativeflow.db` and `storage/`. To start over: `cd backend && ../.venv/bin/flask --app app seed --reset && ../.venv/bin/flask --app app seed-demo-calendar`.

Useful commands (from `backend/`, using `../.venv/bin/flask`):

```bash
flask --app app seed --reset        # wipe the database and stored files, reload sample data
flask --app app seed-demo-calendar  # add the sample monthly client (Spice Route Café)
flask --app app create-admin        # create your own admin, or reset a password
python -m pytest -q                 # run the test suite (89 tests)
```

### About "Create a test account"

It exists only to let people try the tool and is switched on by `./dev.sh` and `./start.sh` (the variable `DEMO_SIGNUP=1`). It is **off everywhere else**, so a real server, set up as described in [DEPLOY.md](DEPLOY.md), has no public sign-up. Every account made this way is a studio owner of *your local copy*, so don't use it on a server that others can reach.

## Quotations

**Quotes** (in the sidebar) is where work starts. Make a quote for a client: tap the services you offer (or type your own), set the prices, discount, GST and how long it is valid, and save it as a draft.

Share it with **Send on WhatsApp** or **Copy link**. Either one marks the quote as *sent* and turns the link on. The client opens a page on their phone with the full quote and **Accept** / **Decline** buttons; they can add a short message. You see when they open it, how many times, and their answer, in the quote's activity and in the notification bell.

When a quote is accepted, **Create project from this quote** makes the project with the client, price, discount and GST filled in, and the items listed in the description. If a client answers on a call instead, use **Mark as accepted / declined**.

**Free extras.** Tick *Free for the client* on a line, or tap a green "+ Free: Instagram story design" button. The client sees the item with its value crossed out and marked **FREE**, plus a "You save ₹100" line. It adds nothing to the price, discount or GST.

**Closing message.** Every quote ends with a friendly note to the client, filled in with their name. Edit it per quote, or change the standard wording in **Settings → Quotations**.

**Downloads.** On a quote, **Download PDF** and **Download image** give you a clean A4 PDF (with selectable text) or a single PNG, ready to send on WhatsApp. Both include a QR code that opens the quote online for one-tap acceptance. Your client has the same buttons on their page. Files are drawn on the server using the bundled Noto Sans font (SIL Open Font License, in `backend/app/fonts`), so the ₹ sign always prints.

**Payment QR.** Put your UPI ID and name in **Settings → UPI payments** and every quote shows a *Pay by UPI* block: a QR code, your UPI ID, and the quote number as the note (on phones, an *Open UPI app* button instead of the QR). It is in the PDF and image downloads too. Invoices use the same details, with the exact amount and invoice number filled in, and the QR also prints when a client saves the invoice as PDF. Quotes have no amount in the QR, because you and the client agree the advance.

Good to know:
- A quote is *expired* automatically after its valid-until date; edit the date and the same link works again.
- Accepted and declined quotes are locked. **Duplicate** one to start a similar quote, or **Reopen** a declined one.
- Only drafts can be deleted.
- Numbering, validity, default terms and the WhatsApp message are in **Settings → Quotations**.
- The dashboard lists quotes that need a nudge: accepted but not started, not opened, viewed without a reply, or expiring soon.

## Several designs, one link

A quote with a banner, a standee and two posts becomes **one project with one client link** and four **designs**. When you create the project from the accepted quote, each item becomes a design (two of the same item become "Post (1 of 2)" and "Post (2 of 2)"; free items are designs too).

- On the project page, **Designs** lists them. Pick one and **Upload** its versions. Use **Add design** for extra work, the pencil to rename, **Reopen** to take an approved design back.
- Your client opens the same link and sees all designs, each with its status. They approve or ask for changes **per design**, so approving the banner never blocks the poster. The project moves on to final files and the invoice once *every* design is approved.
- **Revisions are per design** (4 by default, set on the quote and in Settings). A client's extra change on one design never uses up another design's revisions, and beyond the included ones it is billed as an extra revision.

## Advance payment

A quote carries an **advance** (50% by default). When you create the project, the client's link gets an **Advance** tab: the amount, a UPI QR and an *Open UPI app* button, and a box for their payment reference. You confirm it like any payment, or use **Mark as received** for cash or a transfer you already saw.

- The **dashboard** reminds you about advances that are still unpaid after a few days (Settings → Quotations). **Remind on WhatsApp** on the project opens a ready-made message and notes that you reminded them.
- The advance is **taken off the final invoice**: the client only pays the balance, the QR and the amount due show the balance, and if the advance covered everything the files are released automatically.
- You can ask for an advance on any project from the **...** menu (**Ask for an advance**), and change or remove it until it is paid.

## How the workflow runs

**1. Create the project.** Add a client, then a project with the price, GST and revision limit. You can attach the first design file now or later.

**2. Upload a version.** The server makes a separate preview asset from the upload:
- It is scaled down to 900 px on the longest side, and never more than 65% of the original.
- A repeated, rotated watermark is burned into the pixels: *CLIENT REVIEW COPY*, the client's name, the project number, and your studio name.
- It is saved as a fresh JPEG with no metadata.
- PDFs are rendered page by page.

The original stays private. A review link is created automatically.

**Watermark switch.** Each project has a *Watermark* switch in its Creative panel. Turn it off when a client wants to see the design clean: every existing version is re-rendered without the watermark (from the stored original) and the client's link shows the clean preview, still reduced in size. Turn it on again at any time. New versions follow the current setting, and each change is logged in the project timeline. The original and final files are never affected.

**3. Client reviews.** They open the link (usually from WhatsApp), zoom the preview, and either request changes or approve. Requests beyond the included revisions are flagged, and the client sees the extra charge before sending.

**4. Approval → final files → invoice.** After approval you attach the deliverables (JPG, PNG, print PDF, ZIP and so on). They are stored privately and nobody can reach them yet. Then you issue the invoice: the project moves to *Payment pending*, and the invoice appears on the same client link.

**5. Payment by UPI.** The invoice shows a QR code with the exact amount and the project and invoice number already filled in. On phones there is also an "Open UPI app" button.

After paying, the client enters the UTR (transaction reference) and can attach a screenshot. **That does not unlock anything.** You check your bank or UPI app, then press *Confirm payment received* on the Payments page or the project page. Only that confirmation releases the files.

**6. Delivery.** The client downloads from the *Final files* tab. Each click gets a fresh signed URL that is valid for 5 minutes and is checked again on download. Every download is logged, and the first one moves the project to *Delivered*.

### Sharing links

On the project page, *Client link* has **Copy** and **WhatsApp** for the review, payment and delivery views. It is one link that opens at different tabs. WhatsApp opens with your message template and the client's number already filled in; 10-digit numbers get +91. You can edit the templates in Settings.

You can replace a link (the old one stops working immediately), set it to expire (24 hours, 3 days, 7 days, 30 days, a date, or never), or revoke it.

## What the protection does and doesn't do

There is no way to stop someone screenshotting a preview. CreativeFlow makes a screenshot a poor substitute for the real file, and keeps the real file unreachable until you have been paid:

- The client only ever receives the low-resolution, watermarked preview. The original upload has no client-facing URL.
- Finals are stored outside any web directory and served only through `/api/r/<token>/files/<id>/link` → `/api/dl/<signed>`. Both steps check the token, that the file belongs to this project, that payment was confirmed by you, the delivery expiry and the download limit.
- Tokens are 128-bit random values. A token for project A returns *not found* for any version or file of project B. Project IDs in the URL are never trusted.
- Revoking a link also kills any download URL already issued from it.
- After a client legitimately downloads a file, they have it. Nothing can change that.

## Security notes

- Admin sessions use a signed, httpOnly, SameSite=Lax cookie. Every change needs the `X-CSRF-Token` header. Passwords are hashed with Werkzeug (scrypt).
- Logins are limited to 10 a minute per IP, and client actions (revisions, payment submissions, downloads) are limited too.
- Uploads are checked by extension *and* file signature. Images are fully decoded before a preview is made, with a pixel limit against decompression bombs. The size limit is 100 MB, set with `MAX_UPLOAD_MB`.
- Headers sent on every response: CSP, `X-Frame-Options: DENY`, `nosniff`, and `Referrer-Policy: no-referrer` (so tokens in URLs don't leak to other sites).
- All queries go through SQLAlchemy (parameterised). React escapes all output. Final files are always sent as `application/octet-stream` attachments, so an uploaded SVG or HTML file can't run in the browser.
- Secrets come from the environment (see `.env.example`). None are in the frontend.

## Project layout

```
creativeflow/
├── backend/
│   ├── app/
│   │   ├── models.py        all tables (users, clients, projects, project_versions, project_files,
│   │   │                    review_tokens, comments, invoices, invoice_items, payments, downloads,
│   │   │                    activity_logs, notifications, settings)
│   │   ├── services.py      workflow rules: versions, revisions, approval, invoice maths, payments, delivery checks
│   │   ├── preview.py       downscale + watermark (Pillow, PyMuPDF for PDFs)
│   │   ├── storage.py       storage abstraction (local today; S3/R2 needs the same 4 methods)
│   │   ├── security.py      sessions, CSRF, rate limiting, review tokens, signed download links
│   │   ├── serializers.py   separate admin and client JSON shapes (clients never see internal fields)
│   │   ├── routes/          auth.py, admin.py, client.py
│   │   └── seed.py          demo data, built through the real workflow
│   └── tests/               access control, tokens, payment unlock, downloads, invoice maths
├── frontend/src/
│   ├── pages/admin/         dashboard, projects, project detail, clients, invoices, payments, files, activity, settings
│   ├── pages/client/        review, invoice + UPI payment, delivery, expired/invalid link
│   ├── components/          UI kit, preview stage with zoom viewer, project table
│   └── services/api.ts      fetch wrapper (CSRF, errors)
├── storage/private/         every stored file (git-ignored)
├── dev.sh / start.sh        run it locally (with sample data and test sign-up)
└── .env.example
```

Money is stored as integer paise and GST as basis points (1800 = 18%), so there is no floating-point rounding on invoices.

## Moving to a server

When you're happy locally, this is the shape of the deployment on an Ubuntu VPS:

1. **Code and packages.** Clone to `/srv/creativeflow`, create `.venv`, then `pip install -r backend/requirements.txt "psycopg[binary]"`. Run `cd frontend && npm ci && npm run build`.
2. **Database.** Install Postgres, create a database and user, and set `DATABASE_URL` in `.env`. Tables are created on first start. Add Alembic migrations before you change the schema with live data in it.
3. **`.env`.** Set a real `SECRET_KEY`, `PUBLIC_URL=https://review.yourstudio.in` and `SESSION_COOKIE_SECURE=1`. Set the SMTP variables if you want emails.
4. **Admin account.** Run `flask --app app create-admin`. Don't run `seed` on the server.
5. **Gunicorn.** Run it under systemd: `gunicorn -w 2 -b 127.0.0.1:8000 wsgi:app` from `backend/`. Flask serves the built frontend itself.
6. **Nginx.** Put Nginx in front with Let's Encrypt, `client_max_body_size 110m;` and `proxy_pass http://127.0.0.1:8000;`.
7. **Backups.** Back up the Postgres database and `storage/private/` nightly. Those two hold everything.

Rate-limit counters live in each Gunicorn worker. That's fine at this scale; move them to Redis if you ever run many workers.

## What's deliberately not built yet

- **Razorpay.** Payments are UPI QR plus your manual confirmation, as agreed. The payment code is isolated in `services.submit_payment` / `confirm_payment`. Adding Razorpay means a webhook route that verifies the signature and calls the same `confirm_payment`.
- **Video previews** (low-res watermarked transcodes with ffmpeg).
- **Charts on the dashboard.**
