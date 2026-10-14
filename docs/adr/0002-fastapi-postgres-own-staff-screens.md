# FastAPI and Postgres, with staff screens we build ourselves

The backend is Python with FastAPI, SQLAlchemy 2 and Alembic on Postgres; the frontend is a React and TypeScript single-page app using an API client generated from the OpenAPI spec. We chose not to use Django even though its built-in admin would have given storytellers back-office screens for free, because we want the staff tools (approvals, downtime assignment and responses) designed as part of the product rather than generated from the data model. The cost is that sign-in, sessions and permissions are ours to write, so permissions go through one module that every route calls rather than being checked ad hoc.

## Considered Options

- **Django + Django Ninja.** Admin, auth and permissions included; rejected for the reason above.
- **Go.** A single deployable binary; rejected because the rules code is mostly lookups and arithmetic and reads better in Python, and performance is irrelevant at this scale.
