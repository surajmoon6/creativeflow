import getpass

import click
from werkzeug.security import generate_password_hash

from .models import User, db


def register(app):
    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.option("--name", default="Studio Admin")
    def create_admin(email, name):
        """Create (or reset the password of) an admin user."""
        pw = getpass.getpass("Password (min 10 chars): ")
        if len(pw) < 10:
            raise click.ClickException("Password must be at least 10 characters.")
        u = User.query.filter_by(email=email.lower()).first()
        if u:
            u.password_hash = generate_password_hash(pw)
        else:
            db.session.add(User(email=email.lower(), name=name, password_hash=generate_password_hash(pw)))
        db.session.commit()
        click.echo(f"Admin ready: {email}")

    @app.cli.command("seed")
    @click.option("--reset", is_flag=True, help="Delete the database and stored files first.")
    def seed(reset):
        """Load demo data (clients, projects in every stage)."""
        from .seed import run
        run(reset=reset)

    @app.cli.command("seed-showcase")
    @click.option("--remove", is_flag=True, help="Remove the showcase data (and only that) again.")
    def seed_showcase(remove):
        """Add a believable studio history: past clients, completed work and projects in every stage."""
        from .showcase import run
        run(remove=remove)

    @app.cli.command("seed-demo-calendar")
    @click.option("--remove", is_flag=True, help="Remove the demo calendar (and only that) again.")
    def seed_demo_calendar(remove):
        """Add a demo monthly client with a content calendar, designs, chat and a client sign-in."""
        from .demo_calendar import run
        run(remove=remove)

    @app.cli.command("rerender-previews")
    @click.option("--max-px", default=1800, show_default=True, help="Longest side of a preview, in pixels.")
    @click.option("--scale", default=0.9, show_default=True, help="Largest share of the original size (0.2 to 0.95).")
    def rerender_previews(max_px, scale):
        """Save the sharper preview size to settings and rebuild every existing preview from its master."""
        from . import services as sv
        from .models import Project, Setting
        if not (300 <= max_px <= 2400 and 0.2 <= scale <= 0.95):
            raise click.ClickException("max-px must be 300 to 2400 and scale 0.2 to 0.95.")
        for key, val in (("preview_max_px", max_px), ("preview_scale", scale)):
            row = db.session.get(Setting, key) or Setting(key=key)
            row.value = val
            db.session.add(row)
        db.session.commit()
        done = 0
        for p in Project.query.all():
            if p.versions:
                sv.rerender_previews(p)
                db.session.commit()
                done += 1
        click.echo(f"Rebuilt previews for {done} projects at up to {max_px}px, {round(scale * 100)}% of the original.")
