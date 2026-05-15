# Migrations Skeleton

This directory contains the database migration skeleton for phased PostgreSQL adoption.

Phase 1 intentionally introduced a placeholder foundation revision first.
Concrete schema evolution is added in follow-up revisions so previously applied
revision ids remain immutable across environments.

## Layout

- `env.py`: Alembic environment entrypoint
- `script.py.mako`: revision template
- `versions/`: migration revision files

Current sequence:

- `20260513_0001`: placeholder foundation revision
- `20260513_0002`: auth schema foundation tables

## Notes

- Runtime remains on legacy storage by default in Phase 1.
- `AETHOS_DATABASE_ENABLED` and `AETHOS_DATABASE_URL` gate future cutovers.
