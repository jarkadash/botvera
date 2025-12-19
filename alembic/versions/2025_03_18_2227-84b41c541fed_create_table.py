"""Create Table

Revision ID: 84b41c541fed
Revises: 
Create Date: 2025-03-18 22:27:08.577093

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '84b41c541fed'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Создаем таблицу roles ПЕРВОЙ
    op.create_table('roles',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('role_name', sa.String(length=100), nullable=False),
                    sa.PrimaryKeyConstraint('id')
                    )

    # Создаем таблицу users
    op.create_table('users',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('user_id', sa.BigInteger(), nullable=False),
                    sa.Column('username', sa.String(length=100), nullable=False),
                    sa.Column('role_id', sa.Integer(), nullable=True),
                    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
                    sa.PrimaryKeyConstraint('id'),
                    sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ),
                    sa.UniqueConstraint('user_id')
                    )

    # Создаем таблицу services
    op.create_table('services',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('service_name', sa.String(length=100), nullable=False),
                    sa.Column('allowed_roles', sa.String(), nullable=False),
                    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
                    sa.PrimaryKeyConstraint('id')
                    )

    # Создаем таблицу orders
    op.create_table('orders',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('client_id', sa.BigInteger(), nullable=False),
                    sa.Column('client_name', sa.String(), nullable=False),
                    sa.Column('support_id', sa.BigInteger(), nullable=True),
                    sa.Column('support_name', sa.String(length=100), nullable=True),
                    sa.Column('service_id', sa.BigInteger(), nullable=False),
                    sa.Column('service_name', sa.String(), nullable=False),
                    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
                    sa.Column('accept_at', sa.DateTime(), nullable=True),
                    sa.Column('completed_at', sa.DateTime(), nullable=True),
                    sa.Column('status', sa.String(length=100), nullable=False),
                    sa.Column('description', sa.String(length=100), nullable=True),
                    sa.ForeignKeyConstraint(['client_id'], ['users.user_id'], ),
                    sa.ForeignKeyConstraint(['support_id'], ['users.user_id'], ),
                    sa.PrimaryKeyConstraint('id')
                    )

    # Создаем таблицу medias
    op.create_table('medias',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('url', sa.String(), nullable=False),
                    sa.Column('description', sa.String(length=100), nullable=True),
                    sa.Column('name_cheat', sa.String(length=100), nullable=False),
                    sa.Column('user_id', sa.BigInteger(), nullable=True),
                    sa.Column('username', sa.String(length=100), nullable=True),
                    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
                    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
                    sa.PrimaryKeyConstraint('id')
                    )

    # Создаем таблицу history_messages
    op.create_table('history_messages',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('support_message_id', sa.BigInteger(), nullable=False),
                    sa.Column('client_message_id', sa.BigInteger(), nullable=False),
                    sa.Column('chat_id', sa.BigInteger(), nullable=False),
                    sa.Column('order_id', sa.BigInteger(), nullable=True),
                    sa.PrimaryKeyConstraint('id')
                    )

    # Создаем таблицу banned_users
    op.create_table('banned_users',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('user_id', sa.BigInteger(), nullable=False),
                    sa.Column('username', sa.String(length=100), nullable=False),
                    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
                    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
                    sa.PrimaryKeyConstraint('id')
                    )


def downgrade() -> None:
    # Удаляем в обратном порядке
    op.drop_table('banned_users')
    op.drop_table('history_messages')
    op.drop_table('medias')
    op.drop_table('orders')
    op.drop_table('services')
    op.drop_table('users')
    op.drop_table('roles')