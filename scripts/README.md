# Scripts

Run commands from the repository root. `walkthrough.sh` exercises the local
fictional demo through HTTP using Bash, curl, jq and Python 3.11 or newer.

## Prepare and run the walkthrough

Follow the [project setup instructions](../README.md) to configure `.env` and
start the application with PostgreSQL. Initialize the fictional accounts in a
fresh, empty database, then run the walkthrough:

```sh
make app-up
make seed-demo
bash scripts/walkthrough.sh
```

The initializer asks for an explicit password of 12–128 characters. Enter that
same password at the walkthrough's hidden prompt. The walkthrough signs in as
`owner@example.test` and `member@example.test`; it also uses the seeded trainer.
The initializer refuses a populated database. The walkthrough can run repeatedly
against the initialized demo.

Use a different local API port by setting the base URL:

```sh
APP_BASE_URL=http://127.0.0.1:8080 bash scripts/walkthrough.sh
```

Run this against a demonstration database. The script creates catalog records and
retains reservation and cancellation history through the application's normal API.

## Behavior and exit status

The script checks readiness, logs in, reads identity/catalogs, creates a room and
class, reserves a seat and checks the expected duplicate conflict. It then checks
own history, cancellation replay, rebooking, owner class cancellation and logout.
An expected HTTP 409 is a successful assertion in this workflow. A network failure,
unexpected HTTP status or failed JSON/state assertion exits with a nonzero status.

Request logging prints method, path and status. Passwords and bearer tokens are
stored temporarily in a private directory rather than supplied as command-line
arguments. Curl reads bearer values through header files. Exit cleanup attempts
to cancel the walkthrough's class and revoke its login sessions, then removes the
temporary credential files. Persisted catalog and history records remain.

## Validate the script

```sh
bash -n scripts/walkthrough.sh
shellcheck scripts/walkthrough.sh
```

CI performs these checks alongside the Python checks and image build. Shared local
commands such as migrations, owner bootstrap and service startup live in the root
Makefile. Add scripts here when an implemented operational workflow needs one.
