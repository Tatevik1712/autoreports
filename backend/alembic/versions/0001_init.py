"""init

Revision ID: 0001
Revises:
Create Date: 2026-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # users
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('username', sa.String(100), nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('role', sa.Enum('user', 'admin', name='userrole'), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('username'),
    )
    op.create_index('ix_users_email', 'users', ['email'])
    op.create_index('ix_users_username', 'users', ['username'])

    # report_templates
    op.create_table(
        'report_templates',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('slug', sa.String(100), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('schema', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_by_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug', 'version', name='uq_template_slug_version'),
    )
    op.create_index('ix_report_templates_slug', 'report_templates', ['slug'])

    # source_files
    op.create_table(
        'source_files',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('owner_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('original_filename', sa.String(500), nullable=False),
        sa.Column('content_type', sa.String(100), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('storage_key', sa.String(500), nullable=False),
        sa.Column('status', sa.Enum('uploaded', 'parsed', 'parse_error',
                                    name='sourcefilestatus'), nullable=False),
        sa.Column('parse_error', sa.Text(), nullable=True),
        sa.Column('extracted_text', sa.Text(), nullable=True),
        sa.Column('meta', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_source_files_owner_id', 'source_files', ['owner_id'])

    # reports
    op.create_table(
        'reports',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('owner_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('template_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('status', sa.Enum('pending', 'processing', 'done', 'error',
                                    name='reportstatus'), nullable=False),
        sa.Column('task_id', sa.String(255), nullable=True),
        sa.Column('result_storage_key', sa.String(500), nullable=True),
        sa.Column('generation_params', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('llm_model', sa.String(100), nullable=True),
        sa.Column('template_version', sa.Integer(), nullable=True),
        sa.Column('processing_seconds', sa.Float(), nullable=True),
        sa.Column('prompt_tokens', sa.Integer(), nullable=True),
        sa.Column('completion_tokens', sa.Integer(), nullable=True),
        sa.Column('validation_errors', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id']),
        sa.ForeignKeyConstraint(['template_id'], ['report_templates.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_reports_owner_id', 'reports', ['owner_id'])
    op.create_index('ix_reports_status', 'reports', ['status'])

    # report_source_files
    op.create_table(
        'report_source_files',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('report_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('source_file_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.ForeignKeyConstraint(['report_id'], ['reports.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_file_id'], ['source_files.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # audit_logs
    op.create_table(
        'audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('resource_type', sa.String(50), nullable=True),
        sa.Column('resource_id', sa.String(50), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(500), nullable=True),
        sa.Column('extra', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'])
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'])


def downgrade() -> None:
    op.drop_table('audit_logs')
    op.drop_table('report_source_files')
    op.drop_table('reports')
    op.drop_table('source_files')
    op.drop_table('report_templates')
    op.drop_table('users')
    op.execute("DROP TYPE IF EXISTS userrole")
    op.execute("DROP TYPE IF EXISTS reportstatus")
    op.execute("DROP TYPE IF EXISTS sourcefilestatus")
