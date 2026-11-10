import click

from .storage import get_db
from .workflow import now


def register(app):
    @app.cli.command('seed-demo')
    def seed_demo():
        """Insert clearly labelled synthetic facilities and inventory into an empty DB."""
        db = get_db()
        with db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT EXISTS(SELECT 1 FROM facilities)').fetchone()[0]:
                raise click.ClickException('Database already has facilities; refusing to overwrite data.')
            db.executemany('INSERT INTO facilities VALUES(?,?,?)', [
                ('DEMO-H1', 'Synthetic Demo Hospital', 'hospital'),
                ('DEMO-C1', 'Synthetic Demo Centre', 'centre'),
            ])
            db.execute('INSERT INTO inventory VALUES(?,?,?,?,?,?,?)',
                       ('DEMO-C1', 'A+', 'red_cells', 10, 0, 2, now().isoformat()))
        click.echo('Inserted synthetic DEMO-H1 and DEMO-C1; no real facility data used.')
