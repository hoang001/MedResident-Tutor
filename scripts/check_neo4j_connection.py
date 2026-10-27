"""Read-only Bolt connection check. Run: python scripts/check_neo4j_connection.py

Dependencies: python -m pip install neo4j python-dotenv
Reads the repository .env regardless of the current working directory.
"""

from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def check_neo4j_connection(env_file=ENV_FILE):
    """Return True on authenticated query success; never print credentials."""
    try:
        from dotenv import dotenv_values
        from neo4j import GraphDatabase, Query, READ_ACCESS
        from neo4j.exceptions import AuthError, Neo4jError, ServiceUnavailable, SessionExpired
    except ImportError:
        print("Missing dependencies. Run: python -m pip install neo4j python-dotenv")
        return False
    if not Path(env_file).is_file():
        print("Configuration error: .env file not found.")
        return False
    # Literal passwords containing ${...} must not undergo variable interpolation.
    config = dotenv_values(env_file, encoding="utf-8-sig", interpolate=False)
    keys = ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "NEO4J_DATABASE")
    missing = [key for key in keys if not config.get(key)]
    if missing:
        print("Missing configuration: " + ", ".join(missing))
        return False
    try:
        with GraphDatabase.driver(
            config["NEO4J_URI"], auth=(config["NEO4J_USERNAME"], config["NEO4J_PASSWORD"]),
            connection_timeout=5, connection_acquisition_timeout=10,
            max_transaction_retry_time=0,
        ) as driver:
            driver.verify_connectivity()
            with driver.session(database=config["NEO4J_DATABASE"], default_access_mode=READ_ACCESS) as session:
                record = session.run(Query("RETURN 1 AS connection_ok", timeout=10)).single(strict=True)
                if record["connection_ok"] != 1:
                    print("FAIL: unexpected query result.")
                    return False
        print("PASS: Bolt authentication and RETURN 1 succeeded for the configured database.")
        return True
    except AuthError:
        print("FAIL: authentication rejected. Check username/password for the selected instance.")
    except (ServiceUnavailable, SessionExpired):
        print("FAIL: instance unavailable. Check instance status and connection URI/port.")
    except Neo4jError as exc:
        print("FAIL: Neo4j rejected the query. Error code: " + str(exc.code))
    except Exception as exc:
        # Exception messages may contain connection details; print type only.
        print("FAIL: " + type(exc).__name__ + ". Check configuration and driver compatibility.")
    return False


if __name__ == "__main__":
    raise SystemExit(0 if check_neo4j_connection() else 1)
