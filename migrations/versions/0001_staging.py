"""Append-only collector staging; independent of website publication data."""
from alembic import op
import sqlalchemy as sa

revision = '0001_collector'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('CREATE EXTENSION IF NOT EXISTS postgis')
    op.create_table('collector_raw_artifacts',
                    sa.Column('sha256', sa.String(64), primary_key=True),
                    sa.Column('metadata', sa.JSON(), nullable=False))
    op.create_table('collector_entities',
                    sa.Column('id', sa.String(200), primary_key=True),
                    sa.Column('source_id', sa.String(100), nullable=False))
    op.create_table('collector_record_versions',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('entity_id', sa.String(200), sa.ForeignKey('collector_entities.id'), nullable=False),
                    sa.Column('version_sha256', sa.String(64), nullable=False),
                    sa.Column('artifact_sha256', sa.String(64), sa.ForeignKey('collector_raw_artifacts.sha256'), nullable=False),
                    sa.Column('record', sa.JSON(), nullable=False),
                    sa.UniqueConstraint('entity_id', 'version_sha256', name='uq_collector_entity_version'))
    op.create_table('collector_runs',
                    sa.Column('sequence', sa.Integer(), primary_key=True),
                    sa.Column('run_id', sa.String(100), nullable=False, unique=True),
                    sa.Column('source_id', sa.String(100), nullable=False),
                    sa.Column('artifact_sha256', sa.String(64), sa.ForeignKey('collector_raw_artifacts.sha256'), nullable=True),
                    sa.Column('status', sa.String(20), nullable=False),
                    sa.Column('report', sa.JSON(), nullable=False))


def downgrade():
    raise RuntimeError('Evidence tables cannot be automatically dropped; arrange an audited archive first')
